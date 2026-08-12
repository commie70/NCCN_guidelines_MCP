"""SQLite-backed catalog with independent per-site refresh state."""

from __future__ import annotations

import json
import sqlite3
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Iterable

from .models import GuidelineRecord, now_iso


class CatalogStore:
    TTL = timedelta(hours=24)

    def __init__(self, data_dir: Path) -> None:
        self.data_dir = data_dir
        self.data_dir.mkdir(parents=True, exist_ok=True, mode=0o700)
        self.path = self.data_dir / "catalog.sqlite3"
        self._init_db()

    def _connect(self) -> sqlite3.Connection:
        connection = sqlite3.connect(self.path)
        connection.row_factory = sqlite3.Row
        return connection

    def _init_db(self) -> None:
        with self._connect() as db:
            db.executescript(
                """
                CREATE TABLE IF NOT EXISTS records (
                    record_id TEXT PRIMARY KEY,
                    source TEXT NOT NULL,
                    language TEXT NOT NULL,
                    guide_type TEXT NOT NULL,
                    guideline_key TEXT NOT NULL,
                    title TEXT NOT NULL,
                    retrieved_at TEXT NOT NULL,
                    record_json TEXT NOT NULL
                );
                CREATE INDEX IF NOT EXISTS records_lookup
                    ON records(source, language, guide_type, guideline_key);
                CREATE TABLE IF NOT EXISTS refresh_status (
                    source TEXT PRIMARY KEY,
                    last_success TEXT,
                    last_error TEXT
                );
                """
            )

    def upsert(self, records: Iterable[GuidelineRecord]) -> int:
        rows = list(records)
        with self._connect() as db:
            db.executemany(
                """
                INSERT INTO records(record_id, source, language, guide_type, guideline_key, title, retrieved_at, record_json)
                VALUES (:record_id, :source, :language, :guide_type, :guideline_key, :title, :retrieved_at, :record_json)
                ON CONFLICT(record_id) DO UPDATE SET
                  source=excluded.source, language=excluded.language, guide_type=excluded.guide_type,
                  guideline_key=excluded.guideline_key, title=excluded.title,
                  retrieved_at=excluded.retrieved_at, record_json=excluded.record_json
                """,
                [
                    {
                        "record_id": record.record_id,
                        "source": record.source,
                        "language": record.language,
                        "guide_type": record.guide_type,
                        "guideline_key": record.guideline_key,
                        "title": record.title,
                        "retrieved_at": record.retrieved_at,
                        "record_json": json.dumps(record.db_dict(), ensure_ascii=False, sort_keys=True),
                    }
                    for record in rows
                ],
            )
        return len(rows)

    def get(self, record_id: str) -> GuidelineRecord | None:
        with self._connect() as db:
            row = db.execute("SELECT record_json FROM records WHERE record_id = ?", (record_id,)).fetchone()
        return GuidelineRecord.from_dict(json.loads(row["record_json"])) if row else None

    def search(self, query: str, source: str, language: str, guide_type: str = "clinical", limit: int = 8) -> list[GuidelineRecord]:
        limit = max(1, min(int(limit), 20))
        text = f"%{query.casefold().strip()}%"
        with self._connect() as db:
            if language == "paired":
                rows = db.execute(
                    """
                    SELECT record_json FROM records
                    WHERE source = ? AND language IN ('en', 'zh') AND pairing_status = 'verified'
                    ORDER BY guideline_key, language, retrieved_at DESC
                    """.replace("pairing_status", "json_extract(record_json, '$.pairing_status')"),
                    (source,),
                ).fetchall()
                records = [GuidelineRecord.from_dict(json.loads(row["record_json"])) for row in rows]
                matched = [record for record in records if query.casefold().strip() in (record.title_en + " " + (record.title_zh or "")).casefold()]
                by_key: dict[str, dict[str, GuidelineRecord]] = {}
                for record in matched:
                    by_key.setdefault(record.guideline_key, {}).setdefault(record.language, record)
                result = [item for pair in by_key.values() if {"en", "zh"} <= set(pair) for item in (pair["en"], pair["zh"])]
                return result[:limit]
            params: list[object] = [source, language]
            clauses = ["source = ?", "language = ?"]
            if guide_type != "any":
                clauses.append("guide_type = ?")
                params.append(guide_type)
            clauses.append("lower(title) LIKE ?")
            params.extend([text, limit])
            rows = db.execute(
                f"SELECT record_json FROM records WHERE {' AND '.join(clauses)} ORDER BY retrieved_at DESC LIMIT ?", params
            ).fetchall()
        return [GuidelineRecord.from_dict(json.loads(row["record_json"])) for row in rows]

    def search_auto_paired(self, query: str, guide_type: str = "clinical", limit: int = 8) -> list[GuidelineRecord]:
        """Pair Global English with China Chinese, using China English as fallback."""

        limit = max(1, min(int(limit), 20))
        if limit < 2:
            return []
        clauses = ["source IN ('global', 'china')", "language IN ('en', 'zh')"]
        params: list[object] = []
        if guide_type != "any":
            clauses.append("guide_type = ?")
            params.append(guide_type)
        with self._connect() as db:
            rows = db.execute(
                f"SELECT record_json FROM records WHERE {' AND '.join(clauses)} ORDER BY retrieved_at DESC",
                params,
            ).fetchall()
        records = [GuidelineRecord.from_dict(json.loads(row["record_json"])) for row in rows]
        needle = query.casefold().strip().replace("-", " ")
        by_key: dict[str, dict[str, GuidelineRecord]] = {}
        matched_keys: set[str] = set()
        for record in records:
            if record.source == "china" and record.pairing_status != "verified":
                continue
            slot = "global_en" if record.source == "global" else f"china_{record.language}"
            by_key.setdefault(record.guideline_key, {}).setdefault(slot, record)
            haystack = " ".join(filter(None, (record.guideline_key.replace("-", " "), record.title_en, record.title_zh))).casefold()
            if needle in haystack:
                matched_keys.add(record.guideline_key)
        result: list[GuidelineRecord] = []
        for key in sorted(matched_keys):
            pair = by_key[key]
            english = pair.get("global_en") or pair.get("china_en")
            chinese = pair.get("china_zh")
            if english and chinese:
                result.extend((english, chinese))
            if len(result) + 2 > limit:
                break
        return result

    def mark_refresh(self, source: str, error: str | None = None) -> None:
        with self._connect() as db:
            if error:
                db.execute(
                    "INSERT INTO refresh_status(source, last_error) VALUES (?, ?) ON CONFLICT(source) DO UPDATE SET last_error=excluded.last_error",
                    (source, error[:500]),
                )
            else:
                db.execute(
                    "INSERT INTO refresh_status(source, last_success, last_error) VALUES (?, ?, NULL) ON CONFLICT(source) DO UPDATE SET last_success=excluded.last_success, last_error=NULL",
                    (source, now_iso()),
                )

    def status(self, source: str) -> dict[str, object]:
        with self._connect() as db:
            row = db.execute("SELECT last_success, last_error FROM refresh_status WHERE source = ?", (source,)).fetchone()
        last_success = row["last_success"] if row else None
        stale = True
        if last_success:
            try:
                parsed = datetime.fromisoformat(last_success).astimezone(timezone.utc)
                stale = datetime.now(timezone.utc) - parsed > self.TTL
            except ValueError:
                stale = True
        return {"source": source, "stale": stale, "last_success": last_success, "last_error": row["last_error"] if row else None}
