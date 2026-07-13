"""Credential-backed Azure OpenAI adapters used by final indexing/querying code."""
from __future__ import annotations

import json
import threading
from typing import Any

from core.services import services
from services.credential import azure_keyvault_credential_provider

_CHAT_API_VERSION = "2024-06-01"
_CHAT_DEPLOYMENT = "gpt-4o"
_EMBEDDING_API_VERSION = "2024-02-01"
_MODEL_DIMS = {
    "text-embedding-3-large": 3072,
    "text-embedding-3-small": 1536,
    "text-embedding-ada-002": 1536,
}


class JsonCompletionError(ValueError):
    """A chat response was returned but was not valid JSON."""

    def __init__(self, message: str, raw_output: str | None = None):
        self.raw_output = raw_output
        super().__init__(message)


class ChatClient:
    """Thread-safe-by-call adapter with thread-local token accounting."""

    def __init__(self, config: dict):
        conf = config or {}
        self._endpoint = conf["endpoint"]
        self._key = conf["key"]
        self._deployment = conf.get("deployment") or _CHAT_DEPLOYMENT
        self._api_version = conf.get("api_version") or _CHAT_API_VERSION
        self._client = None
        self._client_lock = threading.Lock()
        self._local = threading.local()

    def _usage(self) -> dict[str, int]:
        value = getattr(self._local, "usage", None)
        if value is None:
            value = {"input": 0, "output": 0, "cached": 0}
            self._local.usage = value
        return value

    def reset_usage(self) -> None:
        self._local.usage = {"input": 0, "output": 0, "cached": 0}

    def pop_usage(self) -> dict[str, int]:
        usage = self._usage()
        self.reset_usage()
        return {key: value for key, value in usage.items() if value}

    def _add_usage(self, response: Any) -> None:
        response_usage = getattr(response, "usage", None)
        if response_usage is None:
            return
        usage = self._usage()
        usage["input"] += int(getattr(response_usage, "prompt_tokens", 0) or 0)
        usage["output"] += int(getattr(response_usage, "completion_tokens", 0) or 0)
        details = getattr(response_usage, "prompt_tokens_details", None)
        if details is not None:
            usage["cached"] += int(getattr(details, "cached_tokens", 0) or 0)

    def _ensure_client(self):
        if self._client is None:
            with self._client_lock:
                if self._client is None:
                    from openai import AzureOpenAI

                    self._client = AzureOpenAI(
                        azure_endpoint=self._endpoint,
                        api_key=self._key,
                        api_version=self._api_version,
                    )
        return self._client

    def complete(
        self,
        system: str,
        user: str,
        temperature: float = 0.0,
        max_tokens: int | None = None,
    ) -> str:
        messages = []
        if system:
            messages.append({"role": "system", "content": system})
        messages.append({"role": "user", "content": user})
        kwargs: dict[str, Any] = {
            "model": self._deployment,
            "messages": messages,
            "temperature": temperature,
        }
        if max_tokens is not None:
            kwargs["max_tokens"] = int(max_tokens)
        response = self._ensure_client().chat.completions.create(**kwargs)
        self._add_usage(response)
        return (response.choices[0].message.content or "").strip()

    def complete_json(
        self,
        system: str,
        user: str,
        temperature: float = 0.0,
    ) -> dict | list:
        """Return parsed JSON; API and parsing failures are never converted to an empty object."""
        messages = []
        if system:
            messages.append({"role": "system", "content": system})
        messages.append({"role": "user", "content": user})
        response = self._ensure_client().chat.completions.create(
            model=self._deployment,
            messages=messages,
            temperature=temperature,
            response_format={"type": "json_object"},
        )
        self._add_usage(response)
        raw = response.choices[0].message.content
        if raw is None or not raw.strip():
            raise JsonCompletionError("chat completion returned empty JSON content", raw)
        try:
            return json.loads(raw)
        except json.JSONDecodeError as exc:
            raise JsonCompletionError(f"chat completion returned invalid JSON: {exc}", raw) from exc


class EmbeddingClient:
    """Azure OpenAI embedding adapter with thread-local token accounting."""

    def __init__(self, config: dict):
        conf = config or {}
        self._endpoint = conf["endpoint"]
        self._key = conf["key"]
        self._deployment = conf["deployment"]
        self._api_version = conf.get("api_version") or _EMBEDDING_API_VERSION
        self._dimensions = int(conf["dimensions"]) if conf.get("dimensions") else None
        self._client = None
        self._client_lock = threading.Lock()
        self._local = threading.local()

    def reset_usage(self) -> None:
        self._local.embedding = 0

    def pop_usage(self) -> dict[str, int]:
        value = int(getattr(self._local, "embedding", 0) or 0)
        self._local.embedding = 0
        return {"embedding": value} if value else {}

    @property
    def dimensions(self) -> int:
        if self._dimensions:
            return self._dimensions
        deployment = self._deployment or ""
        return next((dim for name, dim in _MODEL_DIMS.items() if name in deployment), 1536)

    def _ensure_client(self):
        if self._client is None:
            with self._client_lock:
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
        kwargs: dict[str, Any] = {"model": self._deployment, "input": texts}
        if self._dimensions:
            kwargs["dimensions"] = self._dimensions
        response = self._ensure_client().embeddings.create(**kwargs)
        usage = getattr(response, "usage", None)
        if usage is not None:
            current = int(getattr(self._local, "embedding", 0) or 0)
            self._local.embedding = current + int(getattr(usage, "total_tokens", 0) or 0)
        vectors = [item.embedding for item in response.data]
        if len(vectors) != len(texts):
            raise RuntimeError(f"embedding service returned {len(vectors)} vectors for {len(texts)} inputs")
        return vectors

    def embed_one(self, text: str) -> list[float]:
        vectors = self.embed([text])
        if not vectors:
            raise RuntimeError("embedding service returned no vector")
        return vectors[0]


def _credential_config(credential_name: str) -> dict:
    credential = services[azure_keyvault_credential_provider].load(credential_name)
    if credential is None:
        raise ValueError(f"credential does not exist or is unavailable: {credential_name!r}")
    return credential.to_config()


def make_chat(credential_name: str) -> ChatClient:
    return ChatClient(_credential_config(credential_name))


def make_embedder(credential_name: str) -> EmbeddingClient:
    return EmbeddingClient(_credential_config(credential_name))
