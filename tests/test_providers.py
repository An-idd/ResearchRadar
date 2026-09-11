import json
import subprocess
from pathlib import Path

import httpx
import pytest
from pydantic import ValidationError

from app.domain import Screening
from app.providers.base import Message
from app.providers.codex import CodexLLMProvider, ProviderError
from app.providers.embedding import validate_vectors
from app.providers.openai import OpenAIProvider


async def test_codex_structured_output_and_isolation(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr("shutil.which", lambda c: "codex.exe")
    monkeypatch.setenv("DATABASE_URL", "secret")

    def fake_run(args: list[str], **kwargs: object) -> subprocess.CompletedProcess[str]:
        assert "--ignore-user-config" in args and "read-only" in args
        assert "shell_tool" in args and "apps" in args and "multi_agent" in args
        assert "UNTRUSTED" in str(kwargs["input"])
        assert "DATABASE_URL" not in kwargs["env"]
        Path(args[args.index("--output-last-message") + 1]).write_text(
            '{"selected":true,"reason":"method"}', encoding="utf-8"
        )
        return subprocess.CompletedProcess(
            args,
            0,
            json.dumps(
                {"type": "turn.completed", "usage": {"input_tokens": 12, "output_tokens": 5}}
            ),
            "",
        )

    monkeypatch.setattr("subprocess.run", fake_run)
    result = await CodexLLMProvider().generate_structured(
        [Message(role="user", content="UNTRUSTED paper")], Screening
    )
    assert result.output.selected and result.usage.input_tokens == 12


async def test_codex_failure_sanitized(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr("shutil.which", lambda c: "codex.exe")
    monkeypatch.setattr(
        "subprocess.run",
        lambda *a, **k: subprocess.CompletedProcess(a, 1, "secret", "credential secret"),
    )
    with pytest.raises(ProviderError, match="exited with code 1") as exc:
        await CodexLLMProvider().generate_structured([], Screening)
    assert "secret" not in str(exc.value)


async def test_openai_schema_and_usage() -> None:
    def handler(req: httpx.Request) -> httpx.Response:
        data = json.loads(req.content)
        assert data["response_format"]["json_schema"]["strict"]
        return httpx.Response(
            200,
            json={
                "choices": [{"message": {"content": '{"selected": true, "reason": "test"}'}}],
                "usage": {"prompt_tokens": 10, "completion_tokens": 3},
            },
        )

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        provider = OpenAIProvider(client, "https://example.org/v1", "test", "fixture")
        result = await provider.generate_structured([], Screening)
        assert result.output.selected and result.usage.cost_usd is None


def test_embedding_and_output_validation() -> None:
    with pytest.raises(ValueError):
        validate_vectors([[float("nan")] * 384], 1)
    with pytest.raises(ValueError):
        validate_vectors([[0.0] * 384], 1)
    with pytest.raises(ValidationError):
        Screening.model_validate({"selected": True})
