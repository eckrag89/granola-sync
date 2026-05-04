"""Tests for the prep subcommand and prep-note rendering."""

import io
import json
import os
import sys
import tempfile
import unittest
from unittest.mock import patch

from granola_sync.__main__ import main
from granola_sync.config import Config
from granola_sync.prep import render_prep_note


class RenderPrepNoteTests(unittest.TestCase):
    """The render layer — independent of CLI plumbing."""

    def test_includes_all_frontmatter_fields(self) -> None:
        body = render_prep_note(
            title="Weekly Sync",
            date="2026-05-08",
            attendees=["Alice", "Bob"],
            outlook_event_id="AAMkAGI=",
        )
        self.assertIn("date: 2026-05-08", body)
        self.assertIn("meeting-title: Weekly Sync", body)
        self.assertIn("outlook-event-id: AAMkAGI=", body)
        self.assertIn("status: draft", body)
        self.assertIn("- Alice", body)
        self.assertIn("- Bob", body)
        self.assertIn("## Prep Notes", body)
        self.assertNotIn("## Notes", body)
        self.assertNotIn("## Enhanced Notes", body)
        self.assertNotIn("## Transcript", body)

    def test_empty_attendees_renders_explicit_empty_list(self) -> None:
        body = render_prep_note(title="Solo", date="2026-05-08", attendees=[])
        self.assertIn("attendees: []", body)

    def test_yaml_quotes_titles_with_special_chars(self) -> None:
        body = render_prep_note(
            title="1-1: Alice & Bob", date="2026-05-08", attendees=["Alice"]
        )
        self.assertIn('meeting-title: "1-1: Alice & Bob"', body)

    def test_omits_outlook_event_id_when_blank(self) -> None:
        body = render_prep_note(title="Foo", date="2026-05-08", attendees=[])
        # Field is present so the user can fill in later, but value is empty
        self.assertIn("outlook-event-id:", body)


class PrepCLITests(unittest.TestCase):
    """End-to-end via the CLI entry point."""

    def _run(self, argv, *, default_destination):
        captured = io.StringIO()
        old_stdout = sys.stdout
        sys.stdout = captured
        try:
            with patch("granola_sync.__main__.Config.load") as mock_config:
                mock_config.return_value = Config(
                    folder_mappings={},
                    default_destination=default_destination,
                )
                rc = main(argv)
        finally:
            sys.stdout = old_stdout
        return rc, captured.getvalue()

    def test_writes_file_to_default_destination(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            rc, out = self._run(
                [
                    "prep",
                    "--title", "Weekly Sync",
                    "--date", "2026-05-08",
                    "--attendees", '["Alice","Bob"]',
                    "--outlook-event-id", "AAMkAGI=",
                ],
                default_destination=tmpdir,
            )
            self.assertEqual(rc, 0)
            self.assertIn("Created prep note at:", out)
            files = [f for f in os.listdir(tmpdir) if f.endswith(".md")]
            self.assertEqual(len(files), 1)
            with open(os.path.join(tmpdir, files[0])) as f:
                content = f.read()
            self.assertIn("meeting-title: Weekly Sync", content)
            self.assertIn("outlook-event-id: AAMkAGI=", content)
            self.assertIn("- Alice", content)

    def test_output_folder_overrides_default(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            sub = os.path.join(tmpdir, "Custom", "Place")
            rc, out = self._run(
                [
                    "prep",
                    "--title", "Foo",
                    "--date", "2026-05-08",
                    "--attendees", "Alice",
                    "--output-folder", sub,
                ],
                default_destination=tmpdir,
            )
            self.assertEqual(rc, 0)
            self.assertTrue(os.path.isdir(sub))
            self.assertIn(sub, out)

    def test_existing_match_returns_exit_4(self) -> None:
        # Prep note already exists in the destination with matching title+date.
        with tempfile.TemporaryDirectory() as tmpdir:
            existing = os.path.join(tmpdir, "preexisting.md")
            with open(existing, "w") as f:
                f.write(
                    "---\n"
                    "date: 2026-05-08\n"
                    "meeting-title: Weekly Sync\n"
                    "---\n\n"
                    "## Prep Notes\n"
                )
            rc, out = self._run(
                [
                    "prep",
                    "--title", "Weekly Sync",
                    "--date", "2026-05-08",
                ],
                default_destination=tmpdir,
            )
            self.assertEqual(rc, 4)
            payload = json.loads(out)
            self.assertTrue(payload["existing"])
            self.assertIn(existing, payload["candidates"])
            self.assertEqual(payload["meeting_title"], "Weekly Sync")
            self.assertEqual(payload["date"], "2026-05-08")

    def test_force_writes_through_existing_match(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            existing = os.path.join(
                tmpdir, "2026-05-08 - Weekly Sync - Meeting Notes.md"
            )
            with open(existing, "w") as f:
                f.write(
                    "---\n"
                    "date: 2026-05-08\n"
                    "meeting-title: Weekly Sync\n"
                    "---\n\n"
                    "old prep content that should be overwritten\n"
                )
            rc, _ = self._run(
                [
                    "prep",
                    "--title", "Weekly Sync",
                    "--date", "2026-05-08",
                    "--force",
                ],
                default_destination=tmpdir,
            )
            self.assertEqual(rc, 0)
            with open(existing) as f:
                content = f.read()
            self.assertNotIn("old prep content", content)
            self.assertIn("## Prep Notes", content)


if __name__ == "__main__":
    unittest.main()
