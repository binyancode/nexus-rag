"""Chat 客户端：Azure OpenAI Chat Completions。

由 azure_openai 凭据的 to_config() 构造：{endpoint, key, deployment?, api_version?}
用于实体抽取、归一判定（是否同一实体）、关系判定。
"""
from __future__ import annotations

import json
import threading

from utils.logger import get_logger

_logger = get_logger("nexus.chat")

_DEFAULT_API_VERSION = "2024-06-01"
_DEFAULT_DEPLOYMENT = "gpt-4o"


class chat_client:
    def __init__(self, config: dict):
        conf = config or {}
        self._endpoint = conf["endpoint"]
        self._key = conf["key"]
        self._deployment = conf.get("deployment") or _DEFAULT_DEPLOYMENT
        self._api_version = conf.get("api_version") or _DEFAULT_API_VERSION
        self._client = None
        # token 用量按线程本地累计：一个实例被多线程并行调用时互不串号；
        # 每个算子调 reset_usage() 归零、干完调 pop_usage() 取本算子的用量。
        self._local = threading.local()

    def _acc(self) -> dict:
        acc = getattr(self._local, "acc", None)
        if acc is None:
            acc = {"input": 0, "output": 0, "cached": 0}
            self._local.acc = acc
        return acc

    def reset_usage(self) -> None:
        self._local.acc = {"input": 0, "output": 0, "cached": 0}

    def pop_usage(self) -> dict:
        acc = self._acc()
        self._local.acc = {"input": 0, "output": 0, "cached": 0}
        return {k: v for k, v in acc.items() if v}

    def _add_usage(self, resp) -> None:
        u = getattr(resp, "usage", None)
        if not u:
            return
        acc = self._acc()
        acc["input"] += getattr(u, "prompt_tokens", 0) or 0
        acc["output"] += getattr(u, "completion_tokens", 0) or 0
        details = getattr(u, "prompt_tokens_details", None)
        if details is not None:
            acc["cached"] += getattr(details, "cached_tokens", 0) or 0

    def _ensure_client(self):
        if self._client is None:
            from openai import AzureOpenAI
            self._client = AzureOpenAI(
                azure_endpoint=self._endpoint,
                api_key=self._key,
                api_version=self._api_version,
            )
        return self._client

    def complete(self, system: str, user: str, temperature: float = 0.0, max_tokens: int | None = None) -> str:
        client = self._ensure_client()
        messages = []
        if system:
            messages.append({"role": "system", "content": system})
        messages.append({"role": "user", "content": user})
        kwargs = {"model": self._deployment, "messages": messages, "temperature": temperature}
        if max_tokens:
            kwargs["max_tokens"] = max_tokens
        resp = client.chat.completions.create(**kwargs)
        self._add_usage(resp)
        return (resp.choices[0].message.content or "").strip()

    def complete_json(self, system: str, user: str, temperature: float = 0.0) -> dict | list:
        """要求模型返回 JSON 对象；失败时返回 {}。"""
        client = self._ensure_client()
        messages = []
        if system:
            messages.append({"role": "system", "content": system})
        messages.append({"role": "user", "content": user})
        try:
            resp = client.chat.completions.create(
                model=self._deployment,
                messages=messages,
                temperature=temperature,
                response_format={"type": "json_object"},
            )
            self._add_usage(resp)
            raw = resp.choices[0].message.content or "{}"
            return json.loads(raw)
        except Exception as exc:
            _logger.warning(f"complete_json failed: {exc}")
            return {}
