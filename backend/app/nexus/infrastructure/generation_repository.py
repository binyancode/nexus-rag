"""SQL persistence for index runs, isolated generations, and activation."""
from __future__ import annotations

from .base import SqlRepository, json_text


class GenerationRepository(SqlRepository):
    def active_generation(self, store_id: str) -> dict | None:
        rows = self.db.execute_query(
            """SELECT TOP 1 s.active_generation_id AS generation_id,
                                            g.embedding_dimensions,g.ontology_version,g.extractor_version,
                                            r.embedding_credential,g.[state]
               FROM nexus.search_store s
               JOIN nexus.index_generation g
                 ON g.generation_id=s.active_generation_id AND g.store_id=s.store_id
                             JOIN nexus.index_run r ON r.run_id=g.run_id
               WHERE s.store_id=? AND g.[state]='active'""",
            (store_id,),
        )
        return rows[0] if rows else None

    def create_run_and_generation(
        self,
        *,
        run_id: str,
        generation_id: str,
        as_user: str | None,
        store_id: str,
        category: str,
        llm_credential: str,
        embedding_credential: str,
        max_parallel: int,
        ontology_version: str,
        extractor_version: str,
        embedding_dimensions: int,
        input_snapshot: dict,
        base_generation_id: str | None = None,
    ) -> None:
        """Atomically establish both audit rows before the workflow starts."""
        self.db.execute_non_query(
            """BEGIN TRY
                   BEGIN TRANSACTION;
                   INSERT INTO nexus.index_run
                       (run_id, generation_id, as_user, store_id, category,
                        llm_credential, embedding_credential, max_parallel, [state],
                        input_snapshot, created_at, updated_at)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, 'running', ?, SYSUTCDATETIME(), SYSUTCDATETIME());

                   INSERT INTO nexus.index_generation
                       (generation_id, run_id, store_id, base_generation_id, [state], quality_state,
                        ontology_version, extractor_version, embedding_dimensions)
                   VALUES (?, ?, ?, ?, 'building', 'pending', ?, ?, ?);
                   COMMIT TRANSACTION;
               END TRY
               BEGIN CATCH
                   IF @@TRANCOUNT > 0 ROLLBACK TRANSACTION;
                   THROW;
               END CATCH""",
            (
                run_id, generation_id, as_user, store_id, category,
                llm_credential, embedding_credential, int(max_parallel), json_text(input_snapshot),
                generation_id, run_id, store_id, base_generation_id, ontology_version, extractor_version,
                int(embedding_dimensions),
            ),
        )

    def set_phase(self, run_id: str, phase: str | None) -> None:
        self.db.execute_non_query(
            "UPDATE nexus.index_run SET current_phase=?, updated_at=SYSUTCDATETIME() WHERE run_id=?",
            (phase, run_id),
        )

    def set_counts(self, run_id: str, generation_id: str, counts: dict[str, int]) -> None:
        values = (
            int(counts.get("documents", 0)), int(counts.get("blocks", 0)),
            int(counts.get("entities", 0)), int(counts.get("actions", 0)),
            int(counts.get("assertions", 0)), int(counts.get("graph_edges", 0)),
        )
        self.db.execute_non_query(
            """UPDATE nexus.index_run SET
                   document_count=?, block_count=?, entity_count=?, action_count=?,
                   assertion_count=?, graph_edge_count=?, updated_at=SYSUTCDATETIME()
               WHERE run_id=?""",
            values + (run_id,),
        )
        self.db.execute_non_query(
            """UPDATE nexus.index_generation SET
                   document_count=?, block_count=?, entity_count=?, action_count=?,
                   assertion_count=?, graph_edge_count=?
               WHERE generation_id=?""",
            values + (generation_id,),
        )

    def mark_terminal(self, run_id: str, generation_id: str, state: str) -> None:
        if state not in {"failed", "cancelled"}:
            return
        self.db.execute_non_query(
            """UPDATE nexus.index_generation
               SET [state]=?
               WHERE generation_id=? AND [state] IN ('building', 'validating')""",
            (state, generation_id),
        )

    def activate(
        self,
        store_id: str,
        generation_id: str,
        expected_base_generation_id: str | None = None,
    ) -> None:
        """Atomically publish a quality-passed generation and retire its predecessor."""
        self.db.execute_non_query(
            """BEGIN TRY
                   BEGIN TRANSACTION;

                   DECLARE @previous nvarchar(64);
                   SELECT @previous = active_generation_id
                   FROM nexus.search_store WITH (UPDLOCK, HOLDLOCK)
                   WHERE store_id = ?;

                   IF @@ROWCOUNT <> 1
                       THROW 51000, 'search store does not exist', 1;

                   IF NOT (
                       (@previous IS NULL AND ? IS NULL)
                       OR @previous=?
                   )
                       THROW 51003, 'active generation changed while candidate was building', 1;

                   IF NOT EXISTS (
                       SELECT 1 FROM nexus.index_generation WITH (UPDLOCK, HOLDLOCK)
                       WHERE generation_id=? AND store_id=?
                         AND quality_state='passed' AND [state]='validating'
                   )
                       THROW 51001, 'generation is not ready for activation', 1;

                   UPDATE nexus.index_generation
                   SET [state]='retired', retired_at=SYSUTCDATETIME()
                   WHERE generation_id=@previous AND [state]='active';

                   UPDATE nexus.index_generation
                   SET [state]='active', activated_at=SYSUTCDATETIME()
                   WHERE generation_id=?;

                   UPDATE nexus.search_store
                   SET active_generation_id=?, updated_at=SYSUTCDATETIME()
                   WHERE store_id=?;

                   UPDATE e
                   SET lifecycle_state='active', updated_at=SYSUTCDATETIME()
                   FROM nexus.entity e
                   WHERE e.lifecycle_state='candidate'
                     AND e.created_generation_id=?
                     AND (
                         EXISTS (
                             SELECT 1
                             FROM nexus.assertion_entity ae
                             JOIN nexus.legal_assertion la ON la.assertion_id=ae.assertion_id
                             WHERE ae.entity_id=e.entity_id AND la.generation_id=? AND la.[state]='accepted'
                         )
                         OR EXISTS (
                             SELECT 1
                             FROM nexus.action_participant ap
                             JOIN nexus.legal_assertion la ON la.action_id=ap.action_id
                             WHERE ap.entity_id=e.entity_id AND la.generation_id=? AND la.[state]='accepted'
                         )
                     );

                   UPDATE a
                   SET lifecycle_state='active', updated_at=SYSUTCDATETIME()
                   FROM nexus.action a
                   WHERE a.lifecycle_state='candidate'
                     AND a.created_generation_id=?
                     AND EXISTS (
                         SELECT 1 FROM nexus.legal_assertion la
                         WHERE la.action_id=a.action_id AND la.generation_id=? AND la.[state]='accepted'
                     );

                   UPDATE nexus.document_version
                   SET [state]='validated'
                   WHERE generation_id=? AND [state]='staged';

                   COMMIT TRANSACTION;
               END TRY
               BEGIN CATCH
                   IF @@TRANCOUNT > 0 ROLLBACK TRANSACTION;
                   THROW;
               END CATCH""",
            (
                store_id,
                expected_base_generation_id, expected_base_generation_id,
                generation_id, store_id,
                generation_id,
                generation_id, store_id,
                generation_id, generation_id, generation_id,
                generation_id, generation_id,
                generation_id,
            ),
        )
