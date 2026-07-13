"""建立索引阶段（§2）：把索引流程组织成 Workflow DAG 执行。

- workflow/：runner / ops / expanders / recorder（DAG 编排与执行）
- attach_entity / entity_extractor / chunker：可复用的索引逻辑
"""
from .workflow import run_index, cancel_run, build_index_workflow, build_seed
from .attach_entity import attach_entity
from .entity_extract import entity_extractor
from .chunker import chunk_document, make_doc_id, content_hash

__all__ = [
    "run_index", "cancel_run", "build_index_workflow", "build_seed",
    "attach_entity", "entity_extractor",
    "chunk_document", "make_doc_id", "content_hash",
]
