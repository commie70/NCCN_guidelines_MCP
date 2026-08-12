# Direct official-site baseline (NCCN China)

Run: 2026-08-11.  One real, no-retry browser run against the official NCCN China
site only.  The browser already had the user's authorized NCCN China session;
no credential, cookie, CSRF value, or issued download URL was recorded.

## Selected record and output

| Field | Observed value |
| --- | --- |
| Project record ID | `china:1158:en` |
| Official source | NCCN China (`nccnchina.org.cn`) |
| Stable detail route | `/guide/detail/1158` |
| Title / language | Non-Small Cell Lung Cancer / English (`非小细胞肺癌`) |
| Version | 2026.7 |
| Downloaded bytes | 5,804,744 |
| SHA-256 | `89a315e4b4a762b35953d31eff51420e7eccca2830ca30d0d0d1fb20ae917987` |
| PDF validation | PDF 1.4, 302 pages, not encrypted |

## Direct-browser result

| Metric | Result |
| --- | --- |
| Outcome | Success: an official-site browser download completed and the saved bytes passed PDF/header/page-count checks. |
| Timed interval | Authorization confirmation click to final local-file modification time. |
| Wall time | 2.5–3.0 s (filesystem timestamp is one-second resolution; start was 2026-08-11T01:59:12.541Z and final modification was 01:59:15Z). |
| User-visible interactions | 4: select catalog record, choose English download, tick EULA acceptance, confirm authorization. |
| Required network steps | 4 observed/necessary steps: catalog navigation, detail navigation, one `/guide/download-log` XHR (206 ms), then the browser PDF transfer. |
| Retries / extra probes | 0 / 0. |

The Chrome download surface still displayed its independent malware-scanning
status after the bytes were already complete; it was not part of transfer timing.

## Measurement boundary

This is the **direct official-site** control, not the plugin.  Timing starts
only after the exact NCCN China record and its license confirmation screen were
already selected, so it measures authorization plus file transfer rather than
human catalog search/reading time.  Compare plugin runs using the same record,
account state, network, success criterion, and timing boundary.
