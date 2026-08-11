from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from nccn_guidelines.content import ContentError, ContentStore
from nccn_guidelines.models import GuidelineRecord


class ContentTests(unittest.TestCase):
    def setUp(self) -> None:
        self.store = ContentStore(Path(tempfile.mkdtemp()))
        self.record = GuidelineRecord(
            record_id="global:test:en", source="global", guideline_key="test", version_id=None,
            title_en="Test Guideline", language="en", version="2026.1", detail_url="https://example.test/test.pdf",
        )
        self.store.ingest_text_pages(
            self.record,
            ["immunotherapy " * 400, "chemotherapy " * 400],
            sha256="fixture-sha",
        )

    def test_search_and_extract_are_bounded(self) -> None:
        found = self.store.search(self.record.record_id, "immunotherapy", top_k=12, include_neighbors=1)
        self.assertTrue(found["snippets"])
        self.assertLessEqual(sum(len(item["text"]) for item in found["snippets"]), 18_000)
        self.assertTrue(all(len(item["text"]) <= 1200 for item in found["snippets"]))
        extracted = self.store.extract(self.record.record_id, pages=[1], max_chars=1000)
        self.assertLessEqual(sum(len(item["text"]) for item in extracted["chunks"]), 1000)
        self.assertTrue(extracted["truncated"])
        continued = self.store.extract(self.record.record_id, pages=[1], max_chars=1000, cursor=extracted["next_cursor"])
        self.assertTrue(continued["chunks"])
        self.assertNotEqual(extracted["chunks"][0]["text"], continued["chunks"][0]["text"])

    def test_search_falls_back_to_any_term_for_long_queries(self) -> None:
        found = self.store.search(self.record.record_id, "first-line immunotherapy extensive-stage", top_k=3)
        self.assertTrue(found["snippets"])

    def test_whole_document_and_over_limit_extracts_fail(self) -> None:
        with self.assertRaises(ContentError):
            self.store.extract(self.record.record_id)
        with self.assertRaises(ContentError):
            self.store.extract(self.record.record_id, pages=list(range(1, 10)))
        with self.assertRaises(ContentError):
            self.store.extract(self.record.record_id, pages=[1], max_chars=50_001)
