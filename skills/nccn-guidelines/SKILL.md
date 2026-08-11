---
name: nccn-guidelines
description: Search, download, and cite NCCN Global or NCCN China clinical guidelines; use for English, Chinese, or paired NCCN evidence questions.
---

1. `language`: `en`, `zh`, or `paired`; `source="auto"` unless the user names a site.
2. Call `search_guidelines` first; query in the record's title language (China titles are Chinese: 前列腺). Preserve `record_id`; never invent URLs or filenames.
3. Multiple hits for one cancer → pick the exact title match or list candidates; never take the first hit blindly.
4. 🔴 CHECKPOINT · STOP before any China download: show exact title, source, language, version; get explicit permission, then one `download_guideline` call with `confirm_license=true`.
5. Call `search_content` before `extract_content`; use short keyword queries; expand only relevant chunks or pages, never a whole PDF.
6. Cite title, source, version, PDF page, detail URL.

Failure handling:
- No record or ambiguous version → report and stop; never invent identifiers.
- Auth, network, quota, license, non-PDF error → surface the exact category; never retry or switch sources.
- PDF `ocr_required`/indexing failed → report retrieval unavailable; never claim evidence.
- No `search_content` hit → narrow the query or stop; never extract whole-document text.
- Unverified en/zh pairing → label each version independently; never merge records.

Blacklist: no invented IDs/URLs, silent source switches, whole-PDF extraction, or medical advice.

No medical advice; NCCN licensing, China download quota, and site access rules apply.
