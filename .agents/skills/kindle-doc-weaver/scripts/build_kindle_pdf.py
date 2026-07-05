#!/usr/bin/env python3
"""Build cross-linked Lorecraft docs for Kindle and optionally email them."""

from __future__ import annotations

import argparse
import datetime as dt
import getpass
import os
import re
import shutil
import smtplib
import subprocess
import sys
import tempfile
from email.message import EmailMessage
from mimetypes import guess_type
from pathlib import Path
from urllib.parse import unquote


DEFAULT_KINDLE_TO = "smartattack_GW@kindle.com"
DEFAULT_SMTP_USER = "smartattack@gmail.com"
DEFAULT_DOC_ORDER = [
    "roadmap.md",
    "architecture.md",
    "implementation_guides.md",
    "architecture_tiers.md",
    "tier_split_refactor.md",
    "engine_core.md",
    "tier_modules.md",
    "feature-registration.md",
    "command_parser.md",
    "parser_and_commands.md",
    "tooling_infrastructure.md",
    "inventory_equipment.md",
    "trade_economy.md",
    "transit_systems.md",
    "dialogue_npcs_quests.md",
    "player_authentication.md",
    "disconnect_handling.md",
    "world_versioning_changesets.md",
    "combat_system.md",
    "death_resurrection.md",
    "wishlist.md",
]
DEFAULT_IGNORED_DOCS = {
    "admin_builder_guide.md",
    "user_guide.md",
    "world_building.md",
}
PDF_ENGINES = (
    "xelatex",
    "lualatex",
    "pdflatex",
    "tectonic",
    "wkhtmltopdf",
    "weasyprint",
)


def slugify(value: str) -> str:
    value = re.sub(r"\{#[A-Za-z0-9_.:-]+\}\s*$", "", value).strip().lower()
    value = value.replace("&", " ")
    value = re.sub(r"`([^`]+)`", r"\1", value)
    value = re.sub(r"<[^>]+>", "", value)
    value = re.sub(r"[^a-z0-9 _.-]+", "", value)
    value = re.sub(r"[\s_.-]+", "-", value).strip("-")
    return value or "section"


def normalize_fragment(fragment: str) -> str:
    return slugify(unquote(fragment).lstrip("#"))


def split_frontmatter(text: str) -> tuple[dict[str, str], list[str]]:
    lines = text.splitlines()
    if not lines or lines[0].strip() != "---":
        return {}, lines

    for index, line in enumerate(lines[1:], start=1):
        if line.strip() != "---":
            continue
        metadata: dict[str, str] = {}
        for entry in lines[1:index]:
            key, separator, value = entry.partition(":")
            if separator:
                metadata[key.strip()] = value.strip().strip("\"'")
        return metadata, lines[index + 1 :]

    return {}, lines


def read_markdown(path: Path) -> tuple[dict[str, str], list[str]]:
    return split_frontmatter(path.read_text(encoding="utf-8"))


def ignored_by_frontmatter(metadata: dict[str, str]) -> bool:
    values = [
        metadata.get("kindle_doc_weaver"),
        metadata.get("kindle-doc-weaver"),
        metadata.get("doc_weaver"),
        metadata.get("doc-weaver"),
    ]
    return any((value or "").lower() in {"ignore", "skip", "false"} for value in values)


def title_from_markdown(path: Path) -> str:
    _, lines = read_markdown(path)
    for line in lines:
        match = re.match(r"^#\s+(.+?)\s*$", line)
        if match:
            return re.sub(r"\s*\{#[^}]+\}\s*$", "", match.group(1)).strip()
    return path.stem.replace("_", " ").replace("-", " ").title()


def doc_id(path: Path) -> str:
    return slugify(path.stem)


def ordered_docs(docs_dir: Path) -> list[Path]:
    existing = {
        path.name: path
        for path in docs_dir.glob("*.md")
        if path.name not in DEFAULT_IGNORED_DOCS
        and not ignored_by_frontmatter(read_markdown(path)[0])
    }
    ordered = [existing[name] for name in DEFAULT_DOC_ORDER if name in existing]
    remaining = [
        path for name, path in sorted(existing.items()) if name not in DEFAULT_DOC_ORDER
    ]
    return ordered + remaining


def rewrite_links(line: str, current_doc: str, known_docs: dict[str, str]) -> str:
    pattern = re.compile(r"(?<!!)\[([^\]]+)\]\(([^)]+)\)")

    def replace(match: re.Match[str]) -> str:
        label, target = match.groups()
        if re.match(r"^[a-z][a-z0-9+.-]*:", target, re.IGNORECASE):
            return match.group(0)
        if target.startswith("#"):
            return f"[{label}](#{current_doc}-{normalize_fragment(target)})"

        base, sep, fragment = target.partition("#")
        base_path = unquote(base).split("?", 1)[0]
        if not base_path.endswith(".md"):
            return match.group(0)

        target_name = Path(base_path).name
        target_doc = known_docs.get(target_name)
        if target_doc is None:
            return match.group(0)
        if sep:
            return f"[{label}](#{target_doc}-{normalize_fragment(fragment)})"
        return f"[{label}](#{target_doc})"

    return pattern.sub(replace, line)


def rewrite_links_in_lines(
    lines: list[str], current_doc: str, known_docs: dict[str, str]
) -> list[str]:
    in_fence = False
    output: list[str] = []
    for line in lines:
        if re.match(r"^\s*(```|~~~)", line):
            in_fence = not in_fence
            output.append(line)
            continue
        output.append(
            line if in_fence else rewrite_links(line, current_doc, known_docs)
        )
    return output


def add_heading_ids(lines: list[str], current_doc: str) -> list[str]:
    seen: dict[str, int] = {}
    output: list[str] = []
    in_fence = False
    for line in lines:
        if re.match(r"^\s*(```|~~~)", line):
            in_fence = not in_fence
            output.append(line)
            continue
        if in_fence:
            output.append(line)
            continue
        match = re.match(r"^(#{1,6})\s+(.+?)\s*$", line)
        if not match:
            output.append(line)
            continue
        hashes, heading = match.groups()
        clean_heading = re.sub(r"\s*\{#[^}]+\}\s*$", "", heading).strip()
        base = f"{current_doc}-{slugify(clean_heading)}"
        count = seen.get(base, 0)
        seen[base] = count + 1
        anchor = base if count == 0 else f"{base}-{count + 1}"
        output.append(f"{hashes} {clean_heading} {{#{anchor}}}")
    return output


def weave_docs(docs: list[Path], title: str) -> str:
    known_docs = {path.name: doc_id(path) for path in docs}
    generated = dt.datetime.now().astimezone().strftime("%Y-%m-%d %H:%M %Z")
    parts = [
        "---",
        f'title: "{title}"',
        f'date: "{generated}"',
        "lang: en-US",
        "geometry: margin=0.75in",
        "---",
        "",
        f"# {title}",
        "",
        f"Generated from Lorecraft `docs/*.md` on {generated}.",
        "",
    ]

    for path in docs:
        current_doc = doc_id(path)
        title_line = title_from_markdown(path)
        _, raw_lines = read_markdown(path)
        lines = add_heading_ids(raw_lines, current_doc)
        lines = rewrite_links_in_lines(lines, current_doc, known_docs)
        if lines and re.match(r"^#\s+", lines[0]):
            lines[0] = f"# {title_line} {{#{current_doc}}}"
        else:
            lines.insert(0, f"# {title_line} {{#{current_doc}}}")
        parts.extend(["\\newpage", "", *lines, ""])

    return "\n".join(parts).rstrip() + "\n"


def split_pipe_row(line: str) -> list[str]:
    line = line.strip()
    if line.startswith("|"):
        line = line[1:]
    if line.endswith("|"):
        line = line[:-1]
    return [cell.strip() for cell in line.split("|")]


def is_table_separator(line: str) -> bool:
    cells = split_pipe_row(line)
    if not cells:
        return False
    return all(re.fullmatch(r":?-{3,}:?", cell.replace(" ", "")) for cell in cells)


def is_pipe_table_start(lines: list[str], index: int) -> bool:
    if index + 1 >= len(lines):
        return False
    return "|" in lines[index] and is_table_separator(lines[index + 1])


def convert_pipe_tables_to_lists(markdown: str) -> str:
    lines = markdown.splitlines()
    output: list[str] = []
    index = 0
    in_fence = False

    while index < len(lines):
        line = lines[index]
        if re.match(r"^\s*(```|~~~)", line):
            in_fence = not in_fence
            output.append(line)
            index += 1
            continue
        if in_fence or not is_pipe_table_start(lines, index):
            output.append(line)
            index += 1
            continue

        headers = split_pipe_row(lines[index])
        index += 2
        rows: list[list[str]] = []
        while index < len(lines) and "|" in lines[index].strip():
            rows.append(split_pipe_row(lines[index]))
            index += 1

        output.append("")
        output.append(
            "<!-- kindle-doc-weaver: table converted for small e-ink screens -->"
        )
        for row in rows:
            row = [*row, *([""] * max(0, len(headers) - len(row)))]
            primary = row[0] if row else ""
            primary_header = headers[0] if headers else "Item"
            output.append(f"- **{primary_header}:** {primary}".rstrip())
            for header, value in zip(headers[1:], row[1:], strict=False):
                if value:
                    output.append(f"  - **{header}:** {value}")
        output.append("")

    return "\n".join(output).rstrip() + "\n"


def kindle_epub_css() -> str:
    return """
body {
  line-height: 1.35;
}
table {
  border-collapse: collapse;
  font-size: 0.82em;
  max-width: 100%;
  table-layout: fixed;
  width: 100%;
}
th,
td {
  overflow-wrap: anywhere;
  padding: 0.15em 0.25em;
  vertical-align: top;
  word-break: break-word;
}
pre {
  font-size: 0.78em;
  overflow-wrap: anywhere;
  white-space: pre-wrap;
}
code {
  overflow-wrap: anywhere;
}
ul,
ol {
  margin-left: 1em;
  padding-left: 1em;
}
""".strip()


def unique_output_stem(output_dir: Path, today: dt.date, extensions: list[str]) -> str:
    stem = f"lorecraft_{today:%Y%m%d}"
    existing_suffixes = {
        match.group(1)
        for path in output_dir.iterdir()
        if (match := re.match(rf"^{re.escape(stem)}([a-z])\.", path.name))
    }
    start_code = ord(max(existing_suffixes)) + 1 if existing_suffixes else ord("a")
    reserved = [*extensions, "md"]
    for code in range(start_code, ord("z") + 1):
        candidate = f"{stem}{chr(code)}"
        if not any(
            (output_dir / f"{candidate}.{extension}").exists() for extension in reserved
        ):
            return candidate
    index = 2
    while True:
        candidate = f"{stem}_{index}"
        if not any(
            (output_dir / f"{candidate}.{extension}").exists() for extension in reserved
        ):
            return candidate
        index += 1


def find_pdf_engine(requested: str | None) -> str | None:
    if requested:
        return requested if shutil.which(requested) else None
    for engine in PDF_ENGINES:
        if shutil.which(engine):
            return engine
    return None


def run_pandoc(
    markdown_path: Path,
    output_path: Path,
    toc_depth: int,
    pdf_engine: str | None,
    epub_split_level: int,
    epub_table_mode: str,
) -> None:
    pandoc_input = markdown_path
    temp_dir: tempfile.TemporaryDirectory[str] | None = None
    command = [
        "pandoc",
        str(pandoc_input),
        "--from",
        "markdown+smart",
        "--toc",
        f"--toc-depth={toc_depth}",
        "--number-sections",
        "-o",
        str(output_path),
    ]
    if output_path.suffix == ".epub":
        temp_dir = tempfile.TemporaryDirectory()
        temp_path = Path(temp_dir.name)
        css_path = temp_path / "kindle-paperwhite.css"
        css_path.write_text(kindle_epub_css(), encoding="utf-8")
        if epub_table_mode == "lists":
            epub_markdown_path = temp_path / markdown_path.name
            epub_markdown_path.write_text(
                convert_pipe_tables_to_lists(markdown_path.read_text(encoding="utf-8")),
                encoding="utf-8",
            )
            pandoc_input = epub_markdown_path
            command[1] = str(pandoc_input)
        command.extend(
            [
                "--standalone",
                "--to",
                "epub3",
                f"--split-level={epub_split_level}",
                "--css",
                str(css_path),
            ]
        )
    elif pdf_engine:
        command.extend(["--pdf-engine", pdf_engine])
    try:
        subprocess.run(command, check=True)
    finally:
        if temp_dir is not None:
            temp_dir.cleanup()


def smtp_password(args: argparse.Namespace) -> str:
    if args.smtp_password:
        return args.smtp_password
    if args.smtp_password_file:
        return Path(args.smtp_password_file).read_text(encoding="utf-8").strip()
    for name in (
        "LORECRAFT_KINDLE_SMTP_PASSWORD",
        "GMAIL_APP_PASSWORD",
        "SMTP_PASSWORD",
    ):
        value = os.environ.get(name)
        if value:
            return value
    return getpass.getpass(f"SMTP password for {args.smtp_user}: ")


def send_email(attachment_paths: list[Path], args: argparse.Namespace) -> None:
    msg = EmailMessage()
    msg["From"] = args.from_address or args.smtp_user
    msg["To"] = args.kindle_to
    msg["Subject"] = args.subject or ", ".join(path.name for path in attachment_paths)
    msg.set_content(args.body or "Lorecraft documentation attached.")

    for path in attachment_paths:
        mime_type, _ = guess_type(path.name)
        if mime_type is None and path.suffix == ".epub":
            mime_type = "application/epub+zip"
        if mime_type is None:
            mime_type = "application/octet-stream"
        maintype, subtype = mime_type.split("/", 1)
        msg.add_attachment(
            path.read_bytes(),
            maintype=maintype,
            subtype=subtype,
            filename=path.name,
        )

    with smtplib.SMTP(args.smtp_host, args.smtp_port) as smtp:
        smtp.starttls()
        smtp.login(args.smtp_user, smtp_password(args))
        smtp.send_message(msg)


def parse_args(argv: list[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repo-root", type=Path, default=Path.cwd())
    parser.add_argument("--docs-dir", type=Path, default=None)
    parser.add_argument("--output-dir", type=Path, default=None)
    parser.add_argument(
        "--format",
        choices=("pdf", "epub", "both"),
        default="pdf",
        help="Output format to build. EPUB is best for Kindle Paperwhite reading.",
    )
    parser.add_argument(
        "--filename", help="Output filename, e.g. lorecraft_20260705b.epub"
    )
    parser.add_argument("--title", default="Lorecraft Documentation")
    parser.add_argument("--toc-depth", type=int, default=3)
    parser.add_argument(
        "--epub-split-level",
        type=int,
        default=2,
        help="EPUB chunk split heading level. 2 keeps Kindle chapters responsive.",
    )
    parser.add_argument(
        "--epub-table-mode",
        choices=("lists", "css"),
        default="lists",
        help="Use lists for Paperwhite-readable tables or css to preserve tables.",
    )
    parser.add_argument("--pdf-engine", help="Pandoc PDF engine to use")
    parser.add_argument(
        "--skip-pdf", action="store_true", help="Only write the woven Markdown"
    )
    parser.add_argument(
        "--email", action="store_true", help="Email the generated PDF to Kindle"
    )
    parser.add_argument("--kindle-to", default=DEFAULT_KINDLE_TO)
    parser.add_argument("--smtp-user", default=DEFAULT_SMTP_USER)
    parser.add_argument("--from-address")
    parser.add_argument("--smtp-host", default="smtp.gmail.com")
    parser.add_argument("--smtp-port", type=int, default=587)
    parser.add_argument("--smtp-password")
    parser.add_argument("--smtp-password-file")
    parser.add_argument("--subject")
    parser.add_argument("--body")
    return parser.parse_args(argv)


def main(argv: list[str]) -> int:
    args = parse_args(argv)
    repo_root = args.repo_root.resolve()
    docs_dir = (args.docs_dir or repo_root / "docs").resolve()
    output_dir = (args.output_dir or repo_root / "build" / "kindle-docs").resolve()
    output_dir.mkdir(parents=True, exist_ok=True)

    docs = ordered_docs(docs_dir)
    if not docs:
        print(f"No Markdown files found in {docs_dir}", file=sys.stderr)
        return 2

    formats = ["pdf", "epub"] if args.format == "both" else [args.format]
    filename = args.filename
    if filename:
        requested_path = Path(filename)
        if requested_path.suffix:
            stem = requested_path.stem
            requested_extension = requested_path.suffix.lstrip(".")
            if requested_extension not in {"pdf", "epub"}:
                print(
                    f"Unsupported output extension: .{requested_extension}",
                    file=sys.stderr,
                )
                return 2
            if args.format != "both" and requested_extension != args.format:
                formats = [requested_extension]
        else:
            stem = requested_path.name
    else:
        stem = unique_output_stem(output_dir, dt.date.today(), formats)

    output_paths = [output_dir / f"{stem}.{extension}" for extension in formats]
    markdown_path = output_dir / f"{stem}.md"

    markdown_path.write_text(weave_docs(docs, args.title), encoding="utf-8")
    print(f"Wrote woven Markdown: {markdown_path}")

    if args.skip_pdf:
        print("Skipped PDF generation.")
        return 0

    if not shutil.which("pandoc"):
        print(
            "pandoc is required to build EPUB/PDF output; install pandoc and rerun.",
            file=sys.stderr,
        )
        return 3

    engine: str | None = None
    if "pdf" in formats:
        engine = find_pdf_engine(args.pdf_engine)
        if engine is None:
            engines = ", ".join(PDF_ENGINES)
            print(f"No PDF engine found. Install one of: {engines}.", file=sys.stderr)
            return 3

    for output_path in output_paths:
        run_pandoc(
            markdown_path,
            output_path,
            args.toc_depth,
            engine,
            args.epub_split_level,
            args.epub_table_mode,
        )
        print(f"Wrote {output_path.suffix.lstrip('.').upper()}: {output_path}")

    if args.email:
        send_email(output_paths, args)
        names = ", ".join(path.name for path in output_paths)
        print(f"Sent {names} to {args.kindle_to}")

    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
