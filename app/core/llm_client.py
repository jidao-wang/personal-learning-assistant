import json
from typing import Any

from app.core.errors import ConfigurationError


class LLMClient:
    def __init__(self, settings) -> None:
        self.api_key = settings.api_key
        self.base_url = settings.base_url
        self.model = settings.chat_model
        self.timeout = settings.timeout_seconds
        self.temperature = settings.temperature
        self.client = None

    def _get_client(self):
        if not self.api_key.strip():
            raise ConfigurationError("请先在 .env 中配置 DASHSCOPE_API_KEY")
        if self.client is None:
            try:
                from openai import OpenAI
            except ImportError as exc:
                raise ConfigurationError("未安装 openai，无法调用模型") from exc
            self.client = OpenAI(
                api_key=self.api_key,
                base_url=self.base_url,
                timeout=self.timeout,
            )
        return self.client

    def chat(self, messages: list[dict[str, str]], temperature: float | None = None) -> str:
        response = self._get_client().chat.completions.create(
            model=self.model,
            messages=messages,
            temperature=self.temperature if temperature is None else temperature,
        )
        content = response.choices[0].message.content
        return (content or "").strip()

    def chat_json(self, messages: list[dict[str, str]]) -> dict[str, Any]:
        content = self.chat(messages, temperature=0).strip()
        if content.startswith("```"):
            content = content.removeprefix("```json").removeprefix("```")
            content = content.removesuffix("```").strip()
        return json.loads(content)
