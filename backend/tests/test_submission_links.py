"""Относительные ссылки пакета сдачи ведут на файлы репозитория."""

from __future__ import annotations

import re
import subprocess

from kontur.evaluation.agent_dumps import repo_root

_LINK = re.compile(r"\[[^\]]*\]\(([^)\s]+)\)")


def test_submission_markdown_links_are_tracked() -> None:
    root = repo_root()
    tracked = set(
        subprocess.check_output(
            ["git", "ls-files"],  # noqa: S607
            cwd=root,
            text=True,
            encoding="utf-8",
        ).splitlines()
    )
    missing: list[str] = []
    for path in sorted((root / "submission").rglob("*.md")):
        for raw in _LINK.findall(path.read_text(encoding="utf-8")):
            target = raw.split("#", 1)[0].strip()
            if not target or target.startswith(("http://", "https://", "mailto:")):
                continue
            resolved = (path.parent / target).resolve()
            relative = resolved.relative_to(root).as_posix().rstrip("/")
            if relative in tracked or any(item.startswith(relative + "/") for item in tracked):
                continue
            missing.append(f"{path.relative_to(root).as_posix()} -> {target}")
    assert missing == []
