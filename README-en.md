# 🏥 nccn-guidelines plugin

An MCP for NCCN (National Comprehensive Cancer Network) guidelines. Search small excerpts, cite exact pages, and keep agents from swallowing an entire guideline. Batch-download the latest Chinese and English PDFs.

[简体中文](README.md)

## What It Can Do

- Access [NCCN Global](https://www.nccn.org/) and [NCCN China](https://www.nccnchina.org.cn/)
- Prefer Global for English guidelines and China for Chinese guidelines; paired requests fetch each language from the corresponding site
- Search guideline evidence and answer with the title, source, version, detail page, and PDF page number
- Download one guideline or batch-download the latest Chinese and English PDFs
- Store PDFs and searchable indexes locally

## Workflow

1. Tell the agent the cancer type, treatment question, language, or Chinese/English guidelines to download.
2. The MCP searches the current catalogs and selects the appropriate site.
3. The agent downloads the PDF and builds a local page-level index.
4. It searches the relevant pages and returns an answer with citations.

## Installation

### Codex plugin

```bash
codex plugin marketplace add commie70/NCCN_guidelines_MCP --ref main
codex plugin add nccn-guidelines@nccn-guidelines
# Or tell the agent: "Install this plugin: https://github.com/commie70/NCCN_guidelines_MCP"
```

### Kimi Code

```text
/plugins install https://github.com/commie70/NCCN_guidelines_MCP
/reload
```

### Other agents: configure a generic MCP

```bash
git clone https://github.com/commie70/NCCN_guidelines_MCP
cd NCCN_guidelines_MCP
uv sync
```

Replace `<absolute-path-to-repo>` with the actual path.

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

## Configuration

### Register accounts

Global and China use separate accounts.

- **NCCN Global**  [Sign in or register](https://www.nccn.org/login)
- **NCCN China**  [Official registration page](https://www.nccnchina.org.cn/user/register?redirect_url=https%253A%252F%252Fwww.nccnchina.org.cn%252Findex)

For NCCN China, set `NCCN_CHINA_USERNAME` to the mobile number or other login identifier accepted by the site.

### Option A  Set environment variables

Set credentials before starting the agents.

```bash
export NCCN_GLOBAL_USERNAME='<global-email>'
export NCCN_GLOBAL_PASSWORD='<global-password>'
export NCCN_CHINA_USERNAME='<china-login-identifier>'
export NCCN_CHINA_PASSWORD='<china-password>'
export NCCN_DATA_DIR="$HOME/.nccn-guidelines"  # optional
```

Codex and Kimi can read these variables from `~/.codex/config.toml` and `~/.kimi-code/config.toml`.

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

Restart Codex after changing the configuration, or run `/reload` in Kimi Code.

### Option B  Save credentials directly in a private MCP configuration

You can also place credentials directly in a local MCP configuration. Do not expose that file.

Codex `~/.codex/config.toml`

```toml
[mcp_servers.nccn-guidelines-auth]
command = "uv"
args = ["--directory", "/absolute/path/to/NCCN_guidelines_MCP", "run", "nccn-guidelines-mcp"]

[mcp_servers.nccn-guidelines-auth.env]
NCCN_GLOBAL_USERNAME = "<global-email>"
NCCN_GLOBAL_PASSWORD = "<global-password>"
NCCN_CHINA_USERNAME = "<china-login-identifier>"
NCCN_CHINA_PASSWORD = "<china-password>"
NCCN_DATA_DIR = "/absolute/path/to/private-data"
```

Kimi Code `~/.kimi-code/mcp.json`

```json
{
  "mcpServers": {
    "nccn-guidelines-auth": {
      "command": "uv",
      "args": ["--directory", "/absolute/path/to/NCCN_guidelines_MCP", "run", "nccn-guidelines-mcp"],
      "env": {
        "NCCN_GLOBAL_USERNAME": "<global-email>",
        "NCCN_GLOBAL_PASSWORD": "<global-password>",
        "NCCN_CHINA_USERNAME": "<china-login-identifier>",
        "NCCN_CHINA_PASSWORD": "<china-password>",
        "NCCN_DATA_DIR": "/absolute/path/to/private-data"
      }
    }
  }
}
```

`NCCN_DATA_DIR` defaults to `~/.nccn-guidelines`.

### Automatic routing

| Request | `source=auto` |
| --- | --- |
| English guideline with Global credentials | NCCN Global |
| English guideline without Global credentials | NCCN China |
| Chinese guideline | NCCN China |
| Paired Chinese and English guidelines | Global English + China Chinese |

If the preferred catalog cannot refresh or returns no results, automatic search tries the other site for the same language and reports the actual source. An explicit source overrides automatic selection and disables automatic switching.

### Agent Computer Use fallback

If the MCP connection is unavailable, an agent can use a Computer Use tool to control the browser and download guidelines.

Prefer [Kimi Computer Use](https://www.kimi.com/code/docs/kimi-code-cli/customization/plugins.html#kimi-computer-use). It can control a browser through Kimi Code, Codex CLI, or the ChatGPT app. Before using Computer Use, make sure the browser is signed in to both NCCN Global and NCCN China. The agent can then open the exact guideline, select the language, accept the site terms, and download the PDF.

PDFs downloaded through the browser are not added to this plugin's searchable index automatically. Restore the MCP connection when page-level search is needed.

ChatGPT and Codex users can refer to the official [Computer Use documentation](https://learn.chatgpt.com/docs/computer-use) and [desktop app use case](https://learn.chatgpt.com/use-cases/use-your-computer-with-codex).

## Use Cases

Use `$nccn-guidelines` in Codex or `/skill:nccn-guidelines` in Kimi Code.

### What are the available first-line immunotherapy options for ES-SCLC?

```text
Available options include
- Atezolizumab with carboplatin/etoposide, followed by maintenance atezolizumab.
- Durvalumab with carboplatin/etoposide or cisplatin/etoposide, followed by maintenance durvalumab.

Guideline: Small Cell Lung Cancer
Source: NCCN Global
Version: 1.2027, July 1, 2026
PDF: page 21
Detail page: https://www.nccn.org/guidelines/nccn-guidelines/guidelines-detail?category=1&id=1462
```

### What is the initial chemotherapy for triple-negative breast cancer?

```text
For stage II–III triple-negative breast cancer, NCCN lists preoperative
carboplatin/paclitaxel plus pembrolizumab, followed by
cyclophosphamide/doxorubicin or epirubicin plus pembrolizumab, then adjuvant
pembrolizumab.

Guideline: Breast Cancer
Source: NCCN Global
Version: 6.2026, July 29, 2026
PDF: page 73
Detail page: https://www.nccn.org/guidelines/nccn-guidelines/guidelines-detail?category=1&id=1419
```

### What are the immunotherapy options for neuroendocrine tumors?

```text
For extrapulmonary poorly differentiated neuroendocrine carcinoma, NCCN lists
- Pembrolizumab for MSI-H, dMMR, or TMB-H tumors after progression on prior treatment when no satisfactory alternative is available.
- Ipilimumab plus nivolumab for metastatic disease with progression, category 2B.

Guideline: Neuroendocrine and Adrenal Tumors
Source: NCCN Global
Version: 1.2026, April 21, 2026
PDF: pages 108–109
Detail page: https://www.nccn.org/guidelines/nccn-guidelines/guidelines-detail?category=1&id=1448
```

These examples demonstrate guideline evidence retrieval and are not individualized medical advice.

## Notes

- NCCN content is licensed. Use an entitled account and accept the applicable site terms.
- NCCN sites provide only the latest guideline version through this workflow; historical versions are unavailable.
- NCCN China requires confirmation for each PDF and currently limits each account to 10 downloads per day.
- Chinese and English guidelines may have different versions. Paired downloads save both versions separately.
- Keep credentials out of prompts, screenshots, logs, issues, and files committed to the repository. Rotate exposed credentials promptly.
- This plugin retrieves and downloads guideline evidence. Clinical decisions still require professional judgment and local policy.
