"""Render a minimal prep-meeting note from explicit calendar inputs.

Prep notes are created BEFORE the meeting happens — there is no Granola
record yet. The file is intentionally minimal: frontmatter sourced from
the calendar event plus a single ``# Prep Notes`` heading. When
``/pull-granola-notes`` later runs and matches the prep note (by
``meeting-title`` + ``date`` frontmatter), the merger appends the
``# Notes`` / ``# Enhanced Notes`` / ``# Transcript`` sections in
canonical order without disturbing whatever the user wrote under
``# Prep Notes``.
"""

from __future__ import annotations

from .renderer import _escape_yaml_scalar, _escape_yaml_title, _participants_yaml_list


def render_prep_note(
    title: str,
    date: str,
    attendees: list[str],
    outlook_event_id: str = "",
) -> str:
    """Build a prep-note markdown body for an upcoming calendar meeting.

    Args:
        title: Meeting subject — becomes ``meeting-title`` frontmatter and
            participates in matcher lookups when granola-sync later pulls.
        date: YYYY-MM-DD. Becomes ``date`` frontmatter; the matcher's date
            filter relies on this value being either empty or equal to the
            Granola meeting's date.
        attendees: Display names. The first becomes the implicit ``creator``
            convention used elsewhere in the repo, but is just a list here.
        outlook_event_id: Stable Outlook event ID. Reserved for future use as
            a primary match key (today the matcher uses title + date only).
    """
    attendees_yaml = (
        f"\n{_participants_yaml_list(attendees)}"
        if attendees
        else " []"
    )
    title_yaml = _escape_yaml_title(title)
    event_id_yaml = _escape_yaml_scalar(outlook_event_id) if outlook_event_id else ""

    return (
        "---\n"
        f"date: {date}\n"
        "type:\n"
        f"attendees:{attendees_yaml}\n"
        f"meeting-title: {title_yaml}\n"
        f"outlook-event-id: {event_id_yaml}\n"
        "status: draft\n"
        "---\n"
        "\n"
        "# Prep Notes\n"
        "\n"
    )
