"""模型接入：把任意 OpenAI 兼容的 chat completions 端点包成 `complete(prompt) -> str`。

AGH 本身不带网络代码；这个模块是**适配器**，只做三件事：
拼请求、抽 `choices[0].message.content`、失败重试。密钥只从环境变量读，不落盘、不写日志。

支持任何 OpenAI 兼容端点（DeepSeek、OpenAI、OpenRouter、vLLM、Ollama 的 /v1 等）。
传输函数可注入，测试不需要网络。
"""

from __future__ import annotations

import json
import os
import time
import urllib.error
import urllib.request
from collections.abc import Callable, Sequence
from dataclasses import dataclass, field
from typing import Any

from .netutil import open_http

Transport = Callable[[str, dict[str, str], dict[str, Any]], dict[str, Any]]


def _urllib_transport(url: str, headers: dict[str, str], payload: dict[str, Any]) -> dict[str, Any]:
    with open_http(
        url,
        data=json.dumps(payload).encode(),
        headers=headers,
        method="POST",
        timeout=120,
    ) as resp:
        return json.loads(resp.read().decode())


@dataclass
class ChatClient:
    """OpenAI 兼容 chat completions 客户端。实例本身是 `complete(prompt)`。"""

    base_url: str
    model: str
    api_key_env: str = "OPENAI_API_KEY"
    temperature: float = 0.2
    max_tokens: int = 2048
    json_mode: bool = True
    timeout: int = 120
    retries: int = 2
    transport: Transport = field(default=_urllib_transport, repr=False)
    system: str = "You are a precise JSON generator. Reply with JSON only."
    user_agent: str = (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/120.0 Safari/537.36"
    )
    last_usage: dict[str, Any] | None = field(default=None, repr=False)

    @property
    def api_key(self) -> str:
        key = os.environ.get(self.api_key_env, "")
        if not key:
            raise RuntimeError(f"环境变量 {self.api_key_env} 未设置")
        return key

    def chat(self, messages: Sequence[dict[str, str]]) -> str:
        url = self.base_url.rstrip("/") + "/chat/completions"
        payload: dict[str, Any] = {
            "model": self.model,
            "messages": list(messages),
            "temperature": self.temperature,
            "max_tokens": self.max_tokens,
        }
        if self.json_mode:
            payload["response_format"] = {"type": "json_object"}
        headers = {
            "Content-Type": "application/json",
            "Authorization": f"Bearer {self.api_key}",
            "User-Agent": self.user_agent,
        }
        last_error: Exception | None = None
        for attempt in range(self.retries + 1):
            attempt_payload = dict(payload)
            # 推理模型的 reasoning token 也算 completion；截断时放大预算重试
            attempt_payload["max_tokens"] = min(8192, self.max_tokens * (2**attempt))
            try:
                data = self.transport(url, headers, attempt_payload)
                self.last_usage = data.get("usage")
                message = data["choices"][0]["message"]
                content = message.get("content")
                if data["choices"][0].get("finish_reason") == "length":
                    raise ValueError("输出被截断（finish_reason=length）")
                if content is None:
                    raise ValueError(
                        f"模型没有返回 content（finish_reason={data['choices'][0].get('finish_reason')}）"
                    )
                return str(content)
            except (urllib.error.URLError, TimeoutError, KeyError, IndexError, ValueError) as exc:
                last_error = exc
                if attempt < self.retries:
                    time.sleep(1.5 * (attempt + 1))
        raise RuntimeError(f"模型调用失败：{last_error}")

    def __call__(self, prompt: str) -> str:
        return self.chat(
            [
                {"role": "system", "content": self.system},
                {"role": "user", "content": prompt},
            ]
        )


PRESETS: dict[str, dict[str, Any]] = {
    "deepseek": {
        "base_url": "https://api.deepseek.com",
        "model": "deepseek-chat",
        "api_key_env": "DEEPSEEK_API_KEY",
    },
    "openai": {
        "base_url": "https://api.openai.com/v1",
        "model": "gpt-4o-mini",
        "api_key_env": "OPENAI_API_KEY",
    },
    "openrouter": {
        "base_url": "https://openrouter.ai/api/v1",
        "model": "deepseek/deepseek-chat",
        "api_key_env": "OPENROUTER_API_KEY",
    },
    "command-code": {
        "base_url": "https://api.commandcode.ai/provider/v1",
        "model": "deepseek/deepseek-v4.1-flash",
        "api_key_env": "COMMAND_CODE_API_KEY",
    },
    "zhipu": {
        "base_url": "https://open.bigmodel.cn/api/paas/v4",
        "model": "glm-4-flash",
        "api_key_env": "ZHIPU_API_KEY",
    },
    "ollama": {
        "base_url": "http://127.0.0.1:11434/v1",
        "model": "qwen2.5:7b",
        "api_key_env": "OLLAMA_API_KEY",
    },
}


def make_client(
    provider: str = "deepseek",
    *,
    model: str | None = None,
    base_url: str | None = None,
    api_key_env: str | None = None,
    json_mode: bool = True,
    transport: Transport | None = None,
) -> ChatClient:
    preset = PRESETS.get(provider, {})
    return ChatClient(
        base_url=base_url or preset.get("base_url", "https://api.openai.com/v1"),
        model=model or preset.get("model", "gpt-4o-mini"),
        api_key_env=api_key_env or preset.get("api_key_env", "OPENAI_API_KEY"),
        json_mode=json_mode,
        transport=transport or _urllib_transport,
    )


__all__ = ["PRESETS", "ChatClient", "make_client"]
