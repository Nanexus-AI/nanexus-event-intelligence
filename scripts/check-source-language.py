#!/usr/bin/env python3
"""Reject Han characters in source comments and Python docstrings."""

from __future__ import annotations

import ast
import io
from pathlib import Path
import re
import subprocess
import sys
import tokenize


ROOT = Path(__file__).resolve().parent.parent
HAN = re.compile(r"[\u3400-\u4dbf\u4e00-\u9fff\uf900-\ufaff]")
PYTHON_SUFFIXES = {".py", ".pyi"}
SLASH_COMMENT_SUFFIXES = {".c", ".cc", ".cpp", ".css", ".go", ".h", ".hpp", ".js", ".jsx", ".rs", ".ts", ".tsx"}
HASH_COMMENT_SUFFIXES = {".env", ".ini", ".sh", ".toml", ".yaml", ".yml"}
ROOT_SOURCE_FILES = {".env.example", "Dockerfile", "Makefile", "compose.demo.yaml", "compose.yaml"}
SOURCE_PREFIXES = (".github/", "backend/", "scripts/", "web/")
IGNORED_DIRECTORIES = {
    ".git",
    ".mypy_cache",
    ".pytest_cache",
    ".ruff_cache",
    ".venv",
    "dist",
    "node_modules",
    "release",
}
BILINGUAL_PREFIXES = ("docs/architecture/", "docs/runbooks/")


def repository_files() -> list[str]:
    result = subprocess.run(
        ["git", "ls-files", "--cached", "--others", "--exclude-standard"],
        cwd=ROOT,
        capture_output=True,
        text=True,
    )
    if result.returncode == 0:
        return result.stdout.splitlines()
    return [
        str(path.relative_to(ROOT))
        for path in ROOT.rglob("*")
        if path.is_file() and not any(part in IGNORED_DIRECTORIES for part in path.parts)
    ]


def tracked_source_files() -> list[Path]:
    files: list[Path] = []
    for relative in repository_files():
        path = Path(relative)
        if relative not in ROOT_SOURCE_FILES and not relative.startswith(SOURCE_PREFIXES):
            continue
        if path.name.startswith("Dockerfile") or path.suffix in (
            PYTHON_SUFFIXES | SLASH_COMMENT_SUFFIXES | HASH_COMMENT_SUFFIXES
        ):
            files.append(ROOT / path)
    return files


def bilingual_documents() -> list[Path]:
    documents: list[Path] = []
    for relative in repository_files():
        is_named_bilingual_document = (
            relative.endswith("/README.md")
            or relative.endswith("/architecture.md")
            or relative.endswith("-runbook.md")
        )
        if is_named_bilingual_document or (
            relative.endswith(".md") and relative.startswith(BILINGUAL_PREFIXES)
        ):
            documents.append(ROOT / relative)
    return documents


def python_violations(path: Path, text: str) -> list[tuple[int, str]]:
    violations: list[tuple[int, str]] = []
    try:
        tokens = tokenize.generate_tokens(io.StringIO(text).readline)
        for token in tokens:
            if token.type == tokenize.COMMENT and HAN.search(token.string):
                violations.append((token.start[0], token.string.strip()))
        tree = ast.parse(text, filename=str(path))
    except (SyntaxError, tokenize.TokenError) as error:
        raise RuntimeError(f"cannot parse {path.relative_to(ROOT)}: {error}") from error

    for node in ast.walk(tree):
        if not isinstance(node, (ast.Module, ast.ClassDef, ast.FunctionDef, ast.AsyncFunctionDef)):
            continue
        docstring = ast.get_docstring(node, clean=False)
        if docstring and HAN.search(docstring) and node.body:
            violations.append((node.body[0].lineno, docstring.splitlines()[0]))
    return violations


def slash_comment_violations(text: str) -> list[tuple[int, str]]:
    violations: list[tuple[int, str]] = []
    index = 0
    line = 1
    state = "code"
    comment_line = 1
    comment: list[str] = []
    quote = ""

    def finish_comment() -> None:
        value = "".join(comment).strip()
        if HAN.search(value):
            violations.append((comment_line, value.splitlines()[0]))
        comment.clear()

    while index < len(text):
        char = text[index]
        nxt = text[index + 1] if index + 1 < len(text) else ""
        if state == "code":
            if char in {"'", '"', "`"}:
                state, quote = "string", char
            elif char == "/" and nxt == "/":
                state, comment_line = "line-comment", line
                index += 1
            elif char == "/" and nxt == "*":
                state, comment_line = "block-comment", line
                index += 1
        elif state == "string":
            if char == "\\":
                index += 1
            elif char == quote:
                state = "code"
        elif state == "line-comment":
            if char == "\n":
                finish_comment()
                state = "code"
            else:
                comment.append(char)
        elif state == "block-comment":
            if char == "*" and nxt == "/":
                finish_comment()
                state = "code"
                index += 1
            else:
                comment.append(char)
        if char == "\n":
            line += 1
        index += 1
    if state in {"line-comment", "block-comment"}:
        finish_comment()
    return violations


def hash_comment_violations(text: str) -> list[tuple[int, str]]:
    violations: list[tuple[int, str]] = []
    for line_number, line in enumerate(text.splitlines(), 1):
        stripped = line.lstrip()
        if stripped.startswith("#") and HAN.search(stripped):
            violations.append((line_number, stripped))
    return violations


def main() -> int:
    violations: list[str] = []
    for path in tracked_source_files():
        text = path.read_text(encoding="utf-8")
        if path.suffix in PYTHON_SUFFIXES:
            found = python_violations(path, text)
        elif path.suffix in SLASH_COMMENT_SUFFIXES:
            found = slash_comment_violations(text)
        else:
            found = hash_comment_violations(text)
        for line, excerpt in found:
            violations.append(f"{path.relative_to(ROOT)}:{line}: {excerpt}")

    for path in bilingual_documents():
        text = path.read_text(encoding="utf-8")
        if "English" not in text or not HAN.search(text):
            violations.append(
                f"{path.relative_to(ROOT)}: bilingual English/Chinese content is required"
            )

    english_readme = ROOT / "README.md"
    chinese_readme = ROOT / "README.zh-CN.md"
    if not english_readme.is_file() or not chinese_readme.is_file():
        violations.append("README.md and README.zh-CN.md are both required")
    else:
        english_text = english_readme.read_text(encoding="utf-8")
        chinese_text = chinese_readme.read_text(encoding="utf-8")
        if "[简体中文](./README.zh-CN.md)" not in english_text:
            violations.append("README.md: missing link to README.zh-CN.md")
        if "[English](./README.md)" not in chinese_text:
            violations.append("README.zh-CN.md: missing link to README.md")
        english_without_language_link = english_text.replace(
            "English | [简体中文](./README.zh-CN.md)", ""
        )
        if HAN.search(english_without_language_link):
            violations.append("README.md: Han characters are allowed only in the language link")
        if not HAN.search(chinese_text):
            violations.append("README.zh-CN.md: Chinese content is required")

    if violations:
        print(
            "Language policy check failed; source comments/docstrings must use English "
            "and designated documents must be bilingual:",
            file=sys.stderr,
        )
        print("\n".join(violations), file=sys.stderr)
        return 1
    print("Language policy check passed")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
