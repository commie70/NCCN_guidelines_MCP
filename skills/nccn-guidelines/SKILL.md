---
name: nccn-guidelines
description: Search, download, and cite NCCN Global or NCCN China clinical guidelines; use for English, Chinese, or paired NCCN evidence questions.
---

Use this skill for NCCN evidence questions.

1. Choose `language`: `en`, `zh`, or `paired`. Use `source="auto"` unless the user asks for a specific site.
2. Call `search_guidelines` first. Keep the returned stable `record_id`; never invent a URL or filename.
3. Before a China download, show the user the exact title, source, language, and version. Call `download_guideline` only after clear permission for that record, with `confirm_license=true`.
4. Call `search_content` before `extract_content`. Expand only the relevant chunk IDs or pages; never request an entire PDF.
5. Cite the title, source, version, PDF page, and detail URL in the final answer. Treat English and Chinese records as separate versions. A paired result may have different English and Chinese versions.

Do not provide medical advice. Explain that NCCN licensing, China quota limits, and site access rules apply.
