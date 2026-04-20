"""Tests for config loading and path resolution."""

import json
import os
import tempfile
import unittest

from granola_sync.config import Config, resolve_output_path, _safe_filename
from granola_sync.models import CalendarEvent, Meeting, parse_datetime


class TestConfigLoad(unittest.TestCase):
    def test_load_from_file(self):
        data = {
            "folder_mappings": {"Folder A": "/path/to/a"},
            "default_destination": "/path/to/default",
        }
        with tempfile.NamedTemporaryFile(mode="w", suffix=".json", delete=False) as f:
            json.dump(data, f)
            path = f.name
        try:
            config = Config.load(path)
            self.assertEqual(config.folder_mappings["Folder A"], "/path/to/a")
            self.assertEqual(config.default_destination, "/path/to/default")
        finally:
            os.unlink(path)

    def test_missing_file_returns_defaults(self):
        config = Config.load("/nonexistent/config.json")
        self.assertEqual(config.folder_mappings, {})
        self.assertEqual(config.default_destination, "")


class TestResolveOutputPath(unittest.TestCase):
    def test_mapped_folder(self):
        config = Config(
            folder_mappings={"Team Meetings": "/vault/team"},
            default_destination="/vault/default",
        )
        meeting = Meeting(
            title="Standup",
            folder="Team Meetings",
            calendar=CalendarEvent(start=parse_datetime("2026-03-15T09:00:00Z")),
        )
        path = resolve_output_path(meeting, config)
        self.assertEqual(path, "/vault/team/2026-03-15 - Standup - Meeting Notes.md")

    def test_unmapped_folder_uses_default(self):
        config = Config(
            folder_mappings={},
            default_destination="/vault/default",
        )
        meeting = Meeting(
            title="Random Chat",
            folder="Unknown Folder",
            calendar=CalendarEvent(start=parse_datetime("2026-04-01T10:00:00Z")),
        )
        path = resolve_output_path(meeting, config)
        self.assertTrue(path.startswith("/vault/default/"))
        self.assertIn("2026-04-01 - Random Chat", path)

    def test_no_folder_uses_default(self):
        config = Config(default_destination="/vault/default")
        meeting = Meeting(title="Meeting", created_at=parse_datetime("2026-01-01T00:00:00Z"))
        path = resolve_output_path(meeting, config)
        self.assertTrue(path.startswith("/vault/default/"))

    def test_no_date(self):
        config = Config(default_destination="/vault")
        meeting = Meeting(title="Dateless")
        path = resolve_output_path(meeting, config)
        self.assertIn("undated", path)

    def test_folder_override_wins_over_mapping(self):
        config = Config(
            folder_mappings={"Team Meetings": "/vault/team"},
            default_destination="/vault/default",
        )
        meeting = Meeting(
            title="Standup",
            folder="Team Meetings",
            calendar=CalendarEvent(start=parse_datetime("2026-03-15T09:00:00Z")),
        )
        path = resolve_output_path(
            meeting, config, folder_override="/vault/overridden"
        )
        self.assertEqual(
            path, "/vault/overridden/2026-03-15 - Standup - Meeting Notes.md"
        )

    def test_title_override_replaces_filename_base(self):
        config = Config(default_destination="/vault")
        meeting = Meeting(
            title="Original",
            calendar=CalendarEvent(start=parse_datetime("2026-03-15T09:00:00Z")),
        )
        path = resolve_output_path(meeting, config, title_override="Weekly Sync")
        self.assertEqual(path, "/vault/Weekly Sync.md")

    def test_both_overrides(self):
        config = Config(default_destination="/vault")
        meeting = Meeting(title="Ignored")
        path = resolve_output_path(
            meeting,
            config,
            folder_override="/custom/folder",
            title_override="Custom Name",
        )
        self.assertEqual(path, "/custom/folder/Custom Name.md")


class TestSafeFilename(unittest.TestCase):
    def test_strips_unsafe_chars(self):
        result = _safe_filename('Meeting: "Important" <Urgent>')
        self.assertNotIn(":", result)
        self.assertNotIn('"', result)
        self.assertNotIn("<", result)

    def test_truncates_long_title(self):
        result = _safe_filename("A" * 200)
        self.assertLessEqual(len(result), 80)

    def test_collapses_whitespace(self):
        result = _safe_filename("Hello   World")
        self.assertEqual(result, "Hello World")


if __name__ == "__main__":
    unittest.main()
