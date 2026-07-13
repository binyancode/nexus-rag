"""attach_entity：幂等的实体入网算子（§1.5）。

三个来源（索引抽取 / 事前种子 / 事后手工）共用：
  1. 归一/去重：精确名/别名命中 → 复用；否则（auto）LLM 判定是否同一概念。
  2. 连块 evidence：把给定块 fullname 挂到该实体（带 store_id）。
  3. （连实体 edges 由 edge_builder 处理，此处只负责节点与出处。）

source: seed | manual | llm；manual 默认 locked（不被系统覆盖）。
"""
from __future__ import annotations

import math

from core.services import services

from ..llm.chat import chat_client
from ..llm.embedder import embedder as Embedder
from ..models.entity import Entity
from ..models.evidence import Evidence
from ..stores.edge_store import edge_store
from ..stores.entity_store import entity_store
from .prompts import (NORMALIZE_BATCH_SYSTEM, NORMALIZE_SYSTEM,
                      normalize_batch_user, normalize_user)

_MAX_CANDIDATES = 40      # 单条判定交给 LLM 的候选上限
_BATCH_CAND_CAP = 80      # 批量判定：一次给 LLM 的候选上限
_PER_NAME_TOPK = 12       # 批量判定：候选过多时，每个新名取相似 top-K 求并集


class attach_entity:
    def __init__(self, config: dict = None):
        pass

    @property
    def _entities(self) -> entity_store:
        return services[entity_store]

    @property
    def _edges(self) -> edge_store:
        return services[edge_store]

    def attach(self, name: str, type_: str, aliases: list[str] | None = None,
               source: str = "llm", evidence: list[str] | None = None,
               store_id: str | None = None, chat: chat_client | None = None,
               embedder: Embedder | None = None, auto: bool = True) -> str:
        name = (name or "").strip()
        if not name or not type_:
            raise ValueError("attach_entity 需要 name 与 type")
        aliases = [a.strip() for a in (aliases or []) if a and a.strip()]

        matched_id = self._resolve(name, type_, chat if auto else None, embedder)

        if matched_id:
            entity_id = matched_id
            # 复用已有：只补别名，不改核心字段（尊重 locked）
            new_aliases = aliases + ([name] if name else [])
            if new_aliases:
                self._entities.add_aliases(entity_id, new_aliases)
        else:
            entity_id = Entity.make_id(type_, name)
            self._entities.upsert(Entity(
                entity_id=entity_id, type=type_, name=name,
                aliases=aliases, source=source, locked=(source == "manual"),
            ))

        # 连块 evidence
        if evidence and store_id:
            for fullname in dict.fromkeys(evidence):
                self._edges.add_evidence(Evidence(
                    entity_id=entity_id, fullname=fullname, store_id=store_id, source=source,
                ))

        return entity_id

    # ---------------- 批量入网（索引期：一次 LLM 判一整类，减少往返）----------------
    def attach_batch(self, mentions: list[dict], chat: chat_client | None = None,
                     embedder: Embedder | None = None, auto: bool = True) -> dict[tuple[str, str], str]:
        """把一批实体提及入网，返回 {(type, name): entity_id}。
        - 精确名/别名命中 → 复用；未命中的按 type 分组，每类一次 LLM 批量归一（同时对批内新名做同概念分组）。
        - 只建实体节点与别名；出处 evidence、结构边由调用方按块写（它有 fullname）。
        """
        uniq: dict[tuple[str, str], set] = {}
        for m in mentions:
            name = m.get("name")
            type_ = m.get("type")
            if not name or not type_:
                continue
            uniq.setdefault((type_, name), set()).update(
                a.strip() for a in (m.get("aliases") or []) if a and a.strip())

        result: dict[tuple[str, str], str] = {}
        pending: dict[str, list[str]] = {}     # type -> [name]（未精确命中的）

        # 1) 精确命中（名/别名）→ 复用并补别名
        for (type_, name), aliases in uniq.items():
            exact = self._entities.find_by_name(name)
            if exact:
                same = [e for e in exact if e.type == type_]
                eid = (same or exact)[0].entity_id
                result[(type_, name)] = eid
                self._entities.add_aliases(eid, list(aliases) + [name])
            else:
                pending.setdefault(type_, []).append(name)

        # 2) 未命中的按类型批量归一（每类一次 LLM）
        for type_, names in pending.items():
            groups: list[dict] = []
            if auto and chat is not None:
                candidates = self._entities.list(type_=type_)
                if candidates:
                    cand = self._shrink_batch(names, candidates, embedder)
                    groups = self._normalize_groups(names, type_, cand, chat)
            self._apply_groups(type_, names, uniq, groups, result)

        return result

    def _apply_groups(self, type_: str, names: list[str], uniq: dict, groups: list[dict],
                      result: dict[tuple[str, str], str]) -> None:
        """按 LLM 分组结果落实体：命中候选→复用；否则组内首名为规范名、其余为别名，建一个新实体。"""
        remaining = set(names)

        def collect_aliases(nms: list[str]) -> set:
            al: set = set()
            for n in nms:
                al.update(uniq.get((type_, n), set()))
            return al

        for g in groups:
            gnames = [n for n in g.get("names", []) if n in remaining]
            if not gnames:
                continue
            remaining.difference_update(gnames)
            mid = g.get("match_id")
            extra = collect_aliases(gnames)
            if mid:
                eid = mid
                self._entities.add_aliases(eid, list(extra) + gnames)
            else:
                canonical = gnames[0]
                eid = Entity.make_id(type_, canonical)
                self._entities.upsert(Entity(
                    entity_id=eid, type=type_, name=canonical,
                    aliases=list(extra) + [n for n in gnames if n != canonical],
                    source="llm", locked=False,
                ))
            for n in gnames:
                result[(type_, n)] = eid

        # LLM 没归入任何组的名字 → 各自建新实体（兜底）
        for n in remaining:
            eid = Entity.make_id(type_, n)
            self._entities.upsert(Entity(
                entity_id=eid, type=type_, name=n,
                aliases=list(uniq.get((type_, n), set())), source="llm", locked=False,
            ))
            result[(type_, n)] = eid

    def _normalize_groups(self, names: list[str], type_: str, candidates: list,
                          chat: chat_client) -> list[dict]:
        """一次 LLM 调用：把 names 分组，每组给出 match_id（候选 id）或 null。match_id 会校验必须是候选。"""
        cand_dicts = [{"entity_id": c.entity_id, "name": c.name, "aliases": c.aliases} for c in candidates]
        valid = {c.entity_id for c in candidates}
        name_set = set(names)
        try:
            res = chat.complete_json(NORMALIZE_BATCH_SYSTEM, normalize_batch_user(names, type_, cand_dicts))
        except Exception:  # noqa: BLE001
            return []
        raw = res.get("groups") if isinstance(res, dict) else None
        out: list[dict] = []
        if isinstance(raw, list):
            for g in raw:
                if not isinstance(g, dict):
                    continue
                gnames = [n for n in (g.get("names") or []) if n in name_set]
                if not gnames:
                    continue
                mid = g.get("match_id")
                out.append({"names": gnames, "match_id": mid if mid in valid else None})
        return out

    def _shrink_batch(self, names: list[str], candidates: list, embedder: Embedder | None) -> list:
        """候选过多时：对每个新名取向量相似 top-K，求并集，作为交给 LLM 的候选集。"""
        if len(candidates) <= _BATCH_CAND_CAP or embedder is None or not names:
            return candidates[:_BATCH_CAND_CAP]
        try:
            vectors = embedder.embed(list(names) + [c.name for c in candidates])
        except Exception:  # noqa: BLE001
            return candidates[:_BATCH_CAND_CAP]
        name_vecs = vectors[:len(names)]
        cand_vecs = vectors[len(names):]
        chosen: dict[str, object] = {}
        for nv in name_vecs:
            scored = sorted(
                ((self._cosine(nv, cand_vecs[i]), c) for i, c in enumerate(candidates)),
                key=lambda t: t[0], reverse=True,
            )
            for _, c in scored[:_PER_NAME_TOPK]:
                chosen[c.entity_id] = c
            if len(chosen) >= _BATCH_CAND_CAP:
                break
        return list(chosen.values())[:_BATCH_CAND_CAP]

    # ---------------- 归一（单条，手工/种子用）----------------
    def _resolve(self, name: str, type_: str, chat: chat_client | None,
                 embedder: Embedder | None) -> str | None:
        # 1) 精确名/别名命中（优先同类型）
        exact = self._entities.find_by_name(name)
        if exact:
            same_type = [e for e in exact if e.type == type_]
            return (same_type or exact)[0].entity_id

        # 2) LLM 判定（仅 auto 模式）
        if chat is None:
            return None
        candidates = self._entities.list(type_=type_)
        if not candidates:
            return None
        candidates = self._shrink(name, candidates, embedder)
        cand_dicts = [{"entity_id": c.entity_id, "name": c.name, "aliases": c.aliases} for c in candidates]
        result = chat.complete_json(NORMALIZE_SYSTEM, normalize_user(name, type_, cand_dicts))
        match_id = result.get("match_id") if isinstance(result, dict) else None
        if match_id and any(c.entity_id == match_id for c in candidates):
            return match_id
        return None

    def _shrink(self, name: str, candidates: list, embedder: Embedder | None) -> list:
        """候选过多时用向量相似度取 top-N，缩小交给 LLM 的集合。"""
        if len(candidates) <= _MAX_CANDIDATES or embedder is None:
            return candidates[:_MAX_CANDIDATES]
        try:
            vectors = embedder.embed([name] + [c.name for c in candidates])
        except Exception:
            return candidates[:_MAX_CANDIDATES]
        base = vectors[0]
        scored = [(self._cosine(base, vectors[i + 1]), c) for i, c in enumerate(candidates)]
        scored.sort(key=lambda t: t[0], reverse=True)
        return [c for _, c in scored[:_MAX_CANDIDATES]]

    @staticmethod
    def _cosine(a: list[float], b: list[float]) -> float:
        if not a or not b:
            return 0.0
        dot = sum(x * y for x, y in zip(a, b))
        na = math.sqrt(sum(x * x for x in a))
        nb = math.sqrt(sum(y * y for y in b))
        return dot / (na * nb) if na and nb else 0.0
