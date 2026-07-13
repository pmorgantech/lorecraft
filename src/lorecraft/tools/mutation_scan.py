"""AST inventory of direct SQL/ORM mutation in Tier 2 + composition code.

Rust-port Phase 0 tooling. Enumerates the places where `features/**` and the
composition layers write to persistent state *directly* — bypassing the
`engine/repos/*` seam — so that inventory becomes the conversion backlog for
the Phase 4/5 "route all writes through a typed repository/effect boundary"
work. This is a **diagnostic**, not a gate: it uses best-effort static
heuristics (no type inference), so it deliberately over- and under-reports at
the margins. The point is a reviewable checklist keyed by `file:line`, not a
proof.

Two flagged patterns:

- **session_mutation** — a `.add` / `.delete` / `.commit` / `.flush` / `.exec`
  call on something that looks like a SQLModel/SQLAlchemy `Session`: either the
  explicit `ctx.session.<m>(...)` form, or a `.<m>(...)` call whose receiver is
  a name containing "session" (case-insensitive). Heuristic limits: a `Session`
  stored under a differently-named variable is missed; a `.commit()` on an
  unrelated object whose name happens to contain "session" is a false positive;
  `.exec(<select>)` reads are flagged the same as `.exec(<update/delete>)`
  because distinguishing them needs statement-type inference this tool doesn't
  do. Reviewers triage `.exec` hits by hand.

- **model_attr_write** — an attribute assignment (`obj.attr = ...`, or an
  augmented `obj.attr += ...`) to an object that was, earlier in the same
  function, bound from a `*_repo.get(...)`-style call. Approximates "mutating a
  persisted engine model in place instead of going through a repo method".
  Heuristic limits: only intra-function `x = <...>_repo.get(...)` /
  `.get_or_create(...)` bindings are tracked (no cross-function flow, no
  aliasing), and any later `obj.attr = ...` on that name is flagged regardless
  of whether the attribute is actually persisted.

CLI: `python -m lorecraft.tools.mutation_scan [--root SRC] [--output FILE]
[--format json|markdown]`.
"""

from __future__ import annotations

import argparse
import ast
import json
import sys
from collections.abc import Iterable, Sequence
from dataclasses import asdict, dataclass
from pathlib import Path

# `.exec` is included per the Part A4 spec (it covers `session.exec(<mutating
# stmt>)`); it also matches read `select`s, which reviewers triage by hand.
_SESSION_METHODS = frozenset({"add", "delete", "commit", "flush", "exec"})

# Repo accessors whose result is treated as a persisted model for pattern 2.
_REPO_GETTERS = frozenset({"get", "get_or_create", "one", "first"})

# Default scan roots relative to a `src/lorecraft` tree.
_DEFAULT_SUBPATHS = (
    "features",
    "commands",
    "services/container.py",
    "main.py",
)


@dataclass(frozen=True)
class Finding:
    """One flagged mutation site, keyed by `file:line`."""

    file: str
    line: int
    pattern: str  # "session_mutation" | "model_attr_write"
    detail: str
    snippet: str


def _receiver_is_session(node: ast.expr) -> bool:
    """True if `node` looks like a SQLModel/SQLAlchemy Session receiver.

    Matches the explicit `ctx.session` attribute chain and any `Name`/attribute
    whose final identifier contains "session" (case-insensitive).
    """
    if isinstance(node, ast.Attribute):
        if node.attr == "session":  # ctx.session, self.session, ...
            return True
        return "session" in node.attr.lower()
    if isinstance(node, ast.Name):
        return "session" in node.id.lower()
    return False


class _ModuleScanner(ast.NodeVisitor):
    """Collects findings for one module's AST."""

    def __init__(self, file: str, source_lines: Sequence[str]) -> None:
        self._file = file
        self._lines = source_lines
        self.findings: list[Finding] = []
        # Names bound to a `*_repo.get(...)`-style result in the current function
        # scope. Reset per function so bindings don't leak across functions.
        self._repo_bound: set[str] = set()

    def _snippet(self, lineno: int) -> str:
        if 1 <= lineno <= len(self._lines):
            return self._lines[lineno - 1].strip()
        return ""

    def _add(self, node: ast.AST, pattern: str, detail: str) -> None:
        lineno = getattr(node, "lineno", 0)
        self.findings.append(
            Finding(
                file=self._file,
                line=lineno,
                pattern=pattern,
                detail=detail,
                snippet=self._snippet(lineno),
            )
        )

    def visit_FunctionDef(self, node: ast.FunctionDef) -> None:
        self._visit_function_scope(node)

    def visit_AsyncFunctionDef(self, node: ast.AsyncFunctionDef) -> None:
        self._visit_function_scope(node)

    def _visit_function_scope(
        self, node: ast.FunctionDef | ast.AsyncFunctionDef
    ) -> None:
        # Isolate repo-binding tracking to this function (restore on exit so a
        # nested function doesn't clobber the enclosing scope's bindings).
        outer = self._repo_bound
        self._repo_bound = set()
        for child in node.body:
            self.visit(child)
        self._repo_bound = outer

    def visit_Assign(self, node: ast.Assign) -> None:
        # Track `x = <...>_repo.<getter>(...)` bindings for pattern 2.
        if self._is_repo_get_call(node.value):
            for target in node.targets:
                if isinstance(target, ast.Name):
                    self._repo_bound.add(target.id)
        # Flag `obj.attr = ...` where obj was repo-bound.
        for target in node.targets:
            self._flag_model_attr_write(target)
        self.generic_visit(node)

    def visit_AugAssign(self, node: ast.AugAssign) -> None:
        self._flag_model_attr_write(node.target)
        self.generic_visit(node)

    def _flag_model_attr_write(self, target: ast.expr) -> None:
        if (
            isinstance(target, ast.Attribute)
            and isinstance(target.value, ast.Name)
            and target.value.id in self._repo_bound
        ):
            self._add(
                target,
                "model_attr_write",
                f"in-place write to `{target.value.id}.{target.attr}` on a "
                "repo-fetched model (bypasses a repo method)",
            )

    @staticmethod
    def _is_repo_get_call(value: ast.expr) -> bool:
        return (
            isinstance(value, ast.Call)
            and isinstance(value.func, ast.Attribute)
            and value.func.attr in _REPO_GETTERS
            and _receiver_ends_with_repo(value.func.value)
        )

    def visit_Call(self, node: ast.Call) -> None:
        if (
            isinstance(node.func, ast.Attribute)
            and node.func.attr in _SESSION_METHODS
            and _receiver_is_session(node.func.value)
        ):
            self._add(
                node,
                "session_mutation",
                f"`.{node.func.attr}(...)` on a Session receiver",
            )
        self.generic_visit(node)


def _receiver_ends_with_repo(node: ast.expr) -> bool:
    """True if the call receiver's final identifier ends with `_repo` or is a
    `*Repo(...)` construction (e.g. `ctx.item_repo`, `BankRepo(session)`)."""
    if isinstance(node, ast.Attribute):
        return node.attr.endswith("_repo") or node.attr.endswith("Repo")
    if isinstance(node, ast.Name):
        return node.id.endswith("_repo") or node.id.endswith("Repo")
    if isinstance(node, ast.Call):
        return _receiver_ends_with_repo(node.func)
    return False


def scan_source(source: str, file: str) -> list[Finding]:
    """Scan one module's source text; return its findings."""
    tree = ast.parse(source, filename=file)
    scanner = _ModuleScanner(file, source.splitlines())
    scanner.visit(tree)
    return sorted(scanner.findings, key=lambda f: (f.line, f.pattern))


def _iter_python_files(root: Path, subpaths: Iterable[str]) -> list[Path]:
    files: list[Path] = []
    for sub in subpaths:
        target = root / sub
        if target.is_dir():
            files.extend(sorted(target.rglob("*.py")))
        elif target.is_file():
            files.append(target)
    return files


def scan_tree(root: Path, subpaths: Iterable[str] = _DEFAULT_SUBPATHS) -> list[Finding]:
    """Scan every Python file under the configured Tier 2 + composition paths."""
    findings: list[Finding] = []
    for path in _iter_python_files(root, subpaths):
        try:
            source = path.read_text(encoding="utf-8")
        except OSError:
            continue
        findings.extend(scan_source(source, str(path.relative_to(root))))
    return findings


def render_markdown(findings: Sequence[Finding]) -> str:
    """A grouped-by-file markdown checklist of the findings."""
    lines = ["# Direct SQL/ORM mutation inventory", ""]
    lines.append(f"{len(findings)} finding(s).")
    lines.append("")
    lines.append("| file:line | pattern | detail | snippet |")
    lines.append("| --- | --- | --- | --- |")
    for finding in findings:
        snippet = finding.snippet.replace("|", "\\|")
        lines.append(
            f"| `{finding.file}:{finding.line}` | {finding.pattern} | "
            f"{finding.detail} | `{snippet}` |"
        )
    return "\n".join(lines) + "\n"


def render_json(findings: Sequence[Finding]) -> str:
    payload = {
        "count": len(findings),
        "findings": [asdict(finding) for finding in findings],
    }
    return json.dumps(payload, indent=2) + "\n"


def _default_root() -> Path:
    # This file lives at src/lorecraft/tools/mutation_scan.py; the scan root is
    # the `src/lorecraft` package directory two levels up.
    return Path(__file__).resolve().parent.parent


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="python -m lorecraft.tools.mutation_scan",
        description="AST inventory of direct SQL/ORM mutation in Tier 2 + composition code.",
    )
    parser.add_argument(
        "--root",
        type=Path,
        default=_default_root(),
        help="package root to scan (default: the installed lorecraft package)",
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=None,
        help="write the report here instead of stdout",
    )
    parser.add_argument(
        "--format",
        choices=("json", "markdown"),
        default="json",
    )
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = _build_parser().parse_args(argv)
    findings = scan_tree(args.root)
    report = (
        render_markdown(findings)
        if args.format == "markdown"
        else render_json(findings)
    )
    if args.output is not None:
        args.output.write_text(report, encoding="utf-8")
        print(f"{len(findings)} finding(s) -> {args.output}", file=sys.stderr)
    else:
        sys.stdout.write(report)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
