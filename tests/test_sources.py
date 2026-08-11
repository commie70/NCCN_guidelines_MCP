from __future__ import annotations

import asyncio
import tempfile
import unittest
from pathlib import Path
from urllib.parse import parse_qs

import httpx

from nccn_guidelines.models import GuidelineRecord
from nccn_guidelines.routing import Credentials
from nccn_guidelines.sources import SourceError
from nccn_guidelines.sources.china_site import ChinaSource
from nccn_guidelines.sources.global_site import GlobalSource


FIXTURES = Path(__file__).parent / "fixtures"


class SourceTests(unittest.TestCase):
    def test_fixture_catalog_parsers_keep_records_separate(self) -> None:
        global_records = GlobalSource.parse_category((FIXTURES / "global-category.html").read_text(), "https://www.nccn.org/guidelines/category_1")
        self.assertEqual(global_records[0].record_id, "global:prostate-cancer:en")
        china_records = ChinaSource.parse_catalog_page((FIXTURES / "china-catalog.html").read_text())
        self.assertEqual({record.record_id for record in china_records}, {"china:1151:en", "china:1102:zh"})
        self.assertTrue(all(record.pairing_status == "verified" for record in china_records))
        self.assertNotEqual(china_records[0].version, china_records[1].version)

    def test_current_global_category_links_are_discovered(self) -> None:
        records = GlobalSource.parse_category(
            (FIXTURES / "global-category-current.html").read_text(),
            "https://www.nccn.org/guidelines/category_1",
        )
        self.assertEqual([record.record_id for record in records], ["global:breast-cancer:en", "global:central-nervous-system-cancers:en"])
        self.assertEqual(records[0].detail_url, "https://www.nccn.org/guidelines/nccn-guidelines/guidelines-detail?category=1&id=1419")

    def test_current_global_detail_resolves_selected_pdf(self) -> None:
        def handler(request: httpx.Request) -> httpx.Response:
            if request.url.path == "/guidelines/nccn-guidelines/guidelines-detail":
                return httpx.Response(200, text=(FIXTURES / "global-detail-current.html").read_text())
            if request.url.path == "/professionals/physician_gls/pdf/breast.pdf":
                return httpx.Response(200, content=b"%PDF-1.7\nfixture", headers={"content-type": "application/pdf"})
            return httpx.Response(404)

        source = GlobalSource(
            Credentials(None, None, "NCCN_GLOBAL_USERNAME", "NCCN_GLOBAL_PASSWORD"),
            lambda: httpx.AsyncClient(transport=httpx.MockTransport(handler), follow_redirects=True),
        )
        record = GuidelineRecord(
            record_id="global:breast-cancer:en", source="global", guideline_key="breast-cancer", version_id=None,
            title_en="Breast Cancer", language="en", detail_url="https://www.nccn.org/guidelines/nccn-guidelines/guidelines-detail?category=1&id=1419",
        )

        async def run() -> None:
            downloaded = await source.download(record, Path(tempfile.mkdtemp()))
            self.assertTrue(Path(downloaded.path).is_file())

        asyncio.run(run())

    def test_global_detail_prefers_canonical_pdf_over_distractors(self) -> None:
        def handler(request: httpx.Request) -> httpx.Response:
            if request.url.path == "/guidelines/nccn-guidelines/guidelines-detail":
                return httpx.Response(200, text=(FIXTURES / "global-detail-distractors.html").read_text())
            if request.url.path == "/professionals/physician_gls/pdf/prostate.pdf":
                return httpx.Response(200, content=b"%PDF-1.7\ncanonical", headers={"content-type": "application/pdf"})
            if request.url.path.endswith(".pdf"):
                return httpx.Response(200, content=b"%PDF-1.7\ndistractor", headers={"content-type": "application/pdf"})
            return httpx.Response(404)

        source = GlobalSource(
            Credentials(None, None, "NCCN_GLOBAL_USERNAME", "NCCN_GLOBAL_PASSWORD"),
            lambda: httpx.AsyncClient(transport=httpx.MockTransport(handler), follow_redirects=True),
        )
        record = GuidelineRecord(
            record_id="global:prostate-cancer:en", source="global", guideline_key="prostate-cancer", version_id=None,
            title_en="Prostate Cancer", language="en", detail_url="https://www.nccn.org/guidelines/nccn-guidelines/guidelines-detail?category=1&id=1459",
        )

        async def run() -> None:
            downloaded = await source.download(record, Path(tempfile.mkdtemp()))
            self.assertEqual(Path(downloaded.path).read_bytes(), b"%PDF-1.7\ncanonical")

        asyncio.run(run())

    def test_china_discover_paginates_while_has_next(self) -> None:
        pages: list[int] = []
        cards = {
            1: '<div class="cardData-li" onclick="guide_detail(200)"><h3>Prostate Cancer</h3><span>2026.1</span></div>'
               '<div class="cardData-li" onclick="guide_detail(201)"><h3>前列腺癌</h3><span>2026.2</span></div>',
            2: '<div class="cardData-li" onclick="guide_detail(202)"><h3>Lung Cancer</h3><span>2026.3</span></div>',
        }

        def handler(request: httpx.Request) -> httpx.Response:
            if request.url.path == "/guide/index":
                return httpx.Response(200, text='<meta name="csrf-token" content="csrf-token">')
            if request.url.path == "/guide/more":
                page = int(parse_qs(request.content.decode())["page"][0])
                pages.append(page)
                has_next = page < 2
                return httpx.Response(200, json={"success": True, "msg": "ok", "html": cards[page], "hasNext": has_next, "dataSize": 1})
            return httpx.Response(404)

        source = ChinaSource(
            Credentials(None, None, "NCCN_CHINA_USERNAME", "NCCN_CHINA_PASSWORD"),
            lambda: httpx.AsyncClient(transport=httpx.MockTransport(handler)),
        )

        async def run() -> None:
            records = await source.discover()
            self.assertEqual(len(records), 3)

        asyncio.run(run())
        self.assertEqual(pages, [1, 2])

    def test_china_live_card_markup_parses_clean_fields(self) -> None:
        records = ChinaSource.parse_catalog_page((FIXTURES / "china-catalog-live.html").read_text())
        self.assertEqual(len(records), 2)
        nsclc, ovarian = records
        self.assertEqual(nsclc.record_id, "china:1158:en")
        self.assertEqual(nsclc.title, "非小细胞肺癌")
        self.assertEqual(nsclc.version, "2026.7")
        self.assertNotIn("英文版", nsclc.title)
        self.assertNotIn(nsclc.guideline_key, ("unknown-guideline", "2026-7"))
        self.assertEqual(ovarian.record_id, "china:1027:zh")
        self.assertEqual(ovarian.title, "卵巢癌-中国版")
        self.assertEqual(ovarian.version, "2025.3")

    def test_china_catalog_keys_align_with_global(self) -> None:
        records = {record.record_id: record for record in ChinaSource.parse_catalog_page((FIXTURES / "china-catalog-live.html").read_text())}
        nsclc = records["china:1158:en"]
        self.assertEqual(nsclc.guideline_key, "non-small-cell-lung-cancer")
        self.assertEqual(nsclc.pairing_status, "verified")
        ovarian = records["china:1027:zh"]
        self.assertEqual(ovarian.guideline_key, "ovarian-cancer-fallopian-tube-cancer-primary-peritoneal-cancer")
        self.assertEqual(ovarian.pairing_status, "verified")

    def test_china_catalog_alias_lookup_is_casefolded_and_cjk_titles_never_fragment_slug(self) -> None:
        html = """
        <div class="cardData-li" onclick="guide_detail(1118)">
         <div class="cardData-li-title"><div><span>B细胞淋巴瘤</span></div></div>
         <div class="li-tags fl">英文版</div><div class="li-tags fr">版本 2026.3</div>
        </div>
        <div class="cardData-li" onclick="guide_detail(1109)">
         <div class="cardData-li-title"><div><span>Castleman病</span></div></div>
         <div class="li-tags fl">英文版</div><div class="li-tags fr">版本 2025.1</div>
        </div>
        <div class="cardData-li" onclick="guide_detail(781)">
         <div class="cardData-li-title"><div><span>肝胆癌</span></div></div>
         <div class="li-tags fl">英文版</div><div class="li-tags fr">版本 2024.2</div>
        </div>
        """
        records = {record.record_id: record for record in ChinaSource.parse_catalog_page(html)}
        self.assertEqual(records["china:1118:en"].guideline_key, "b-cell-lymphomas")
        self.assertEqual(records["china:1118:en"].pairing_status, "verified")
        self.assertEqual(records["china:1109:en"].guideline_key, "castleman-disease")
        self.assertEqual(records["china:781:en"].guideline_key, "china-guide-781")
        self.assertEqual(records["china:781:en"].pairing_status, "unverified")

    def test_china_download_language_mismatch_blocks_download_log(self) -> None:
        calls = {"download_log": 0}
        detail_html = (FIXTURES / "china-detail-browser.html").read_text().replace("fixture-type", "中文版")

        def handler(request: httpx.Request) -> httpx.Response:
            if request.url.path == "/guide/detail/1151":
                return httpx.Response(200, text=detail_html)
            if request.url.path == "/guide/download-log":
                calls["download_log"] += 1
                return httpx.Response(200, json={"success": True})
            return httpx.Response(404)

        source = ChinaSource(
            Credentials(None, None, "NCCN_CHINA_USERNAME", "NCCN_CHINA_PASSWORD"),
            lambda: httpx.AsyncClient(transport=httpx.MockTransport(handler), follow_redirects=True),
            session_cookie="fixture-session",
        )
        record = GuidelineRecord(
            record_id="china:1151:en", source="china", guideline_key="prostate-cancer", version_id="1151",
            title_en="Prostate Cancer", language="en", version="2026.6", detail_url="https://nccnchina.org.cn/guide/detail/1151",
        )

        async def run() -> None:
            with self.assertRaises(SourceError) as error:
                await source.download(record, Path(tempfile.mkdtemp()), confirm_license=True)
            self.assertIn("language", str(error.exception))

        asyncio.run(run())
        self.assertEqual(calls["download_log"], 0)

    def test_china_download_language_match_passes(self) -> None:
        detail_html = (FIXTURES / "china-detail-browser.html").read_text().replace("fixture-type", "中文版")

        def handler(request: httpx.Request) -> httpx.Response:
            if request.url.path == "/guide/detail/1151":
                return httpx.Response(200, text=detail_html)
            if request.url.path == "/guide/download-log":
                return httpx.Response(200, json={"success": True})
            if request.url.path == "/guide/download":
                return httpx.Response(200, content=b"%PDF-1.7\nfixture", headers={"content-type": "application/pdf"})
            return httpx.Response(404)

        source = ChinaSource(
            Credentials(None, None, "NCCN_CHINA_USERNAME", "NCCN_CHINA_PASSWORD"),
            lambda: httpx.AsyncClient(transport=httpx.MockTransport(handler), follow_redirects=True),
            session_cookie="fixture-session",
        )
        record = GuidelineRecord(
            record_id="china:1102:zh", source="china", guideline_key="prostate-cancer", version_id="1151",
            title_en="Prostate Cancer", language="zh", title_zh="前列腺癌", version="2022.4", detail_url="https://nccnchina.org.cn/guide/detail/1151",
        )

        async def run() -> None:
            downloaded = await source.download(record, Path(tempfile.mkdtemp()), confirm_license=True)
            self.assertTrue(Path(downloaded.path).is_file())

        asyncio.run(run())

    def test_china_confirmation_blocks_download_log(self) -> None:
        calls = {"download_log": 0}

        def handler(request: httpx.Request) -> httpx.Response:
            if request.url.path == "/guide/detail/1151":
                return httpx.Response(200, text=(FIXTURES / "china-detail.html").read_text())
            if request.url.path == "/guide/download-log":
                calls["download_log"] += 1
                return httpx.Response(200, json={"url": "https://nccnchina.org.cn/guide/download/fixture.pdf"})
            if request.url.path == "/guide/download/fixture.pdf":
                return httpx.Response(200, content=b"%PDF-1.7\nfixture", headers={"content-type": "application/pdf"})
            return httpx.Response(404)

        source = ChinaSource(Credentials(None, None, "NCCN_CHINA_USERNAME", "NCCN_CHINA_PASSWORD"), lambda: httpx.AsyncClient(transport=httpx.MockTransport(handler)))
        record = GuidelineRecord(
            record_id="china:1151:en", source="china", guideline_key="prostate-cancer", version_id="1151",
            title_en="Prostate Cancer", language="en", version="2026.6", detail_url="https://nccnchina.org.cn/guide/detail/1151",
        )

        async def run() -> None:
            with self.assertRaises(SourceError):
                await source.download(record, Path(tempfile.mkdtemp()), confirm_license=False)
            self.assertEqual(calls["download_log"], 0)
            downloaded = await source.download(record, Path(tempfile.mkdtemp()), confirm_license=True)
            self.assertEqual(calls["download_log"], 1)
            self.assertTrue(Path(downloaded.path).is_file())
            self.assertEqual(downloaded.sha256, "f581fc87f30296eff11777c3ce1b9a8b7077071ad8abedfcba317fef0c807224")

        asyncio.run(run())

    def test_china_detail_mismatch_blocks_download_log(self) -> None:
        calls = {"download_log": 0}

        def handler(request: httpx.Request) -> httpx.Response:
            if request.url.path == "/guide/detail/1151":
                return httpx.Response(200, text=(FIXTURES / "china-detail.html").read_text().replace("2026.6", "2025.1"))
            if request.url.path == "/guide/download-log":
                calls["download_log"] += 1
                return httpx.Response(200)
            return httpx.Response(404)

        source = ChinaSource(Credentials(None, None, "NCCN_CHINA_USERNAME", "NCCN_CHINA_PASSWORD"), lambda: httpx.AsyncClient(transport=httpx.MockTransport(handler)))
        record = GuidelineRecord(
            record_id="china:1151:en", source="china", guideline_key="prostate-cancer", version_id="1151",
            title_en="Prostate Cancer", language="en", version="2026.6", detail_url="https://nccnchina.org.cn/guide/detail/1151",
        )

        async def run() -> None:
            with self.assertRaises(SourceError):
                await source.download(record, Path(tempfile.mkdtemp()), confirm_license=True)
            self.assertEqual(calls["download_log"], 0)

        asyncio.run(run())

    def test_china_download_log_quota_message_is_classified(self) -> None:
        def handler(request: httpx.Request) -> httpx.Response:
            if request.url.path == "/guide/detail/1151":
                return httpx.Response(200, text=(FIXTURES / "china-detail.html").read_text())
            if request.url.path == "/guide/download-log":
                return httpx.Response(200, json={"success": False, "msg": "今日下载次数已达上限"})
            return httpx.Response(404)

        source = ChinaSource(Credentials(None, None, "NCCN_CHINA_USERNAME", "NCCN_CHINA_PASSWORD"), lambda: httpx.AsyncClient(transport=httpx.MockTransport(handler)))
        record = GuidelineRecord(
            record_id="china:1151:en", source="china", guideline_key="prostate-cancer", version_id="1151",
            title_en="Prostate Cancer", language="en", version="2026.6", detail_url="https://nccnchina.org.cn/guide/detail/1151",
        )

        async def run() -> None:
            with self.assertRaises(SourceError) as caught:
                await source.download(record, Path(tempfile.mkdtemp()), confirm_license=True)
            self.assertIn("quota", str(caught.exception))

        asyncio.run(run())

    def test_china_download_log_quota_wording_variants_are_classified(self) -> None:
        # Live wording observed 2026-08-11: {"success":false,"msg":"已超出今日最高限额10篇"}
        def handler(request: httpx.Request) -> httpx.Response:
            if request.url.path == "/guide/detail/1151":
                return httpx.Response(200, text=(FIXTURES / "china-detail.html").read_text())
            if request.url.path == "/guide/download-log":
                return httpx.Response(200, json={"success": False, "msg": "已超出今日最高限额10篇"})
            return httpx.Response(404)

        source = ChinaSource(Credentials(None, None, "NCCN_CHINA_USERNAME", "NCCN_CHINA_PASSWORD"), lambda: httpx.AsyncClient(transport=httpx.MockTransport(handler)))
        record = GuidelineRecord(
            record_id="china:1151:en", source="china", guideline_key="prostate-cancer", version_id="1151",
            title_en="Prostate Cancer", language="en", version="2026.6", detail_url="https://nccnchina.org.cn/guide/detail/1151",
        )

        async def run() -> None:
            with self.assertRaises(SourceError) as caught:
                await source.download(record, Path(tempfile.mkdtemp()), confirm_license=True)
            self.assertIn("quota", str(caught.exception))

        asyncio.run(run())

    def test_china_js_login_posts_declared_password_contract(self) -> None:
        state = {"logged_in": False, "download_log": 0}
        captured: dict[str, object] = {}
        login_page = """
        <meta name="csrf-token" content="csrf-token">
        <input type="hidden" name="check_type" value="password">
        <input type="hidden" name="redirect_url" value="/guide/detail/1151">
        <input name="mobile"><input name="password" type="password">
        <script>$.ajax({url: '/user/login-do', type: 'POST'});</script>
        """

        def handler(request: httpx.Request) -> httpx.Response:
            if request.url.path == "/guide/detail/1151":
                if state["logged_in"]:
                    return httpx.Response(200, text=(FIXTURES / "china-detail.html").read_text())
                return httpx.Response(302, headers={"location": "/user/login"})
            if request.url.path == "/user/login":
                return httpx.Response(200, text=login_page)
            if request.url.path == "/user/login-do":
                captured["data"] = parse_qs(request.content.decode())
                captured["csrf"] = request.headers.get("x-csrf-token")
                state["logged_in"] = True
                return httpx.Response(200, json={"success": True, "msg": "ok"})
            if request.url.path == "/guide/download-log":
                state["download_log"] += 1
                return httpx.Response(200, json={"url": "https://nccnchina.org.cn/guide/download/fixture.pdf"})
            if request.url.path == "/guide/download/fixture.pdf":
                return httpx.Response(200, content=b"%PDF-1.7\nfixture", headers={"content-type": "application/pdf"})
            return httpx.Response(404)

        source = ChinaSource(
            Credentials("account@example.test", "test-password", "NCCN_CHINA_USERNAME", "NCCN_CHINA_PASSWORD"),
            lambda: httpx.AsyncClient(transport=httpx.MockTransport(handler), follow_redirects=True),
        )
        record = GuidelineRecord(
            record_id="china:1151:en", source="china", guideline_key="prostate-cancer", version_id="1151",
            title_en="Prostate Cancer", language="en", version="2026.6", detail_url="https://nccnchina.org.cn/guide/detail/1151",
        )

        async def run() -> None:
            await source.download(record, Path(tempfile.mkdtemp()), confirm_license=True)

        asyncio.run(run())
        self.assertEqual(captured["csrf"], "csrf-token")
        self.assertEqual(
            captured["data"],
            {
                "check_type": ["password"], "redirect_url": ["/guide/detail/1151"],
                "mobile": ["account@example.test"], "password": ["test-password"],
                "login_type": ["1"], "is_agree": ["1"],
            },
        )
        self.assertEqual(state["download_log"], 1)

    def test_china_browser_download_contract_posts_once_and_builds_pdf_url(self) -> None:
        calls = {"download_log": 0, "download": 0}

        def handler(request: httpx.Request) -> httpx.Response:
            if request.url.path == "/guide/detail/1151":
                return httpx.Response(200, text=(FIXTURES / "china-detail-browser.html").read_text())
            if request.url.path == "/guide/download-log":
                calls["download_log"] += 1
                self.assertEqual(parse_qs(request.content.decode()), {
                    "gid": ["1"], "verid": ["1151"], "pt": ["fixture-type"], "vid": ["77"], "_token": ["fixture-csrf-token"],
                })
                self.assertEqual(request.headers.get("x-csrf-token"), "fixture-csrf-token")
                return httpx.Response(200, json={"success": True})
            if request.url.path == "/guide/download":
                calls["download"] += 1
                query = dict(request.url.params)
                self.assertEqual(query["n"], "fixture.pdf")
                self.assertEqual(query["dn"], "fixture-display-name")
                self.assertEqual(query["f"], "L3Byb3RlY3RlZC8=")
                return httpx.Response(200, content=b"%PDF-1.7\nfixture", headers={"content-type": "application/pdf"})
            return httpx.Response(404)

        source = ChinaSource(
            Credentials(None, None, "NCCN_CHINA_USERNAME", "NCCN_CHINA_PASSWORD"),
            lambda: httpx.AsyncClient(transport=httpx.MockTransport(handler), follow_redirects=True),
            session_cookie="fixture-session",
        )
        record = GuidelineRecord(
            record_id="china:1151:en", source="china", guideline_key="prostate-cancer", version_id="1151",
            title_en="Prostate Cancer", language="en", version="2026.6", detail_url="https://nccnchina.org.cn/guide/detail/1151",
        )

        async def run() -> None:
            downloaded = await source.download(record, Path(tempfile.mkdtemp()), confirm_license=True)
            self.assertTrue(Path(downloaded.path).is_file())

        asyncio.run(run())
        self.assertEqual(calls, {"download_log": 1, "download": 1})
