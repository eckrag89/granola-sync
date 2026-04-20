"""Tests for CLI entry point (__main__.py)."""

import json
import os
import tempfile
import unittest

from granola_sync.__main__ import (
    _apply_participants_override,
    _format_mcp_transcript_entries,
    _load_meeting_from_file,
    _normalize_transcript_text,
    _parse_participants_flag,
    _read_file_arg,
    _read_transcript_file,
    main,
)
from granola_sync.models import Meeting, Participant


class TestReadFileArg(unittest.TestCase):
    def test_reads_file_content(self):
        with tempfile.NamedTemporaryFile(mode="w", suffix=".md", delete=False) as f:
            f.write("file content here")
            path = f.name
        try:
            self.assertEqual(_read_file_arg(path), "file content here")
        finally:
            os.unlink(path)

    def test_missing_file_returns_empty(self):
        result = _read_file_arg("/nonexistent/path/file.md")
        self.assertEqual(result, "")


class TestLoadMeetingFromFile(unittest.TestCase):
    def test_constructs_meeting(self):
        data = {
            "id": "abc-123",
            "title": "Test Meeting",
            "date": "2026-04-15",
            "participants": ["Alice", "Bob"],
            "folder": "Job search",
            "channel": "Zoom",
        }
        with tempfile.NamedTemporaryFile(mode="w", suffix=".json", delete=False) as f:
            json.dump(data, f)
            path = f.name
        try:
            meeting = _load_meeting_from_file(path)
            self.assertIsNotNone(meeting)
            self.assertEqual(meeting.id, "abc-123")
            self.assertEqual(meeting.title, "Test Meeting")
            self.assertEqual(meeting.folder, "Job search")
            self.assertEqual(meeting.participant_names, ["Alice", "Bob"])
            self.assertEqual(meeting.date_str, "2026-04-15")
        finally:
            os.unlink(path)

    def test_invalid_json_returns_none(self):
        with tempfile.NamedTemporaryFile(mode="w", suffix=".json", delete=False) as f:
            f.write("not json")
            path = f.name
        try:
            self.assertIsNone(_load_meeting_from_file(path))
        finally:
            os.unlink(path)

    def test_missing_file_returns_none(self):
        self.assertIsNone(_load_meeting_from_file("/nonexistent/file.json"))

    def test_date_with_time(self):
        data = {"id": "x", "title": "T", "date": "2026-04-15T14:00:00Z"}
        with tempfile.NamedTemporaryFile(mode="w", suffix=".json", delete=False) as f:
            json.dump(data, f)
            path = f.name
        try:
            meeting = _load_meeting_from_file(path)
            self.assertEqual(meeting.date_str, "2026-04-15")
        finally:
            os.unlink(path)


class TestEnhancedNotesFile(unittest.TestCase):
    """Test --enhanced-notes-file reads content into rendered output."""

    def test_enhanced_notes_file_content_in_output(self):
        """--enhanced-notes-file content appears in rendered output."""
        # Create a meeting data file
        meeting_data = {
            "id": "test-en-file",
            "title": "Enhanced Notes File Test",
            "date": "2026-04-15",
            "participants": ["Alice"],
        }
        # Create enhanced notes file
        with tempfile.NamedTemporaryFile(mode="w", suffix=".md", delete=False) as enf:
            enf.write("Enhanced summary from file")
            en_path = enf.name
        with tempfile.NamedTemporaryFile(mode="w", suffix=".json", delete=False) as mf:
            json.dump(meeting_data, mf)
            md_path = mf.name
        try:
            import io
            import sys

            captured = io.StringIO()
            old_stdout = sys.stdout
            sys.stdout = captured
            try:
                rc = main([
                    "render", "test-en-file",
                    "--meeting-data", md_path,
                    "--enhanced-notes-file", en_path,
                ])
            finally:
                sys.stdout = old_stdout
            self.assertEqual(rc, 0)
            output = captured.getvalue()
            self.assertIn("Enhanced summary from file", output)
        finally:
            os.unlink(en_path)
            os.unlink(md_path)

    def test_file_flag_overrides_string_flag(self):
        """--enhanced-notes-file takes precedence over --enhanced-notes."""
        meeting_data = {
            "id": "test-override",
            "title": "Override Test",
            "date": "2026-04-15",
        }
        with tempfile.NamedTemporaryFile(mode="w", suffix=".md", delete=False) as enf:
            enf.write("From file")
            en_path = enf.name
        with tempfile.NamedTemporaryFile(mode="w", suffix=".json", delete=False) as mf:
            json.dump(meeting_data, mf)
            md_path = mf.name
        try:
            import io
            import sys

            captured = io.StringIO()
            old_stdout = sys.stdout
            sys.stdout = captured
            try:
                rc = main([
                    "render", "test-override",
                    "--meeting-data", md_path,
                    "--enhanced-notes", "From string",
                    "--enhanced-notes-file", en_path,
                ])
            finally:
                sys.stdout = old_stdout
            self.assertEqual(rc, 0)
            output = captured.getvalue()
            self.assertIn("From file", output)
            self.assertNotIn("From string", output)
        finally:
            os.unlink(en_path)
            os.unlink(md_path)


class TestTranscriptFile(unittest.TestCase):
    """Test --transcript-file reads content into rendered output."""

    def test_transcript_file_content_in_output(self):
        meeting_data = {
            "id": "test-tf",
            "title": "Transcript File Test",
            "date": "2026-04-15",
        }
        with tempfile.NamedTemporaryFile(mode="w", suffix=".md", delete=False) as tf:
            tf.write("Speaker A: Hello\nSpeaker B: Hi there")
            t_path = tf.name
        with tempfile.NamedTemporaryFile(mode="w", suffix=".json", delete=False) as mf:
            json.dump(meeting_data, mf)
            md_path = mf.name
        try:
            import io
            import sys

            captured = io.StringIO()
            old_stdout = sys.stdout
            sys.stdout = captured
            try:
                rc = main([
                    "render", "test-tf",
                    "--meeting-data", md_path,
                    "--transcript-file", t_path,
                ])
            finally:
                sys.stdout = old_stdout
            self.assertEqual(rc, 0)
            output = captured.getvalue()
            self.assertIn("Speaker A: Hello", output)
            self.assertIn("Speaker B: Hi there", output)
        finally:
            os.unlink(t_path)
            os.unlink(md_path)


class TestCollisionDetection(unittest.TestCase):
    """Test push collision detection (exit code 2 + JSON)."""

    def test_collision_returns_exit_2(self):
        """Push to existing file returns exit 2 with collision JSON."""
        meeting_data = {
            "id": "test-collision",
            "title": "Collision Test",
            "date": "2026-04-15",
        }
        with tempfile.TemporaryDirectory() as tmpdir:
            # Create the meeting data file
            md_path = os.path.join(tmpdir, "meeting.json")
            with open(md_path, "w") as f:
                json.dump(meeting_data, f)

            # Create a config that points to tmpdir
            config_data = {"default_destination": tmpdir, "folder_mappings": {}}
            config_path = os.path.join(tmpdir, "config.json")
            with open(config_path, "w") as f:
                json.dump(config_data, f)

            # Pre-create the target file (collision)
            target = os.path.join(tmpdir, "2026-04-15 - Collision Test - Meeting Notes.md")
            with open(target, "w") as f:
                f.write("existing content")

            import io
            import sys
            from unittest.mock import patch

            captured = io.StringIO()
            old_stdout = sys.stdout
            sys.stdout = captured
            try:
                with patch("granola_sync.__main__.Config.load") as mock_config:
                    from granola_sync.config import Config
                    mock_config.return_value = Config(
                        folder_mappings={},
                        default_destination=tmpdir,
                    )
                    rc = main([
                        "push", "test-collision",
                        "--meeting-data", md_path,
                    ])
            finally:
                sys.stdout = old_stdout

            self.assertEqual(rc, 2)
            result = json.loads(captured.getvalue())
            self.assertTrue(result["collision"])
            self.assertEqual(result["meeting_id"], "test-collision")
            self.assertEqual(result["meeting_title"], "Collision Test")
            self.assertIn("existing_path", result)

    def test_force_overwrites(self):
        """--force bypasses collision check and writes the file."""
        meeting_data = {
            "id": "test-force",
            "title": "Force Test",
            "date": "2026-04-15",
        }
        with tempfile.TemporaryDirectory() as tmpdir:
            md_path = os.path.join(tmpdir, "meeting.json")
            with open(md_path, "w") as f:
                json.dump(meeting_data, f)

            target = os.path.join(tmpdir, "2026-04-15 - Force Test - Meeting Notes.md")
            with open(target, "w") as f:
                f.write("old content")

            import io
            import sys
            from unittest.mock import patch

            captured = io.StringIO()
            old_stdout = sys.stdout
            sys.stdout = captured
            try:
                with patch("granola_sync.__main__.Config.load") as mock_config:
                    from granola_sync.config import Config
                    mock_config.return_value = Config(
                        folder_mappings={},
                        default_destination=tmpdir,
                    )
                    rc = main([
                        "push", "test-force",
                        "--meeting-data", md_path,
                        "--force",
                    ])
            finally:
                sys.stdout = old_stdout

            self.assertEqual(rc, 0)
            with open(target) as f:
                content = f.read()
            self.assertNotEqual(content, "old content")
            self.assertIn("Force Test", content)


class TestDryRun(unittest.TestCase):
    """Test --dry-run prints path without writing."""

    def test_dry_run_no_write(self):
        meeting_data = {
            "id": "test-dry",
            "title": "Dry Run Test",
            "date": "2026-04-15",
        }
        with tempfile.TemporaryDirectory() as tmpdir:
            md_path = os.path.join(tmpdir, "meeting.json")
            with open(md_path, "w") as f:
                json.dump(meeting_data, f)

            import io
            import sys
            from unittest.mock import patch

            captured = io.StringIO()
            old_stdout = sys.stdout
            sys.stdout = captured
            try:
                with patch("granola_sync.__main__.Config.load") as mock_config:
                    from granola_sync.config import Config
                    mock_config.return_value = Config(
                        folder_mappings={},
                        default_destination=tmpdir,
                    )
                    rc = main([
                        "push", "test-dry",
                        "--meeting-data", md_path,
                        "--dry-run",
                    ])
            finally:
                sys.stdout = old_stdout

            self.assertEqual(rc, 0)
            printed_path = captured.getvalue().strip()
            self.assertIn("Dry Run Test", printed_path)
            self.assertTrue(printed_path.endswith(".md"))
            # File should NOT exist
            self.assertFalse(os.path.exists(printed_path))


class TestMeetingDataFile(unittest.TestCase):
    """Test --meeting-data constructs Meeting without cache."""

    def test_meeting_data_renders_without_cache(self):
        """--meeting-data renders a note without touching cache."""
        meeting_data = {
            "id": "mcp-only-123",
            "title": "MCP Only Meeting",
            "date": "2026-04-15",
            "participants": ["Alice", "Bob"],
            "folder": "",
        }
        with tempfile.NamedTemporaryFile(mode="w", suffix=".json", delete=False) as mf:
            json.dump(meeting_data, mf)
            md_path = mf.name
        try:
            import io
            import sys

            captured = io.StringIO()
            old_stdout = sys.stdout
            sys.stdout = captured
            try:
                rc = main([
                    "render", "mcp-only-123",
                    "--meeting-data", md_path,
                ])
            finally:
                sys.stdout = old_stdout
            self.assertEqual(rc, 0)
            output = captured.getvalue()
            self.assertIn("MCP Only Meeting", output)
            self.assertIn("2026-04-15", output)
            self.assertIn("Alice", output)
        finally:
            os.unlink(md_path)


class TestParseParticipantsFlag(unittest.TestCase):
    def test_none_returns_none(self):
        self.assertIsNone(_parse_participants_flag(None))

    def test_empty_returns_none(self):
        self.assertIsNone(_parse_participants_flag(""))

    def test_json_array(self):
        self.assertEqual(
            _parse_participants_flag('["Alice", "Bob", "Carol"]'),
            ["Alice", "Bob", "Carol"],
        )

    def test_comma_separated(self):
        self.assertEqual(
            _parse_participants_flag("Alice, Bob , Carol"),
            ["Alice", "Bob", "Carol"],
        )

    def test_json_drops_empty(self):
        self.assertEqual(
            _parse_participants_flag('["Alice", "", "Bob"]'),
            ["Alice", "Bob"],
        )


class TestApplyParticipantsOverride(unittest.TestCase):
    def test_sets_creator_and_attendees(self):
        meeting = Meeting(
            creator=Participant(name="OldCreator"),
            attendees=[Participant(name="OldAttendee")],
        )
        _apply_participants_override(meeting, ["Alice", "Bob", "Carol"])
        self.assertEqual(meeting.creator.name, "Alice")
        self.assertEqual(
            [a.name for a in meeting.attendees], ["Bob", "Carol"]
        )

    def test_empty_list_noop(self):
        meeting = Meeting(creator=Participant(name="Keep"))
        _apply_participants_override(meeting, [])
        self.assertEqual(meeting.creator.name, "Keep")


class TestParticipantsFlagInCLI(unittest.TestCase):
    def test_participants_override_applied_to_meeting_data(self):
        meeting_data = {
            "id": "mcp-part",
            "title": "Participants Override",
            "date": "2026-04-15",
            "participants": ["Eckrag"],
        }
        with tempfile.NamedTemporaryFile(mode="w", suffix=".json", delete=False) as mf:
            json.dump(meeting_data, mf)
            md_path = mf.name
        try:
            import io
            import sys

            captured = io.StringIO()
            old_stdout = sys.stdout
            sys.stdout = captured
            try:
                rc = main([
                    "render", "mcp-part",
                    "--meeting-data", md_path,
                    "--participants", '["Alice","Bob","Carol","Dave"]',
                ])
            finally:
                sys.stdout = old_stdout
            self.assertEqual(rc, 0)
            output = captured.getvalue()
            self.assertIn("Alice, Bob, Carol, Dave", output)
            self.assertNotIn("Eckrag", output)
        finally:
            os.unlink(md_path)


class TestReadTranscriptFile(unittest.TestCase):
    def test_plain_text_passthrough(self):
        with tempfile.NamedTemporaryFile(mode="w", suffix=".md", delete=False) as f:
            f.write("**You:** Hi\n\n**Other:** Hello")
            path = f.name
        try:
            self.assertIn("**You:** Hi", _read_transcript_file(path))
        finally:
            os.unlink(path)

    def test_mcp_wrapper_string_transcript(self):
        wrapper = {
            "id": "abc",
            "title": "Big meeting",
            "transcript": "**You:** Hi\n\n**Other:** Hello",
        }
        with tempfile.NamedTemporaryFile(mode="w", suffix=".json", delete=False) as f:
            json.dump(wrapper, f)
            path = f.name
        try:
            result = _read_transcript_file(path)
            self.assertEqual(result, "**You:** Hi\n\n**Other:** Hello")
            self.assertNotIn("\"id\"", result)
            self.assertNotIn("\"title\"", result)
        finally:
            os.unlink(path)

    def test_mcp_wrapper_structured_list(self):
        wrapper = {
            "id": "abc",
            "title": "Big meeting",
            "transcript": [
                {"speaker": "microphone", "text": "Hello."},
                {"speaker": "system", "text": "Hi there."},
            ],
        }
        with tempfile.NamedTemporaryFile(mode="w", suffix=".json", delete=False) as f:
            json.dump(wrapper, f)
            path = f.name
        try:
            result = _read_transcript_file(path)
            self.assertIn("**You:** Hello.", result)
            self.assertIn("**Other:** Hi there.", result)
        finally:
            os.unlink(path)

    def test_non_wrapper_json_passthrough(self):
        # JSON but not a {transcript: ...} envelope — should pass through unchanged
        with tempfile.NamedTemporaryFile(mode="w", suffix=".json", delete=False) as f:
            f.write('{"other": "shape"}')
            path = f.name
        try:
            result = _read_transcript_file(path)
            self.assertEqual(result, '{"other": "shape"}')
        finally:
            os.unlink(path)


class TestNormalizeTranscriptText(unittest.TestCase):
    def test_passes_through_when_no_markers(self):
        text = "**You:** Hello\n\n**Other:** Hi"
        self.assertEqual(_normalize_transcript_text(text), text)

    def test_splits_inline_me_them(self):
        # Real Granola MCP transcript shape: one long line with inline Me:/Them:
        text = " Them: Recording in progress. I see you. Me: Thanks. Them: Ready?"
        result = _normalize_transcript_text(text)
        lines = result.split("\n\n")
        self.assertEqual(len(lines), 3)
        self.assertTrue(lines[0].startswith("**Other:**"))
        self.assertIn("Recording in progress", lines[0])
        self.assertTrue(lines[1].startswith("**You:**"))
        self.assertIn("Thanks", lines[1])
        self.assertTrue(lines[2].startswith("**Other:**"))

    def test_wrapper_with_inline_markers(self):
        wrapper = {
            "id": "abc",
            "title": "Big",
            "transcript": " Them: Hi. Me: Hello.",
        }
        with tempfile.NamedTemporaryFile(mode="w", suffix=".json", delete=False) as f:
            json.dump(wrapper, f)
            path = f.name
        try:
            result = _read_transcript_file(path)
            self.assertIn("**Other:** Hi.", result)
            self.assertIn("**You:** Hello.", result)
        finally:
            os.unlink(path)

    def test_empty_returns_empty(self):
        self.assertEqual(_normalize_transcript_text(""), "")


class TestFormatMcpTranscriptEntries(unittest.TestCase):
    def test_speaker_source_normalization(self):
        entries = [
            {"speaker": "microphone", "text": "A"},
            {"speaker": "system", "text": "B"},
            {"speaker": "Alice", "text": "C"},
        ]
        result = _format_mcp_transcript_entries(entries)
        self.assertIn("**You:** A", result)
        self.assertIn("**Other:** B", result)
        self.assertIn("**Alice:** C", result)

    def test_skips_empty_text(self):
        entries = [
            {"speaker": "Alice", "text": ""},
            {"speaker": "Bob", "text": "Real line"},
        ]
        result = _format_mcp_transcript_entries(entries)
        self.assertIn("**Bob:** Real line", result)
        self.assertNotIn("**Alice:**", result)


if __name__ == "__main__":
    unittest.main()
