from __future__ import annotations

import tempfile
import unittest

from nccn_guidelines.models import GuidelineRecord
from nccn_guidelines.routing import Settings
from nccn_guidelines.server import NCCNService
from nccn_guidelines.sources import SourceError


class FailingSource:
    async def discover(self) -> list[GuidelineRecord]:
        raise SourceError("NCCN Global catalog refresh failed")


class ServerRoutingTests(unittest.IsolatedAsyncioTestCase):
    def service(self, fresh_sources: tuple[str, ...] = ("global", "china")) -> NCCNService:
        settings = Settings.from_env(
            {
                "NCCN_DATA_DIR": tempfile.mkdtemp(),
                "NCCN_GLOBAL_USERNAME": "u",
                "NCCN_GLOBAL_PASSWORD": "p",
            }
        )
        service = NCCNService(settings)
        for source in fresh_sources:
            service.catalog.mark_refresh(source)
        return service

    async def test_auto_english_falls_back_to_china_when_global_has_no_match(self) -> None:
        service = self.service()
        service.catalog.upsert(
            [GuidelineRecord("china:1:en", "china", "lung-cancer", "1", "Lung Cancer", "en")]
        )

        result = await service.search("lung", "en", "auto", "clinical", 8)

        self.assertEqual(result["source"], "china")
        self.assertTrue(result["fallback_used"])
        self.assertEqual(result["source_attempts"], ["global", "china"])

    async def test_auto_english_falls_back_after_global_refresh_failure(self) -> None:
        service = self.service(("china",))
        service.sources["global"] = FailingSource()
        service.catalog.upsert(
            [GuidelineRecord("china:1:en", "china", "lung-cancer", "1", "Lung Cancer", "en")]
        )

        result = await service.search("lung", "en", "auto", "clinical", 8)

        self.assertEqual(result["source"], "china")
        self.assertTrue(result["fallback_used"])
        self.assertEqual(result["refresh_errors"], {"global": "NCCN Global catalog refresh failed"})

    async def test_explicit_source_does_not_fall_back(self) -> None:
        service = self.service()
        service.catalog.upsert(
            [GuidelineRecord("china:1:en", "china", "lung-cancer", "1", "Lung Cancer", "en")]
        )

        result = await service.search("lung", "en", "global", "clinical", 8)

        self.assertEqual(result["records"], [])
        self.assertFalse(result["fallback_used"])
        self.assertEqual(result["source_attempts"], ["global"])

    async def test_auto_pair_uses_global_english_and_china_chinese(self) -> None:
        service = self.service()
        service.catalog.upsert(
            [
                GuidelineRecord("global:ovarian-cancer:en", "global", "ovarian-cancer", None, "Ovarian Cancer", "en"),
                GuidelineRecord("china:2:zh", "china", "ovarian-cancer", "2", "Ovarian Cancer", "zh", title_zh="卵巢癌", pairing_status="verified"),
            ]
        )

        result = await service.search("卵巢癌", "paired", "auto", "clinical", 8)

        self.assertEqual(result["source"], "global+china")
        self.assertFalse(result["fallback_used"])
        self.assertEqual(
            [record["record_id"] for record in result["records"]],
            ["global:ovarian-cancer:en", "china:2:zh"],
        )
