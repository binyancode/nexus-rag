from __future__ import annotations

import json
import sys
import unittest
from pathlib import Path

APP = Path(__file__).resolve().parents[1] / "app"
if str(APP) not in sys.path:
    sys.path.insert(0, str(APP))

from api.v1.endpoints.index import _extraction_summary, _quarantine_reason


class DocumentManagementTests(unittest.TestCase):
    def test_no_assertion_reason_is_friendly(self):
        raw = json.dumps([{
            "type": "value_error",
            "message": "Value error, non-empty extraction requires at least one legal assertion",
        }])
        code, reason, messages = _quarantine_reason(raw)
        self.assertEqual(code, "no_valid_assertion")
        self.assertIn("没有生成", reason)
        self.assertEqual(len(messages), 1)

    def test_quote_and_modality_reasons_are_classified(self):
        code, reason, _ = _quarantine_reason([{
            "type": "quote_span_mismatch",
            "message": "assertion quote is not an exact source span",
        }])
        self.assertEqual(code, "quote_not_grounded")
        self.assertIn("原文", reason)

        code, reason, _ = _quarantine_reason([{
            "type": "modality_without_lexical_support",
            "message": "modality must has no lexical support in source context",
        }])
        self.assertEqual(code, "unsupported_modality")
        self.assertIn("法律语气", reason)

    def test_missing_audit_is_explicit(self):
        code, reason, messages = _quarantine_reason(None)
        self.assertEqual(code, "audit_unavailable")
        self.assertIn("没有找到", reason)
        self.assertEqual(messages, [])

    def test_extraction_summary_lists_entities_actions_and_rejected_facts(self):
        summary = _extraction_summary({
            "entities": [{
                "local_id": "e1", "mention_text": "申请人",
                "canonical_name": "申请人", "entity_type": "Org",
            }],
            "actions": [{
                "local_id": "a1", "canonical_text": "告知申请人", "verb": "告知",
                "participants": [{"role": "recipient", "entity_local_id": "e1"}],
            }],
            "assertions": [{
                "local_id": "s1", "kind": "norm", "predicate": "inform",
                "modality": "must", "action_local_id": "a1",
                "participants": [{"role": "subject", "entity_local_id": None, "value_text": None}],
            }],
        })
        self.assertEqual(summary["entities"][0]["canonical_name"], "申请人")
        self.assertEqual(summary["actions"][0]["participants"][0]["value"], "申请人")
        self.assertEqual(
            summary["candidate_assertions"][0]["rejection_reasons"],
            ["责任主体为空"],
        )

    def test_extraction_summary_detects_missing_subject(self):
        summary = _extraction_summary({
            "actions": [{
                "local_id": "a1", "canonical_text": "不计入工作时限", "verb": "计入",
                "participants": [],
            }],
            "assertions": [{
                "local_id": "s1", "kind": "norm", "predicate": "exclude",
                "modality": "factual", "action_local_id": "a1", "participants": [],
            }],
        })
        self.assertEqual(
            summary["candidate_assertions"][0]["rejection_reasons"],
            ["缺少责任主体"],
        )


if __name__ == "__main__":
    unittest.main()
