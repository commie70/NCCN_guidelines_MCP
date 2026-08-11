"""NCCN Global discovery and selected-record download adapter."""

from __future__ import annotations

from contextlib import asynccontextmanager
from typing import AsyncIterator, Callable
from urllib.parse import urljoin

import httpx
from bs4 import BeautifulSoup

from ..models import DownloadedGuideline, GuidelineRecord
from ..routing import Credentials
from . import SourceError, persist_pdf, slug


class GlobalSource:
    BASE_URL = "https://www.nccn.org"
    CATEGORY_URLS = tuple(f"https://www.nccn.org/guidelines/category_{number}" for number in range(1, 5))

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

    @classmethod
    def parse_category(cls, html: str, category_url: str, system: str | None = None) -> list[GuidelineRecord]:
        soup = BeautifulSoup(html, "html.parser")
        records: list[GuidelineRecord] = []
        seen: set[str] = set()
        for link in soup.select("div.item-name a[href], a[href*='/guidelines-detail']"):
            title = link.get_text(" ", strip=True)
            href = link.get("href")
            if not title or not href or href in seen:
                continue
            seen.add(href)
            detail_url = urljoin(category_url, href)
            key = slug(title)
            records.append(
                GuidelineRecord(
                    record_id=f"global:{key}:en",
                    source="global",
                    guideline_key=key,
                    version_id=None,
                    title_en=title,
                    language="en",
                    guide_type="clinical",
                    system=system,
                    detail_url=detail_url,
                    license_required=True,
                    credentials_required=True,
                    availability="available",
                )
            )
        return records

    async def discover(self) -> list[GuidelineRecord]:
        records: dict[str, GuidelineRecord] = {}
        async with self._client() as client:
            for category_url in self.CATEGORY_URLS:
                try:
                    response = await client.get(category_url)
                    response.raise_for_status()
                except httpx.HTTPError as error:
                    raise SourceError("NCCN Global catalog refresh failed") from error
                system = BeautifulSoup(response.text, "html.parser").title
                category = system.get_text(" ", strip=True) if system else None
                for record in self.parse_category(response.text, category_url, category):
                    records.setdefault(record.record_id, record)
        return list(records.values())

    @staticmethod
    def _pdf_link(html: str, base_url: str) -> str | None:
        soup = BeautifulSoup(html, "html.parser")
        for link in soup.select("a[href]"):
            href = link.get("href", "")
            label = link.get_text(" ", strip=True).casefold()
            if href.casefold().split("?", 1)[0].endswith(".pdf") and ("nccn" in label or "guideline" in label or href):
                return urljoin(base_url, href)
        return None

    async def _login(self, client: httpx.AsyncClient, target_url: str) -> None:
        if not self.credentials.complete:
            if self.session_cookie:
                raise SourceError("NCCN Global session authentication was rejected")
            raise SourceError("NCCN Global credentials are required: " + ", ".join(self.credentials.missing))
        response = await client.get(target_url, follow_redirects=True)
        soup = BeautifulSoup(response.text, "html.parser")
        form = soup.find("form")
        if not form:
            raise SourceError("NCCN Global login page could not be validated")
        data = {input_.get("name"): input_.get("value", "") for input_ in form.select("input[type=hidden][name]")}
        data.update({"Username": self.credentials.username, "Password": self.credentials.password, "RememberMe": "false"})
        action = urljoin(str(response.url), form.get("action") or "/login/Index/")
        result = await client.post(action, data=data, headers={"Referer": str(response.url)}, follow_redirects=True)
        if result.status_code >= 400 or "/login" in str(result.url).casefold():
            raise SourceError("NCCN Global login failed")

    async def download(self, record: GuidelineRecord, data_dir) -> DownloadedGuideline:
        if record.source != "global":
            raise SourceError("record does not belong to NCCN Global")
        async with self._client() as client:
            target = record.detail_url
            if not target.casefold().split("?", 1)[0].endswith(".pdf"):
                try:
                    detail = await client.get(target)
                    detail.raise_for_status()
                except httpx.HTTPError as error:
                    raise SourceError("NCCN Global detail page could not be loaded") from error
                target = self._pdf_link(detail.text, str(detail.url)) or ""
            if not target:
                raise SourceError("NCCN Global PDF link was not found for this record")
            async with client.stream("GET", target, headers={"Accept": "application/pdf,*/*"}, follow_redirects=True) as response:
                if "pdf" not in response.headers.get("content-type", "").casefold():
                    await response.aread()
                    if "login" not in response.text.casefold():
                        raise SourceError("NCCN Global did not return a PDF")
                    await self._login(client, target)
                else:
                    return await persist_pdf(record, response, data_dir)
            async with client.stream("GET", target, headers={"Accept": "application/pdf,*/*"}, follow_redirects=True) as response:
                return await persist_pdf(record, response, data_dir)
