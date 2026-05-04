"""One-time migration helper for files written under the old H2 convention.

Until the H1 cutover, granola-sync rendered tool sections at H2 (``## Notes``,
``## Enhanced Notes``, etc.) and the legacy vault template used a ``# Notes``
H1 wrapper for user prep content. After the cutover, top-level sections are
all H1 and prep content lives under ``# Prep Notes``.

This module bumps existing files into the new convention. The migration is
idempotent — running it on an already-migrated file produces no changes.

Migration rules (applied in order to each file body, NOT frontmatter):

  1. **Drop legacy title H1.** If the body has an H1 line whose text equals
     the frontmatter ``meeting-title`` value, remove it. The old template
     emitted ``# {title}`` as the first body line; the new template doesn't.
     Filename + frontmatter already carry the title.

  2. **Rename legacy ``# Notes`` to ``# Prep Notes``.** The old vault template
     used ``# Notes`` as the prep-content H1 wrapper. Under the new
     convention, ``# Notes`` is a tool-owned section, so the legacy H1 must
     be renamed to ``# Prep Notes`` before tool sections are processed.

  3. **Bump tool-section H2s to H1.** Headings of exactly the form
     ``## (Notes|Enhanced Notes|Transcript|Meeting Summary|Prep Notes)`` get
     promoted to ``# X``. Other H2s (e.g. ``## General Banter`` user prep
     sub-headings) are left alone.

The dry-run / apply flow is exposed via the ``migrate-headings`` CLI
subcommand in ``__main__.py``.
"""

from __future__ import annotations

import os
import re
from dataclasses import dataclass, field
from typing import Optional

_FRONTMATTER_RE = re.compile(r"\A(---\n.*?\n---\n?)", re.DOTALL)
_TITLE_FIELD_RE = re.compile(r"^meeting-title[ \t]*:[ \t]*([^\n]*?)[ \t]*$", re.MULTILINE)

_TOOL_SECTION_NAMES = ("Notes", "Enhanced Notes", "Transcript", "Meeting Summary", "Prep Notes")
_TOOL_SECTION_PATTERN = "|".join(re.escape(n) for n in _TOOL_SECTION_NAMES)
_H2_TOOL_RE = re.compile(rf"^## ({_TOOL_SECTION_PATTERN})[ \t]*$", re.MULTILINE)
_LEGACY_NOTES_H1_RE = re.compile(r"^# Notes[ \t]*$", re.MULTILINE)


@dataclass
class FileChanges:
    """Summary of what migrate_file would change for a single file."""
    path: str = ""
    dropped_title_h1: bool = False
    renamed_legacy_notes_h1: bool = False
    bumped_tool_sections: list[str] = field(default_factory=list)

    @property
    def changed(self) -> bool:
        return (
            self.dropped_title_h1
            or self.renamed_legacy_notes_h1
            or bool(self.bumped_tool_sections)
        )

    def summary_lines(self) -> list[str]:
        out: list[str] = []
        if self.dropped_title_h1:
            out.append("dropped legacy title H1")
        if self.renamed_legacy_notes_h1:
            out.append("renamed legacy `# Notes` to `# Prep Notes`")
        if self.bumped_tool_sections:
            joined = ", ".join(f"`# {n}`" for n in self.bumped_tool_sections)
            out.append(f"bumped tool sections to H1: {joined}")
        return out


def migrate_file(content: str) -> tuple[str, FileChanges]:
    """Apply migration rules to a file's full text. Returns ``(new_content,
    changes)``. Idempotent — re-running on the result is a no-op.
    """
    changes = FileChanges()

    fm_match = _FRONTMATTER_RE.match(content)
    if fm_match:
        frontmatter = fm_match.group(1)
        body = content[fm_match.end():]
    else:
        frontmatter = ""
        body = content

    title = _extract_meeting_title(frontmatter)
    if title:
        title_h1_re = re.compile(rf"^# {re.escape(title)}[ \t]*$", re.MULTILINE)
        new_body, n = title_h1_re.subn("", body, count=1)
        if n:
            new_body = re.sub(r"\n{3,}", "\n\n", new_body)
            new_body = new_body.lstrip("\n")
            if not new_body.startswith("\n"):
                new_body = "\n" + new_body
            body = new_body
            changes.dropped_title_h1 = True

    # Only rename legacy `# Notes` to `# Prep Notes` when there's no
    # `# Prep Notes` already in the file. If both exist, `# Notes` is a tool
    # section (post-migration state), not the legacy prep container.
    if not re.search(r"^# Prep Notes[ \t]*$", body, re.MULTILINE):
        new_body, n = _LEGACY_NOTES_H1_RE.subn("# Prep Notes", body, count=1)
        if n:
            body = new_body
            changes.renamed_legacy_notes_h1 = True

    bumped: list[str] = []
    def _bump(m: re.Match) -> str:
        bumped.append(m.group(1))
        return f"# {m.group(1)}"
    body = _H2_TOOL_RE.sub(_bump, body)
    if bumped:
        changes.bumped_tool_sections = bumped

    return frontmatter + body, changes


def migrate_folder(folder: str, apply: bool = False) -> list[FileChanges]:
    """Walk ``folder`` recursively, run ``migrate_file`` on each ``.md``
    file, and optionally write changes back. Returns the per-file change
    summary list (only files with any change are included).

    Files whose basename starts with ``*`` are skipped — that's the Obsidian
    convention for index / aggregator files (``*Summary.md``, ``*Home.md``,
    etc.) which are NOT meeting notes and shouldn't have tool-section
    headings bumped.
    """
    results: list[FileChanges] = []
    if not os.path.isdir(folder):
        return results

    for root, _dirs, files in os.walk(folder):
        for name in sorted(files):
            if not name.endswith(".md") or name.startswith("*"):
                continue
            path = os.path.join(root, name)
            try:
                with open(path, "r", encoding="utf-8") as f:
                    original = f.read()
            except (OSError, UnicodeDecodeError):
                continue

            new_content, changes = migrate_file(original)
            if not changes.changed:
                continue
            changes.path = path
            results.append(changes)

            if apply and new_content != original:
                with open(path, "w", encoding="utf-8") as f:
                    f.write(new_content)
    return results


def _extract_meeting_title(frontmatter: str) -> Optional[str]:
    m = _TITLE_FIELD_RE.search(frontmatter)
    if not m:
        return None
    raw = m.group(1).strip()
    if len(raw) >= 2 and raw[0] == raw[-1] and raw[0] in ('"', "'"):
        raw = raw[1:-1]
    return raw or None
