"""向量化客户端：Azure OpenAI Embeddings。

由 azure_openai_embedding 凭据的 to_config() 构造：
    {endpoint, key, deployment, api_version?, dimensions?}
"""
from __future__ import annotations

import threading

from utils.logger import get_logger

_logger = get_logger("nexus.embedder")

_DEFAULT_API_VERSION = "2024-02-01"
# 常见模型默认维度（未显式指定 dimensions 时的兜底）
_MODEL_DIMS = {
    "text-embedding-3-large": 3072,
    "text-embedding-3-small": 1536,
    "text-embedding-ada-002": 1536,
}


class embedder:
    def __init__(self, config: dict):
        conf = config or {}
        self._endpoint = conf["endpoint"]
        self._key = conf["key"]
        self._deployment = conf["deployment"]
        self._api_version = conf.get("api_version") or _DEFAULT_API_VERSION
        self._dimensions = int(conf["dimensions"]) if conf.get("dimensions") else None
        self._client = None
        # token 按线程本地累计（与 chat 一致，并行不串号）
        self._local = threading.local()

    def reset_usage(self) -> None:
        self._local.embedding = 0

    def pop_usage(self) -> dict:
        n = getattr(self._local, "embedding", 0)
        self._local.embedding = 0
        return {"embedding": n} if n else {}

    @property
    def dimensions(self) -> int:
        """向量维度（建索引用）。未显式配置时按模型名兜底，最后退回 1536。"""
        if self._dimensions:
            return self._dimensions
        for name, dim in _MODEL_DIMS.items():
            if name in (self._deployment or ""):
                return dim
        return 1536

    def _ensure_client(self):
        if self._client is None:
            from openai import AzureOpenAI
            self._client = AzureOpenAI(
                azure_endpoint=self._endpoint,
                api_key=self._key,
                api_version=self._api_version,
            )
        return self._client

    def embed(self, texts: list[str]) -> list[list[float]]:
        if not texts:
            return []
        client = self._ensure_client()
        kwargs = {"model": self._deployment, "input": texts}
        if self._dimensions:
            kwargs["dimensions"] = self._dimensions
        resp = client.embeddings.create(**kwargs)
        usage = getattr(resp, "usage", None)
        if usage:
            self._local.embedding = getattr(self._local, "embedding", 0) + (getattr(usage, "total_tokens", 0) or 0)
        return [item.embedding for item in resp.data]

    def embed_one(self, text: str) -> list[float]:
        out = self.embed([text])
        return out[0] if out else []
