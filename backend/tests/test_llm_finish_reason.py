from __future__ import annotations

import sys
import unittest
from pathlib import Path
from types import SimpleNamespace

APP = Path(__file__).resolve().parents[1] / "app"
if str(APP) not in sys.path:
    sys.path.insert(0, str(APP))

from nexus.indexing.extractor import AssertionExtractor
from nexus.infrastructure.ai_clients import ChatClient
from nexus.indexing.recorder import IndexRunRecorder
from nexus.querying.recorder import QueryRunRecorder


class FakeDb:
    def __init__(self):
        self.calls: list[tuple[str, tuple | None]] = []

    def execute_non_query(self, query, params=None):
        self.calls.append((query, params))
        return 1


class FakeQueryRecorder(QueryRunRecorder):
    def __init__(self):
        super().__init__()
        self.fake_db = FakeDb()

    @property
    def db(self):
        return self.fake_db


class FakeGenerations:
    def __init__(self):
        self.db = FakeDb()


class LlmFinishReasonTests(unittest.TestCase):
    def test_chat_usage_captures_finish_reason(self):
        client = ChatClient({
            "endpoint": "https://example.invalid",
            "key": "test",
            "deployment": "test",
        })
        response = SimpleNamespace(
            usage=SimpleNamespace(
                prompt_tokens=100,
                completion_tokens=12,
                prompt_tokens_details=SimpleNamespace(cached_tokens=64),
            ),
            choices=[SimpleNamespace(finish_reason="stop")],
        )
        client._add_usage(response)
        self.assertEqual(client.pop_usage(), {
            "input": 100,
            "output": 12,
            "cached": 64,
            "finish_reason": "stop",
        })

    def test_chat_usage_keeps_finish_reason_without_usage_details(self):
        client = ChatClient({
            "endpoint": "https://example.invalid",
            "key": "test",
            "deployment": "test",
        })
        client._add_usage(SimpleNamespace(
            usage=None,
            choices=[SimpleNamespace(finish_reason="content_filter")],
        ))
        self.assertEqual(client.pop_usage(), {"finish_reason": "content_filter"})

    def test_extraction_usage_sums_tokens_and_keeps_latest_reason(self):
        total = {}
        AssertionExtractor._merge_tokens(total, {
            "input": 10, "output": 2, "finish_reason": "length",
        })
        AssertionExtractor._merge_tokens(total, {
            "input": 7, "output": 3, "finish_reason": "stop",
        })
        self.assertEqual(total, {
            "input": 17,
            "output": 5,
            "finish_reason": "stop",
        })

    def test_query_recorder_persists_finish_reason_without_numeric_coercion(self):
        recorder = FakeQueryRecorder()
        recorder.bump_tokens("run_1", {
            "input": 20,
            "output": 4,
            "finish_reason": "stop",
        })
        self.assertEqual(recorder._tokens["finish_reason"], "stop")
        self.assertEqual(recorder._stage_tokens["finish_reason"], "stop")
        self.assertEqual(recorder._tokens["input"], 20)
        self.assertTrue(recorder.fake_db.calls)
        persisted = recorder.fake_db.calls[-1][1][0]
        self.assertIn('"finish_reason":"stop"', persisted)

    def test_index_recorder_persists_finish_reason_without_numeric_coercion(self):
        generations = FakeGenerations()
        recorder = IndexRunRecorder(generations, "gen_1")
        recorder.bump_tokens("run_1", {
            "input": 20,
            "output": 4,
            "finish_reason": "length",
        })
        self.assertEqual(recorder._tokens["finish_reason"], "length")
        persisted = generations.db.calls[-1][1][0]
        self.assertIn('"finish_reason":"length"', persisted)


if __name__ == "__main__":
    unittest.main()
