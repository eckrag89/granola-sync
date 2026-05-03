"""Tests for matcher.find_existing_match."""

import os
import tempfile
import textwrap
import unittest

from granola_sync.matcher import find_existing_match


def _write(path: str, content: str) -> None:
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        f.write(textwrap.dedent(content).lstrip("\n"))


class FindExistingMatchTests(unittest.TestCase):
    def test_finds_match_in_nested_subfolder(self) -> None:
        with tempfile.TemporaryDirectory() as root:
            _write(
                os.path.join(root, "Alice", "May 1 - 1-1.md"),
                """
                ---
                meeting-title: 1-1 with Alice
                status: draft
                ---

                ## Prep Notes
                """,
            )
            matches = find_existing_match(root, "1-1 with Alice")
            self.assertEqual(len(matches), 1)
            self.assertTrue(matches[0].endswith("May 1 - 1-1.md"))

    def test_case_insensitive_and_trims_whitespace(self) -> None:
        with tempfile.TemporaryDirectory() as root:
            _write(
                os.path.join(root, "a.md"),
                """
                ---
                meeting-title:   Weekly Sync
                ---
                """,
            )
            self.assertEqual(len(find_existing_match(root, "weekly sync")), 1)
            self.assertEqual(len(find_existing_match(root, "  Weekly SYNC  ")), 1)

    def test_handles_quoted_yaml_title(self) -> None:
        with tempfile.TemporaryDirectory() as root:
            _write(
                os.path.join(root, "a.md"),
                """
                ---
                meeting-title: "1-1: Alice & Bob"
                ---
                """,
            )
            matches = find_existing_match(root, "1-1: Alice & Bob")
            self.assertEqual(len(matches), 1)

    def test_returns_multiple_when_ambiguous(self) -> None:
        with tempfile.TemporaryDirectory() as root:
            _write(
                os.path.join(root, "a", "first.md"),
                """
                ---
                meeting-title: Standup
                ---
                """,
            )
            _write(
                os.path.join(root, "b", "second.md"),
                """
                ---
                meeting-title: Standup
                ---
                """,
            )
            matches = find_existing_match(root, "Standup")
            self.assertEqual(len(matches), 2)

    def test_no_match_returns_empty(self) -> None:
        with tempfile.TemporaryDirectory() as root:
            _write(
                os.path.join(root, "a.md"),
                """
                ---
                meeting-title: Other
                ---
                """,
            )
            self.assertEqual(find_existing_match(root, "Standup"), [])

    def test_skips_files_without_meeting_title_frontmatter(self) -> None:
        with tempfile.TemporaryDirectory() as root:
            _write(
                os.path.join(root, "no-fm.md"),
                "## Just content\n\nno frontmatter here\n",
            )
            _write(
                os.path.join(root, "wrong-field.md"),
                """
                ---
                title: Standup
                ---
                """,
            )
            self.assertEqual(find_existing_match(root, "Standup"), [])

    def test_empty_search_term_returns_empty(self) -> None:
        with tempfile.TemporaryDirectory() as root:
            _write(
                os.path.join(root, "a.md"),
                """
                ---
                meeting-title:
                ---
                """,
            )
            # Both empty — but empty search short-circuits to []
            self.assertEqual(find_existing_match(root, ""), [])

    def test_missing_folder_returns_empty(self) -> None:
        self.assertEqual(find_existing_match("/nonexistent/path", "anything"), [])


class DateFilterTests(unittest.TestCase):
    """The date-frontmatter filter prevents recurring-meeting collisions."""

    def test_date_mismatch_excludes_prior_pulled_meeting(self) -> None:
        # Two recurring 1-1s: one pulled previously (date set to its own
        # past date), and a fresh prep note for today's iteration. Pulling
        # today's meeting must not land on yesterday's already-pulled file.
        with tempfile.TemporaryDirectory() as root:
            _write(
                os.path.join(root, "prior.md"),
                """
                ---
                date: 2026-04-22
                meeting-title: 1-1 with Alice
                ---
                """,
            )
            _write(
                os.path.join(root, "today_prep.md"),
                """
                ---
                date:
                meeting-title: 1-1 with Alice
                ---
                """,
            )
            matches = find_existing_match(root, "1-1 with Alice", "2026-05-01")
            self.assertEqual(len(matches), 1)
            self.assertTrue(matches[0].endswith("today_prep.md"))

    def test_matching_date_keeps_candidate(self) -> None:
        # A re-pull of an already-populated meeting still matches.
        with tempfile.TemporaryDirectory() as root:
            _write(
                os.path.join(root, "a.md"),
                """
                ---
                date: 2026-05-01
                meeting-title: Standup
                ---
                """,
            )
            self.assertEqual(
                len(find_existing_match(root, "Standup", "2026-05-01")), 1
            )

    def test_empty_file_date_keeps_candidate(self) -> None:
        # Prep-note convention: empty date frontmatter always matches.
        with tempfile.TemporaryDirectory() as root:
            _write(
                os.path.join(root, "a.md"),
                """
                ---
                date:
                meeting-title: Standup
                ---
                """,
            )
            self.assertEqual(
                len(find_existing_match(root, "Standup", "2026-05-01")), 1
            )

    def test_empty_meeting_date_skips_filter(self) -> None:
        # Caller passing empty meeting_date falls back to title-only — no
        # date filter applied. Backward-compatible default.
        with tempfile.TemporaryDirectory() as root:
            _write(
                os.path.join(root, "a.md"),
                """
                ---
                date: 2026-04-22
                meeting-title: Standup
                ---
                """,
            )
            self.assertEqual(len(find_existing_match(root, "Standup")), 1)

    def test_iso_datetime_compares_by_date_prefix(self) -> None:
        # File frontmatter sometimes carries a time component; we compare
        # only the YYYY-MM-DD prefix.
        with tempfile.TemporaryDirectory() as root:
            _write(
                os.path.join(root, "a.md"),
                """
                ---
                date: 2026-05-01T10:30:00Z
                meeting-title: Standup
                ---
                """,
            )
            self.assertEqual(
                len(find_existing_match(root, "Standup", "2026-05-01")), 1
            )


if __name__ == "__main__":
    unittest.main()
