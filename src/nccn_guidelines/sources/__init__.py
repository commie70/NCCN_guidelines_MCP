"""Site adapters and private download persistence helpers."""

from __future__ import annotations

import hashlib
import json
import os
import re
import tempfile
from pathlib import Path
from typing import AsyncIterator

import httpx

from ..models import DownloadedGuideline, GuidelineRecord, now_iso


class SourceError(RuntimeError):
    """A safe error for MCP callers; never include response bodies or secrets."""


def slug(value: str) -> str:
    value = re.sub(r"[^a-z0-9]+", "-", value.casefold()).strip("-")
    return value or "unknown-guideline"


def safe_part(value: str | None, fallback: str) -> str:
    return slug(value or fallback)[:120]


async def persist_pdf(record: GuidelineRecord, response: httpx.Response, data_dir: Path) -> DownloadedGuideline:
    """Validate and atomically persist an already-authorized PDF response."""

    if response.status_code < 200 or response.status_code >= 300:
        raise SourceError("the guideline download was rejected")
    content_type = response.headers.get("content-type", "").casefold()
    if "pdf" not in content_type:
        raise SourceError("the download response was not a PDF")
    folder = data_dir / "downloads" / record.source / record.language / safe_part(record.guideline_key, "guideline") / safe_part(record.version, "unknown-version")
    folder.mkdir(parents=True, exist_ok=True, mode=0o700)
    fd, temp_name = tempfile.mkstemp(prefix=".partial-", suffix=".pdf", dir=folder)
    digest = hashlib.sha256()
    size = 0
    first = b""
    try:
        with os.fdopen(fd, "wb") as handle:
            async for block in response.aiter_bytes():
                if not first:
                    first = block[:8]
                digest.update(block)
                size += len(block)
                handle.write(block)
        if size == 0 or not first.startswith(b"%PDF-"):
            raise SourceError("the download response did not contain a valid PDF")
        path = folder / "guideline.pdf"
        os.replace(temp_name, path)
    except Exception:
        Path(temp_name).unlink(missing_ok=True)
        raise
    result = DownloadedGuideline(record, str(path), digest.hexdigest(), size)
    manifest = {
        "record_id": record.record_id,
        "source": record.source,
        "language": record.language,
        "version": record.version,
        "downloaded_at": result.downloaded_at,
        "detail_url": record.detail_url,
        "filename": path.name,
        "bytes": size,
        "sha256": result.sha256,
    }
    temp_manifest = folder / ".manifest.tmp"
    temp_manifest.write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    os.replace(temp_manifest, folder / "manifest.json")
    return result


async def streamed_get(client: httpx.AsyncClient, url: str, record: GuidelineRecord, data_dir: Path, headers: dict[str, str] | None = None) -> DownloadedGuideline:
    async with client.stream("GET", url, headers=headers, follow_redirects=True) as response:
        return await persist_pdf(record, response, data_dir)
