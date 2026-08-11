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

# This table is deliberately explicit. Similar-looking titles never pair by normalization alone.
# China titles are mapped to the NCCN Global guideline_key so records pair across sources.
# Verified against both live catalogs on 2026-08-11. Ambiguous titles stay unmapped on purpose:
# "免疫治疗相关毒性的管理", "肝胆癌", "原发性皮肤淋巴瘤" (possible renamed or unmatched guides).
PAIRING_ALIASES = {
    "prostate cancer": "prostate-cancer",
    "前列腺癌": "prostate-cancer",
    "前列腺癌早期检测": "prostate-cancer-early-detection",
    "非小细胞肺癌": "non-small-cell-lung-cancer",
    "小细胞肺癌": "small-cell-lung-cancer",
    "肺癌筛查": "lung-cancer-screening",
    "乳腺癌": "breast-cancer",
    "乳腺癌筛查与诊断": "breast-cancer-screening-and-diagnosis",
    "降低乳腺癌风险": "breast-cancer-risk-reduction",
    "宫颈癌": "cervical-cancer",
    "宫颈癌-中国版": "cervical-cancer",
    "子宫肿瘤": "uterine-neoplasms",
    "子宫肿瘤-中国版": "uterine-neoplasms",
    "卵巢癌包括输卵管癌和原发性腹膜癌": "ovarian-cancer-fallopian-tube-cancer-primary-peritoneal-cancer",
    "卵巢癌-中国版": "ovarian-cancer-fallopian-tube-cancer-primary-peritoneal-cancer",
    "头颈部肿瘤": "head-and-neck-cancers",
    "头颈癌（鼻咽癌）-中国版": "head-and-neck-cancers",
    "阴道癌": "vaginal-cancer",
    "外阴癌": "vulvar-cancer",
    "妊娠滋养细胞肿瘤": "gestational-trophoblastic-neoplasia",
    "结肠癌": "colon-cancer",
    "直肠癌": "rectal-cancer",
    "结直肠癌筛查": "colorectal-cancer-screening",
    "肛门癌": "anal-carcinoma",
    "阑尾肿瘤和癌症": "appendiceal-neoplasms-and-cancers",
    "小肠腺癌": "small-bowel-adenocarcinoma",
    "胃癌": "gastric-cancer",
    "食管和食管胃交界部癌": "esophageal-and-esophagogastric-junction-cancers",
    "胃肠道间质瘤(GISTs)": "gastrointestinal-stromal-tumors",
    "胰腺癌": "pancreatic-adenocarcinoma",
    "肝细胞癌": "hepatocellular-carcinoma",
    "胆道癌": "biliary-tract-cancers",
    "壶腹腺癌": "ampullary-adenocarcinoma",
    "肾癌": "kidney-cancer",
    "膀胱癌": "bladder-cancer",
    "睾丸癌": "testicular-cancer",
    "阴茎癌": "penile-cancer",
    "甲状腺癌": "thyroid-carcinoma",
    "骨癌": "bone-cancer",
    "软组织肉瘤": "soft-tissue-sarcoma",
    "皮肤基底细胞癌": "basal-cell-skin-cancer",
    "皮肤鳞状细胞癌": "squamous-cell-skin-cancer",
    "皮肤黑色素瘤": "melanoma-cutaneous",
    "葡萄膜黑色素瘤": "melanoma-uveal",
    "皮肤淋巴瘤": "cutaneous-lymphomas",
    "Merkel细胞癌": "merkel-cell-carcinoma",
    "隆突性皮肤纤维肉瘤": "dermatofibrosarcoma-protuberans",
    "卡波西肉瘤": "kaposi-sarcoma",
    "中枢神经系统肿瘤": "central-nervous-system-cancers",
    "神经内分泌肿瘤和肾上腺瘤": "neuroendocrine-and-adrenal-tumors",
    "胸腺瘤和胸腺癌": "thymomas-and-thymic-carcinomas",
    "间皮瘤：胸膜": "mesothelioma-pleural",
    "间皮瘤：腹膜": "mesothelioma-peritoneal",
    "不明原发部位肿瘤": "occult-primary",
    "神经母细胞瘤": "neuroblastoma",
    "Wilms瘤（肾母细胞瘤）": "wilms-tumor-nephroblastoma",
    "霍奇金淋巴瘤": "hodgkin-lymphoma",
    "B细胞淋巴瘤": "b-cell-lymphomas",
    "T细胞淋巴瘤": "t-cell-lymphomas",
    "急性淋巴细胞白血病": "acute-lymphoblastic-leukemia",
    "急性髓性白血病": "acute-myeloid-leukemia",
    "慢性淋巴细胞白血病/小淋巴细胞淋巴瘤": "chronic-lymphocytic-leukemia-small-lymphocytic-lymphoma",
    "慢性髓性白血病": "chronic-myeloid-leukemia",
    "骨髓增生异常综合征": "myelodysplastic-syndromes",
    "骨髓增生性肿瘤": "myeloproliferative-neoplasms",
    "多发性骨髓瘤": "multiple-myeloma",
    "毛细胞白血病": "hairy-cell-leukemia",
    "伴有嗜酸性粒细胞和酪氨酸激酶融合基因的骨髓/淋巴肿瘤": "myeloid-lymphoid-neoplasms-with-eosinophilia-and-tyrosine-kinase-gene-fusions",
    "组织细胞瘤": "histiocytic-neoplasms",
    "Castleman病": "castleman-disease",
    "系统性肥大细胞增多症": "systemic-mastocytosis",
    "系统性轻链淀粉样变性": "systemic-light-chain-amyloidosis",
    "巨球蛋白血症/淋巴浆细胞性淋巴瘤": "waldenstr-m-macroglobulinemia-lymphoplasmacytic-lymphoma",
    "儿童急性淋巴细胞白血病": "pediatric-acute-lymphoblastic-leukemia",
    "儿童霍奇金淋巴瘤": "pediatric-hodgkin-lymphoma",
    "儿童中枢神经系统肿瘤": "pediatric-central-nervous-system-cancers",
    "儿童软组织肉瘤": "pediatric-soft-tissue-sarcoma",
    "儿童侵袭性成熟B细胞淋巴瘤": "pediatric-aggressive-mature-b-cell-lymphomas",
    "青少年和年轻成年人肿瘤": "adolescent-and-young-adult-aya-oncology",
    "老年肿瘤": "older-adult-oncology",
    "成人癌痛": "adult-cancer-pain",
    "止吐": "antiemesis",
    "戒烟": "smoking-cessation",
    "姑息治疗": "palliative-care",
    "癌症相关疲劳": "cancer-related-fatigue",
    "心理痛苦的处理": "distress-management",
    "生存指南": "survivorship",
    "癌症相关性静脉血栓栓塞性疾病": "cancer-associated-venous-thromboembolic-disease",
    "癌症相关感染的预防和治疗": "prevention-and-treatment-of-cancer-related-infections",
    "免疫检查点抑制剂相关毒性的管理": "management-of-immune-checkpoint-inhibitor-related-toxicities",
    "CAR-T细胞和淋巴细胞衔接器相关毒性的管理": "management-of-car-t-cell-and-lymphocyte-engager-related-toxicities",
    "造血生长因子": "hematopoietic-growth-factors",
    "造血细胞移植": "hematopoietic-cell-transplantation",
    "HIV感染者癌症": "cancer-in-people-with-hiv",
    "遗传/家族高风险评估-乳腺癌，卵巢癌，胰腺癌和前列腺癌": "genetic-familial-high-risk-assessment-breast-ovarian-pancreatic-and-prostate",
    "遗传/家族高风险评估-结直肠癌，子宫内膜癌，食管癌和胃癌": "genetic-familial-high-risk-assessment-colorectal-endometrial-esophageal-and-gastric",
}

# Lookups run on casefolded titles, so the table is keyed the same way.
_PAIRING_LOOKUP = {title.casefold(): key for title, key in PAIRING_ALIASES.items()}


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
                # Live cards carry a dedicated title block; falling back to the whole
                # card text would drag in the "英文版/版本" tags.
                title_node = card.select_one(".cardData-li-title")
                if title_node:
                    title = title_node.get_text(" ", strip=True)
            if not title:
                heading = card.find(["h1", "h2", "h3", "h4", "strong", "a"])
                title = heading.get_text(" ", strip=True) if heading else card_text
            language = node.get("data-language") or ""
            if not language:
                # Live cards tag the language explicitly ("中文版"/"英文版").
                language_tag = next(
                    (tag.get_text(strip=True) for tag in card.select(".li-tags") if re.search(r"中文版|英文版", tag.get_text())),
                    None,
                )
                language = "zh" if language_tag and "中文" in language_tag else ("en" if language_tag else cls._language(card_text))
            language = "zh" if str(language).casefold().startswith("zh") else "en"
            version_match = re.search(r"版本\s*(20\d{2}(?:\.\d+)*)", card_text) or re.search(r"\b20\d{2}(?:\.\d+)+\b", card_text)
            version = node.get("data-version") or (version_match.group(1) if version_match and version_match.lastindex else (version_match.group(0) if version_match else None))
            title_en = node.get("data-title-en") or (title if language == "en" else node.get("data-title-zh") or title)
            title_zh = node.get("data-title-zh") or (title if language == "zh" else None)
            mapped = _PAIRING_LOOKUP.get(title_en.casefold()) or (_PAIRING_LOOKUP.get(title_zh.casefold()) if title_zh else None)
            if mapped:
                key, status = mapped, "verified"
            elif re.search(r"[一-鿿]", title_en):
                # CJK titles slug to latin fragments ("b", "car-t"); keep keys stable and honest.
                key, status = f"china-guide-{version_id}", "unverified"
            else:
                key = slug(title_en)
                if key == "unknown-guideline":
                    key = f"china-guide-{version_id}"
                status = "unverified"
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
                    has_more = bool(
                        payload.get("has_more") or payload.get("hasMore") or payload.get("hasNext")
                        or data.get("has_more") or data.get("hasMore") or data.get("hasNext")
                    )
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
        # The detail page of a dual-tagged card offers only one language's PDF. Block a
        # mismatch instead of persisting the wrong-language file. Untagged names ("fixture-type",
        # legacy markup) carry no language signal and stay unguarded.
        offered = str(pdf_info.get("data-name") or "")
        offered_language = "zh" if "中文" in offered else ("en" if "英文" in offered else None)
        if offered_language and offered_language != record.language:
            raise SourceError("NCCN China detail language no longer matches the selected record")
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
                    # Surface the quota category when the site declares it; the message
                    # itself stays out of the error so no unexpected text leaks through.
                    message = str(payload.get("msg") or "")
                    if re.search(r"次数|上限|限制|quota|limit", message, re.I):
                        raise SourceError("NCCN China download quota was reached for this account")
                    raise SourceError("NCCN China download authorization was rejected")
                if isinstance(payload, dict):
                    issued_url = payload.get("download_url") or payload.get("url") or issued_url
            except (ValueError, AttributeError):
                pass
            if not issued_url:
                raise SourceError("NCCN China did not issue a download URL")
            async with client.stream("GET", issued_url, headers={"Accept": "application/pdf,*/*"}, follow_redirects=True) as response:
                return await persist_pdf(record, response, data_dir)
