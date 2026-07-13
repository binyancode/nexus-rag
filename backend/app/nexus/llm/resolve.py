"""按凭据名解析 LLM / 向量客户端（运行期，不写死在 config）。"""
from __future__ import annotations

from core.services import services
from services.credential import azure_keyvault_credential_provider

from .chat import chat_client
from .embedder import embedder


def _load_config(credential_name: str) -> dict:
    provider = services[azure_keyvault_credential_provider]
    cred = provider.load(credential_name)
    if cred is None:
        raise ValueError(f"凭据不存在或不可用: {credential_name!r}")
    return cred.to_config()


def make_embedder(credential_name: str) -> embedder:
    return embedder(_load_config(credential_name))


def make_chat(credential_name: str) -> chat_client:
    return chat_client(_load_config(credential_name))
