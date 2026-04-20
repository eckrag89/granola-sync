"""Tests for template rendering."""

import unittest

from granola_sync.models import (
    CalendarEvent,
    Meeting,
    Participant,
    TranscriptEntry,
    parse_datetime,
)
from granola_sync.renderer import (
    _escape_yaml_title,
    _format_transcript,
    render_meeting_note,
)


SIMPLE_TEMPLATE = """\
# {title}

**Date:** {date}
**Participants:** {participants}
**Channel:** {channel}

---

## Notes

{notes}

## Enhanced Notes

{enhanced_notes}

## Transcript

{transcript}
"""


class TestRenderMeetingNote(unittest.TestCase):
    def _make_meeting(self, **overrides):
        defaults = dict(
            id="test-123",
            title="Team Standup",
            created_at=parse_datetime("2026-03-15T14:00:00Z"),
            creator=Participant(name="Alice", email="alice@example.com"),
            attendees=[Participant(name="Bob")],
            calendar=CalendarEvent(
                start=parse_datetime("2026-03-15T09:00:00-05:00"),
                conferencing_type="zoom",
            ),
            notes_markdown="# Meeting Notes\n\nStuff discussed.",
        )
        defaults.update(overrides)
        return Meeting(**defaults)

    def test_basic_rendering(self):
        meeting = self._make_meeting()
        result = render_meeting_note(meeting, template=SIMPLE_TEMPLATE)
        self.assertIn("# Team Standup", result)
        self.assertIn("**Date:** 2026-03-15", result)
        self.assertIn("Alice, Bob", result)
        self.assertIn("Zoom", result)
        self.assertIn("# Meeting Notes", result)

    def test_enhanced_notes(self):
        meeting = self._make_meeting()
        result = render_meeting_note(
            meeting,
            template=SIMPLE_TEMPLATE,
            enhanced_notes="AI Summary: Great meeting.",
        )
        self.assertIn("AI Summary: Great meeting.", result)

    def test_prosemirror_fallback(self):
        pm_doc = {
            "type": "doc",
            "content": [
                {
                    "type": "paragraph",
                    "content": [{"type": "text", "text": "From ProseMirror"}],
                },
            ],
        }
        meeting = self._make_meeting(
            notes_markdown="",
            notes_plain="",
            notes_prosemirror=pm_doc,
        )
        result = render_meeting_note(meeting, template=SIMPLE_TEMPLATE)
        self.assertIn("From ProseMirror", result)

    def test_plain_fallback(self):
        meeting = self._make_meeting(
            notes_markdown="",
            notes_plain="Plain text notes here",
            notes_prosemirror=None,
        )
        result = render_meeting_note(meeting, template=SIMPLE_TEMPLATE)
        self.assertIn("Plain text notes here", result)

    def test_missing_fields_produce_empty(self):
        meeting = Meeting(id="bare", title="Bare Meeting")
        result = render_meeting_note(meeting, template=SIMPLE_TEMPLATE)
        self.assertIn("# Bare Meeting", result)
        # No "None" should appear in output
        self.assertNotIn("None", result)

    def test_title_with_colon_escaped(self):
        meeting = self._make_meeting(title='Review: Q2 "Goals"')
        result = render_meeting_note(meeting, template=SIMPLE_TEMPLATE)
        self.assertIn('"Review: Q2 \\"Goals\\""', result)

    def test_empty_notes_renders_placeholder(self):
        meeting = self._make_meeting(
            notes_markdown="",
            notes_plain="",
            notes_prosemirror=None,
        )
        result = render_meeting_note(meeting, template=SIMPLE_TEMPLATE)
        self.assertIn("_(no notes taken)_", result)

    def test_whitespace_only_notes_renders_placeholder(self):
        meeting = self._make_meeting(notes_markdown="   \n\n  ")
        result = render_meeting_note(meeting, template=SIMPLE_TEMPLATE)
        self.assertIn("_(no notes taken)_", result)

    def test_cache_enhanced_notes_fallback_when_mcp_empty(self):
        meeting = self._make_meeting(cache_enhanced_notes="Cached AI summary.")
        result = render_meeting_note(meeting, template=SIMPLE_TEMPLATE, enhanced_notes="")
        self.assertIn("Cached AI summary.", result)

    def test_mcp_enhanced_notes_wins_over_cache(self):
        meeting = self._make_meeting(cache_enhanced_notes="Cached version.")
        result = render_meeting_note(
            meeting,
            template=SIMPLE_TEMPLATE,
            enhanced_notes="MCP version.",
        )
        self.assertIn("MCP version.", result)
        self.assertNotIn("Cached version.", result)


class TestEscapeYamlTitle(unittest.TestCase):
    def test_plain_title(self):
        self.assertEqual(_escape_yaml_title("Weekly Standup"), "Weekly Standup")

    def test_colon_in_title(self):
        result = _escape_yaml_title("Review: Q2 Plans")
        self.assertEqual(result, '"Review: Q2 Plans"')

    def test_quotes_in_title(self):
        result = _escape_yaml_title('The "Big" Review')
        self.assertEqual(result, '"The \\"Big\\" Review"')

    def test_empty_title(self):
        self.assertEqual(_escape_yaml_title(""), "")


class TestTranscriptOverride(unittest.TestCase):
    def _make_meeting(self, **overrides):
        defaults = dict(
            id="test-override",
            title="Override Test",
            created_at=parse_datetime("2026-03-15T14:00:00Z"),
            notes_markdown="Some notes",
            transcript=[
                TranscriptEntry(text="Cache transcript.", source="microphone"),
            ],
        )
        defaults.update(overrides)
        return Meeting(**defaults)

    def test_transcript_override_replaces_cache(self):
        meeting = self._make_meeting()
        result = render_meeting_note(
            meeting,
            template=SIMPLE_TEMPLATE,
            transcript_override="MCP transcript content here",
        )
        self.assertIn("MCP transcript content here", result)
        self.assertNotIn("Cache transcript.", result)

    def test_empty_override_uses_cache(self):
        meeting = self._make_meeting()
        result = render_meeting_note(
            meeting,
            template=SIMPLE_TEMPLATE,
            transcript_override="",
        )
        self.assertIn("**You:** Cache transcript.", result)
        self.assertNotIn("MCP transcript content here", result)


class TestFormatTranscript(unittest.TestCase):
    def test_groups_consecutive_same_source(self):
        meeting = Meeting(
            transcript=[
                TranscriptEntry(text="Hello.", source="microphone"),
                TranscriptEntry(text="How are you?", source="microphone"),
                TranscriptEntry(text="Good, thanks.", source="system"),
            ]
        )
        result = _format_transcript(meeting)
        self.assertIn("**You:** Hello. How are you?", result)
        self.assertIn("**Other:** Good, thanks.", result)

    def test_alternating_speakers(self):
        meeting = Meeting(
            transcript=[
                TranscriptEntry(text="A", source="microphone"),
                TranscriptEntry(text="B", source="system"),
                TranscriptEntry(text="C", source="microphone"),
            ]
        )
        result = _format_transcript(meeting)
        lines = [l for l in result.split("\n") if l.strip()]
        self.assertEqual(len(lines), 3)

    def test_empty_transcript(self):
        meeting = Meeting()
        self.assertEqual(_format_transcript(meeting), "")


if __name__ == "__main__":
    unittest.main()
