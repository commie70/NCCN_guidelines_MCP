from __future__ import annotations

import json
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


class PluginManifestTests(unittest.TestCase):
    def test_codex_and_kimi_share_the_same_stdio_command(self) -> None:
        codex = json.loads((ROOT / ".codex-plugin" / "plugin.json").read_text())
        mcp = json.loads((ROOT / ".mcp.json").read_text())
        kimi = json.loads((ROOT / "kimi.plugin.json").read_text())
        self.assertEqual(codex["name"], "nccn-guidelines")
        self.assertEqual(codex["skills"], "./skills/")
        self.assertEqual(codex["mcpServers"], "./.mcp.json")
        self.assertEqual(mcp["nccn-guidelines"]["args"], ["run", "nccn-guidelines-mcp"])
        self.assertEqual(kimi["mcpServers"]["nccn-guidelines"]["args"], mcp["nccn-guidelines"]["args"])
        self.assertEqual(kimi["mcpServers"]["nccn-guidelines"]["cwd"], "./")

    def test_skill_exists(self) -> None:
        skill = ROOT / "skills" / "nccn-guidelines" / "SKILL.md"
        self.assertIn("name: nccn-guidelines", skill.read_text())
