"""索引期 LLM 提示词：实体/关系抽取、归一判定。"""
from __future__ import annotations

from .catalog import edge_types_prompt, entity_types_prompt

EXTRACT_SYSTEM = (
    "你是法规知识图谱抽取器。从给定的法规条文块中抽取【实体】与【关系】，"
    "只抽取该块明确表述的内容，不要臆造。所有名称使用规范全称。"
    "严格输出 JSON 对象。"
)


def extract_user(text: str, title: str, section: str) -> str:
    return (
        f"实体类型（只能从中选择 type）：\n{entity_types_prompt()}\n\n"
        f"关系类型（只能从中选择 type）：\n{edge_types_prompt()}\n\n"
        f"文档：《{title}》　章节：{section}\n"
        f"条文块：\n{text}\n\n"
        "请输出如下 JSON：\n"
        "{\n"
        '  "entities": [{"name": "规范全称", "type": "上表之一", "aliases": ["别名或简称", ...]}],\n'
        '  "relations": [{"src": "源实体规范全称", "type": "上表之一", "dst": "目标实体规范全称"}]\n'
        "}\n"
        "要求：relations 里出现的 src/dst 必须同时作为 entities 出现；没有则两者都留空数组。"
    )


NORMALIZE_SYSTEM = (
    "你是实体归一判定器。判断【新实体】是否与【候选已有实体】中的某一个指代同一概念"
    "（同义、简称/全称、不同写法都算同一个）。严格输出 JSON 对象。"
)


def normalize_user(name: str, type_: str, candidates: list[dict]) -> str:
    lines = [f"- id={c['entity_id']}　name={c['name']}　aliases={c.get('aliases', [])}" for c in candidates]
    cand = "\n".join(lines) if lines else "（无候选）"
    return (
        f"新实体：name={name}　type={type_}\n\n"
        f"候选已有实体（同类型）：\n{cand}\n\n"
        '若匹配某一个，输出 {"match_id": "该 entity_id"}；'
        '若都不是同一概念，输出 {"match_id": null}。'
    )


NORMALIZE_BATCH_SYSTEM = (
    "你是实体归一判定器。给定一批【同类型的新实体】和【候选已有实体】，"
    "把新实体按「是否同一概念」分组（同义、简称/全称、不同写法算同一个）；"
    "每组若与某个候选实体指代同一概念，给出该候选的 id，否则 match_id 为 null。"
    "严格输出 JSON 对象。"
)


def normalize_batch_user(names: list[str], type_: str, candidates: list[dict]) -> str:
    new_lines = "\n".join(f"- {n}" for n in names)
    cand_lines = "\n".join(
        f"- id={c['entity_id']}　name={c['name']}　aliases={c.get('aliases', [])}" for c in candidates
    ) or "（无候选）"
    return (
        f"新实体（type={type_}）：\n{new_lines}\n\n"
        f"候选已有实体（同类型）：\n{cand_lines}\n\n"
        "把上面的新实体分组：同一概念的放同一组；每个新实体必须且只能出现在一个组里，"
        "names 用新实体原文。每组若与某个候选是同一概念，给出其 match_id，否则 match_id 为 null。\n"
        '输出：{"groups": [{"names": ["新实体原文", ...], "match_id": "候选 id 或 null"}]}'
    )

