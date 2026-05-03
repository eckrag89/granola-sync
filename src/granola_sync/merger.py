"""Merge tool-generated meeting notes into an existing user file.

Section ownership:
  - Tool-owned H2 headings: ``## Notes``, ``## Enhanced Notes``, ``## Transcript``.
    Replaced wholesale on every push.
  - Everything else is user-owned and preserved verbatim. That includes
    ``## Prep Notes``, custom H2 sections, any H1 preamble, and free text.

Frontmatter merging: keys listed in ``TOOL_OWNED_FRONTMATTER_FIELDS`` update
when the incoming render has a non-empty value. All other fields (and the
existing field order) are preserved from the user's file. Keys present in the
incoming render but absent from the existing file are appended.

Stdlib only — no PyYAML dependency. Frontmatter values round-trip as raw
strings rather than being typed/normalized.
"""

from __future__ import annotations

import re
from typing import Optional

TOOL_OWNED_HEADINGS = ("notes", "enhanced notes", "transcript")
TOOL_OWNED_FRONTMATTER_FIELDS = ("date", "meeting-title", "attendees")

_FRONTMATTER_RE = re.compile(r"\A---\n(.*?)\n---\n?", re.DOTALL)
_H2_LINE_RE = re.compile(r"^## +(.*?)\s*$", re.MULTILINE)
_KEY_LINE_RE = re.compile(r"^[A-Za-z0-9_-]+\s*:")


def merge_files(existing: str, new_render: str) -> str:
    """Merge ``new_render`` into ``existing``, preserving user-owned content.

    Tool-owned sections (and tool-owned frontmatter fields) update from the
    new render; everything else stays put. Tool-owned sections that aren't
    already present in the existing file are appended at the end of the body
    in canonical order.
    """
    existing_fm_block, existing_body = _split_frontmatter(existing)
    new_fm_block, new_body = _split_frontmatter(new_render)

    existing_keys, existing_vals = _parse_frontmatter(existing_fm_block)
    new_keys, new_vals = _parse_frontmatter(new_fm_block)

    merged_keys = list(existing_keys)
    merged_vals = dict(existing_vals)
    for k in new_keys:
        new_v = new_vals.get(k, "")
        if k not in merged_vals:
            merged_keys.append(k)
            merged_vals[k] = new_v
        elif k in TOOL_OWNED_FRONTMATTER_FIELDS and new_v.strip():
            merged_vals[k] = new_v

    new_sections = _split_sections(new_body)
    new_tool: dict[str, str] = {}
    for heading, content in new_sections:
        if _heading_is_tool_owned(heading):
            new_tool[heading.strip().lower()] = content

    existing_sections = _split_sections(existing_body)
    rebuilt: list[str] = []
    tool_positions: dict[str, int] = {}
    for heading, content in existing_sections:
        if _heading_is_tool_owned(heading):
            key = heading.strip().lower()
            tool_positions[key] = len(rebuilt)
            rebuilt.append(new_tool.get(key, content))
        else:
            rebuilt.append(content)

    # Insert tool sections that weren't already present, anchored on the next
    # canonical sibling that IS present so the final layout reads in canonical
    # order. Existing tool sections keep their original position; newcomers
    # slot in where their siblings expect them.
    for canonical in TOOL_OWNED_HEADINGS:
        if canonical in tool_positions or canonical not in new_tool:
            continue
        successors = TOOL_OWNED_HEADINGS[TOOL_OWNED_HEADINGS.index(canonical) + 1:]
        insert_pos = len(rebuilt)
        for succ in successors:
            if succ in tool_positions:
                insert_pos = tool_positions[succ]
                break
        rebuilt.insert(insert_pos, new_tool[canonical])
        for k, v in list(tool_positions.items()):
            if v >= insert_pos:
                tool_positions[k] = v + 1
        tool_positions[canonical] = insert_pos

    body_text = "".join(rebuilt).rstrip("\n") + "\n"

    if not merged_keys:
        return body_text
    return _emit_frontmatter(merged_keys, merged_vals) + "\n" + body_text


def _split_frontmatter(text: str) -> tuple[str, str]:
    m = _FRONTMATTER_RE.match(text)
    if not m:
        return "", text
    return m.group(0), text[m.end():]


def _parse_frontmatter(block: str) -> tuple[list[str], dict[str, str]]:
    """Return ``(ordered_keys, raw_values)`` for a frontmatter block.

    Multi-line values (continuation lines without a key prefix) are joined with
    newlines and stored verbatim, so re-emission round-trips byte-for-byte for
    typical YAML structures (lists, indented scalars).
    """
    if not block:
        return [], {}
    inner = block.split("\n", 1)[1].rsplit("\n---", 1)[0]
    keys: list[str] = []
    values: dict[str, str] = {}
    current_key: Optional[str] = None
    current_lines: list[str] = []

    def flush() -> None:
        nonlocal current_key
        if current_key is not None:
            values[current_key] = "\n".join(current_lines)
        current_key = None
        current_lines.clear()

    for line in inner.split("\n"):
        if _KEY_LINE_RE.match(line):
            flush()
            key, _, rest = line.partition(":")
            current_key = key.strip()
            keys.append(current_key)
            current_lines.append(rest.lstrip())
        else:
            current_lines.append(line)
    flush()
    return keys, values


def _emit_frontmatter(keys: list[str], values: dict[str, str]) -> str:
    lines = ["---"]
    for k in keys:
        v = values.get(k, "")
        if "\n" in v:
            head, _, rest = v.partition("\n")
            lines.append(f"{k}: {head}" if head else f"{k}:")
            lines.append(rest)
        else:
            lines.append(f"{k}: {v}" if v else f"{k}:")
    lines.append("---")
    return "\n".join(lines) + "\n"


def _split_sections(body: str) -> list[tuple[Optional[str], str]]:
    """Split a body into ``[(heading_or_None, content), ...]`` in source order.

    The first tuple has ``heading=None`` when the body has any text before the
    first H2 (e.g. an H1 title or preamble paragraphs).
    """
    matches = list(_H2_LINE_RE.finditer(body))
    if not matches:
        return [(None, body)]
    sections: list[tuple[Optional[str], str]] = []
    if matches[0].start() > 0:
        sections.append((None, body[:matches[0].start()]))
    for i, m in enumerate(matches):
        end = matches[i + 1].start() if i + 1 < len(matches) else len(body)
        sections.append((m.group(1).strip(), body[m.start():end]))
    return sections


def _heading_is_tool_owned(heading: Optional[str]) -> bool:
    if heading is None:
        return False
    return heading.strip().lower() in TOOL_OWNED_HEADINGS
