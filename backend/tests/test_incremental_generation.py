from __future__ import annotations

import sys
import unittest
from pathlib import Path

APP = Path(__file__).resolve().parents[1] / "app"
if str(APP) not in sys.path:
    sys.path.insert(0, str(APP))

from nexus.indexing.chunker import chunk_document, content_hash, document_id
from nexus.indexing.runner import classify_files, plan_document_deletion
from nexus.infrastructure.assertion_repository import AssertionRepository
from nexus.infrastructure.document_repository import DocumentRepository
from nexus.infrastructure.search_adapter import GenerationSearchAdapter


class FakeDb:
    def __init__(self, source_versions: list[dict], source_blocks: list[dict]):
        self.source_versions = source_versions
        self.source_blocks = source_blocks
        self.many: list[tuple[str, list[tuple]]] = []

    def execute_query(self, query, params=None):
        if "FROM nexus.document_version" in query:
            return list(self.source_versions)
        if "FROM nexus.block_manifest" in query:
            return list(self.source_blocks)
        raise AssertionError(query)

    def execute_many(self, query, rows):
        values = list(rows)
        self.many.append((query, values))
        return len(values)


class FakeDocumentRepository(DocumentRepository):
    def __init__(self, db: FakeDb):
        super().__init__()
        self._db = db

    @property
    def db(self):
        return self._db


class FactDb:
    def __init__(self):
        self.many: list[tuple[str, list[tuple]]] = []

    def execute_query(self, query, params=None):
        if "FROM nexus.entity_alias WHERE" in query:
            return [{
                "entity_id": "ent_1", "alias": "机构", "normalized_alias": "机构",
                "source": "llm", "confidence": 0.9,
            }]
        if "FROM nexus.entity_mention WHERE" in query:
            return [{
                "mention_id": 7, "document_version_id": "dv_old_keep",
                "block_key": "old_keep", "local_id": "e1", "mention_text": "机构",
                "canonical_name": "机构", "entity_type": "Org", "start_offset": 0,
                "end_offset": 2, "entity_id": "ent_1", "resolution_state": "matched",
                "confidence": 0.9, "candidates": None,
            }]
        if "FROM nexus.action_mention WHERE" in query:
            return []
        if "FROM nexus.legal_assertion la" in query and "EXISTS" in query:
            return [{
                "assertion_id": "ast_old", "document_version_id": "dv_old_replace",
                "assertion_kind": "relation", "predicate": "relates", "modality": "factual",
                "action_id": None, "condition_text": None, "exception_text": None,
                "scope_text": None, "payload": None, "assertion_hash": "c" * 64,
                "confidence": 0.9, "state": "accepted", "source": "llm", "locked": False,
            }]
        if "FROM nexus.assertion_evidence ev" in query:
            return [
                {
                    "assertion_id": "ast_old", "block_key": "old_replace",
                    "evidence_role": "primary", "quote": "被替换", "quote_start": 0,
                    "quote_end": 3, "confidence": 0.9,
                },
                {
                    "assertion_id": "ast_old", "block_key": "old_keep",
                    "evidence_role": "supporting", "quote": "保留证据", "quote_start": 0,
                    "quote_end": 4, "confidence": 0.8,
                },
            ]
        if "FROM nexus.assertion_entity ae" in query:
            return [{
                "assertion_id": "ast_old", "role": "subject", "ordinal": 1,
                "entity_id": "ent_1", "mention_id": 7, "value_text": "机构",
            }]
        raise AssertionError(query)

    def execute_many(self, query, rows):
        values = list(rows)
        self.many.append((query, values))
        return len(values)


class FakeAssertionRepository(AssertionRepository):
    def __init__(self, db: FactDb):
        super().__init__()
        self._db = db

    @property
    def db(self):
        return self._db

    def mention_ids(self, generation_id: str):
        return {("new_keep", "e1"): 70}


class SearchResult:
    def __init__(self, key: str):
        self.key = key
        self.succeeded = True


class SearchClient:
    def __init__(self, rows: list[dict]):
        self.rows = rows
        self.uploaded: list[dict] = []

    def search(self, **kwargs):
        return list(self.rows)

    def merge_or_upload_documents(self, documents):
        self.uploaded.extend(documents)
        return [SearchResult(document["id"]) for document in documents]


class FakeSearchAdapter(GenerationSearchAdapter):
    def __init__(self, client: SearchClient):
        super().__init__()
        self.client = client

    def _search_client(self, store_id: str, dimensions: int):
        return self.client


class IncrementalGenerationTests(unittest.TestCase):
    def test_generation_keeps_logical_document_and_block_ids_stable(self):
        source = "第一章 总则\n第一条 同一条文。"
        first = chunk_document(
            text=source, category="NDA", title="测试法规", generation_id="gen_a",
        )
        second = chunk_document(
            text=source, category="NDA", title="测试法规", generation_id="gen_b",
        )
        self.assertEqual(first.document.document_id, second.document.document_id)
        self.assertEqual(
            [block.block_id for block in first.blocks],
            [block.block_id for block in second.blocks],
        )
        self.assertNotEqual(first.version.document_version_id, second.version.document_version_id)
        self.assertNotEqual(first.blocks[0].block_key, second.blocks[0].block_key)

    def test_classify_files_add_replace_and_unchanged(self):
        doc_a = document_id("NDA", "法规A")
        doc_b = document_id("NDA", "法规B")
        base = {
            doc_a: {"document_id": doc_a, "content_hash": content_hash("旧A")},
            doc_b: {"document_id": doc_b, "content_hash": content_hash("B")},
        }
        files = [
            ("法规A.txt", "新A", "NDA"),
            ("法规B.txt", "B", "NDA"),
            ("法规C.txt", "C", "NDA"),
        ]
        changed, retained, plan = classify_files(files, base)
        self.assertEqual([item[0] for item in changed], ["法规A.txt", "法规C.txt"])
        self.assertEqual(retained, {doc_b})
        self.assertEqual([item["action"] for item in plan], ["replace", "unchanged", "add"])

    def test_document_deletion_retains_unselected_documents(self):
        base = {"doc_a": {}, "doc_b": {}, "doc_c": {}}
        self.assertEqual(
            plan_document_deletion(base, {"doc_b"}),
            {"doc_a", "doc_c"},
        )
        with self.assertRaisesRegex(ValueError, "not present"):
            plan_document_deletion(base, {"doc_missing"})
        with self.assertRaisesRegex(ValueError, "every document"):
            plan_document_deletion(base, set(base))

    def test_clone_documents_remaps_generation_local_ids(self):
        source_versions = [{
            "document_version_id": "dv_old",
            "document_id": "doc_a",
            "title": "法规A",
            "category": "NDA",
            "source_uri": None,
            "content_hash": "a" * 64,
            "block_count": 1,
            "state": "validated",
            "raw_metadata": '{"filename":"法规A.txt"}',
        }]
        source_blocks = [{
            "block_key": "gen_old:doc_a:article-一",
            "document_version_id": "dv_old",
            "document_id": "doc_a",
            "block_id": "doc_a:article-一",
            "parent_block_id": None,
            "article_no": "一",
            "paragraph_no": None,
            "item_no": None,
            "heading_path": "第一章",
            "ordinal": 1,
            "text_hash": "b" * 64,
            "char_count": 10,
            "extraction_state": "succeeded",
        }]
        db = FakeDb(source_versions, source_blocks)
        result = FakeDocumentRepository(db).clone_documents(
            "gen_old", "gen_new", {"doc_a"},
        )
        self.assertEqual(result["documents"], 1)
        self.assertEqual(result["block_count"], 1)
        mapped = result["blocks"]["gen_old:doc_a:article-一"]
        self.assertEqual(mapped["target_block_key"], "gen_new:doc_a:article-一")
        self.assertNotEqual(result["versions"]["dv_old"], "dv_old")
        block_insert = next(rows for sql, rows in db.many if "block_manifest" in sql)
        self.assertEqual(block_insert[0][-1], "succeeded")
        self.assertIn("'pending'", next(sql for sql, _ in db.many if "block_manifest" in sql))

    def test_duplicate_logical_documents_are_rejected(self):
        with self.assertRaisesRegex(ValueError, "duplicate logical document"):
            classify_files(
                [("法规.txt", "A", "NDA"), ("法规.md", "B", "NDA")],
                {},
            )

    def test_clone_retained_facts_promotes_retained_supporting_evidence(self):
        db = FactDb()
        result = FakeAssertionRepository(db).clone_retained_facts(
            "gen_old",
            "gen_new",
            {
                "versions": {"dv_old_keep": "dv_new_keep"},
                "blocks": {
                    "old_keep": {
                        "source_block_key": "old_keep",
                        "target_block_key": "new_keep",
                        "source_document_version_id": "dv_old_keep",
                        "target_document_version_id": "dv_new_keep",
                        "document_id": "doc_keep",
                        "block_id": "doc_keep:article-1",
                        "ordinal": 1,
                    },
                },
            },
        )
        self.assertEqual(result["assertions"], 1)
        evidence_rows = next(rows for sql, rows in db.many if "assertion_evidence" in sql)
        self.assertEqual(len(evidence_rows), 1)
        self.assertEqual(evidence_rows[0][2], "primary")
        self.assertEqual(evidence_rows[0][1], "new_keep")
        participant_rows = next(rows for sql, rows in db.many if "assertion_entity" in sql)
        self.assertEqual(participant_rows[0][4], 70)

    def test_strict_deletion_drops_assertion_when_any_evidence_is_removed(self):
        db = FactDb()
        result = FakeAssertionRepository(db).clone_retained_facts(
            "gen_old",
            "gen_new",
            {
                "versions": {"dv_old_keep": "dv_new_keep"},
                "blocks": {
                    "old_keep": {
                        "source_block_key": "old_keep",
                        "target_block_key": "new_keep",
                        "source_document_version_id": "dv_old_keep",
                        "target_document_version_id": "dv_new_keep",
                        "document_id": "doc_keep",
                        "block_id": "doc_keep:article-1",
                        "ordinal": 1,
                    },
                },
            },
            require_all_evidence=True,
        )
        self.assertEqual(result["assertions"], 0)
        assertion_rows = next(rows for sql, rows in db.many if "legal_assertion" in sql)
        evidence_rows = next(rows for sql, rows in db.many if "assertion_evidence" in sql)
        self.assertEqual(assertion_rows, [])
        self.assertEqual(evidence_rows, [])

    def test_clone_search_blocks_preserves_vector_and_remaps_scope(self):
        vector = [0.1, 0.2, 0.3]
        client = SearchClient([{
            "generation_id": "gen_old", "block_key": "old_keep", "block_id": "doc:article-1",
            "document_id": "doc", "document_version_id": "dv_old", "category": "NDA",
            "title": "法规", "text": "原文", "parent_block_id": None, "article_no": "一",
            "paragraph_no": None, "item_no": None, "heading_path": "第一章", "ordinal": 1,
            "text_hash": "d" * 64, "vector": vector,
        }])
        copied = FakeSearchAdapter(client).clone_blocks(
            "store", "gen_old", "gen_new",
            {"old_keep": {
                "source_block_key": "old_keep", "target_block_key": "new_keep",
                "target_document_version_id": "dv_new",
            }},
            3,
        )
        self.assertEqual(copied, 1)
        self.assertEqual(client.uploaded[0]["generation_id"], "gen_new")
        self.assertEqual(client.uploaded[0]["block_key"], "new_keep")
        self.assertEqual(client.uploaded[0]["document_version_id"], "dv_new")
        self.assertEqual(client.uploaded[0]["vector"], vector)


if __name__ == "__main__":
    unittest.main()
