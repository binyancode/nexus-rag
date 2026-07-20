from __future__ import annotations

import json
import sys
import unittest
from pathlib import Path

APP = Path(__file__).resolve().parents[1] / "app"
if str(APP) not in sys.path:
    sys.path.insert(0, str(APP))

from nexus.domain import (
    CollectionScope,
    EntityVocabularyItem,
    QueryBudgets,
    QueryContext,
)
from nexus.querying.binder import VocabularyBinder
from nexus.querying.compiler import SQGCompiler
from nexus.querying.planner import DeterministicPlanner


class FakeChat:
    def __init__(self, response: dict | list[dict]):
        self.responses = response if isinstance(response, list) else [response]
        self.calls = 0
        self.request: dict | None = None

    def complete_json(self, system: str, prompt: str):
        self.request = json.loads(prompt)
        response = self.responses[min(self.calls, len(self.responses) - 1)]
        self.calls += 1
        return response


def context(question: str) -> QueryContext:
    return QueryContext(
        run_id="run_test",
        question=question,
        collection=CollectionScope(
            collection_id="default",
            name="默认法规库",
            selected_by="user",
            allowed_stores=("store",),
            generation_scope={"store": "gen"},
        ),
        llm_credential="llm",
        embedding_credential="embedding",
        max_parallel=2,
        budgets=QueryBudgets(max_entities=200, max_blocks=30, max_tokens=30000),
        generation_dimensions={"store": 3},
        entities=(
            EntityVocabularyItem(
                entity_id="ent_org", entity_type="Org",
                name="疫苗上市许可持有人", aliases=(),
            ),
            EntityVocabularyItem(
                entity_id="ent_concept", entity_type="Concept",
                name="疫苗上市许可持有人", aliases=(),
            ),
        ),
        graph_relations=("has_obligation",),
    )


class GraphQueryCompilerTests(unittest.TestCase):
    def test_type_disambiguates_same_name_graph_start(self):
        query = "疫苗上市许可持有人必须履行哪些主要义务？"
        ctx = context(query)
        chat = FakeChat({
            "question": query,
            "intent": {
                "kind": "traverse_relation",
                "start": "疫苗上市许可持有人",
                "start_type": "Org",
                "relation": "has_obligation",
                "inverse": False,
            },
        })
        sqg = SQGCompiler().compile(ctx, chat)
        self.assertEqual(sqg.intent.kind, "traverse_relation")
        pep = DeterministicPlanner().plan(ctx, sqg)
        self.assertEqual([node.op for node in pep.nodes], [
            "EntityLookup", "GraphTraverse", "GroundAssertions",
        ])
        self.assertEqual(pep.nodes[0].params.entity_ids, ["ent_org"])
        self.assertEqual(pep.nodes[1].params.relation, "has_obligation")

    def test_missing_type_remains_ambiguous(self):
        with self.assertRaisesRegex(ValueError, "ambiguous"):
            VocabularyBinder(context("问题")).node("疫苗上市许可持有人")

    def test_prompt_describes_natural_relation_and_graph_priority(self):
        query = "疫苗上市许可持有人必须履行哪些主要义务？"
        chat = FakeChat({
            "question": query,
            "intent": {
                "kind": "traverse_relation",
                "start": "疫苗上市许可持有人",
                "start_type": "Org",
                "relation": "has_obligation",
                "inverse": False,
            },
        })
        SQGCompiler().compile(context(query), chat)
        assert chat.request is not None
        relation = chat.request["visible_graph_relations"][0]
        self.assertEqual(relation["name"], "has_obligation")
        self.assertIn("义务", relation["meaning"])
        self.assertTrue(any(
            "Prefer traverse_relation" in rule for rule in chat.request["rules"]
        ))

    def test_explicit_relation_cannot_fall_back_to_semantic_search(self):
        query = "从疫苗上市许可持有人沿 has_obligation 关系查义务"
        chat = FakeChat([
            {
                "question": query,
                "intent": {
                    "kind": "semantic_evidence",
                    "query": query,
                    "documents": [],
                },
            },
            {
                "question": query,
                "intent": {
                    "kind": "traverse_relation",
                    "start": "疫苗上市许可持有人",
                    "start_type": "Org",
                    "relation": "has_obligation",
                    "inverse": False,
                },
            },
        ])
        sqg = SQGCompiler().compile(context(query), chat)
        self.assertEqual(chat.calls, 2)
        self.assertEqual(sqg.intent.kind, "traverse_relation")


if __name__ == "__main__":
    unittest.main()
