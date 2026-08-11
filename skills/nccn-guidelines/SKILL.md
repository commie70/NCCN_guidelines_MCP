---
name: nccn-guidelines
description: Search, download, and cite NCCN Global or NCCN China clinical guidelines; use for English, Chinese, or paired NCCN evidence questions.
---

Use this skill for NCCN evidence questions.

1. Choose `language`: `en`, `zh`, or `paired`; use `source="auto"` unless the user names a site.
2. Call `search_guidelines` first. Preserve its `record_id`; never invent a URL or filename.
3. For China, show the exact title, source, language, and version, then get clear permission before one `download_guideline` call with `confirm_license=true`.
4. Call `search_content` before `extract_content`; expand only relevant chunk IDs or pages, never a whole PDF.
5. Cite title, source, version, PDF page, and detail URL. Keep English and Chinese records separate; paired versions may differ.

Failure handling:
- No record, or missing/ambiguous version → report and stop; do not invent identifiers.
- Auth, network, quota, license, HTML, or non-PDF error → surface the exact category; do not retry or silently switch sources.
- Saved PDF with `ocr_required` or failed indexing → do not claim evidence; report retrieval unavailable.
- No `search_content` hit → narrow the query or stop; never extract whole-document text.
- Unverified English/Chinese pairing → keep records separate and label versions independently.

Do not provide medical advice. Explain that NCCN licensing, China quota limits, and site access rules apply.
