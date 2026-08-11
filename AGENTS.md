# NCCN Guidelines MCP

## Project

This repository provides a bounded NCCN Global/China MCP plugin with a shared
`nccn-guidelines` Skill, source-aware catalog records, consent-gated downloads,
and page/chunk-bounded PDF evidence retrieval.

## Run and verify

- Install: `uv sync`
- Start stdio MCP: `uv run nccn-guidelines-mcp`
- Tests: `uv run --offline python -m unittest discover -s tests -p 'test_*.py'`
- Build: `uv build --offline`

## Layout and contracts

- Runtime code is under `src/nccn_guidelines/`; manifests are `.codex-plugin/`,
  `.mcp.json`, and `kimi.plugin.json`.
- The agent workflow is `skills/nccn-guidelines/SKILL.md`; its test cases are
  `skills/nccn-guidelines/test-prompts.json`.
- Preserve opaque `record_id` values returned by `search_guidelines`.
- Search content before extraction; never request whole-document extraction.
- China downloads are one-record, explicit-consent operations with
  `confirm_license=true`; do not bulk probe, retry `download-log`, or silently
  switch sources.
- Credentials and session cookies are environment-only. Never put values in
  prompts, tools, logs, screenshots, tests, or repository files.

## Code map (CodeGraph)

This repo is indexed by CodeGraph (`.codegraph/` exists, git-ignored). Prefer
`codegraph explore "<question>"` / `codegraph node <symbol-or-file>` over
grep/read when locating or understanding code; re-run `codegraph sync` after
large edits.

Structure (16 files, 271 nodes):

- `server.py` — MCP tool registration (`search_guidelines`, `download_guideline`,
  `search_content`, `extract_content`, …); entry `nccn-guidelines-mcp`.
- `routing.py` — source auto-selection (Global vs China) and record routing.
- `catalog.py` — catalog store for `search_guidelines` records.
- `content.py` — page/chunk-bounded PDF evidence (`search_content` snippets
  ≤1,200 chars each, ≤45,000 total, centered on the matched term;
  `extract_content` ≤120 chunks/80 pages/250,000 chars per call).
- `models.py` — `GuidelineRecord`, `DownloadedGuideline` data contracts.
- `sources/global_site.py` — NCCN Global discovery/parsing.
- `sources/china_site.py` — NCCN China parsing + consent-gated download
  (`ChinaSource`, CSRF/credential flow, `china:{version_id}:{lang}` record IDs,
  explicit China→Global `PAIRING_ALIASES` map, download language guard,
  quota-wording classification).
- `tests/test_*.py` — per-module contract tests; `test_mcp_smoke.py` guards the
  tool surface, `test_skill_contract.py` guards the Skill workflow.

## Current status

- The current branch and verification state are recorded in
  `.handoff.CODEX0811.md`.
- Python downloads are verified end to end on both sites (2026-08-11/12),
  including the Chinese-language record `china:1026:zh`. China enforces
  10 downloads/account/day, resetting at 00:00 CST.
- China catalog keys pair to Global `guideline_key` via an explicit verified
  map (95/98 live records `verified`); three ambiguous titles stay
  `china-guide-{id}` unpaired by design — see README "record alignment limits".
- A Codex client integration exists in `~/.codex/config.toml`
  (`mcp_servers.nccn-guidelines-auth`, env-forwarded credentials).
- Do not push or delete ignored artifacts without explicit user instruction.
