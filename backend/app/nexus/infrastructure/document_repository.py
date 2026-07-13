"""SQL repository for document snapshots and block manifests."""
from __future__ import annotations

from nexus.domain import Block, DocumentBundle

from .base import SqlRepository, json_text


class DocumentRepository(SqlRepository):
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
        for block_key in block_keys:
            self.db.execute_non_query(
                "UPDATE nexus.block_manifest SET search_state=? WHERE block_key=?",
                (state, block_key),
            )

    def manifest_written_count(self, generation_id: str) -> int:
        rows = self.db.execute_query(
            "SELECT COUNT_BIG(*) AS n FROM nexus.block_manifest WHERE generation_id=? AND search_state='written'",
            (generation_id,),
        )
        return int(rows[0]["n"] if rows else 0)
