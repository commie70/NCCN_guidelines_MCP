# 🏥 nccn-guidelines plugin

[![Python](https://img.shields.io/badge/python-3.11+-blue.svg)](https://www.python.org/)
[![MCP](https://img.shields.io/badge/MCP-stdio-green.svg)](https://modelcontextprotocol.io/)
[![License](https://img.shields.io/badge/license-MIT-blue.svg)](LICENSE)
[![Version](https://img.shields.io/badge/version-0.2.0-orange.svg)](https://github.com/commie70/NCCN_guidelines_MCP/releases)

Bounded NCCN Global and NCCN China guideline retrieval for MCP agents. It returns small, cited evidence slices instead of full catalogs or full PDFs.

[简体中文](README-zh.md)

## 🔬 How It Works

1. Search a source-specific catalog and keep its stable `record_id`.
2. Confirm any China download for that exact record.
3. Parse a downloaded PDF once into page-bound chunks in local SQLite.
4. Search snippets, then expand only the relevant chunks or pages.
5. Cite title, source, version, detail URL, and PDF page.

## ✨ Features

- NCCN Global (`nccn.org`) and NCCN China (`nccnchina.org.cn`) catalogs.
- Automatic routing: English prefers Global when complete Global credentials exist; Chinese and paired requests use China.
- Stable records. No MCP tool accepts an arbitrary URL, path, username, or password.
- Per-record China license confirmation. A rejected/omitted confirmation makes zero `download-log` requests.
- Site/language/version-separated files, atomic writes, SHA-256 manifests, and local SQLite catalog/content stores.
- Bounded retrieval: catalog results ≤20; snippets ≤1,200 chars each and ≤45,000 chars total; extraction requires selectors and is limited to 120 chunks or 80 pages, up to 250,000 chars per call.
- SQLite FTS5 uses `trigram` when available, then `unicode61`, then a bounded deterministic fallback. No vector database or background indexer.

## 🛠️ Installation

### Codex plugin

```bash
codex plugin marketplace add commie70/NCCN_guidelines_MCP --ref main
codex plugin add nccn-guidelines@nccn-guidelines
```

### Kimi Code CLI

```text
/plugins install https://github.com/commie70/NCCN_guidelines_MCP
/reload
```

### Generic MCP agent

```bash
git clone https://github.com/commie70/NCCN_guidelines_MCP
cd NCCN_guidelines_MCP
uv sync
```

Use this stdio configuration, replacing `<absolute-path-to-repo>`:

```json
{
  "mcpServers": {
    "nccn-guidelines": {
      "command": "uv",
      "args": ["--directory", "<absolute-path-to-repo>", "run", "nccn-guidelines-mcp"]
    }
  }
}
```

## ⚙️ Configuration

Set environment variables in the MCP process, never as tool arguments or committed `.env` files.

### Accounts and private MCP configuration

Create the two accounts separately before configuring a download client:

- **NCCN Global:** [account sign-in / registration portal](https://www.nccn.org/login).
- **NCCN China:** [official registration page](https://www.nccnchina.org.cn/user/register?redirect_url=https%253A%252F%252Fwww.nccnchina.org.cn%252Findex). It currently requires mobile and email verification.

The checked-in plugin manifests deliberately contain no user credentials. For
authenticated use with a Codex client, add a **private local** STDIO server and
forward only the variable names. Put this in `~/.codex/config.toml` (or a
trusted project-local `.codex/config.toml`), replacing the path:

```toml
[mcp_servers.nccn-guidelines-auth]
command = "uv"
args = ["--directory", "/absolute/path/to/NCCN_guidelines_MCP", "run", "nccn-guidelines-mcp"]
env_vars = [
  "NCCN_GLOBAL_USERNAME",
  "NCCN_GLOBAL_PASSWORD",
  "NCCN_CHINA_USERNAME",
  "NCCN_CHINA_PASSWORD",
  "NCCN_DATA_DIR",
]
```

Then set the values in the shell that starts Codex and restart the client so it
restarts the MCP process:

```bash
export NCCN_GLOBAL_USERNAME='<global-email>'
export NCCN_GLOBAL_PASSWORD='<global-password>'
export NCCN_CHINA_USERNAME='<china-login-identifier>'
export NCCN_CHINA_PASSWORD='<china-password>'
export NCCN_DATA_DIR="$HOME/.nccn-guidelines"  # optional
codex
```

`env_vars` avoids saving values in `config.toml`. A private host configuration
may instead use its `env` map or `codex mcp add --env NAME=VALUE`; those write
secrets to local configuration, so never commit or share that file. The
marketplace plugin can remain installed for its Skill; disable its bundled MCP
server if the extra `nccn-guidelines-auth` tool set would be confusing. Kimi
Code users apply the same environment variables to the process that launches
its configured STDIO server, then reload the plugin/server. Do **not** add
credentials to `.mcp.json`, `kimi.plugin.json`, or any repository file.

`NCCN_USERNAME` and `NCCN_PASSWORD` remain temporary aliases for the Global pair. If new and legacy names are both present, `NCCN_GLOBAL_*` wins. Catalog, content, downloads, manifests, and logs live under `NCCN_DATA_DIR` (default `~/.nccn-guidelines`), never in the plugin installation directory.

NCCN China currently labels its password-login identifier as `mobile`; set `NCCN_CHINA_USERNAME` to an identifier the China site accepts. Do not assume that a Global email login is accepted by China.

For a site that only works in an already authorized browser session, each source also accepts an **optional, explicit** `NCCN_GLOBAL_SESSION_COOKIE` or `NCCN_CHINA_SESSION_COOKIE` environment value. It is a full `Cookie` request header supplied by the user to the MCP process. The plugin never reads Chrome's cookies, accepts a cookie through an MCP tool, returns it, or writes it to logs/manifests. A rejected explicit session stops with an authentication error; it never falls back to another source.

| Request | `source=auto` route |
| --- | --- |
| English with complete Global credentials | Global |
| English without complete Global credentials | China catalog |
| Chinese | China |
| Paired English + Chinese | China; versions may differ |

An explicit `source` overrides this table. `source=global` with `language=zh` or `paired` is an error. A network, password, quota, or site error never silently switches sources.

### Chinese/English record alignment limits

China catalog records are paired to the NCCN Global `guideline_key` through an explicit, verified title map. As of 2026-08-11, 95 of 98 live China records pair with `pairing_status=verified`. The remaining cases are deliberate, not bugs:

- **Dual-tagged `-中国版` cards are not split.** The 宫颈癌/子宫肿瘤/卵巢癌 China-edition cards show both `中文版` and `英文版` tags, but each detail page offers only the Chinese PDF. Their English versions are separate catalog records (e.g. `china:989:en`). The plugin keeps one record per card instead of inventing English records that would always fail at download.
- **Three ambiguous titles stay unpaired** (`china-guide-{id}`, `pairing_status=unverified`): `免疫治疗相关毒性的管理` (overlaps the immune-checkpoint-toxicity title), `肝胆癌`, and `原发性皮肤淋巴瘤`. They are searchable and downloadable by `record_id`; they just do not merge with a Global key.
- **Language mismatch is blocked, not downloaded.** If a detail page offers a PDF whose language differs from the selected record, the download stops with a `SourceError` before any `download-log` request, so a wrong-language file is never persisted.

### Browser fallback when the Python `httpx` path is blocked

The Python MCP path is the only path that persists, indexes, and searches a
PDF. If a site rejects its login/session, use a browser fallback only to obtain
one permitted PDF; it is not a cookie bridge and it does not make the browser
file available to `search_content` automatically.

1. **Codex Computer Use.** Follow the official [Computer Use guide](https://learn.chatgpt.com/docs/computer-use) and [Codex browser workflow](https://learn.chatgpt.com/use-cases/use-your-computer-with-codex). This is a capability of a supported Codex/ChatGPT host, not a dependency to add to this plugin. In a fresh tab, sign in yourself, navigate to the exact NCCN detail page, choose the requested language, accept the displayed EULA, and confirm one download. Do not ask an agent to reveal or copy cookies.
2. **Kimi Computer Use.** Install [Kimi Code CLI](https://www.kimi.com/help/kimi-code/cli-getting-started) and use its [MCP configuration method](https://platform.kimi.com/docs/guide/kimi-cli-support). A public vendor installer for the separate `kimi-cu` computer-control runtime was not verified when this README was updated; installing Kimi Code alone does **not** install it. If your environment provides `kimi-cu`, expose it as a local MCP server, for example `kimi-cu mcp -s user`, then use the same fresh-tab, user-authenticated, one-record flow. Never put NCCN credentials in that MCP configuration.

Both fallbacks require an account entitled to the content and explicit
acceptance of the site terms. They must not bulk-download, reuse a temporary
PDF URL, or copy an acquired PDF into this plugin's data directory by hand.
Resolve the HTTP authentication issue (or provide a user-explicit session
cookie through the configuration above) before using the MCP content tools.

## 💬 Skill

Plugin installation exposes the `nccn-guidelines` skill automatically. Use `$nccn-guidelines` in Codex or `/skill:nccn-guidelines` in Kimi Code CLI when you want to invoke it explicitly. The skill enforces: search first, China confirmation before download, small evidence search before expansion, and source/version/page citations.

## 🛠️ Available Tools

| Tool | Purpose |
| --- | --- |
| `search_guidelines(query, language, source, guide_type, limit)` | Search a bounded catalog and return stable records. |
| `refresh_catalog(source, force)` | Refresh metadata only; never downloads PDFs. |
| `get_download_requirements(record_id)` | Show the exact record, configuration, and license requirements. |
| `download_guideline(record_id, confirm_license)` | Download one catalogued record; China requires explicit confirmation. |
| `search_content(record_id, query, top_k, include_neighbors)` | Return bounded page-addressable candidate snippets. |
| `extract_content(record_id, chunk_ids, pages, max_chars, cursor)` | Expand selected evidence only; selectors are required. |

`get_index` is a compatibility response only and points agents to `search_guidelines`; it never returns the historic full YAML catalog.

`record_id` is an opaque identifier returned by `search_guidelines`; preserve it verbatim instead of constructing it. For example, a returned `china:1158:en` is passed unchanged to `get_download_requirements`, `download_guideline`, `search_content`, and `extract_content`.

## 💡 Usage Example

Here are some example questions you can ask:

1. 🔬 What are the available first-line immunotherapy options for ES-SCLC?
2. 🎯 What is the initial chemotherapy for triple-negative breast cancer?
3. 🧬 What are the immunotherapy options for neuroendocrine tumors?

## 📊 Live evaluation (2026-08-11)

The two acquisition controls used the same official China record,
`china:1158:en` (Non-Small Cell Lung Cancer, English, version 2026.7). Both
successful browser runs produced the same 5,804,744-byte PDF with SHA-256
`89a315e4b4a762b35953d31eff51420e7eccca2830ca30d0d0d1fb20ae917987`.

| Path | Outcome | Measured acquisition time | Interaction / request count | Evidence-quality E2E |
| --- | --- | ---: | --- | --- |
| Direct official NCCN China browser | Downloaded one validated 302-page PDF | 2.5–3.0 s from license confirmation to completed file | 4 UI actions; 4 necessary network steps; 0 retries | Not measured (acquisition control) |
| Kimi Computer Use browser control | Downloaded the identical validated PDF | 22.5 s from fresh tab to completed file | 5 UI actions; 4 observation snapshots | Not measured (acquisition control) |
| This plugin, live China run | Initial run selected `china:1152:en` (Breast Cancer); the mobile-identifier retry selected the control record `china:1158:en` (NSCLC) but both were blocked at China login | Mobile retry: catalog 0.295 s; selected-record attempt 0.687 s; no PDF transfer | `confirm_license=false` made 0 HTTP requests. Each confirmed run reached detail, login, and one login POST; it made 0 `download-log`/PDF requests | Not run: all three questions require a successfully indexed PDF |

The successful browser controls used an already authorized China browser
session. The mobile-identifier retry used the same record but was blocked before
transfer, so these are still not directly comparable performance measurements,
nor an authentication or end-to-end quality claim for the plugin. The current
China login page submits a password-mode XHR with a `mobile` identifier; neither
the initial email-style identifier nor the later mobile identifier authenticated
in a fresh project session. The plugin now supports that current form/XHR
protocol and tests it, but a successful real plugin E2E requires China
credentials accepted by the site's current login flow. The project must not
import browser cookies or bypass this gate.

Reproducible raw observations: [`baseline_direct.md`](tests/evals/baseline_direct.md),
[`baseline_kimi_cu.md`](tests/evals/baseline_kimi_cu.md), and (when the run is
blocked) `tests/evals/project_live_e2e.md` / `tests/evals/results.json`.

### Compatibility follow-up

Kimi Computer Use reproduced the China browser contract in an isolated tab:
select the exact detail record, open its English download, accept the displayed
EULA, and confirm. That performs one `download-log` request before the browser
constructs the PDF request. The Python adapter now parses that in-memory detail
contract (without storing its token or URL), while retaining the older form
contract as a fallback. A live public refresh after this change found 91 Global
records through current `guidelines-detail` links and 8 China records. The 18
fixture/MCP tests cover both current contracts. The Python process still needs
either accepted site credentials or an explicitly supplied session cookie; it
does not take Chrome's authorized session automatically.

## ⚠️ License, safety, and troubleshooting

- NCCN content is licensed. The user must have the required account and accept the applicable terms. For NCCN China, state the exact title, language, version, and source, then obtain permission before the one-record download call.
- China currently enforces its own quota and access controls. The plugin never bulk-probes, retries `download-log`, or treats an old Chinese translation as the current English version.
- China supports both its historic form contract and its current browser contract: the selected detail page supplies the one-record `download-log` fields, and the plugin constructs the immediate PDF request only after that log call succeeds. Global catalog discovery supports both legacy cards and current `guidelines-detail` links.
- Do not put credentials in prompts, tool calls, logs, issues, screenshots, or repository files. Rotate any credential that was accidentally exposed.
- This plugin retrieves guideline evidence; it is not medical advice. Apply professional judgment and local policy.
- If catalog refresh fails, stale previously successful data is labelled `stale=true` with the last successful time. If FTS is unavailable, the bounded fallback is reported. Image-only PDFs are flagged `ocr_required`; this plugin does not upload licensed PDFs to third-party OCR.
