from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from nccn_guidelines.catalog import CatalogStore
from nccn_guidelines.models import GuidelineRecord


class CatalogTests(unittest.TestCase):
    def test_verified_paired_records_remain_independent_versions(self) -> None:
        store = CatalogStore(Path(tempfile.mkdtemp()))
        records = [
            GuidelineRecord("china:1151:en", "china", "prostate-cancer", "1151", "Prostate Cancer", "en", version="2026.6", detail_url="https://example.test/1151", pairing_status="verified"),
            GuidelineRecord("china:1102:zh", "china", "prostate-cancer", "1102", "Prostate Cancer", "zh", title_zh="前列腺癌", version="2022.4", detail_url="https://example.test/1102", pairing_status="verified"),
            GuidelineRecord("china:9999:zh", "china", "lookalike", "9999", "Lookalike", "zh", title_zh="相似", version="2022.1", detail_url="https://example.test/9999"),
        ]
        store.upsert(records)
        paired = store.search("prostate", "china", "paired")
        self.assertEqual([record.record_id for record in paired], ["china:1151:en", "china:1102:zh"])
        self.assertNotEqual(paired[0].version, paired[1].version)

    def test_auto_pair_prefers_global_english_and_falls_back_to_china_english(self) -> None:
        store = CatalogStore(Path(tempfile.mkdtemp()))
        records = [
            GuidelineRecord("global:ovarian-cancer:en", "global", "ovarian-cancer", None, "Ovarian Cancer", "en"),
            GuidelineRecord("china:2001:en", "china", "ovarian-cancer", "2001", "Ovarian Cancer", "en", pairing_status="verified"),
            GuidelineRecord("china:2002:zh", "china", "ovarian-cancer", "2002", "Ovarian Cancer", "zh", title_zh="卵巢癌", pairing_status="verified"),
            GuidelineRecord("china:3001:en", "china", "cervical-cancer", "3001", "Cervical Cancer", "en", pairing_status="verified"),
            GuidelineRecord("china:3002:zh", "china", "cervical-cancer", "3002", "Cervical Cancer", "zh", title_zh="宫颈癌", pairing_status="verified"),
        ]
        store.upsert(records)

        ovarian = store.search_auto_paired("卵巢癌")
        self.assertEqual([record.record_id for record in ovarian], ["global:ovarian-cancer:en", "china:2002:zh"])
        cervical = store.search_auto_paired("cervical cancer")
        self.assertEqual([record.record_id for record in cervical], ["china:3001:en", "china:3002:zh"])
