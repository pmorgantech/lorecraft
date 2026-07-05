---
name: kindle-doc-weaver
description: Build the Lorecraft docs/ Markdown corpus into a cross-linked, Kindle-ready EPUB and/or PDF and optionally email it as an attachment to a Kindle gateway address. Use when asked to weave, compile, export, publish, upload, send, or email repository Markdown documentation as an e-reader document, especially for docs/*.md and Kindle/Paperwhite delivery.
---

# Kindle Doc Weaver

Use this skill to turn `docs/*.md` into one linked EPUB/PDF and optionally send it to a Kindle email gateway. Prefer EPUB for Kindle Paperwhite reading because text reflows cleanly on the small e-ink screen; use PDF when exact page layout matters.

## Workflow

1. Run from the repository root.
2. Use `scripts/build_kindle_pdf.py` to build the woven Markdown and EPUB:

```bash
python3 .agents/skills/kindle-doc-weaver/scripts/build_kindle_pdf.py \
  --format epub
```

3. To build both EPUB and PDF, pass `--format both`:

```bash
python3 .agents/skills/kindle-doc-weaver/scripts/build_kindle_pdf.py \
  --format both
```

4. To send to Kindle, provide the Gmail app password through an environment variable or prompt, then pass `--email`:

```bash
LORECRAFT_KINDLE_SMTP_PASSWORD='app-password-here' \
python3 .agents/skills/kindle-doc-weaver/scripts/build_kindle_pdf.py \
  --format epub \
  --email
```

Do not commit or paste real mail passwords into repository files. For Gmail, prefer a Google app password over the account's primary password.
If a local password file is useful, store it as `.agents/skills/kindle-doc-weaver/.apppw` and invoke `--smtp-password-file .agents/skills/kindle-doc-weaver/.apppw`; that path is ignored by git.

## Defaults

- Source docs: `docs/*.md`
- Output directory: `build/kindle-docs/`
- Kindle recipient: `smartattack_GW@kindle.com`
- SMTP sender/user: `smartattack@gmail.com`
- Recommended Paperwhite filename pattern: `lorecraft_YYYYMMDDa.epub`, `lorecraft_YYYYMMDDb.epub`, `lorecraft_YYYYMMDDc.epub`, ...
- Archive/exact-layout filename example: `lorecraft_20260705b.pdf`

If no filename is provided, the script creates the next date-based lettered name for today. It scans `build/kindle-docs/` for existing `lorecraft_YYYYMMDD<letter>.*` outputs and chooses the next suffix after the highest existing letter, considering the companion `.md` plus requested `.epub`/`.pdf` files. For example, if `lorecraft_20260705b.epub` already exists, the next automatic EPUB is `lorecraft_20260705c.epub`.

## Master Doc Selection

Treat `docs/roadmap.md` as the current project state: completed and pending sprints. Treat `docs/architecture.md` as the master engine architecture reference. Keep `docs/implementation_guides.md` near the top as the feature implementation guide unless its content is already better represented by roadmap/architecture links.

Ignore player/operator/world-builder guides in the master Kindle bundle. The scanner skips docs with this frontmatter:

```yaml
---
kindle_doc_weaver: ignore
---
```

The current ignored guides are `user_guide.md`, `admin_builder_guide.md`, and `world_building.md`. The scanner only reads Markdown files, so `news.yaml` and `issues.yaml` are naturally excluded.

## Paperwhite Format Guidance

- **EPUB:** best for Paperwhite; generated directly by Pandoc with no Python PDF module and no PDF engine.
- **EPUB split level:** default to `--epub-split-level 2`. The Kindle will paginate reflowable text on the device; this setting only keeps the EPUB's internal chapter files shorter and more responsive by splitting at `##` sections.
- **PDF:** useful for exact layout/archive. If PDF is requested, prefer `xelatex` through TeX Live for Markdown-heavy technical docs with Unicode and tables. `lualatex` is a reasonable second choice; `pdflatex` is less Unicode-friendly. `weasyprint` is a Python package but depends on native Cairo/Pango libraries and is better for HTML/CSS page rendering than this docs workflow. `wkhtmltopdf` is older WebKit-based HTML rendering. `tectonic` is convenient when available as a single binary, but TeX Live `xelatex` is usually the most predictable Pandoc target.

The script requires `pandoc` for EPUB/PDF output. PDF output additionally requires a Pandoc-compatible PDF engine such as `xelatex`, `lualatex`, `pdflatex`, `tectonic`, `wkhtmltopdf`, or `weasyprint`. If a PDF engine is missing, build `--format epub` or install one of those engines.

## Link Weaving

The script:

- Orders the main Lorecraft docs in a stable reading sequence, with unknown docs appended alphabetically.
- Adds deterministic per-file heading anchors.
- Rewrites local Markdown links such as `architecture.md#module-layout` into internal links in the combined document.
- Leaves external URLs and non-Markdown links unchanged.

## Email Delivery

Use `--email` only after an EPUB/PDF has been built. Password lookup order:

1. `--smtp-password`
2. `--smtp-password-file`
3. `LORECRAFT_KINDLE_SMTP_PASSWORD`
4. `GMAIL_APP_PASSWORD`
5. `SMTP_PASSWORD`
6. Secure interactive prompt

Gmail SMTP uses `smtp.gmail.com:587` with STARTTLS by default. The sending Gmail address must be approved in the target Amazon Kindle account's approved personal document email list.
