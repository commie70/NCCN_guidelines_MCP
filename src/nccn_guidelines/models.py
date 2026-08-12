"""Small, serialisable domain records shared by MCP tools and sources."""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from typing import Any, Literal

Language = Literal["en", "zh"]
SourceName = Literal["global", "china"]


def now_iso() -> str:
    return datetime.now(timezone.utc).astimezone().isoformat(timespec="seconds")


@dataclass(slots=True)
class GuidelineRecord:
    """One downloadable, language-specific guideline version.

    ``download_url`` is intentionally runtime-only: China-issued download URLs
    are never written to the catalog database or returned by MCP tools.
    """

    record_id: str
    source: SourceName
    guideline_key: str
    version_id: str | None
    title_en: str
    language: Language
    guide_type: str = "clinical"
    system: str | None = None
    version: str | None = None
    detail_url: str = ""
    title_zh: str | None = None
    license_required: bool = True
    credentials_required: bool = True
    availability: str = "unknown"
    retrieved_at: str = field(default_factory=now_iso)
    pairing_status: str = "unverified"
    download_url: str | None = None

    def __post_init__(self) -> None:
        if self.source not in {"global", "china"}:
            raise ValueError("source must be global or china")
        if self.language not in {"en", "zh"}:
            raise ValueError("language must be en or zh")
        if not self.record_id or not self.guideline_key or not self.title_en:
            raise ValueError("record_id, guideline_key, and title_en are required")

    @property
    def title(self) -> str:
        return self.title_zh if self.language == "zh" and self.title_zh else self.title_en

    def public_dict(self) -> dict[str, Any]:
        data = asdict(self)
        data.pop("download_url", None)
        return data

    def db_dict(self) -> dict[str, Any]:
        return self.public_dict()

    @classmethod
    def from_dict(cls, value: dict[str, Any]) -> "GuidelineRecord":
        value = dict(value)
        value.pop("download_url", None)
        return cls(**value)


@dataclass(slots=True)
class DownloadedGuideline:
    record: GuidelineRecord
    path: str
    sha256: str
    bytes_written: int
    downloaded_at: str = field(default_factory=now_iso)

    def public_dict(self) -> dict[str, Any]:
        return {
            "record": self.record.public_dict(),
            "path": self.path,
            "sha256": self.sha256,
            "bytes": self.bytes_written,
            "downloaded_at": self.downloaded_at,
        }
