from __future__ import annotations

import json
import re
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SKILL = ROOT / "skills" / "nccn-guidelines" / "SKILL.md"
PROMPTS = SKILL.parent / "test-prompts.json"


class SkillContractTests(unittest.TestCase):
    def test_skill_keeps_execution_safety_contract(self) -> None:
        text = SKILL.read_text()
        self.assertLessEqual(len(text.encode()), 1599)
        for required in (
            "search_guidelines",
            "download_guideline",
            "search_content",
            "extract_content",
            "record_id",
            "Failure handling:",
            "🔴 CHECKPOINT · STOP",
            "Blacklist:",
        ):
            self.assertIn(required, text)
        runtime_drift = re.compile(
            r"在 Claude Code|Claude Code skill|Claude Code 用户|Cursor only|Codex 中|/\.claude/skills/[a-z]|/plugin install\b"
        )
        self.assertIsNone(runtime_drift.search(text))

    def test_confirmed_prompts_are_three_bounded_cases(self) -> None:
        prompts = json.loads(PROMPTS.read_text())
        self.assertEqual([item["id"] for item in prompts], [1, 2, 3])
        self.assertTrue(all(item["prompt"] and item["expected"] for item in prompts))


if __name__ == "__main__":
    unittest.main()
