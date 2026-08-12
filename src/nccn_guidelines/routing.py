"""Credential loading and the routing contract shared by all entry points."""

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path
from typing import Literal

LanguageRequest = Literal["en", "zh", "paired"]
SourceRequest = Literal["auto", "global", "china"]


class RoutingError(ValueError):
    pass


@dataclass(frozen=True, slots=True)
class Credentials:
    username: str | None
    password: str | None
    username_var: str
    password_var: str

    @property
    def complete(self) -> bool:
        return bool(self.username and self.password)

    @property
    def missing(self) -> list[str]:
        return [name for value, name in ((self.username, self.username_var), (self.password, self.password_var)) if not value]


@dataclass(frozen=True, slots=True)
class Settings:
    global_credentials: Credentials
    china_credentials: Credentials
    data_dir: Path
    global_alias_used: bool = False
    global_session_cookie: str | None = None
    china_session_cookie: str | None = None

    @classmethod
    def from_env(cls, environ: dict[str, str] | None = None) -> "Settings":
        env = os.environ if environ is None else environ
        # New names win even when incomplete; this prevents surprising secret mixing.
        new_global_present = "NCCN_GLOBAL_USERNAME" in env or "NCCN_GLOBAL_PASSWORD" in env
        global_creds = Credentials(
            env.get("NCCN_GLOBAL_USERNAME") if new_global_present else env.get("NCCN_USERNAME"),
            env.get("NCCN_GLOBAL_PASSWORD") if new_global_present else env.get("NCCN_PASSWORD"),
            "NCCN_GLOBAL_USERNAME",
            "NCCN_GLOBAL_PASSWORD",
        )
        china_creds = Credentials(
            env.get("NCCN_CHINA_USERNAME"),
            env.get("NCCN_CHINA_PASSWORD"),
            "NCCN_CHINA_USERNAME",
            "NCCN_CHINA_PASSWORD",
        )
        root = Path(env.get("NCCN_DATA_DIR", Path.home() / ".nccn-guidelines")).expanduser()
        return cls(
            global_credentials=global_creds,
            china_credentials=china_creds,
            data_dir=root,
            global_alias_used=not new_global_present and bool(env.get("NCCN_USERNAME") or env.get("NCCN_PASSWORD")),
            global_session_cookie=env.get("NCCN_GLOBAL_SESSION_COOKIE") or None,
            china_session_cookie=env.get("NCCN_CHINA_SESSION_COOKIE") or None,
        )

    def authentication_configured(self, source: Literal["global", "china"]) -> bool:
        if source == "global":
            return self.global_credentials.complete or bool(self.global_session_cookie)
        return self.china_credentials.complete or bool(self.china_session_cookie)


@dataclass(frozen=True, slots=True)
class Route:
    source: Literal["global", "china"]
    language: LanguageRequest
    global_configured: bool
    fallback_source: Literal["global", "china"] | None = None


def select_source(language: LanguageRequest = "en", source: SourceRequest = "auto", settings: Settings | None = None) -> Route:
    """Select the primary catalog and the transparent auto-mode fallback."""

    if language not in {"en", "zh", "paired"}:
        raise RoutingError("language must be en, zh, or paired")
    if source not in {"auto", "global", "china"}:
        raise RoutingError("source must be auto, global, or china")
    configured = (settings or Settings.from_env()).authentication_configured("global")
    if source == "global":
        if language in {"zh", "paired"}:
            raise RoutingError("source=global only supports language=en")
        return Route("global", language, configured)
    if source == "china":
        return Route("china", language, configured)
    if language in {"zh", "paired"}:
        return Route("china", language, configured, "global")
    primary = "global" if configured else "china"
    return Route(primary, language, configured, "china" if primary == "global" else "global")
