"""CLI output formatting for meeting lists."""

from __future__ import annotations

import json
from typing import Any

from .models import Meeting


def meetings_to_json(meetings: list[Meeting]) -> str:
    """Serialize meetings to a JSON array for programmatic consumption."""
    records: list[dict[str, Any]] = []
    for m in meetings:
        records.append({
            "id": m.id,
            "title": m.title,
            "date": m.date_str,
            "participants": m.participant_names,
            "folder": m.folder,
            "has_notes": m.has_cached_notes,
            "has_transcript": m.has_cached_transcript,
        })
    return json.dumps(records, indent=2, ensure_ascii=False)


def meetings_to_table(meetings: list[Meeting], limit: int = 0) -> str:
    """Format meetings as an aligned text table for human display."""
    if not meetings:
        return "No meetings found."

    display = meetings[:limit] if limit > 0 else meetings

    # Column headers
    headers = ["Date", "Title", "Folder", "Notes", "Transcript", "ID (prefix)"]

    # Build rows
    rows: list[list[str]] = []
    for m in display:
        rows.append([
            m.date_str or "—",
            _truncate(m.title or "Untitled", 40),
            _truncate(m.folder, 20) or "—",
            "yes" if m.has_cached_notes else "no",
            "yes" if m.has_cached_transcript else "no",
            m.id[:8],
        ])

    # Calculate column widths
    col_widths = [len(h) for h in headers]
    for row in rows:
        for i, cell in enumerate(row):
            col_widths[i] = max(col_widths[i], len(cell))

    # Format output
    def format_row(cells: list[str]) -> str:
        parts = []
        for i, cell in enumerate(cells):
            parts.append(cell.ljust(col_widths[i]))
        return "  ".join(parts)

    lines = [format_row(headers)]
    lines.append("  ".join("—" * w for w in col_widths))
    for row in rows:
        lines.append(format_row(row))

    total_msg = ""
    if limit > 0 and len(meetings) > limit:
        total_msg = f"\n({len(meetings)} total, showing {limit})"

    return "\n".join(lines) + total_msg


def _truncate(text: str, max_len: int) -> str:
    """Truncate text with ellipsis if needed."""
    if len(text) <= max_len:
        return text
    return text[: max_len - 1] + "…"
