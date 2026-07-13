"""Nexus 存储层。

- store_registry：Store / Collection 注册 + allowed_stores 解析（§1.6）
- document_store：文档路由 + 增量 hash（§1.5）
- entity_store：实体 + 别名（§1.2）
- edge_store：结构边 + 出处边（§1.3/§1.4）
"""
from .store_registry import store_registry
from .document_store import document_store
from .entity_store import entity_store
from .edge_store import edge_store
from .block_store import block_store

__all__ = ["store_registry", "document_store", "entity_store", "edge_store", "block_store"]
