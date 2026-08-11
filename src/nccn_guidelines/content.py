"""Parse PDFs once, then serve bounded page-addressable evidence."""

from __future__ import annotations

import re
import sqlite3
from pathlib import Path
from typing import Iterable

from pypdf import PdfReader

from .models import GuidelineRecord, now_iso


class ContentError(ValueError):
    pass


class ContentStore:
    """SQLite FTS5 index with a deterministic bounded fallback."""

    def __init__(self, data_dir: Path) -> None:
        self.data_dir = data_dir
        self.data_dir.mkdir(parents=True, exist_ok=True, mode=0o700)
        self.path = data_dir / "content.sqlite3"
        self.fts_mode = "fallback"
        self._init_db()

    def _connect(self) -> sqlite3.Connection:
        db = sqlite3.connect(self.path)
        db.row_factory = sqlite3.Row
        return db

    def _init_db(self) -> None:
        with self._connect() as db:
            db.executescript(
                """
                CREATE TABLE IF NOT EXISTS documents (
                    record_id TEXT PRIMARY KEY,
                    path TEXT NOT NULL,
                    sha256 TEXT NOT NULL,
                    title TEXT NOT NULL,
                    source TEXT NOT NULL,
                    language TEXT NOT NULL,
                    version TEXT,
                    indexed_at TEXT NOT NULL,
                    ocr_required INTEGER NOT NULL DEFAULT 0
                );
                CREATE TABLE IF NOT EXISTS chunks (
                    chunk_id TEXT PRIMARY KEY,
                    record_id TEXT NOT NULL,
                    pdf_page INTEGER NOT NULL,
                    ordinal INTEGER NOT NULL,
                    text TEXT NOT NULL,
                    FOREIGN KEY(record_id) REFERENCES documents(record_id)
                );
                CREATE INDEX IF NOT EXISTS chunks_record_page ON chunks(record_id, pdf_page, ordinal);
                """
            )
            for mode in ("trigram", "unicode61"):
                try:
                    db.execute(
                        f"CREATE VIRTUAL TABLE IF NOT EXISTS chunks_fts USING fts5(chunk_id UNINDEXED, record_id UNINDEXED, text, tokenize='{mode}')"
                    )
                    self.fts_mode = mode
                    break
                except sqlite3.OperationalError:
                    continue

    @staticmethod
    def _chunks_for_page(text: str, target: int = 1800, overlap: int = 200) -> list[str]:
        text = re.sub(r"\r\n?", "\n", text).strip()
        if not text:
            return []
        result: list[str] = []
        start = 0
        while start < len(text):
            end = min(len(text), start + target)
            if end < len(text):
                boundary = max(text.rfind("\n", start + target // 2, end), text.rfind(" ", start + target // 2, end))
                if boundary > start:
                    end = boundary
            result.append(text[start:end].strip())
            if end >= len(text):
                break
            start = max(end - overlap, start + 1)
        return [chunk for chunk in result if chunk]

    def _replace_document(self, record: GuidelineRecord, path: Path, sha256: str, pages: Iterable[str], ocr_required: bool) -> dict[str, object]:
        page_chunks = [(page_number, chunk) for page_number, text in enumerate(pages, 1) for chunk in self._chunks_for_page(text)]
        with self._connect() as db:
            db.execute("DELETE FROM chunks_fts WHERE record_id = ?", (record.record_id,)) if self.fts_mode != "fallback" else None
            db.execute("DELETE FROM chunks WHERE record_id = ?", (record.record_id,))
            db.execute(
                """
                INSERT INTO documents(record_id, path, sha256, title, source, language, version, indexed_at, ocr_required)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(record_id) DO UPDATE SET path=excluded.path, sha256=excluded.sha256, title=excluded.title,
                    source=excluded.source, language=excluded.language, version=excluded.version,
                    indexed_at=excluded.indexed_at, ocr_required=excluded.ocr_required
                """,
                (record.record_id, str(path), sha256, record.title, record.source, record.language, record.version, now_iso(), int(ocr_required)),
            )
            per_page: dict[int, int] = {}
            rows = []
            for page, text in page_chunks:
                ordinal = per_page.get(page, 0) + 1
                per_page[page] = ordinal
                rows.append((f"{record.record_id}:p{page}:c{ordinal}", record.record_id, page, ordinal, text))
            db.executemany("INSERT INTO chunks(chunk_id, record_id, pdf_page, ordinal, text) VALUES (?, ?, ?, ?, ?)", rows)
            if self.fts_mode != "fallback":
                db.executemany("INSERT INTO chunks_fts(chunk_id, record_id, text) VALUES (?, ?, ?)", [(item[0], item[1], item[4]) for item in rows])
        return {"record_id": record.record_id, "chunks": len(page_chunks), "ocr_required": ocr_required, "fts": self.fts_mode}

    def ingest_pdf(self, record: GuidelineRecord, path: Path, sha256: str) -> dict[str, object]:
        try:
            reader = PdfReader(str(path))
        except Exception as error:  # pypdf error text may include a path; do not expose it to MCP callers.
            raise ContentError("PDF parsing failed") from error
        pages: list[str] = []
        for page in reader.pages:
            try:
                pages.append(page.extract_text(extraction_mode="layout") or page.extract_text() or "")
            except Exception:
                pages.append("")
        return self._replace_document(record, path, sha256, pages, not any(page.strip() for page in pages))

    def ingest_text_pages(self, record: GuidelineRecord, pages: Iterable[str], sha256: str = "test-sha") -> dict[str, object]:
        """Fixture seam: follows the same chunking/indexing path without a PDF."""
        return self._replace_document(record, Path("fixture.pdf"), sha256, pages, False)

    def _document(self, record_id: str) -> sqlite3.Row:
        with self._connect() as db:
            row = db.execute("SELECT * FROM documents WHERE record_id = ?", (record_id,)).fetchone()
        if not row:
            raise ContentError("guideline content is not downloaded; call download_guideline for this record first")
        return row

    @staticmethod
    def _snippet(text: str, terms: list[str]) -> str:
        if len(text) <= 1200:
            return text
        # Center the window on the first matched term so the evidence is visible
        # instead of sliced off by a head-only truncation.
        folded = text.casefold()
        positions = [position for term in terms if (position := folded.find(term)) >= 0]
        start = max(0, min(min(positions) - 200, len(text) - 1200)) if positions else 0
        return text[start : start + 1200]

    def search(self, record_id: str, query: str, top_k: int = 6, include_neighbors: int = 1) -> dict[str, object]:
        if not query.strip():
            raise ContentError("query is required")
        if not 1 <= int(top_k) <= 12:
            raise ContentError("top_k must be between 1 and 12")
        if not 0 <= int(include_neighbors) <= 2:
            raise ContentError("include_neighbors must be between 0 and 2")
        document = self._document(record_id)
        terms = [term for term in re.findall(r"[\w一-鿿-]+", query.casefold()) if len(term) > 1]
        with self._connect() as db:
            rows: list[sqlite3.Row] = []
            safe_query = " ".join(re.findall(r"[\w\u4e00-\u9fff-]+", query))
            if self.fts_mode != "fallback" and safe_query:
                try:
                    rows = db.execute(
                        """
                        SELECT c.* FROM chunks_fts f JOIN chunks c ON c.chunk_id = f.chunk_id
                        WHERE f.record_id = ? AND chunks_fts MATCH ? ORDER BY bm25(chunks_fts) LIMIT ?
                        """,
                        (record_id, safe_query, int(top_k)),
                    ).fetchall()
                except sqlite3.OperationalError:
                    rows = []
            if not rows:
                # Long natural-language queries rarely match as one string; degrade to
                # any-term substring matching so agents still get candidate chunks.
                rows = [
                    row
                    for row in db.execute("SELECT * FROM chunks WHERE record_id = ? ORDER BY pdf_page, ordinal", (record_id,)).fetchall()
                    if any(term in row["text"].casefold() for term in terms)
                ][: int(top_k)]
            selected: dict[str, sqlite3.Row] = {row["chunk_id"]: row for row in rows}
            for row in rows:
                if include_neighbors:
                    for neighbor in db.execute(
                        """
                        SELECT * FROM chunks WHERE record_id = ? AND pdf_page = ?
                        AND ordinal BETWEEN ? AND ?
                        """,
                        (record_id, row["pdf_page"], row["ordinal"] - int(include_neighbors), row["ordinal"] + int(include_neighbors)),
                    ):
                        selected.setdefault(neighbor["chunk_id"], neighbor)
        snippets = []
        remaining = 45_000
        for row in sorted(selected.values(), key=lambda item: (item["pdf_page"], item["ordinal"])):
            text = self._snippet(row["text"], terms)
            if len(text) > remaining:
                break
            snippets.append({"chunk_id": row["chunk_id"], "pdf_page": row["pdf_page"], "text": text})
            remaining -= len(text)
        return {
            "record_id": record_id,
            "title": document["title"],
            "source": document["source"],
            "language": document["language"],
            "version": document["version"],
            "sha256": document["sha256"],
            "snippets": snippets,
            "fts": self.fts_mode,
        }

    def extract(self, record_id: str, chunk_ids: list[str] | None = None, pages: list[int] | None = None, max_chars: int = 24_000, cursor: str | None = None) -> dict[str, object]:
        if not chunk_ids and not pages:
            raise ContentError("provide chunk_ids or pages; whole-document extraction is disabled")
        if max_chars < 1 or max_chars > 250_000:
            raise ContentError("max_chars must be between 1 and 250000")
        if chunk_ids and len(chunk_ids) > 120:
            raise ContentError("at most 120 chunk_ids may be requested")
        if pages and len(pages) > 80:
            raise ContentError("at most 80 pages may be requested")
        document = self._document(record_id)
        with self._connect() as db:
            if chunk_ids:
                placeholders = ",".join("?" for _ in chunk_ids)
                found = db.execute(
                    f"SELECT * FROM chunks WHERE record_id = ? AND chunk_id IN ({placeholders})", [record_id, *chunk_ids]
                ).fetchall()
                order = {chunk_id: index for index, chunk_id in enumerate(chunk_ids)}
                rows = sorted(found, key=lambda row: order[row["chunk_id"]])
            else:
                clean_pages = sorted({int(page) for page in pages or []})
                if not clean_pages or any(page < 1 for page in clean_pages):
                    raise ContentError("pages must contain positive PDF page numbers")
                placeholders = ",".join("?" for _ in clean_pages)
                rows = db.execute(
                    f"SELECT * FROM chunks WHERE record_id = ? AND pdf_page IN ({placeholders}) ORDER BY pdf_page, ordinal", [record_id, *clean_pages]
                ).fetchall()
        try:
            parts = (cursor or "0:0").split(":", 1)
            offset, character_offset = int(parts[0]), int(parts[1]) if len(parts) == 2 else 0
        except ValueError as error:
            raise ContentError("cursor is invalid") from error
        if offset < 0 or character_offset < 0:
            raise ContentError("cursor is invalid")
        selected = []
        used = 0
        index = offset
        next_cursor: str | None = None
        while index < len(rows):
            row = rows[index]
            text = row["text"][character_offset:]
            remaining_chars = max_chars - used
            if selected and len(text) > remaining_chars:
                next_cursor = f"{index}:{character_offset}"
                break
            if not text:
                index += 1
                character_offset = 0
                continue
            selected.append(
                {
                    "chunk_id": row["chunk_id"],
                    "pdf_page": row["pdf_page"],
                    "text": text[:remaining_chars],
                }
            )
            used += len(selected[-1]["text"])
            if len(selected[-1]["text"]) < len(text):
                next_cursor = f"{index}:{character_offset + len(selected[-1]['text'])}"
                break
            index += 1
            character_offset = 0
            if used >= max_chars:
                next_cursor = f"{index}:0" if index < len(rows) else None
                break
        if next_cursor is None and index < len(rows):
            next_cursor = f"{index}:0"
        return {
            "record_id": record_id,
            "title": document["title"],
            "source": document["source"],
            "language": document["language"],
            "version": document["version"],
            "sha256": document["sha256"],
            "chunks": selected,
            "truncated": next_cursor is not None,
            "next_cursor": next_cursor,
            "remaining": max(0, len(rows) - index),
        }
