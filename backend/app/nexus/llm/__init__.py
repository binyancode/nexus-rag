"""LLM / 向量客户端。

- embedder：Azure OpenAI 向量模型（块/实体名向量化，索引与查询须同一模型）
- chat_client：Azure OpenAI Chat（实体抽取、归一判定、关系判定）
- 均由「凭据名」按运行期解析（不写死在 config）。
"""
from .embedder import embedder
from .chat import chat_client
from .resolve import make_embedder, make_chat

__all__ = ["embedder", "chat_client", "make_embedder", "make_chat"]
