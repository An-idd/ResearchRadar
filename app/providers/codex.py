"""Isolated Codex CLI adapter; research content is sent through stdin only."""

import asyncio
import json
import os
import shutil
import subprocess
import tempfile
from pathlib import Path
from typing import Any

from pydantic import BaseModel

from app.domain import Usage
from app.providers.base import Generation, Message


class ProviderError(RuntimeError):
    """A sanitized provider error suitable for persisted job state."""


class CodexLLMProvider:
    name = "codex"

    def __init__(self, command: str = "codex", model: str = "", timeout: float = 180) -> None:
        self.command = command
        self.model = model or "cli-default"
        self.timeout = timeout

    def _run(self, messages: list[Message], schema: dict[str, Any]) -> tuple[str, Usage]:
        executable = shutil.which(self.command)
        if executable is None:
            raise ProviderError("codex executable not found; install CLI and run codex login")
        with tempfile.TemporaryDirectory(prefix="researchradar-codex-") as folder:
            root = Path(folder)
            schema_path, output_path = root / "schema.json", root / "output.json"
            schema_path.write_text(json.dumps(schema), encoding="utf-8")
            args = [
                executable,
                "exec",
                "--ignore-user-config",
                "--skip-git-repo-check",
                "--ephemeral",
                "--sandbox",
                "read-only",
                "--color",
                "never",
                "--json",
                "--output-schema",
                str(schema_path),
                "--output-last-message",
                str(output_path),
                "--cd",
                folder,
                "-c",
                'web_search="disabled"',
                "-c",
                "features.skip_host_skill_discovery=true",
                "-c",
                'shell_environment_policy.inherit="none"',
            ]
            for feature in (
                "shell_tool",
                "unified_exec",
                "apps",
                "plugins",
                "multi_agent",
                "remote_plugin",
                "skill_search",
            ):
                args.extend(["--disable", feature])
            if self.model != "cli-default":
                args.extend(["--model", self.model])
            args.append("-")
            # Keep login and OS configuration; don't pass app/Neon credentials to the child.
            env = {
                k: v
                for k, v in os.environ.items()
                if not any(
                    s in k.upper()
                    for s in (
                        "DATABASE",
                        "NEON_",
                        "RADAR_",
                        "ADMIN_TOKEN",
                        "LLM_API_KEY",
                        "SEMANTIC_SCHOLAR",
                    )
                )
            }
            prompt = "\n\n".join(f"[{m.role}]\n{m.content}" for m in messages)
            try:
                result = subprocess.run(
                    args,
                    input=prompt,
                    encoding="utf-8",
                    errors="replace",
                    capture_output=True,
                    cwd=folder,
                    env=env,
                    timeout=self.timeout,
                    creationflags=subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0,
                )
            except subprocess.TimeoutExpired as exc:
                raise TimeoutError("codex request timed out") from exc
            if result.returncode:
                # Do not expose stdout/stderr: they may contain research text or credentials.
                if "429" in result.stderr or "rate limit" in result.stderr.lower():
                    raise TimeoutError("codex rate limited")
                raise ProviderError(f"codex exited with code {result.returncode}")
            if not output_path.exists():
                raise ProviderError("codex returned no structured output")
            usage = Usage()
            for line in result.stdout.splitlines():
                try:
                    item = json.loads(line)
                except ValueError:
                    continue
                if item.get("type") == "turn.completed":
                    data = item.get("usage", {})
                    usage = Usage(
                        input_tokens=data.get("input_tokens"),
                        output_tokens=data.get("output_tokens"),
                    )
            return output_path.read_text(encoding="utf-8"), usage

    async def generate_structured[T: BaseModel](
        self, messages: list[Message], schema: type[T]
    ) -> Generation[T]:
        for attempt in range(3):
            try:
                data, usage = await asyncio.to_thread(
                    self._run, messages, schema.model_json_schema()
                )
                return Generation(
                    output=schema.model_validate_json(data),
                    provider=self.name,
                    model=self.model,
                    usage=usage,
                )
            except TimeoutError:
                if attempt == 2:
                    raise
                import random

                await asyncio.sleep(2**attempt + random.random())
        raise AssertionError("unreachable")
