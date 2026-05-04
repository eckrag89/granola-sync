"""Template loading and meeting note rendering."""

from __future__ import annotations

import os
import re
from typing import Optional

from .models import Meeting
from .prosemirror import prosemirror_to_markdown

# Default template path
_DEFAULT_TEMPLATE = os.path.join(
    os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))),
    "templates",
    "meeting-note-template.md",
)


def load_template(path: str = _DEFAULT_TEMPLATE) -> str:
    """Read the meeting note template file."""
    with open(path, "r", encoding="utf-8") as f:
        return f.read()


def render_meeting_note(
    meeting: Meeting,
    template: Optional[str] = None,
    enhanced_notes: str = "",
    transcript_override: str = "",
    meeting_summary: str = "",
) -> str:
    """Populate a template with meeting data.

    Args:
        meeting: Meeting data to render.
        template: Template string. If None, loads default template.
        enhanced_notes: AI-generated summary (from MCP), inserted as-is.
        transcript_override: Pre-formatted transcript text (from MCP).
            When non-empty, used instead of formatting cache transcript entries.
        meeting_summary: Caller-generated summary (Summary + Key Decisions +
            Action Items, typically derived from the transcript by the
            /pull-granola-notes skill). When non-empty, prepended as a
            ``# Meeting Summary`` section above the first H1 in the body.
            When empty, no Meeting Summary section is rendered — the template
            stays clean for cases where transcript-driven generation isn't
            available (cache-only mode, MCP failure, etc.).

    Returns:
        Populated markdown string.
    """
    if template is None:
        template = load_template()

    # Resolve notes via fallback chain
    notes = meeting.notes_markdown
    if not notes and meeting.notes_prosemirror:
        notes = prosemirror_to_markdown(meeting.notes_prosemirror)
    if not notes:
        notes = meeting.notes_plain
    if not notes.strip():
        notes = "_(no notes taken)_"

    # Enhanced notes: fall back to cache-extracted summary when MCP-supplied is empty
    if not enhanced_notes and getattr(meeting, "cache_enhanced_notes", ""):
        enhanced_notes = meeting.cache_enhanced_notes

    # Format transcript -- override takes precedence over cache entries
    if transcript_override:
        transcript = transcript_override
    else:
        transcript = _format_transcript(meeting)

    title = meeting.title or "Untitled"

    # Build replacement map
    replacements = {
        "{title}": title,
        "{title_yaml}": _escape_yaml_title(title),
        "{date}": meeting.date_str,
        "{participants}": ", ".join(meeting.participant_names) or "",
        "{participants_yaml}": _participants_yaml_list(meeting.participant_names),
        "{notes}": notes,
        "{enhanced_notes}": enhanced_notes,
        "{transcript}": transcript,
    }

    result = template
    for placeholder, value in replacements.items():
        result = result.replace(placeholder, value)

    if meeting_summary.strip():
        result = _insert_meeting_summary(result, meeting_summary)

    return result


def _insert_meeting_summary(rendered: str, content: str) -> str:
    """Insert ``# Meeting Summary`` immediately before the first H1 in the
    body, or append it when no H1 exists.

    Top-level sections (Prep Notes / Notes / Enhanced Notes / Transcript) are
    H1 in the current convention; this slots Meeting Summary in just before
    them so it appears at the top of the body when the merger places it.
    """
    block = f"# Meeting Summary\n\n{content.strip()}\n\n"
    match = re.search(r"^# ", rendered, re.MULTILINE)
    if not match:
        return rendered.rstrip() + "\n\n" + block
    return rendered[:match.start()] + block + rendered[match.start():]


def _participants_yaml_list(names: list[str]) -> str:
    """Render participant names as an indented YAML list body.

    Returns an empty string for an empty list, producing an empty-list frontmatter value.
    """
    if not names:
        return ""
    return "\n".join(f"  - {_escape_yaml_scalar(n)}" for n in names)


def _escape_yaml_scalar(value: str) -> str:
    """Quote a YAML scalar when it contains characters that would break parsing."""
    if not value:
        return '""'
    needs_quoting = any(c in value for c in (':', '"', "'", "#", "[", "]", "{", "}", ",", "&", "*", "|", ">", "!", "%", "@", "`"))
    if value.strip() != value:
        needs_quoting = True
    if needs_quoting:
        escaped = value.replace('"', '\\"')
        return f'"{escaped}"'
    return value


def _escape_yaml_title(title: str) -> str:
    """Escape a title for safe YAML frontmatter usage.

    Wraps in quotes if the title contains colons, quotes, or other special chars.
    """
    if not title:
        return ""
    needs_quoting = any(c in title for c in (':', '"', "'", "#", "[", "]", "{", "}"))
    if needs_quoting:
        # Double-quote and escape internal double quotes
        escaped = title.replace('"', '\\"')
        return f'"{escaped}"'
    return title


def _format_transcript(meeting: Meeting) -> str:
    """Format transcript entries with speaker grouping.

    Groups consecutive entries from the same source and labels them.
    """
    if not meeting.transcript:
        return ""

    lines = []
    current_source = None
    current_texts: list[str] = []

    def flush():
        if current_texts:
            label = _speaker_label(current_source or "")
            combined = " ".join(current_texts)
            lines.append(f"**{label}:** {combined}")

    for entry in meeting.transcript:
        if entry.source != current_source:
            flush()
            current_source = entry.source
            current_texts = []
        current_texts.append(entry.text)

    flush()

    return "\n\n".join(lines)


def _speaker_label(source: str) -> str:
    """Convert transcript source to human-readable label."""
    labels = {
        "microphone": "You",
        "system": "Other",
    }
    return labels.get(source, source or "Unknown")
