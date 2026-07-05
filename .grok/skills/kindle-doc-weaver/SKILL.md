---
name: kindle-doc-weaver
description: Build the Lorecraft docs/ Markdown corpus into a cross-linked, Kindle-ready EPUB and/or PDF and optionally email it as an attachment to a Kindle gateway address. Use when asked to weave, compile, export, publish, upload, send, or email repository Markdown documentation as an e-reader document, especially for docs/*.md and Kindle/Paperwhite delivery.
---

# Kindle Doc Weaver

Use the canonical repo skill at `.agents/skills/kindle-doc-weaver/`.

Run from the repository root:

```bash
python3 .agents/skills/kindle-doc-weaver/scripts/build_kindle_pdf.py \
  --format epub
```

To send through Gmail SMTP to the configured Kindle gateway:

```bash
LORECRAFT_KINDLE_SMTP_PASSWORD='app-password-here' \
python3 .agents/skills/kindle-doc-weaver/scripts/build_kindle_pdf.py \
  --format epub \
  --email
```

Do not commit mail passwords. Use a Gmail app password via `LORECRAFT_KINDLE_SMTP_PASSWORD`, `GMAIL_APP_PASSWORD`, `SMTP_PASSWORD`, `--smtp-password-file`, or the script's secure prompt.
