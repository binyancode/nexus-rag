"""SQL repository for document snapshots and block manifests."""
from __future__ import annotations

from nexus.domain import Block, DocumentBundle
from nexus.domain.documents import make_block_key, make_document_version_id

from .base import SqlRepository, json_text


class DocumentRepository(SqlRepository):
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
