"""Built-in generation quality gate and metric persistence."""
from __future__ import annotations

from dataclasses import dataclass
import math

from .base import SqlRepository, json_text


@dataclass(frozen=True)
class QualityMetric:
    code: str
    passed: bool
    actual: int
    threshold: int
    details: dict
    severity: str = "error"


class QualityRepository(SqlRepository):
    def evaluate(self, run_id: str, generation_id: str, ai_search_count: int) -> tuple[bool, list[QualityMetric]]:
        self.db.execute_non_query(
            "UPDATE nexus.index_generation SET [state]='validating' WHERE generation_id=? AND [state]='building'",
            (generation_id,),
        )
        rows = self.db.execute_query(
            """SELECT
                (SELECT COUNT_BIG(*) FROM nexus.block_manifest
                 WHERE generation_id=? AND extraction_state IN ('pending','failed')) AS bad_extraction_blocks,
                (SELECT COUNT_BIG(*) FROM nexus.block_manifest
                 WHERE generation_id=? AND extraction_state='quarantined') AS quarantined_blocks,
                (SELECT COUNT_BIG(*) FROM nexus.block_manifest
                 WHERE generation_id=?) AS total_blocks,
                (SELECT COUNT_BIG(*) FROM nexus.block_manifest
                 WHERE generation_id=? AND search_state IN ('pending','failed')) AS bad_search_blocks,
                (SELECT COUNT_BIG(*)
                 FROM nexus.assertion_entity ae
                 JOIN nexus.legal_assertion la ON la.assertion_id=ae.assertion_id
                 WHERE la.generation_id=? AND la.[state]='accepted'
                   AND (
                       (ae.mention_id IS NOT NULL AND ae.entity_id IS NULL)
                       OR (
                           ae.entity_id IS NOT NULL AND NOT EXISTS (
                               SELECT 1 FROM nexus.entity e WHERE e.entity_id=ae.entity_id
                           )
                       )
                   )) AS unresolved_participants,
                (SELECT COUNT_BIG(*) FROM nexus.legal_assertion la
                 WHERE la.generation_id=? AND la.[state]='accepted'
                   AND la.action_id IS NOT NULL
                   AND NOT EXISTS (SELECT 1 FROM nexus.action a WHERE a.action_id=la.action_id)) AS missing_actions,
                                (SELECT COUNT_BIG(DISTINCT la.assertion_id)
                                 FROM nexus.legal_assertion la
                                 JOIN nexus.action_mention am
                                     ON am.action_id=la.action_id AND am.generation_id=la.generation_id
                                 WHERE la.generation_id=? AND la.[state]='accepted'
                                     AND am.resolution_state IN ('pending','ambiguous','rejected')) AS unresolved_action_participants,
                (SELECT COUNT_BIG(*) FROM nexus.legal_assertion la
                 WHERE la.generation_id=? AND la.[state]='accepted'
                   AND NOT EXISTS (
                       SELECT 1 FROM nexus.assertion_evidence ev
                       WHERE ev.assertion_id=la.assertion_id AND ev.evidence_role='primary'
                   )) AS assertions_without_primary,
                (SELECT COUNT_BIG(*) FROM nexus.graph_edge ge
                 WHERE ge.generation_id=? AND NOT EXISTS (
                     SELECT 1
                     FROM nexus.graph_edge_support gs
                     JOIN nexus.legal_assertion la ON la.assertion_id=gs.assertion_id
                     WHERE gs.edge_id=ge.edge_id AND la.generation_id=ge.generation_id
                       AND la.[state]='accepted'
                 )) AS edges_without_support,
                (SELECT COUNT_BIG(*) FROM nexus.block_manifest
                 WHERE generation_id=? AND search_state='written') AS manifest_written,
                (SELECT COUNT_BIG(*) FROM nexus.legal_assertion
                 WHERE generation_id=? AND [state]='accepted') AS accepted_assertions,
                (SELECT COUNT_BIG(*) FROM nexus.legal_assertion la
                 WHERE la.generation_id=? AND NOT EXISTS (
                     SELECT 1 FROM nexus.document_version dv
                     WHERE dv.document_version_id=la.document_version_id
                       AND dv.generation_id=la.generation_id
                 )) AS assertion_version_mismatch,
                (SELECT COUNT_BIG(*) FROM nexus.assertion_evidence ev
                 JOIN nexus.legal_assertion la ON la.assertion_id=ev.assertion_id
                 WHERE la.generation_id=? AND NOT EXISTS (
                     SELECT 1 FROM nexus.block_manifest bm
                     WHERE bm.block_key=ev.block_key AND bm.generation_id=la.generation_id
                 )) AS evidence_block_mismatch,
                (SELECT COUNT_BIG(*) FROM nexus.entity_mention em
                 WHERE em.generation_id=? AND NOT EXISTS (
                     SELECT 1 FROM nexus.block_manifest bm
                     WHERE bm.block_key=em.block_key AND bm.generation_id=em.generation_id
                       AND bm.document_version_id=em.document_version_id
                 )) AS entity_mention_mismatch,
                (SELECT COUNT_BIG(*) FROM nexus.action_mention am
                 WHERE am.generation_id=? AND NOT EXISTS (
                     SELECT 1 FROM nexus.block_manifest bm
                     WHERE bm.block_key=am.block_key AND bm.generation_id=am.generation_id
                       AND bm.document_version_id=am.document_version_id
                 )) AS action_mention_mismatch,
                (SELECT COUNT_BIG(*) FROM nexus.assertion_entity ae
                 JOIN nexus.legal_assertion la ON la.assertion_id=ae.assertion_id
                 WHERE la.generation_id=? AND ae.mention_id IS NOT NULL AND NOT EXISTS (
                     SELECT 1 FROM nexus.entity_mention em
                     WHERE em.mention_id=ae.mention_id AND em.generation_id=la.generation_id
                 )) AS assertion_mention_mismatch""",
            (generation_id,) * 16,
        )
        r = rows[0]
        unresolved = (
            int(r["unresolved_participants"] or 0)
            + int(r["missing_actions"] or 0)
            + int(r["unresolved_action_participants"] or 0)
        )
        written = int(r["manifest_written"] or 0)
        accepted = int(r["accepted_assertions"] or 0)
        quarantined = int(r["quarantined_blocks"] or 0)
        total_blocks = int(r["total_blocks"] or 0)
        quarantine_threshold = max(1, math.ceil(total_blocks * 0.05))
        metrics = [
            self._zero("blocks_extraction_complete", int(r["bad_extraction_blocks"] or 0)),
            QualityMetric(
                code="quarantined_blocks_within_tolerance",
                passed=quarantined <= quarantine_threshold,
                actual=quarantined,
                threshold=quarantine_threshold,
                details={
                    "quarantined_blocks": quarantined,
                    "total_blocks": total_blocks,
                    "maximum_ratio": 0.05,
                },
                severity=("warning" if quarantined <= quarantine_threshold else "error"),
            ),
            self._zero("blocks_search_complete", int(r["bad_search_blocks"] or 0)),
            self._zero("accepted_participants_resolved", unresolved),
            self._zero("accepted_assertions_have_primary_evidence", int(r["assertions_without_primary"] or 0)),
            self._zero("graph_edges_have_support", int(r["edges_without_support"] or 0)),
            self._zero("assertion_versions_in_generation", int(r["assertion_version_mismatch"] or 0)),
            self._zero("evidence_blocks_in_generation", int(r["evidence_block_mismatch"] or 0)),
            self._zero("entity_mentions_in_generation", int(r["entity_mention_mismatch"] or 0)),
            self._zero("action_mentions_in_generation", int(r["action_mention_mismatch"] or 0)),
            self._zero("assertion_mentions_in_generation", int(r["assertion_mention_mismatch"] or 0)),
            QualityMetric(
                code="ai_search_manifest_count_match",
                passed=int(ai_search_count) == written,
                actual=int(ai_search_count),
                threshold=written,
                details={"ai_search_count": int(ai_search_count), "written_manifest_count": written},
            ),
            QualityMetric(
                code="accepted_assertions_nonempty",
                passed=accepted > 0,
                actual=accepted,
                threshold=1,
                details={"accepted_assertions": accepted},
            ),
        ]
        self._persist(run_id, generation_id, metrics)
        passed = all(metric.passed for metric in metrics)
        summary = {
            "passed": passed,
            "issues": [m.code for m in metrics if not m.passed],
            "warnings": [m.code for m in metrics if m.severity == "warning" and m.actual > 0],
            "metrics": {
                m.code: {
                    "passed": m.passed,
                    "actual": m.actual,
                    "threshold": m.threshold,
                    "severity": m.severity,
                }
                for m in metrics
            },
        }
        self.db.execute_non_query(
            """UPDATE nexus.index_generation
               SET quality_state=?, quality_summary=?, validated_at=SYSUTCDATETIME()
               WHERE generation_id=?""",
            ("passed" if passed else "failed", json_text(summary), generation_id),
        )
        self.db.execute_non_query(
            """UPDATE nexus.index_run
               SET quality_issue_count=?, updated_at=SYSUTCDATETIME()
               WHERE run_id=?""",
            (sum(1 for m in metrics if not m.passed) + quarantined, run_id),
        )
        return passed, metrics

    @staticmethod
    def _zero(code: str, actual: int) -> QualityMetric:
        return QualityMetric(code=code, passed=actual == 0, actual=actual, threshold=0, details={"issue_count": actual})

    def _persist(self, run_id: str, generation_id: str, metrics: list[QualityMetric]) -> None:
        self.db.execute_non_query(
            "DELETE FROM nexus.index_quality_metric WHERE run_id=? AND generation_id=?",
            (run_id, generation_id),
        )
        for metric in metrics:
            self.db.execute_non_query(
                """INSERT INTO nexus.index_quality_metric
                       (run_id, generation_id, metric_code, scope_type, severity,
                        passed, actual_value, threshold_value, details)
                   VALUES (?, ?, ?, 'generation', ?, ?, ?, ?, ?)""",
                (
                    run_id, generation_id, metric.code, metric.severity, int(metric.passed),
                    metric.actual, metric.threshold, json_text(metric.details),
                ),
            )
