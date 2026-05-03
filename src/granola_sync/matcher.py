"""Find an existing Obsidian note that corresponds to a Granola meeting.

Matching uses two frontmatter fields:

  - ``meeting-title`` must equal the Granola meeting's title (case-insensitive,
    trimmed). This is the primary match key.
  - ``date`` acts as a filter for recurring meetings: a candidate is only kept
    when its ``date`` frontmatter is empty OR equals the Granola meeting's
    date (YYYY-MM-DD). Without this filter, two prior pulls of the same
    recurring 1-1 (sharing a title) would collide — newer pulls would land in
    the older file and clobber it.

The search walks the destination folder recursively so prep notes nested under
sub-folders (e.g. per-person 1-1 folders) are still found.

The ``outlook-event-id`` frontmatter field is reserved for the prep-note
creation flow but is not used as a match key here — Granola's cache currently
only models Google Calendar events explicitly, so there is no reliable way to
recover an Outlook event ID from the Granola side. Title + date is the v1
match contract; richer fuzzy matching (filename date, attendee names in
folder path) is tracked in the backlog.
"""

from __future__ import annotations

import os
import re
from typing import Optional

_FRONTMATTER_RE = re.compile(r"\A---\n(.*?)\n---", re.DOTALL)
# Inline whitespace only — `\s*` would let `:` greedily consume the newline and
# absorb the next line's content into the captured value.
_TITLE_LINE_RE = re.compile(r"^meeting-title[ \t]*:[ \t]*([^\n]*?)[ \t]*$", re.MULTILINE)
_DATE_LINE_RE = re.compile(r"^date[ \t]*:[ \t]*([^\n]*?)[ \t]*$", re.MULTILINE)


def find_existing_match(
    folder: str,
    meeting_title: str,
    meeting_date: str = "",
) -> list[str]:
    """Return paths of ``.md`` files under ``folder`` matching this meeting.

    A candidate matches when its frontmatter ``meeting-title`` equals
    ``meeting_title`` (case-insensitive, trimmed) AND its frontmatter ``date``
    is either empty or equals ``meeting_date`` (compared as YYYY-MM-DD strings;
    only the date prefix is checked so files with time components still match).

    ``meeting_date`` defaults to the empty string for backward compatibility;
    when empty, the date filter is skipped and the matcher falls back to
    title-only behavior.

    Returns an empty list when nothing matches. Multiple matches mean the
    caller must disambiguate with the user.
    """
    needle_title = _normalize(meeting_title)
    needle_date = meeting_date.strip()[:10]
    if not needle_title or not os.path.isdir(folder):
        return []

    matches: list[str] = []
    for root, _dirs, files in os.walk(folder):
        for name in files:
            if not name.endswith(".md"):
                continue
            path = os.path.join(root, name)
            fields = _read_frontmatter_fields(path)
            if fields is None:
                continue
            file_title = fields.get("meeting-title", "")
            if _normalize(file_title) != needle_title:
                continue
            file_date = fields.get("date", "").strip()[:10]
            if needle_date and file_date and file_date != needle_date:
                continue
            matches.append(path)
    matches.sort()
    return matches


def _read_frontmatter_fields(path: str) -> Optional[dict[str, str]]:
    """Read just the head of a file and pull out the frontmatter values for
    ``meeting-title`` and ``date``. Returns ``None`` when no frontmatter is
    present.

    Reads at most the first 4KB so large transcripts stay cheap to skip.
    """
    try:
        with open(path, "r", encoding="utf-8") as f:
            head = f.read(4096)
    except (OSError, UnicodeDecodeError):
        return None

    fm = _FRONTMATTER_RE.match(head)
    if not fm:
        return None
    block = fm.group(1)
    fields: dict[str, str] = {}
    title_match = _TITLE_LINE_RE.search(block)
    if title_match:
        fields["meeting-title"] = _strip_yaml_quotes(title_match.group(1).strip())
    date_match = _DATE_LINE_RE.search(block)
    if date_match:
        fields["date"] = _strip_yaml_quotes(date_match.group(1).strip())
    return fields


def _strip_yaml_quotes(raw: str) -> str:
    if len(raw) >= 2 and raw[0] == raw[-1] and raw[0] in ('"', "'"):
        return raw[1:-1]
    return raw


def _normalize(s: str) -> str:
    return s.strip().casefold()
