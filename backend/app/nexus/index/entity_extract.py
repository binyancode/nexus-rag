"""实体/关系抽取：对单个块调用 LLM，返回结构化结果。"""
from __future__ import annotations

from ..llm.chat import chat_client
from ..models.block import Block
from .catalog import ENTITY_TYPES, EDGE_TYPES
from .prompts import EXTRACT_SYSTEM, extract_user


class extracted_entity:
    def __init__(self, name: str, type_: str, aliases: list[str]):
        self.name = name
        self.type = type_
        self.aliases = aliases


class extracted_relation:
    def __init__(self, src: str, type_: str, dst: str):
        self.src = src
        self.type = type_
        self.dst = dst


class entity_extractor:
    def __init__(self, chat: chat_client):
        self._chat = chat

    def extract(self, block: Block) -> tuple[list[extracted_entity], list[extracted_relation]]:
        data = self._chat.complete_json(
            EXTRACT_SYSTEM,
            extract_user(block.text, block.title or "", block.section or ""),
        )
        if not isinstance(data, dict):
            return [], []

        entities: list[extracted_entity] = []
        for e in data.get("entities", []) or []:
            name = (e.get("name") or "").strip()
            type_ = (e.get("type") or "").strip()
            if not name or type_ not in ENTITY_TYPES:
                continue
            aliases = [a.strip() for a in (e.get("aliases") or []) if a and a.strip()]
            entities.append(extracted_entity(name, type_, aliases))

        relations: list[extracted_relation] = []
        for r in data.get("relations", []) or []:
            src = (r.get("src") or "").strip()
            dst = (r.get("dst") or "").strip()
            type_ = (r.get("type") or "").strip()
            if not src or not dst or type_ not in EDGE_TYPES:
                continue
            relations.append(extracted_relation(src, type_, dst))

        return entities, relations
