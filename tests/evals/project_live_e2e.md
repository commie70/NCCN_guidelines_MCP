# Project live China evaluation

## Result

Blocked before licensed content retrieval. The current project refreshed the official NCCN China catalog directly and selected the public catalog record `china:1152:en` (Breast Cancer, English, version `2026.6`). The refresh returned 8 records in 0.385 seconds.

`confirm_license=false` was rejected before network activity: 0 requests and 0 `download-log` posts. With the user-authorized, per-record confirmation, the current source reached the China login endpoint but did not authenticate. It made no `download-log` request, did not request or persist a PDF, and therefore produced no PDF hash, page index, content search, or extraction result. Credentials, cookies, CSRF values, response messages, issued URLs, and PDF content are intentionally absent from this report.

An authorized retry using the subsequently supplied mobile identifier selected `china:1158:en` (Non-Small Cell Lung Cancer, English, version `2026.7`) from the same 8-record catalog. It also reached `POST /user/login-do` but was blocked with the same safe error category. It made 0 `download-log` requests, no PDF request, no persistence, and consequently no index or bounded search. The mobile identifier and server response are not retained.

## Reproduction boundary

- Data directory: a fresh temporary `NCCN_DATA_DIR` for each run; no project directory writes.
- Record: `china:1152:en`; source `china`; English; version `2026.6`.
- Runtime credentials: supplied only as process environment variables; not written to an artifact.
- After the JS-login update, observable safe request sequence was `GET detail`, `GET login`, `POST login`; outcome category `SourceError`.
- Observable licensed-download effects: `download-log=0`; PDF request=0; persisted PDF=false.
- Mobile-identifier retry: catalog 0.295 s; selected-record operation 0.687 s; same safe request sequence and zero licensed-download effects.

## NCCN China login addendum

Observed on the official login page without credentials:

- It currently contains zero HTML `form` elements. Its hidden inputs are named `check_type`, `redirect_url`, `authorize_url`, and `_token`; it exposes a CSRF meta value.
- Password login is an AJAX `POST /user/login-do` with standard form encoding and `X-CSRF-TOKEN`. Its fields are `login_type=1`, `_token`, `mobile`, `password`, and `is_agree=1`.
- OTP login fields are `login_type`, `_token`, `mobile`, `mobile_code`, `check_type`, and `is_agree=1`. CAPTCHA controls are visible, but the password-mode request sends no CAPTCHA field.
- A safe invalid request returned JSON with a boolean `success` and string `msg`; the page JavaScript redirects only when `success` is true.

This explains why the old HTML-form-only login parser failed. The post-update project reached the declared endpoint, but neither authorized runtime identifier yielded an authenticated session in this run. No server response text is retained here.

## Three-question Codex E2E

The requested `gpt-5.6-terra` / `high` isolation exists locally (`codex-cli 0.147.0`). A first isolated session started the project MCP `search_guidelines` call, but the call was cancelled before a result and is excluded from scoring. The three question runs are `not_run`, rather than failed answers: authenticated download did not yield a fixed PDF hash or page-addressable evidence, so reporting medical conclusions, page citations, token peaks, or a comparison score would be fabricated.

| Question | Status | Peak context | Compaction |
| --- | --- | ---: | --- |
| First-line immunotherapy options for ES-SCLC | Not run | N/A | N/A |
| Initial chemotherapy for triple-negative breast cancer | Not run | N/A | N/A |
| Immunotherapy options for neuroendocrine tumors | Not run | N/A | N/A |

- 2026-08-11T12:15:35+08:00 — Fresh isolated validation for `china:1158:en`: not authenticated after reaching the login endpoint; `download-log=0`, PDF requests=0.
