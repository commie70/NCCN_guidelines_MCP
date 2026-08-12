from __future__ import annotations

import asyncio
import tempfile
import unittest
from pathlib import Path

from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client


ROOT = Path(__file__).resolve().parents[1]


class MCPProcessSmokeTests(unittest.TestCase):
    def test_stdio_server_lists_bounded_tools(self) -> None:
        async def run() -> list[str]:
            parameters = StdioServerParameters(
                command="uv",
                args=["run", "nccn-guidelines-mcp"],
                cwd=str(ROOT),
                env={"NCCN_DATA_DIR": tempfile.mkdtemp()},
            )
            async with stdio_client(parameters) as (reader, writer):
                async with ClientSession(reader, writer) as session:
                    await session.initialize()
                    return [tool.name for tool in (await session.list_tools()).tools]

        names = asyncio.run(run())
        self.assertEqual(
            set(names),
            {
                "search_guidelines",
                "refresh_catalog",
                "get_download_requirements",
                "download_guideline",
                "search_content",
                "extract_content",
                "get_index",
            },
        )
