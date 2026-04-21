"""Domain models for Granola meeting data."""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from datetime import datetime
from typing import Optional


@dataclass
class Participant:
    name: str
    email: str = ""


@dataclass
class CalendarEvent:
    start: Optional[datetime] = None
    end: Optional[datetime] = None
    location: str = ""
    conferencing_url: str = ""
    conferencing_type: str = ""
    timezone: str = ""


@dataclass
class TranscriptEntry:
    timestamp: Optional[datetime] = None
    text: str = ""
    source: str = ""  # "microphone" or "system"


@dataclass
class Meeting:
    id: str = ""
    title: str = ""
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None
    meeting_type: str = ""  # "meeting" or null
    folder: str = ""

    creator: Optional[Participant] = None
    attendees: list[Participant] = field(default_factory=list)
    calendar: Optional[CalendarEvent] = None

    notes_markdown: str = ""
    notes_plain: str = ""
    notes_prosemirror: Optional[dict] = None  # raw ProseMirror JSON from "notes" field

    # AI summary extracted from cache (overview/summary/chapters). Empty when cache
    # has no AI content; renderer uses this as a fallback when MCP-supplied
    # enhanced_notes is empty.
    cache_enhanced_notes: str = ""

    transcript: list[TranscriptEntry] = field(default_factory=list)

    @property
    def date(self) -> Optional[datetime]:
        """Prefer calendar start time over created_at."""
        if self.calendar and self.calendar.start:
            return self.calendar.start
        return self.created_at

    @property
    def date_str(self) -> str:
        """YYYY-MM-DD formatted date."""
        d = self.date
        return d.strftime("%Y-%m-%d") if d else ""

    @property
    def participant_names(self) -> list[str]:
        """Flat list of all participant names (creator + attendees)."""
        names = []
        if self.creator and self.creator.name:
            names.append(self.creator.name)
        for a in self.attendees:
            if a.name:
                names.append(a.name)
        return names

    @property
    def best_notes(self) -> str:
        """Fallback chain: markdown > plain. ProseMirror conversion is caller's job."""
        if self.notes_markdown:
            return self.notes_markdown
        if self.notes_plain:
            return self.notes_plain
        return ""

    @property
    def has_cached_notes(self) -> bool:
        return bool(self.notes_markdown or self.notes_plain or self.notes_prosemirror)

    @property
    def has_cached_transcript(self) -> bool:
        return bool(self.transcript)

    @property
    def duration_minutes(self) -> Optional[int]:
        """Derive duration from transcript timestamps, if available."""
        if not self.transcript:
            return None
        first = self.transcript[0].timestamp
        last = self.transcript[-1].timestamp
        if first and last:
            delta = last - first
            return max(1, int(delta.total_seconds() / 60))
        return None


def parse_datetime(value: Optional[str]) -> Optional[datetime]:
    """Parse ISO 8601 datetime string, handling Z suffix and offsets."""
    if not value:
        return None
    try:
        # Replace trailing Z with +00:00 for fromisoformat compatibility
        cleaned = re.sub(r"Z$", "+00:00", value)
        return datetime.fromisoformat(cleaned)
    except (ValueError, TypeError):
        return None
