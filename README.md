# 🏥 nccn-guidelines plugin

NCCN（National Comprehensive Cancer Network）MCP。小段检索，按页引用，不让 Agent 吃满整本指南。批量下载最新中/英 PDF。

[English](README-en.md)

## 能做什么

- 触达 [NCCN Global](https://www.nccn.org/) 和 [NCCN China](https://www.nccnchina.org.cn/)
- 英文指南优先走 Global，中文指南优先走 China；中英配套请求分别从两站取对应语言
- 检索指南证据，答案附标题、来源、版本、详情页和 PDF 页码
- 下载单份指南，也可以批量下载最新中/英 PDF
- PDF 和可检索索引存至本地

## 工作流

1. 直接告诉 Agent 癌种、治疗问题、语言或下载 中/英 指南。
2. MCP 搜索当前目录并选择合适站点。
3. Agent 下载 PDF 并建立本地分页索引。
4. 检索相关页面，给出带出处的回答。

## 安装

`nccn-guidelines` skill 随 plugin 自动获得。

### Codex plugin

```bash
codex plugin marketplace add commie70/NCCN_guidelines_MCP --ref main
codex plugin add nccn-guidelines@nccn-guidelines
# 或直接告诉Agent：“安装这个plugin：https://github.com/commie70/NCCN_guidelines_MCP”
```

### Kimi Code

```text
/plugins install https://github.com/commie70/NCCN_guidelines_MCP
/reload
```

### 其他 Agents：配置通用 MCP

```bash
git clone https://github.com/commie70/NCCN_guidelines_MCP
cd NCCN_guidelines_MCP
uv sync
```

把 `<仓库绝对路径>` 换成真实路径。

```json
{
  "mcpServers": {
    "nccn-guidelines": {
      "command": "uv",
      "args": ["--directory", "<仓库绝对路径>", "run", "nccn-guidelines-mcp"]
    }
  }
}
```

## 配置

### 注册账号

Global 与 China 使用两套账号。

- **NCCN Global**　[登录或注册](https://www.nccn.org/login)
- **NCCN China**　[官方注册页](https://www.nccnchina.org.cn/user/register?redirect_url=https%253A%252F%252Fwww.nccnchina.org.cn%252Findex)

China 账号请把网站接受的手机号或其他登录标识填入 `NCCN_CHINA_USERNAME`。

### 方式一　设置环境变量

启动 Agents 前设置凭据。

```bash
export NCCN_GLOBAL_USERNAME='<global-email>'
export NCCN_GLOBAL_PASSWORD='<global-password>'
export NCCN_CHINA_USERNAME='<china-login-identifier>'
export NCCN_CHINA_PASSWORD='<china-password>'
export NCCN_DATA_DIR="$HOME/.nccn-guidelines"  # 可选
```

Codex / Kimi 可在 `~/.codex/config.toml` `~/.kimi-code/config.toml` 中读取这些变量。

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

配置变化后重启 Codex，或在 Kimi Code 中运行 `/reload`。

### 方式二　直接写入私有 MCP 配置

也可以把凭据直接写入本机 MCP 配置。注意配置文件不要泄露。

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

`NCCN_DATA_DIR` 默认使用 `~/.nccn-guidelines`。

### 自动选站

| 需求 | `source=auto` |
| --- | --- |
| 英文指南且有 Global 凭据 | NCCN Global |
| 英文指南但没有 Global 凭据 | NCCN China |
| 中文指南 | NCCN China |
| 中 / 英 指南 | Global 英文 + China 中文 |

自动搜索在首选目录刷新失败或无结果时会尝试同语言跨站兜底，并返回实际来源。手动指定来源会覆盖自动选择，不再自动换站。

### Agent Computer Use 工具备选

MCP 链路不通时，可让 Agents 使用 Computer Use 工具接管浏览器下载指南。

优先推荐 [Kimi Computer Use](https://www.kimi.com/code/docs/kimi-code-cli/customization/plugins.html#kimi-computer-use)。它可以通过 Kimi Code、Codex CLI 或 ChatGPT app 控制浏览器。使用前只需保证浏览器里的 NCCN Global 和 NCCN China 都处于登录状态。随后让 Agent 打开准确的指南、选择语言、接受站点协议并下载 PDF。

浏览器下载的 PDF 不会自动加入本 plugin 的检索索引。需要分页检索时，再恢复 MCP 链路。

ChatGPT / Codex 用户可参阅 [Computer Use 官方文档](https://learn.chatgpt.com/docs/computer-use) 和 [桌面端使用案例](https://learn.chatgpt.com/use-cases/use-your-computer-with-codex)。

## 使用案例

Codex 使用 `$nccn-guidelines`，Kimi Code 使用 `/skill:nccn-guidelines`。

### ES-SCLC 一线有哪些免疫治疗方案？


```text
可用方案包括
- 卡铂/依托泊苷联合阿替利珠单抗，随后使用阿替利珠单抗维持。
- 卡铂或顺铂/依托泊苷联合度伐利尤单抗，随后使用度伐利尤单抗维持。

指南：Small Cell Lung Cancer
来源：NCCN Global
版本：1.2027，2026 年 7 月 1 日
PDF：第 21 页
详情页：https://www.nccn.org/guidelines/nccn-guidelines/guidelines-detail?category=1&id=1462
```

### 三阴性乳腺癌的初始化疗是什么？


```text
对于 II 至 III 期三阴性乳腺癌，NCCN 列出的术前方案为卡铂/紫杉醇联合
帕博利珠单抗，随后使用环磷酰胺/多柔比星或表柔比星联合帕博利珠单抗，
术后继续帕博利珠单抗。

指南：Breast Cancer
来源：NCCN Global
版本：6.2026，2026 年 7 月 29 日
PDF：第 73 页
详情页：https://www.nccn.org/guidelines/nccn-guidelines/guidelines-detail?category=1&id=1419
```

### 神经内分泌肿瘤有哪些免疫治疗方案？


```text
对于肺外低分化神经内分泌癌，NCCN 列出的方案包括
- 既往治疗后进展、没有满意替代方案的 MSI-H、dMMR 或 TMB-H 肿瘤可考虑帕博利珠单抗。
- 转移性疾病进展后可考虑伊匹木单抗联合纳武利尤单抗，推荐等级为 2B 类。

指南：Neuroendocrine and Adrenal Tumors
来源：NCCN Global
版本：1.2026，2026 年 4 月 21 日
PDF：第 108 至 109 页
详情页：https://www.nccn.org/guidelines/nccn-guidelines/guidelines-detail?category=1&id=1448
```

以上案例用于展示指南证据检索，不构成针对个人的医疗建议。

## 注意

- NCCN 内容受许可保护。请使用有访问资格的账号，并接受对应站点协议。
- NCCN 站点通过本流程只提供最新版指南，无法访问历史版本。
- NCCN China 每份 PDF 都要单独确认，目前每个账号每天最多下载 10 份。
- 中英文指南的版本可能不同。成对下载时会分别保存两个版本。
- 凭据不要放进提示词、截图、日志、Issue 或提交到仓库的文件。泄露后请及时轮换。
- 本 plugin 用于检索和下载指南证据。临床决策仍需结合专业判断和本地规范。
