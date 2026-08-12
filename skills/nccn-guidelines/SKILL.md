---
name: nccn-guidelines
description: Search, download, and cite English, Chinese, or paired NCCN guidelines.
---

1. Use `language=en|zh|paired`; use `source="auto"` unless the user names a site. Auto: en→Global, zh→China, paired→Global en + China zh; MCP may report same-language fallback.
2. Call `search_guidelines` first in the title's language. Preserve `record_id`; never invent URLs/filenames.
3. Pick an exact title match or list candidates; never blindly take the first hit.
4. 🔴 CHECKPOINT · STOP before a China download: show title, source, language, version; get permission, then call `download_guideline` once with `confirm_license=true`.
5. Call `search_content` before `extract_content`; use short keywords and expand only relevant chunks/pages.
6. Cite title, source, version, PDF page, detail URL.

Failure handling:
- No requested-language record → report what exists and stop; never substitute.
- Cite an auto fallback's actual source. For explicit-source/download errors, state the category; never retry or switch records.
- PDF `ocr_required`/indexing failed → report unavailable; never claim evidence.
- No `search_content` hit → narrow the query or stop; never extract whole-document text.
- Unverified en/zh pairing → label versions independently; never merge records.

Blacklist: invented IDs/URLs, unreported source switches, whole-PDF extraction, medical advice.

No medical advice; NCCN licensing, China download quota, and site rules apply.
