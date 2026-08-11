"""The bounded public MCP surface for the nccn-guidelines plugin."""

from __future__ import annotations

from pathlib import Path
from typing import Literal

from mcp.server.fastmcp import FastMCP

from .catalog import CatalogStore
from .content import ContentError, ContentStore
from .models import GuidelineRecord
from .routing import RoutingError, Settings, select_source
from .sources import SourceError
from .sources.china_site import ChinaSource
from .sources.global_site import GlobalSource


class NCCNService:
    def __init__(self, settings: Settings | None = None) -> None:
        self.settings = settings or Settings.from_env()
        self.catalog = CatalogStore(self.settings.data_dir)
        self.content = ContentStore(self.settings.data_dir)
        self.sources = {
            "global": GlobalSource(self.settings.global_credentials, session_cookie=self.settings.global_session_cookie),
            "china": ChinaSource(self.settings.china_credentials, session_cookie=self.settings.china_session_cookie),
        }

    async def refresh(self, source: Literal["auto", "global", "china"] = "auto", force: bool = False) -> dict[str, object]:
        names = ("global", "china") if source == "auto" else (source,)
        result: dict[str, object] = {"sources": []}
        for name in names:
            previous = self.catalog.status(name)
            if not force and not previous["stale"]:
                result["sources"].append({**previous, "refreshed": False})
                continue
            try:
                records = await self.sources[name].discover()
                self.catalog.upsert(records)
                self.catalog.mark_refresh(name)
                result["sources"].append({**self.catalog.status(name), "refreshed": True, "records": len(records)})
            except SourceError as error:
                self.catalog.mark_refresh(name, str(error))
                # Stale data is deliberately still usable, but is labelled as such.
                result["sources"].append({**self.catalog.status(name), "refreshed": False, "error": str(error)})
        return result

    async def search(self, query: str, language: str, source: str, guide_type: str, limit: int) -> dict[str, object]:
        route = select_source(language, source, self.settings)
        status = self.catalog.status(route.source)
        refresh_error = None
        if status["stale"]:
            refreshed = await self.refresh(route.source)
            source_result = refreshed["sources"][0]
            refresh_error = source_result.get("error") if isinstance(source_result, dict) else None
            status = self.catalog.status(route.source)
        records = self.catalog.search(query, route.source, route.language, guide_type, limit)
        return {
            "query": query,
            "source": route.source,
            "language": route.language,
            "guide_type": guide_type,
            "records": [record.public_dict() for record in records],
            "stale": status["stale"],
            "last_success": status["last_success"],
            "refresh_error": refresh_error,
            "global_credentials_configured": route.global_configured,
        }

    def requirements(self, record_id: str) -> dict[str, object]:
        record = self._record(record_id)
        credentials = self.settings.global_credentials if record.source == "global" else self.settings.china_credentials
        configured = self.settings.authentication_configured(record.source)
        return {
            "record": record.public_dict(),
            "confirm_license_required": record.source == "china" and record.license_required,
            "credentials_configured": configured,
            "missing_environment_variables": credentials.missing if not configured else [],
            "notes": "China authorization is per record and does not apply to any other download." if record.source == "china" else "Global login is attempted only when the selected record requires it.",
        }

    async def download(self, record_id: str, confirm_license: bool) -> dict[str, object]:
        record = self._record(record_id)
        if record.source == "china" and not confirm_license:
            # This check happens before opening a detail page or posting a download log.
            raise SourceError("NCCN China download requires confirm_license=true for this exact record")
        downloader = self.sources[record.source]
        if record.source == "china":
            downloaded = await downloader.download(record, self.settings.data_dir, confirm_license=confirm_license)
        else:
            downloaded = await downloader.download(record, self.settings.data_dir)
        try:
            indexed = self.content.ingest_pdf(record, path=Path(downloaded.path), sha256=downloaded.sha256)
        except ContentError:
            indexed = {"record_id": record.record_id, "indexed": False, "diagnostic": "PDF was saved but could not be parsed"}
        return {**downloaded.public_dict(), "content": indexed}

    def _record(self, record_id: str) -> GuidelineRecord:
        record = self.catalog.get(record_id)
        if not record:
            raise ValueError("unknown record_id; call search_guidelines first")
        return record


service = NCCNService()
mcp = FastMCP("nccn-guidelines")


@mcp.tool()
async def search_guidelines(
    query: str,
    language: Literal["en", "zh", "paired"] = "en",
    source: Literal["auto", "global", "china"] = "auto",
    guide_type: Literal["clinical", "patient", "any"] = "clinical",
    limit: int = 8,
) -> dict[str, object]:
    """Search a bounded NCCN Global or China catalog and return stable record IDs."""
    try:
        return await service.search(query, language, source, guide_type, limit)
    except (RoutingError, ValueError, SourceError) as error:
        return {"error": str(error)}


@mcp.tool()
async def refresh_catalog(
    source: Literal["auto", "global", "china"] = "auto", force: bool = False
) -> dict[str, object]:
    """Refresh catalog metadata only; this tool never downloads a guideline PDF."""
    try:
        return await service.refresh(source, force)
    except (ValueError, SourceError) as error:
        return {"error": str(error)}


@mcp.tool()
async def get_download_requirements(record_id: str) -> dict[str, object]:
    """Show the selected record's source, version, license confirmation, and configuration requirements."""
    try:
        return service.requirements(record_id)
    except ValueError as error:
        return {"error": str(error)}


@mcp.tool()
async def download_guideline(record_id: str, confirm_license: bool = False) -> dict[str, object]:
    """Download one previously catalogued record; China requires per-record confirmation."""
    try:
        return await service.download(record_id, confirm_license)
    except (ValueError, SourceError) as error:
        return {"error": str(error)}


@mcp.tool()
async def search_content(record_id: str, query: str, top_k: int = 6, include_neighbors: int = 1) -> dict[str, object]:
    """Search one parsed PDF with bounded snippets; no whole-document text is returned."""
    try:
        return service.content.search(record_id, query, top_k, include_neighbors)
    except ContentError as error:
        return {"error": str(error)}


@mcp.tool()
async def extract_content(
    record_id: str,
    chunk_ids: list[str] | None = None,
    pages: list[int] | None = None,
    max_chars: int = 24_000,
    cursor: str | None = None,
) -> dict[str, object]:
    """Expand at most 12 chunks or 8 pages. A selector is required; whole PDFs are disabled."""
    try:
        return service.content.extract(record_id, chunk_ids, pages, max_chars, cursor)
    except ContentError as error:
        return {"error": str(error)}


@mcp.tool()
async def get_index() -> dict[str, object]:
    """Deprecated compatibility tool; use search_guidelines instead of a full catalog dump."""
    return {"deprecated": True, "message": "Use search_guidelines(query, language, source, guide_type, limit)."}


def main() -> None:
    mcp.run(transport="stdio")


if __name__ == "__main__":
    main()
