# 🏥 nccn-guidelines plugin

NCCN Global + NCCN China 指南 MCP。小段检索。按页引用。不把整本 PDF 塞进上下文。

[English](README.md)

## 怎么工作

1. 先搜目录。拿 `record_id`。
2. China 下载前，确认这一条记录。
3. PDF 本地解析一次。按页切块。
4. 先搜小段。再展开需要的页/块。
5. 答案写标题、来源、版本、详情 URL、页码。

## 能做什么

- 支持 `nccn.org` 和 `nccnchina.org.cn`。
- 自动选站：英文且 Global 凭据完整 → Global；英文无完整 Global 凭据 → China 目录；中文/中英配套 → China。
- 不收任意 URL、文件路径、账号、密码。只收目录返回的 `record_id`。
- China 每次下载单独确认。未确认：不会提交 `download-log`。
- 下载按来源/语言/版本隔离。原子写入。记录 SHA-256。
- 目录最多 20 条。检索片段单条最多 1,200 字符、总共最多 45,000。展开必须选块或页，最多 120 块或 80 页，单次调用最多 250,000 字符。
- 优先 SQLite FTS5 `trigram`，再 `unicode61`，最后受限本地匹配。不用向量库，不开后台索引器。

## 安装

### Codex

```bash
codex plugin marketplace add commie70/NCCN_guidelines_MCP --ref main
codex plugin add nccn-guidelines@nccn-guidelines
```

### Kimi Code CLI

```text
/plugins install https://github.com/commie70/NCCN_guidelines_MCP
/reload
```

### 通用 MCP Agent

```bash
git clone https://github.com/commie70/NCCN_guidelines_MCP
cd NCCN_guidelines_MCP
uv sync
```

配置。把 `<仓库绝对路径>` 换成真实路径。

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

只给 MCP 进程环境变量。不要写进 `.env`、提示词、工具参数或仓库。

### 注册账号与私有 MCP 配置

Global 与 China 是两套账号。先分别注册：

- **NCCN Global：**[登录 / 注册入口](https://www.nccn.org/login)。
- **NCCN China：**[官方注册页](https://www.nccnchina.org.cn/user/register?redirect_url=https%253A%252F%252Fwww.nccnchina.org.cn%252Findex)，当前需要手机和邮箱验证。

仓库里的 plugin 清单故意不放用户凭据。Codex 要带认证下载时，推荐另建一个**仅本机私有**的 STDIO MCP，并只转发变量名。将下段写入 `~/.codex/config.toml`（或可信项目的 `.codex/config.toml`），替换真实路径：

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

然后在启动 Codex 的 shell 里设置变量，并重启客户端，让 MCP 进程重启：

```bash
export NCCN_GLOBAL_USERNAME='<global-email>'
export NCCN_GLOBAL_PASSWORD='<global-password>'
export NCCN_CHINA_USERNAME='<china-login-identifier>'
export NCCN_CHINA_PASSWORD='<china-password>'
export NCCN_DATA_DIR="$HOME/.nccn-guidelines"  # 可选
codex
```

`env_vars` 不会把变量值写进 `config.toml`。也可以在私有主机配置中用 `env`，或用 `codex mcp add --env NAME=VALUE`；后两者会把密钥写到本机配置，不能提交或分享。marketplace plugin 可保留其 Skill；若 `nccn-guidelines-auth` 造成两套同类工具混淆，可关闭 plugin 自带的 MCP server。Kimi Code 也要把同一组变量注入它启动的 STDIO server，再 reload plugin/server。不要把凭据写进 `.mcp.json`、`kimi.plugin.json` 或任何仓库文件。

兼容期支持 `NCCN_USERNAME` / `NCCN_PASSWORD` 作为 Global 别名。新旧同时存在时，新变量优先。默认数据目录：`~/.nccn-guidelines`。目录、PDF、SQLite、manifest、日志都在这里，不在 plugin 安装目录。

China 当前密码登录页把账号字段叫作 `mobile`。`NCCN_CHINA_USERNAME` 要填写 China 站实际接受的登录标识；不要默认 Global 邮箱也能登录 China。

如果某站只能在已授权浏览器会话中工作，可为对应来源**显式**设置 `NCCN_GLOBAL_SESSION_COOKIE` 或 `NCCN_CHINA_SESSION_COOKIE`。值是用户给 MCP 进程的完整 `Cookie` 请求头。plugin 不会读取 Chrome Cookie，不从 MCP 工具参数收 Cookie，不返回，也不写入日志或 manifest。显式会话被拒绝时只报认证错误，不会换站。

| 需求 | `source=auto` |
| --- | --- |
| 英文 + 完整 Global 凭据 | Global |
| 英文 + Global 凭据不完整 | China 目录 |
| 中文 | China |
| 中英配套 | China；两个版本可以不同 |

手动 `source` 覆盖自动选择。`source=global` + `zh`/`paired` 会报参数错误。密码错误、配额、网络错误时不会偷偷换站。

### 中英文记录对齐的边界

China 目录通过一张显式核对过的标题映射表对齐到 NCCN Global 的 `guideline_key`。截至 2026-08-11，线上 98 条 China 记录中 95 条 `pairing_status=verified`。其余情况是刻意保留，不是缺陷：

- **双标签「-中国版」卡片不拆。** 宫颈癌/子宫肿瘤/卵巢癌中国版卡片同时挂「中文版」「英文版」两个标签，但详情页只提供中文版 PDF 下载；它们的英文版本是独立目录记录（如 `china:989:en`）。plugin 一张卡片只留一条记录，不会编造下载必失败的幻影英文记录。
- **3 个歧义标题保持未配对**（`china-guide-{id}`，`pairing_status=unverified`）：`免疫治疗相关毒性的管理`（与免疫检查点毒性条目疑似新旧名）、`肝胆癌`、`原发性皮肤淋巴瘤`。它们仍可凭 `record_id` 正常搜索与下载，只是不并入 Global key。
- **语言不匹配直接拦截。** 详情页提供的 PDF 语言与所选记录不一致时，下载在任何 `download-log` 请求之前以 `SourceError` 终止，不会落盘错误语言的文件。

### 只有当前版本

目录只存每个指南当前版本。归档页不解析，旧版搜不到，旧版下不了。refresh 拿新版本号覆盖记录。本地旧 PDF 还在盘上、还能检索，但同一 `record_id` 重新下载会顶掉索引。站点就算有归档，本 MCP 也不暴露。

### Python `httpx` 链路不通时：浏览器备选

Python MCP 才会把 PDF 入库、建索引、供 `search_content` 检索。若站点拒绝它的登录/会话，浏览器只作为“下载一份已许可 PDF”的备选；它不是 Cookie 桥，浏览器下载的文件也不会自动进入 `search_content`。

1. **Codex Computer Use：**按 [Computer Use 官方说明](https://learn.chatgpt.com/docs/computer-use) 与 [Codex 浏览器工作流](https://learn.chatgpt.com/use-cases/use-your-computer-with-codex) 操作。这是支持该能力的 Codex/ChatGPT host 功能，不是本 plugin 需要安装的依赖。新开标签页，自己登录，打开精确 NCCN 详情页，选择语言，勾选页面 EULA，再确认单条下载。不要让 Agent 读取、复制或回显 Cookie。
2. **Kimi Computer Use：**先按 [Kimi Code CLI 官方安装](https://www.kimi.com/help/kimi-code/cli-getting-started) 与 [MCP 接入说明](https://platform.kimi.com/docs/guide/kimi-cli-support) 配置。更新本 README 时，没有核实到独立 `kimi-cu` 电脑控制运行时的公开厂商安装页；安装 Kimi Code 本身**不会**安装它。若组织/host 已提供 `kimi-cu`，可作为本地 MCP 暴露，例如运行 `kimi-cu mcp -s user`，再按同样的“新标签页、用户已登录、单条记录”流程下载。其 MCP 配置中不要放 NCCN 凭据。

两条备选都要求用户有内容访问资格并显式同意站点条款。不得批量下载、复用临时 PDF URL，也不得手工把浏览器拿到的 PDF 复制到本 plugin 数据目录。要使用 MCP 内容检索工具，仍需修复 HTTP 认证，或按上面的配置由用户显式提供会话 Cookie。

## Skill

安装后自动发现 `nccn-guidelines`。

- Codex：`$nccn-guidelines`
- Kimi：`/skill:nccn-guidelines`

流程：先搜目录；China 下载前展示标题/语言/版本/来源并拿明确许可；先 `search_content`，再小范围 `extract_content`；答案带来源和页码。

## 工具

| 工具 | 做什么 |
| --- | --- |
| `search_guidelines` | 搜目录，返回 `record_id`。 |
| `refresh_catalog` | 只更新目录。不下载 PDF。 |
| `get_download_requirements` | 看这一条的许可和配置要求。 |
| `download_guideline` | 下载一条。China 需要 `confirm_license=true`。 |
| `search_content` | 找小段证据。 |
| `extract_content` | 展开指定块/页。 |

`get_index` 只返回迁移提示，不再给整包 YAML。

`record_id` 是 `search_guidelines` 返回的“不透明 ID”。原样保存、原样传回；不要自己拼。例如返回 `china:1158:en` 后，直接传给 `get_download_requirements`、`download_guideline`、`search_content` 或 `extract_content`。

## 例子

1. What are the available first-line immunotherapy options for ES-SCLC?
2. What is the initial chemotherapy for triple-negative breast cancer?
3. What are the immunotherapy options for neuroendocrine tumors?

## 真实评测（2026-08-11）

两条成功浏览器基线用同一条 China 记录：`china:1158:en`（非小细胞肺癌、英文、2026.7）。它们拿到同一个有效 PDF：5,804,744 bytes，SHA-256 为 `89a315e4b4a762b35953d31eff51420e7eccca2830ca30d0d0d1fb20ae917987`。

| 路径 | 结果 | 获取耗时 | 操作 / 请求 | 三题证据 E2E |
| --- | --- | ---: | --- | --- |
| 直接 NCCN China 浏览器 | 成功，302 页 PDF | 同意授权到文件完成：2.5–3.0 s | 4 次 UI；4 个必要网络步骤；0 重试 | 未测（只作下载基线） |
| Kimi Computer Use 控制浏览器 | 成功，拿到相同 PDF | 新标签到文件完成：22.5 s | 5 次 UI；4 次观察快照 | 未测（只作下载基线） |
| 本 plugin Python 实测（2026-08-11/12） | 通过 Codex MCP 客户端下载并索引了 China（中/英文）与 Global 记录 | 目录约 0.3 s；每条确认记录数秒 | `confirm_license=false`：0 HTTP；每条确认记录恰好一次 `download-log` | 通过：ES-SCLC 一线免疫方案作答并引用标题、版本与 PDF 页码（SCL-E 1 of 6，p.21） |

Python 链路现已按当前契约双站端到端验证：Global 目录与 PDF 下载（如非小细胞肺癌，3,818,554 bytes，索引为 1541 个 chunk），以及 China 密码登录（`mobile` 标识符）后的逐条授权下载，包括中文版记录 `china:1026:zh`（宫颈癌-中国版，2025.4）。China 配额为每账号每日 10 篇，每日 00:00（CST）重置；配额被拒会被归类为独立的「download quota was reached」错误。不会导入浏览器 Cookie，也不会绕过此门槛。

原始观察：[`baseline_direct.md`](tests/evals/baseline_direct.md)、[`baseline_kimi_cu.md`](tests/evals/baseline_kimi_cu.md)，以及 `tests/evals/project_live_e2e.md` / `tests/evals/results.json`。

### 兼容性跟进

Kimi Computer Use 在隔离标签页复现了 China 的真实浏览器契约：选中详情记录，打开下载，勾选页面展示的 EULA，再确认。浏览器先发一次 `download-log`，才构造 PDF 请求。Python 适配器在内存中解析这套详情契约（不保存 token 或下载 URL），同时保留旧表单兼容路径；详情页提供的 PDF 语言与所选记录不一致时会直接拦截下载。2026-08-11 的真实刷新得到 91 条 Global 记录与 98 条 China 记录，其中 95 条 China 记录与 Global `guideline_key` 配对（`pairing_status=verified`）。31 个 fixture/MCP 测试覆盖两套当前契约、配对映射表与配额/语言防线。

## 注意

- NCCN 内容有许可。用户需要有账号并接受站点条款。China 每条下载都要单独确认。
- China 有配额和访问限制：每账号每日 10 篇，每日 00:00（CST）重置；配额被拒会报独立的「quota was reached」错误。不会批量试探，不会重试 `download-log`，不会把旧中文译本说成新版英文的同版翻译。
- China 同时支持旧表单和当前浏览器下载契约：详情页提供本条 `download-log` 字段，只有该调用成功后才构造即时 PDF 请求。Global 目录同时兼容旧卡片和当前 `guidelines-detail` 链接。
- 凭据不要出现在对话、日志、截图、Issue、仓库。泄露过就轮换。
- 这是证据检索，不是医疗建议。临床决策请遵循专业判断和本地规范。
- 刷新失败时旧目录会标记 `stale=true`。FTS 不可用时走受限回退。扫描 PDF 会标记 `ocr_required`；本 plugin 不会把受许可 PDF 上传第三方 OCR。
