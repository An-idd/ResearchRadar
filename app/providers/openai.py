import json

import httpx
from pydantic import BaseModel

from app.domain import Usage
from app.providers.base import Generation, Message
from app.providers.codex import ProviderError
from app.providers.http import request


class OpenAIProvider:
    name = "openai-compatible"

    def __init__(self, client: httpx.AsyncClient, base_url: str, api_key: str, model: str) -> None:
        self.client, self.base_url, self.api_key, self.model = client, base_url, api_key, model

    async def generate_structured[T: BaseModel](
        self, messages: list[Message], schema: type[T]
    ) -> Generation[T]:
        if not self.api_key or not self.model:
            raise ProviderError("LLM_API_KEY and LLM_MODEL are required")
        response = await request(
            self.client,
            "POST",
            self.base_url.rstrip("/") + "/chat/completions",
            headers={"Authorization": f"Bearer {self.api_key}"},
            json={
                "model": self.model,
                "messages": [m.model_dump() for m in messages],
                "response_format": {
                    "type": "json_schema",
                    "json_schema": {
                        "name": schema.__name__,
                        "strict": True,
                        "schema": schema.model_json_schema(),
                    },
                },
            },
        )
        body = response.json()
        message = body["choices"][0]["message"]
        if message.get("refusal"):
            raise ProviderError("model refused structured generation")
        output = schema.model_validate(json.loads(message["content"]))
        usage = body.get("usage", {})
        return Generation(
            output=output,
            provider=self.name,
            model=body.get("model", self.model),
            usage=Usage(
                input_tokens=usage.get("prompt_tokens"),
                output_tokens=usage.get("completion_tokens"),
            ),
        )
