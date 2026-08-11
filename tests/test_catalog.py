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
