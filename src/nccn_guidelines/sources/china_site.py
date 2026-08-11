"""NCCN China catalog and single-record licensed download state machine."""

from __future__ import annotations

import base64
import json
import re
from contextlib import asynccontextmanager
from typing import AsyncIterator, Callable
from urllib.parse import urlencode, urljoin

import httpx
from bs4 import BeautifulSoup

from ..models import DownloadedGuideline, GuidelineRecord
from ..routing import Credentials
from . import SourceError, persist_pdf, slug

# This table is deliberately small and explicit. Similar-looking titles never pair by normalization alone.
PAIRING_ALIASES = {
    "prostate cancer": "prostate-cancer",
    "前列腺癌": "prostate-cancer",
}


class ChinaSource:
    BASE_URL = "https://nccnchina.org.cn"

    def __init__(
        self,
        credentials: Credentials,
        client_factory: Callable[[], httpx.AsyncClient] | None = None,
        session_cookie: str | None = None,
    ) -> None:
        self.credentials = credentials
        self.session_cookie = session_cookie
        self.client_factory = client_factory or self._default_client

    def _default_client(self) -> httpx.AsyncClient:
        headers = {"User-Agent": "nccn-guidelines/0.2 (+https://github.com/commie70/NCCN_guidelines_MCP)"}
        if self.session_cookie:
            headers["Cookie"] = self.session_cookie
        return httpx.AsyncClient(
            follow_redirects=True,
            timeout=30,
            headers=headers,
        )

    @asynccontextmanager
    async def _client(self) -> AsyncIterator[httpx.AsyncClient]:
        client = self.client_factory()
        try:
            yield client
        finally:
            await client.aclose()

    @staticmethod
    def _csrf(html: str) -> str | None:
        soup = BeautifulSoup(html, "html.parser")
        token = soup.select_one("meta[name=csrf-token], meta[name=_token], input[name=_token], input[name=csrf_token]")
        return token.get("content") or token.get("value") if token else None

    @staticmethod
    def _language(text: str) -> str:
        return "zh" if re.search(r"中文|简体|chinese|\bzh\b", text, re.I) else "en"

    @classmethod
    def parse_catalog_page(cls, html: str, base_url: str | None = None) -> list[GuidelineRecord]:
        base_url = base_url or cls.BASE_URL
        soup = BeautifulSoup(html, "html.parser")
        records: list[GuidelineRecord] = []
        seen: set[str] = set()
        for node in soup.select("[onclick*='guide_detail'], [data-version-id], [data-guide-id]"):
            raw = " ".join(filter(None, [node.get("onclick"), node.get("data-version-id"), node.get("data-guide-id")]))
            match = re.search(r"guide_detail\s*\(\s*['\"]?(\d+)|(?:version|guide)[_-]?id\D+(\d+)", raw, re.I)
            version_id = node.get("data-version-id") or node.get("data-guide-id") or (next((value for value in match.groups() if value), None) if match else None)
            if not version_id or version_id in seen:
                continue
            seen.add(version_id)
            card = node.find_parent(["article", "li", "div"]) or node
            card_text = card.get_text(" ", strip=True)
            title = node.get("data-title") or ""
            if not title:
                heading = card.find(["h1", "h2", "h3", "h4", "strong", "a"])
                title = heading.get_text(" ", strip=True) if heading else card_text
            language = node.get("data-language") or cls._language(card_text)
            language = "zh" if str(language).casefold().startswith("zh") else "en"
            version_match = re.search(r"\b20\d{2}(?:\.\d+)+\b", card_text)
            version = node.get("data-version") or (version_match.group(0) if version_match else None)
            title_en = node.get("data-title-en") or (title if language == "en" else node.get("data-title-zh") or title)
            title_zh = node.get("data-title-zh") or (title if language == "zh" else None)
            key = PAIRING_ALIASES.get(title_en.casefold()) or (PAIRING_ALIASES.get(title_zh) if title_zh else None) or slug(title_en)
            status = "verified" if (title_en.casefold() in PAIRING_ALIASES or (title_zh and title_zh in PAIRING_ALIASES)) else "unverified"
            records.append(
                GuidelineRecord(
                    record_id=f"china:{version_id}:{language}",
                    source="china",
                    guideline_key=key,
                    version_id=version_id,
                    title_en=title_en,
                    title_zh=title_zh,
                    language=language,
                    guide_type=node.get("data-guide-type") or "clinical",
                    system=node.get("data-system"),
                    version=version,
                    detail_url=urljoin(base_url, f"/guide/detail/{version_id}"),
                    license_required=True,
                    credentials_required=True,
                    availability="available",
                    pairing_status=status,
                )
            )
        return records

    async def discover(self) -> list[GuidelineRecord]:
        async with self._client() as client:
            try:
                index = await client.get(f"{self.BASE_URL}/guide/index")
                index.raise_for_status()
            except httpx.HTTPError as error:
                raise SourceError("NCCN China catalog refresh failed") from error
            token = self._csrf(index.text)
            headers = {"X-CSRF-TOKEN": token} if token else {}
            index_soup = BeautifulSoup(index.text, "html.parser")
            form = index_soup.select_one("form[action*='guide/more']") or index_soup.find("form")
            base_payload = {input_.get("name"): input_.get("value", "") for input_ in form.select("input[name]")} if form else {}
            records: dict[str, GuidelineRecord] = {}
            for page in range(1, 21):  # ponytail: low, bounded pagination; add server-declared total if the site exposes a stable one.
                try:
                    response = await client.post(f"{self.BASE_URL}/guide/more", data={**base_payload, "page": page}, headers=headers)
                    response.raise_for_status()
                except httpx.HTTPError as error:
                    raise SourceError("NCCN China catalog refresh failed") from error
                try:
                    payload = response.json()
                    data = payload.get("data") if isinstance(payload.get("data"), dict) else {}
                    html = payload.get("html") or data.get("html") or payload.get("data") or ""
                    has_more = bool(payload.get("has_more") or payload.get("hasMore") or data.get("has_more") or data.get("hasMore"))
                except (ValueError, AttributeError):
                    html, has_more = response.text, False
                page_records = self.parse_catalog_page(html)
                for record in page_records:
                    records[record.record_id] = record
                if not page_records or not has_more:
                    break
            return list(records.values())

    async def _login_if_required(self, client: httpx.AsyncClient, response: httpx.Response) -> None:
        text = response.text.casefold()
        if "login" not in str(response.url).casefold() and "login" not in text:
            return
        if not self.credentials.complete:
            if self.session_cookie:
                raise SourceError("NCCN China session authentication was rejected")
            raise SourceError("NCCN China credentials are required: " + ", ".join(self.credentials.missing))
        soup = BeautifulSoup(response.text, "html.parser")
        form = soup.find("form")
        scope = form or soup
        data = {input_.get("name"): input_.get("value", "") for input_ in scope.select("input[type=hidden][name]")}
        username = scope.select_one("input[type=email][name], input[name*=user i], input[name*=email i], input[name*=mobile i]")
        password = scope.select_one("input[type=password][name]")
        if not username or not password:
            raise SourceError("NCCN China login form could not be validated")
        data[username["name"]] = self.credentials.username
        data[password["name"]] = self.credentials.password
        action = form.get("action") if form else None
        if not action:
            # The live site currently renders its login controls outside a form and submits
            # to this declared XHR endpoint. Limit the fallback to its own login page.
            action_match = re.search(r"(?:url|action)\s*[:=]\s*['\"]([^'\"]*(?:login|signin)[^'\"]*)['\"]", response.text, re.I)
            action = action_match.group(1) if action_match else ("/user/login-do" if "/user/login" in str(response.url).casefold() else None)
        if not action:
            raise SourceError("NCCN China login endpoint could not be validated")
        if not form:
            # Password-mode XHR contract used by the current China login page.
            data.setdefault("login_type", "1")
            data.setdefault("is_agree", "1")
        csrf = self._csrf(response.text)
        headers = {"Referer": str(response.url)}
        if csrf:
            headers["X-CSRF-TOKEN"] = csrf
        result = await client.post(urljoin(str(response.url), action), data=data, headers=headers, follow_redirects=True)
        if result.status_code >= 400:
            raise SourceError("NCCN China login failed")
        try:
            payload = result.json()
        except ValueError:
            payload = None
        if isinstance(payload, dict) and isinstance(payload.get("success"), bool):
            if not payload["success"]:
                raise SourceError("NCCN China login failed")
            return
        if "login" in str(result.url).casefold():
            raise SourceError("NCCN China login failed")

    @staticmethod
    def _script_field(script: str, name: str) -> str | None:
        match = re.search(
            rf"['\"]?{re.escape(name)}['\"]?\s*:\s*(?:['\"]([^'\"]*)['\"]|(\d+))",
            script,
            re.I,
        )
        return next((value for value in match.groups() if value is not None), None) if match else None

    @classmethod
    def _browser_download_state(cls, record: GuidelineRecord, detail_html: str, detail_url: str) -> tuple[str, dict[str, str], str] | None:
        """Parse the current China UI contract without retaining its runtime URL/token."""

        soup = BeautifulSoup(detail_html, "html.parser")
        pdf_info = soup.select_one(".pdf_info[data-url][data-name][data-dname]")
        script = next((node.get_text("\n") for node in soup.select("script") if "download-log" in node.get_text()), None)
        if not pdf_info or not script:
            return None
        encoded_path = pdf_info.get("data-url")
        try:
            path = base64.b64decode(encoded_path or "", validate=True).decode("utf-8")
        except (UnicodeDecodeError, ValueError):
            raise SourceError("NCCN China browser download contract could not be validated") from None
        directory, separator, filename = path.rpartition("/")
        if not separator or not filename:
            raise SourceError("NCCN China browser download contract could not be validated")
        fields = {
            "gid": cls._script_field(script, "gid"),
            "verid": cls._script_field(script, "verid") or record.version_id,
            "pt": str(pdf_info.get("data-name") or ""),
            "vid": cls._script_field(script, "vid"),
            "_token": cls._script_field(script, "_token") or cls._csrf(detail_html),
        }
        if not all(fields.values()):
            raise SourceError("NCCN China browser download contract could not be validated")
        encoded_directory = base64.b64encode(f"{directory}/".encode("utf-8")).decode("ascii")
        download_url = urljoin(
            detail_url,
            "/guide/download?" + urlencode({"n": filename, "f": encoded_directory, "dn": str(pdf_info.get("data-dname"))}),
        )
        return urljoin(detail_url, "/guide/download-log"), {key: str(value) for key, value in fields.items()}, download_url

    @classmethod
    def _download_state(cls, record: GuidelineRecord, detail_html: str, detail_url: str) -> tuple[str, dict[str, str], str | None]:
        browser_state = cls._browser_download_state(record, detail_html, detail_url)
        if browser_state:
            return browser_state
        soup = BeautifulSoup(detail_html, "html.parser")
        form = soup.select_one("form[action*='download-log'], form[data-download-log-url]")
        if not form:
            raise SourceError("NCCN China license form could not be validated")
        log_url = form.get("data-download-log-url") if form else None
        log_url = log_url or (form.get("action") if form else "/guide/download-log")
        data = {input_.get("name"): input_.get("value", "") for input_ in form.select("input[name]")} if form else {}
        token = ChinaSource._csrf(detail_html)
        if token:
            data.setdefault("_token", token)
        candidate = soup.select_one("[data-download-url], a[href*='/guide/download']")
        return urljoin(detail_url, log_url), data, (urljoin(detail_url, candidate.get("data-download-url") or candidate.get("href")) if candidate else None)

    @staticmethod
    def _validate_detail(record: GuidelineRecord, detail_html: str) -> None:
        soup = BeautifulSoup(detail_html, "html.parser")
        marker = soup.select_one("[data-version], [data-language]")
        if not marker:
            return  # Current markup did not expose the field; the record is still checked by version_id in the log form.
        shown_version = marker.get("data-version")
        shown_language = marker.get("data-language")
        if shown_version and record.version and shown_version != record.version:
            raise SourceError("NCCN China detail version no longer matches the selected record")
        if shown_language and str(shown_language).casefold()[:2] != record.language:
            raise SourceError("NCCN China detail language no longer matches the selected record")

    async def download(self, record: GuidelineRecord, data_dir, confirm_license: bool) -> DownloadedGuideline:
        if record.source != "china":
            raise SourceError("record does not belong to NCCN China")
        if not confirm_license:
            raise SourceError("NCCN China download requires confirm_license=true for this exact record")
        async with self._client() as client:
            try:
                detail = await client.get(record.detail_url, follow_redirects=True)
                detail.raise_for_status()
                await self._login_if_required(client, detail)
                if "login" in str(detail.url).casefold():
                    detail = await client.get(record.detail_url, follow_redirects=True)
                    detail.raise_for_status()
            except httpx.HTTPError as error:
                raise SourceError("NCCN China detail page could not be loaded") from error
            self._validate_detail(record, detail.text)
            log_url, log_data, issued_url = self._download_state(record, detail.text, str(detail.url))
            selected_version = log_data.get("version_id") or log_data.get("verid")
            if record.version_id and selected_version and selected_version != record.version_id:
                raise SourceError("NCCN China license form no longer matches the selected record")
            if record.version_id:
                log_data.setdefault("verid" if "verid" in log_data else "version_id", record.version_id)
            # Exactly one audit-log attempt; no retry, even when a quota or server error occurs.
            try:
                headers = {"Referer": str(detail.url)}
                if log_data.get("_token"):
                    headers["X-CSRF-TOKEN"] = log_data["_token"]
                logged = await client.post(log_url, data=log_data, headers=headers)
            except httpx.HTTPError as error:
                raise SourceError("NCCN China download authorization failed") from error
            if logged.status_code < 200 or logged.status_code >= 300:
                raise SourceError("NCCN China download authorization was rejected")
            try:
                payload = logged.json()
                if isinstance(payload, dict) and payload.get("success") is False:
                    raise SourceError("NCCN China download authorization was rejected")
                if isinstance(payload, dict):
                    issued_url = payload.get("download_url") or payload.get("url") or issued_url
            except (ValueError, AttributeError):
                pass
            if not issued_url:
                raise SourceError("NCCN China did not issue a download URL")
            async with client.stream("GET", issued_url, headers={"Accept": "application/pdf,*/*"}, follow_redirects=True) as response:
                return await persist_pdf(record, response, data_dir)
