"""Granola cache discovery, loading, and parsing."""

from __future__ import annotations

import glob
import json
import os
import sys
from typing import Optional

from .models import (
    CalendarEvent,
    Meeting,
    Participant,
    TranscriptEntry,
    parse_datetime,
)

# Default cache directory
_CACHE_DIR = os.path.expanduser("~/Library/Application Support/Granola")


def find_cache_file(cache_dir: str = _CACHE_DIR) -> Optional[str]:
    """Find the newest cache-v*.json file. Returns None if not found or unreadable."""
    pattern = os.path.join(cache_dir, "cache-v*.json")
    matches = glob.glob(pattern)
    if not matches:
        print(f"granola-sync: no cache files found in {cache_dir}", file=sys.stderr)
        return None

    # Sort by modification time, newest first
    matches.sort(key=lambda p: os.path.getmtime(p), reverse=True)
    path = matches[0]

    # Quick encryption check: try reading first bytes
    try:
        with open(path, "r", encoding="utf-8") as f:
            first_char = f.read(1)
        if first_char != "{":
            print(
                f"granola-sync: cache file may be encrypted (does not start with '{{'): {path}",
                file=sys.stderr,
            )
            return None
    except (UnicodeDecodeError, OSError) as e:
        print(f"granola-sync: cannot read cache file {path}: {e}", file=sys.stderr)
        return None

    return path


def load_cache(path: str) -> dict:
    """Load and decode the cache JSON, handling double-encoded format.

    Returns the 'state' dict from inside the cache.
    Raises ValueError if structure is unexpected.
    """
    with open(path, "r", encoding="utf-8") as f:
        data = json.load(f)

    # Handle double-encoded JSON: cache value might be a string
    cache = data.get("cache", data)
    if isinstance(cache, str):
        cache = json.loads(cache)

    state = cache.get("state")
    if not isinstance(state, dict):
        raise ValueError(
            f"Unexpected cache structure: expected 'state' dict, got {type(state)}"
        )

    return state


def load_meetings(
    cache_path: Optional[str] = None,
) -> list[Meeting]:
    """Load all meetings from the Granola cache, sorted by date descending.

    Args:
        cache_path: Explicit cache file path. If None, auto-discovers.

    Returns:
        List of Meeting objects sorted by date (newest first).
        Empty list if cache is unavailable.
    """
    if cache_path is None:
        cache_path = find_cache_file()
    if cache_path is None:
        return []

    try:
        state = load_cache(cache_path)
    except (json.JSONDecodeError, ValueError, OSError) as e:
        print(f"granola-sync: failed to load cache: {e}", file=sys.stderr)
        return []

    # Build folder lookup: meeting_id -> folder_name
    folder_map = _build_folder_map(state)

    # Parse documents
    documents = state.get("documents", {})
    transcripts = state.get("transcripts", {})

    meetings = []
    for doc_id, doc in documents.items():
        if not isinstance(doc, dict):
            continue
        try:
            meeting = _parse_document(doc_id, doc, folder_map, transcripts)
            meetings.append(meeting)
        except Exception as e:
            print(
                f"granola-sync: skipping document {doc_id}: {e}", file=sys.stderr
            )

    # Sort by date, newest first (None dates sort last)
    meetings.sort(key=lambda m: m.date or parse_datetime("1970-01-01T00:00:00Z"), reverse=True)
    return meetings


def search_meetings(meetings: list[Meeting], query: str) -> list[Meeting]:
    """Case-insensitive search across meeting titles."""
    q = query.lower()
    return [m for m in meetings if q in (m.title or "").lower()]


def get_meeting_by_id(meetings: list[Meeting], meeting_id: str) -> Optional[Meeting]:
    """Find a meeting by UUID. Supports partial ID prefix matching."""
    meeting_id = meeting_id.lower()
    for m in meetings:
        if m.id.lower() == meeting_id:
            return m
    # Try prefix match
    matches = [m for m in meetings if m.id.lower().startswith(meeting_id)]
    if len(matches) == 1:
        return matches[0]
    return None


def _build_folder_map(state: dict) -> dict[str, str]:
    """Cross-reference documentLists and documentListsMetadata to map meeting IDs to folder names."""
    doc_lists = state.get("documentLists", {})
    doc_lists_meta = state.get("documentListsMetadata", {})

    folder_map: dict[str, str] = {}
    for list_id, meeting_ids in doc_lists.items():
        if not isinstance(meeting_ids, list):
            continue
        folder_name = ""
        meta = doc_lists_meta.get(list_id)
        if isinstance(meta, dict):
            folder_name = meta.get("title", "")
        for mid in meeting_ids:
            if isinstance(mid, str) and folder_name:
                folder_map[mid] = folder_name

    return folder_map


def _parse_document(
    doc_id: str,
    doc: dict,
    folder_map: dict[str, str],
    transcripts: dict,
) -> Meeting:
    """Convert a raw cache document dict to a Meeting."""
    meeting = Meeting(
        id=doc_id,
        title=doc.get("title", ""),
        created_at=parse_datetime(doc.get("created_at")),
        updated_at=parse_datetime(doc.get("updated_at")),
        meeting_type=doc.get("type") or "",
        folder=folder_map.get(doc_id, ""),
        notes_markdown=doc.get("notes_markdown") or "",
        notes_plain=doc.get("notes_plain") or "",
        notes_prosemirror=doc.get("notes") if isinstance(doc.get("notes"), dict) else None,
        cache_enhanced_notes=_extract_cache_enhanced_notes(doc),
    )

    # People
    people = doc.get("people")
    if isinstance(people, dict):
        meeting.creator = _parse_participant(people.get("creator"))
        attendees_raw = people.get("attendees", [])
        if isinstance(attendees_raw, list):
            for a in attendees_raw:
                p = _parse_participant(a)
                if p:
                    meeting.attendees.append(p)

        # Conferencing info
        conf = people.get("conferencing")
        if isinstance(conf, dict):
            if meeting.calendar is None:
                meeting.calendar = CalendarEvent()
            meeting.calendar.conferencing_url = conf.get("url", "")
            meeting.calendar.conferencing_type = conf.get("type", "")

    # Google Calendar event
    cal = doc.get("google_calendar_event")
    if isinstance(cal, dict):
        if meeting.calendar is None:
            meeting.calendar = CalendarEvent()
        start = cal.get("start", {})
        end = cal.get("end", {})
        meeting.calendar.start = parse_datetime(
            start.get("dateTime") if isinstance(start, dict) else None
        )
        meeting.calendar.end = parse_datetime(
            end.get("dateTime") if isinstance(end, dict) else None
        )
        meeting.calendar.timezone = (
            start.get("timeZone", "") if isinstance(start, dict) else ""
        )

        # Conferencing from calendar (if not already set from people)
        conf_data = cal.get("conferenceData")
        if isinstance(conf_data, dict) and not meeting.calendar.conferencing_url:
            entry_points = conf_data.get("entryPoints", [])
            if isinstance(entry_points, list) and entry_points:
                meeting.calendar.conferencing_url = entry_points[0].get("uri", "")
            solution = conf_data.get("conferenceSolution", {})
            if isinstance(solution, dict) and not meeting.calendar.conferencing_type:
                name = solution.get("name", "").lower()
                if "zoom" in name:
                    meeting.calendar.conferencing_type = "zoom"
                elif "meet" in name:
                    meeting.calendar.conferencing_type = "google_meet"
                elif "teams" in name:
                    meeting.calendar.conferencing_type = "teams"

    # Transcript
    raw_transcript = transcripts.get(doc_id)
    if isinstance(raw_transcript, list):
        for entry in raw_transcript:
            if not isinstance(entry, dict):
                continue
            text = (entry.get("text") or "").strip()
            if text:
                meeting.transcript.append(
                    TranscriptEntry(
                        timestamp=parse_datetime(entry.get("start_timestamp")),
                        text=text,
                        source=entry.get("source", ""),
                    )
                )

    return meeting


def _extract_cache_enhanced_notes(doc: dict) -> str:
    """Build an AI-summary string from cache fields when Granola has populated them.

    Checks overview, summary, then chapters (array of {title, summary} or {heading,
    content}). Returns empty string when none are present.
    """
    overview = doc.get("overview")
    if isinstance(overview, str) and overview.strip():
        return overview.strip()

    summary = doc.get("summary")
    if isinstance(summary, str) and summary.strip():
        return summary.strip()

    chapters = doc.get("chapters")
    if isinstance(chapters, list) and chapters:
        parts: list[str] = []
        for ch in chapters:
            if not isinstance(ch, dict):
                continue
            heading = ch.get("title") or ch.get("heading") or ""
            body = ch.get("summary") or ch.get("content") or ""
            if isinstance(heading, str):
                heading = heading.strip()
            else:
                heading = ""
            if isinstance(body, str):
                body = body.strip()
            else:
                body = ""
            if heading and body:
                parts.append(f"### {heading}\n\n{body}")
            elif heading:
                parts.append(f"### {heading}")
            elif body:
                parts.append(body)
        if parts:
            return "\n\n".join(parts)

    return ""


def _parse_participant(data: Optional[dict]) -> Optional[Participant]:
    """Parse a participant from people.creator or people.attendees[] format."""
    if not isinstance(data, dict):
        return None
    name = data.get("name", "")
    email = data.get("email", "")
    if not name and not email:
        return None
    return Participant(name=name, email=email)
