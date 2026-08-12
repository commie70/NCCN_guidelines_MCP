# Kimi Computer Use browser-download baseline

Run date: 2026-08-11. KimiCU.app 0.5.4 was used through its local MCP server
(`kimi-cu mcp -s user`) to control Chrome via Accessibility actions only. The
run did not use site HTTP requests, CDP, DOM automation, or shell networking.

| Field | Result |
| --- | --- |
| Status | Downloaded |
| Source | `nccnchina.org.cn` |
| Selected title | 非小细胞肺癌 |
| Language / version | English / 2026.7 |
| Stable record ID for project comparison | `china:1158:en` |
| Wall time | 22.5 s, from opening a fresh tab to a stable completed PDF |
| UI actions | 5: new tab, focus address bar, open catalogue, select guide, request PDF |
| Observation calls | 4 Accessibility snapshots; excluded from UI-action count |
| PDF bytes | 5,804,744 |
| SHA-256 | `89a315e4b4a762b35953d31eff51420e7eccca2830ca30d0d0d1fb20ae917987` |

The browser already had a valid NCCN China session; this run did not type,
print, or persist credentials. It downloaded exactly one PDF, and records no
cookie, CSRF value, temporary download URL, filename, or local filesystem
path. This baseline measures browser-mediated acquisition only; it does not
measure PDF indexing or three-question evidence-answer quality.
