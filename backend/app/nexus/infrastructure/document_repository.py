"""SQL repository for document snapshots and block manifests."""
from __future__ import annotations

from nexus.domain import Block, DocumentBundle
from nexus.domain.documents import make_block_key, make_document_version_id

from .base import SqlRepository, json_text


class DocumentRepository(SqlRepository):
    def generation_document_summaries(
          self,
          generation_id: str,
          document_id: str | None = None,
     ) -> list[dict]:
          """Return one management row per document snapshot in a Generation."""
          where = "dv.generation_id=?"
          params: list[object] = [generation_id]
          if document_id:
                where += " AND dv.document_id=?"
                params.append(document_id)
          return self.db.execute_query(
                f"""SELECT dv.document_id,dv.document_version_id,dv.title,dv.category,
                              dv.source_uri,dv.content_hash,dv.block_count,dv.[state],
                              dv.raw_metadata,dv.created_at,
                              g.quality_state,g.activated_at,
                              (SELECT COUNT_BIG(*) FROM nexus.block_manifest bm
                                WHERE bm.document_version_id=dv.document_version_id) AS manifest_blocks,
                              (SELECT COUNT_BIG(*) FROM nexus.block_manifest bm
                                WHERE bm.document_version_id=dv.document_version_id
                                  AND bm.extraction_state='quarantined') AS quarantined_blocks,
                              (SELECT COUNT_BIG(*) FROM nexus.block_manifest bm
                                WHERE bm.document_version_id=dv.document_version_id
                                  AND bm.extraction_state='failed') AS failed_blocks,
                              (SELECT COUNT_BIG(*) FROM nexus.block_manifest bm
                                WHERE bm.document_version_id=dv.document_version_id
                                  AND bm.search_state<>'written') AS unwritten_blocks,
                              (SELECT COUNT_BIG(*) FROM nexus.entity_mention em
                                WHERE em.document_version_id=dv.document_version_id) AS entity_mentions,
                              (SELECT COUNT_BIG(*) FROM nexus.action_mention am
                                WHERE am.document_version_id=dv.document_version_id) AS action_mentions,
                              (SELECT COUNT_BIG(DISTINCT la.assertion_id)
                                FROM nexus.assertion_evidence ae
                                JOIN nexus.legal_assertion la ON la.assertion_id=ae.assertion_id
                                JOIN nexus.block_manifest bm ON bm.block_key=ae.block_key
                                WHERE la.generation_id=dv.generation_id
                                  AND bm.document_version_id=dv.document_version_id
                                  AND la.[state]='accepted') AS assertions,
                              (SELECT COUNT_BIG(*)
                                FROM nexus.assertion_evidence ae
                                JOIN nexus.legal_assertion la ON la.assertion_id=ae.assertion_id
                                JOIN nexus.block_manifest bm ON bm.block_key=ae.block_key
                                WHERE la.generation_id=dv.generation_id
                                  AND bm.document_version_id=dv.document_version_id) AS evidence_count,
                              (SELECT COUNT_BIG(DISTINCT gs.edge_id)
                                FROM nexus.graph_edge_support gs
                                JOIN nexus.graph_edge ge ON ge.edge_id=gs.edge_id
                                JOIN nexus.assertion_evidence ae ON ae.assertion_id=gs.assertion_id
                                JOIN nexus.block_manifest bm ON bm.block_key=ae.block_key
                                WHERE ge.generation_id=dv.generation_id
                                  AND bm.document_version_id=dv.document_version_id) AS graph_edges
                     FROM nexus.document_version dv
                     JOIN nexus.index_generation g ON g.generation_id=dv.generation_id
                     WHERE {where}
                     ORDER BY dv.category,dv.title,dv.document_id""",
                tuple(params),
          )

    def generation_quarantined_blocks(
                self,
                generation_id: str,
                document_id: str,
        ) -> list[dict]:
                """Return active quarantined Blocks with the audit that originally isolated them."""
                return self.db.execute_query(
                        """SELECT current_block.block_key,current_block.block_id,
                                            current_block.document_id,current_block.document_version_id,
                                            current_block.article_no,current_block.paragraph_no,
                                            current_block.item_no,current_block.heading_path,
                                            current_block.ordinal,current_block.search_state,
                                            audit.source_generation_id,audit.attempt_no,audit.attempt_state,
                                              audit.validation_errors,audit.raw_output,audit.cost_ms,
                                            (SELECT COUNT_BIG(*)
                                             FROM nexus.block_manifest history_block
                                             JOIN nexus.block_extraction_attempt history_attempt
                                                 ON history_attempt.generation_id=history_block.generation_id
                                                AND history_attempt.block_key=history_block.block_key
                                             WHERE history_block.block_id=current_block.block_id) AS attempt_count
                             FROM nexus.block_manifest current_block
                             OUTER APPLY (
                                     SELECT TOP 1 history_block.generation_id AS source_generation_id,
                                                                history_attempt.attempt_no,
                                                                history_attempt.[state] AS attempt_state,
                                                                history_attempt.validation_errors,
                                                                history_attempt.raw_output,
                                                                history_attempt.cost_ms,
                                                                history_generation.created_at
                                     FROM nexus.block_manifest history_block
                                     JOIN nexus.block_extraction_attempt history_attempt
                                         ON history_attempt.generation_id=history_block.generation_id
                                        AND history_attempt.block_key=history_block.block_key
                                     JOIN nexus.index_generation history_generation
                                         ON history_generation.generation_id=history_block.generation_id
                                     WHERE history_block.block_id=current_block.block_id
                                     ORDER BY
                                         CASE history_attempt.[state] WHEN 'quarantined' THEN 0 ELSE 1 END,
                                         history_generation.created_at DESC,
                                         history_attempt.attempt_no DESC
                             ) audit
                             WHERE current_block.generation_id=?
                                 AND current_block.document_id=?
                                 AND current_block.extraction_state='quarantined'
                             ORDER BY current_block.ordinal,current_block.block_key""",
                        (generation_id, document_id),
                )

    def generation_documents(self, generation_id: str | None) -> list[dict]:
        if not generation_id:
            return []
        return self.db.execute_query(
            """SELECT document_version_id,document_id,title,category,source_uri,
                      content_hash,block_count,[state],raw_metadata
               FROM nexus.document_version
               WHERE generation_id=?
               ORDER BY document_id""",
            (generation_id,),
        )

    def clone_documents(
        self,
        source_generation_id: str | None,
        target_generation_id: str,
        retained_document_ids: set[str],
    ) -> dict:
        """Clone unchanged manifests into an isolated candidate Generation.

        Block text and vectors live in AI Search and are copied separately.  Search state
        deliberately stays pending until that copy succeeds.
        """
        if not source_generation_id or not retained_document_ids:
            return {"versions": {}, "blocks": {}, "documents": 0, "block_count": 0}

        source_versions = [
            row for row in self.generation_documents(source_generation_id)
            if row["document_id"] in retained_document_ids
        ]
        found = {row["document_id"] for row in source_versions}
        missing = sorted(retained_document_ids - found)
        if missing:
            raise ValueError("retained documents are missing from the base Generation: " + ", ".join(missing))

        version_map = {
            row["document_version_id"]: make_document_version_id(
                target_generation_id, row["document_id"], row["content_hash"],
            )
            for row in source_versions
        }
        version_rows = [(
            version_map[row["document_version_id"]], target_generation_id,
            row["document_id"], row["title"], row["category"], row.get("source_uri"),
            row["content_hash"], int(row["block_count"]), row.get("raw_metadata"),
        ) for row in source_versions]
        self.db.execute_many(
            """INSERT INTO nexus.document_version
                   (document_version_id,generation_id,document_id,title,category,
                    source_uri,content_hash,block_count,[state],raw_metadata)
               VALUES (?,?,?,?,?,?,?,?,'staged',?)""",
            version_rows,
        )

        source_blocks = self.db.execute_query(
            """SELECT block_key,document_version_id,document_id,block_id,parent_block_id,
                      article_no,paragraph_no,item_no,heading_path,ordinal,text_hash,char_count,
                      extraction_state
               FROM nexus.block_manifest
               WHERE generation_id=?
               ORDER BY document_id,ordinal,block_key""",
            (source_generation_id,),
        )
        block_map: dict[str, dict] = {}
        block_rows: list[tuple] = []
        for row in source_blocks:
            if row["document_id"] not in retained_document_ids:
                continue
            target_version_id = version_map.get(row["document_version_id"])
            if target_version_id is None:
                raise ValueError(f"base block has no retained document version: {row['block_key']}")
            target_block_key = make_block_key(target_generation_id, row["block_id"])
            block_map[row["block_key"]] = {
                "source_block_key": row["block_key"],
                "target_block_key": target_block_key,
                "source_document_version_id": row["document_version_id"],
                "target_document_version_id": target_version_id,
                "document_id": row["document_id"],
                "block_id": row["block_id"],
                "ordinal": int(row["ordinal"]),
            }
            block_rows.append((
                target_block_key, target_generation_id, target_version_id,
                row["document_id"], row["block_id"], row.get("parent_block_id"),
                row.get("article_no"), row.get("paragraph_no"), row.get("item_no"),
                row.get("heading_path"), int(row["ordinal"]), row["text_hash"],
                int(row["char_count"]), row["extraction_state"],
            ))
        expected_blocks = sum(int(row["block_count"]) for row in source_versions)
        if len(block_rows) != expected_blocks:
            raise ValueError(
                f"base manifest is incomplete for retained documents: {len(block_rows)} != {expected_blocks}"
            )
        self.db.execute_many(
            """INSERT INTO nexus.block_manifest
                   (block_key,generation_id,document_version_id,document_id,block_id,
                    parent_block_id,article_no,paragraph_no,item_no,heading_path,
                    ordinal,text_hash,char_count,extraction_state,search_state)
               VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,'pending')""",
            block_rows,
        )
        return {
            "versions": version_map,
            "blocks": block_map,
            "documents": len(source_versions),
            "block_count": len(block_rows),
        }

    def save_bundle(self, bundle: DocumentBundle) -> None:
        doc = bundle.document
        version = bundle.version
        self.db.execute_non_query(
            """MERGE nexus.document AS t
               USING (SELECT ? AS document_id) AS s ON t.document_id=s.document_id
               WHEN MATCHED THEN UPDATE SET
                   canonical_title=?, category=?, source_uri=?, updated_at=SYSUTCDATETIME()
               WHEN NOT MATCHED THEN INSERT
                   (document_id, canonical_title, category, source_uri)
                   VALUES (?, ?, ?, ?);""",
            (
                doc.document_id, doc.canonical_title, doc.category, doc.source_uri,
                doc.document_id, doc.canonical_title, doc.category, doc.source_uri,
            ),
        )
        self.db.execute_non_query(
            """INSERT INTO nexus.document_version
                   (document_version_id, generation_id, document_id, title, category,
                    source_uri, content_hash, block_count, [state], raw_metadata)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, 'staged', ?)""",
            (
                version.document_version_id, version.generation_id, version.document_id,
                version.title, version.category, version.source_uri, version.content_hash,
                version.block_count, json_text(version.raw_metadata),
            ),
        )
        for block in bundle.blocks:
            self._insert_block(block)

    def _insert_block(self, block: Block) -> None:
        self.db.execute_non_query(
            """INSERT INTO nexus.block_manifest
                   (block_key, generation_id, document_version_id, document_id, block_id,
                    parent_block_id, article_no, paragraph_no, item_no, heading_path,
                    ordinal, text_hash, char_count, extraction_state, search_state)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 'pending', 'pending')""",
            (
                block.block_key, block.generation_id, block.document_version_id,
                block.document_id, block.block_id, block.parent_block_id,
                block.article_no, block.paragraph_no, block.item_no, block.heading_path,
                block.ordinal, block.text_hash, len(block.text),
            ),
        )

    def set_extraction_state(self, block_key: str, state: str) -> None:
        if state not in {"succeeded", "empty", "quarantined", "failed"}:
            raise ValueError(f"invalid extraction state: {state}")
        self.db.execute_non_query(
            "UPDATE nexus.block_manifest SET extraction_state=? WHERE block_key=?",
            (state, block_key),
        )

    def set_search_state(self, block_keys: list[str], state: str) -> None:
        if state not in {"written", "failed"}:
            raise ValueError(f"invalid search state: {state}")
        self.db.execute_many(
            "UPDATE nexus.block_manifest SET search_state=? WHERE block_key=?",
            [(state, block_key) for block_key in block_keys],
        )

    def manifest_written_count(self, generation_id: str) -> int:
        rows = self.db.execute_query(
            "SELECT COUNT_BIG(*) AS n FROM nexus.block_manifest WHERE generation_id=? AND search_state='written'",
            (generation_id,),
        )
        return int(rows[0]["n"] if rows else 0)
