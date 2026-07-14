from __future__ import annotations

import sys
import unittest
from pathlib import Path

APP = Path(__file__).resolve().parents[1] / "app"
if str(APP) not in sys.path:
    sys.path.insert(0, str(APP))

from nexus.querying.generator import AnswerGenerationError, AnswerGenerator
from nexus.querying.models import EvidenceGroup, OperatorResult


class AnswerGeneratorCitationTests(unittest.TestCase):
    def test_opaque_citation_id_resolves_assertion_identity(self):
        evidence = OperatorResult(
            kind="evidence_set",
            items=[{
                "evidence_kind": "assertion",
                "assertion_id": "ast_1",
                "block_key": "block_1",
                "quote": "精确断言原文",
            }],
        )
        result = AnswerGenerator._validate_citations(
            evidence, [{"citation_id": "E1"}], {},
        )
        self.assertEqual(result, [{
            "assertion_id": "ast_1",
            "block_key": "block_1",
            "quote": "精确断言原文",
        }])

    def test_citation_includes_friendly_source_metadata(self):
        evidence = OperatorResult(
            kind="evidence_set",
            items=[{
                "evidence_kind": "block",
                "block_key": "block_1",
                "block_id": "doc_1:article-三",
                "document_id": "doc_1",
                "title": "中华人民共和国疫苗管理法",
                "category": "NDA",
                "heading_path": "第一章 总则",
                "article_no": "三",
                "ordinal": 4,
                "text": "第三条原文",
            }],
        )
        result = AnswerGenerator._validate_citations(
            evidence, [{"citation_id": "E1"}], {},
        )[0]
        self.assertEqual(result["title"], "中华人民共和国疫苗管理法")
        self.assertEqual(result["article_no"], "三")
        self.assertEqual(result["heading_path"], "第一章 总则")
        self.assertEqual(result["document_id"], "doc_1")
        self.assertEqual(result["quote"], "第三条原文")

    def test_unknown_opaque_citation_id_is_rejected(self):
        evidence = OperatorResult(
            kind="evidence_set",
            items=[{"evidence_kind": "block", "block_key": "block_1", "text": "原文"}],
        )
        with self.assertRaisesRegex(AnswerGenerationError, "citation_id is outside"):
            AnswerGenerator._validate_citations(
                evidence, [{"citation_id": "E99"}], {},
            )

    def test_server_materializes_exact_assertion_quote(self):
        source = "第一句。模型不得省略的中间句。第三句。"
        evidence = OperatorResult(
            kind="evidence_set",
            items=[{
                "evidence_kind": "assertion",
                "assertion_id": "ast_1",
                "block_key": "block_1",
                "quote": source,
            }],
        )
        citations = [{
            "assertion_id": "ast_1",
            "block_key": "block_1",
            # Legacy/model-authored non-contiguous excerpt must never be persisted.
            "quote": "第一句。第三句。",
        }]
        result = AnswerGenerator._validate_citations(evidence, citations, citations)
        self.assertEqual(result, [{
            "assertion_id": "ast_1",
            "block_key": "block_1",
            "quote": source,
        }])

    def test_block_citation_does_not_require_model_quote(self):
        evidence = OperatorResult(
            kind="evidence_set",
            items=[{
                "evidence_kind": "block",
                "block_key": "block_2",
                "text": "完整原文块",
            }],
        )
        result = AnswerGenerator._validate_citations(
            evidence, [{"block_key": "block_2"}], {},
        )
        self.assertEqual(result[0]["quote"], "完整原文块")

    def test_legacy_spurious_assertion_number_does_not_invalidate_known_block(self):
        evidence = OperatorResult(
            kind="evidence_set",
            items=[{
                "evidence_kind": "block",
                "block_key": "block_2",
                "text": "完整原文块",
            }],
        )
        result = AnswerGenerator._validate_citations(
            evidence,
            [{"assertion_id": "1", "block_key": "block_2"}],
            {},
        )
        self.assertEqual(result, [{"block_key": "block_2", "quote": "完整原文块"}])

    def test_group_identity_is_enforced_and_quote_is_materialized(self):
        evidence = OperatorResult(
            kind="evidence_bundle",
            groups=[EvidenceGroup(
                key="document_1",
                label="文档一",
                document_ids=["doc_1"],
                items=[{"block_key": "block_3", "text": "分组原文"}],
            )],
        )
        result = AnswerGenerator._validate_citations(
            evidence,
            [{"group": "document_1", "block_key": "block_3"}],
            {},
        )
        self.assertEqual(result, [{
            "group": "document_1",
            "group_label": "文档一",
            "block_key": "block_3",
            "quote": "分组原文",
        }])
        with self.assertRaisesRegex(AnswerGenerationError, "does not belong"):
            AnswerGenerator._validate_citations(
                evidence,
                [{"group": "document_2", "block_key": "block_3"}],
                {},
            )

    def test_forged_assertion_block_pair_is_rejected(self):
        evidence = OperatorResult(
            kind="evidence_set",
            items=[{
                "evidence_kind": "assertion",
                "assertion_id": "ast_1",
                "block_key": "block_1",
                "quote": "原文",
            }],
        )
        with self.assertRaisesRegex(AnswerGenerationError, "outside provided evidence"):
            AnswerGenerator._validate_citations(
                evidence,
                [{"assertion_id": "ast_other", "block_key": "block_1"}],
                {},
            )


if __name__ == "__main__":
    unittest.main()
