"""Относительные ссылки публичных Markdown ведут на файлы репозитория."""

from __future__ import annotations

import re
import subprocess

from kontur.evaluation.agent_dumps import repo_root

_LINK = re.compile(r"\[[^\]]*\]\(([^)\s]+)\)|href=\"([^\"]+)\"|src=\"([^\"]+)\"")
_PUBLIC = ("README.md", "docs/", "submission/", "data/", "examples/")


def test_public_markdown_links_are_tracked() -> None:
    root = repo_root()
    tracked = subprocess.check_output(
        ["git", "ls-files"],  # noqa: S607
        cwd=root,
        text=True,
        encoding="utf-8",
    ).splitlines()
    files = set(tracked)
    folders = {
        "/".join(item.split("/")[:depth])
        for item in tracked
        for depth in range(1, item.count("/") + 1)
    }
    missing: list[str] = []
    for relative in tracked:
        if not relative.endswith(".md") or not relative.startswith(_PUBLIC):
            continue
        path = root / relative
        for match in _LINK.finditer(path.read_text(encoding="utf-8")):
            raw = next(group for group in match.groups() if group)
            target = raw.split("#", 1)[0].strip()
            if not target or target.startswith(("http://", "https://", "mailto:")):
                continue
            resolved = (path.parent / target).resolve().relative_to(root).as_posix().rstrip("/")
            if resolved not in files and resolved not in folders:
                missing.append(f"{relative} -> {raw}")
    assert missing == []
