"""Tests for migrate.migrate_file and migrate_folder."""

import os
import tempfile
import textwrap
import unittest

from granola_sync.migrate import migrate_file, migrate_folder


def _dedent(s: str) -> str:
    return textwrap.dedent(s).lstrip("\n")


class MigrateFileTests(unittest.TestCase):
    def test_bumps_all_tool_sections_from_h2_to_h1(self) -> None:
        original = _dedent(
            """
            ---
            meeting-title: Standup
            ---

            ## Notes

            n

            ## Enhanced Notes

            e

            ## Transcript

            t
            """
        )
        new, changes = migrate_file(original)
        self.assertTrue(changes.changed)
        self.assertEqual(
            changes.bumped_tool_sections, ["Notes", "Enhanced Notes", "Transcript"]
        )
        self.assertIn("# Notes\n", new)
        self.assertIn("# Enhanced Notes\n", new)
        self.assertIn("# Transcript\n", new)
        self.assertNotIn("## Notes", new)
        self.assertNotIn("## Enhanced Notes", new)

    def test_renames_legacy_notes_h1_to_prep_notes(self) -> None:
        original = _dedent(
            """
            ---
            meeting-title: Bob Catchup
            ---

            # Notes
            ## General Banter
            * topic
            """
        )
        new, changes = migrate_file(original)
        self.assertTrue(changes.renamed_legacy_notes_h1)
        self.assertIn("# Prep Notes", new)
        self.assertNotIn("# Notes\n", new)
        # User sub-headings are NOT touched
        self.assertIn("## General Banter", new)

    def test_drops_legacy_title_h1_matching_frontmatter(self) -> None:
        original = _dedent(
            """
            ---
            meeting-title: "Alice / Bob - 1:1"
            ---

            # Alice / Bob - 1:1

            ## Notes

            n
            """
        )
        new, changes = migrate_file(original)
        self.assertTrue(changes.dropped_title_h1)
        self.assertNotIn("# Alice / Bob - 1:1", new)
        self.assertIn("# Notes", new)

    def test_user_h2_subheadings_under_prep_notes_left_alone(self) -> None:
        # User content like "## General Banter" inside prep should NOT be
        # bumped — only EXACT tool-section names get promoted.
        original = _dedent(
            """
            ---
            meeting-title: 1-1
            ---

            # Prep Notes

            ## General Banter
            ## Feedback
            ## PG Action Items

            ## Notes

            cached notes
            """
        )
        new, changes = migrate_file(original)
        self.assertEqual(changes.bumped_tool_sections, ["Notes"])
        self.assertIn("## General Banter", new)
        self.assertIn("## Feedback", new)
        self.assertIn("## PG Action Items", new)
        self.assertIn("# Notes\n", new)

    def test_user_h2_with_trailing_text_not_bumped(self) -> None:
        # `## Notes about today` is user content — NOT a tool-section heading.
        # The regex requires the heading to end exactly at the section name.
        original = _dedent(
            """
            ---
            meeting-title: Foo
            ---

            ## Notes about today
            ## Notes
            """
        )
        new, changes = migrate_file(original)
        self.assertEqual(changes.bumped_tool_sections, ["Notes"])
        self.assertIn("## Notes about today", new)  # untouched
        self.assertIn("# Notes\n", new)  # bumped

    def test_idempotent_on_already_migrated_file(self) -> None:
        original = _dedent(
            """
            ---
            meeting-title: Foo
            ---

            # Prep Notes

            prep

            # Notes

            n

            # Enhanced Notes

            e

            # Transcript

            t
            """
        )
        new, changes = migrate_file(original)
        self.assertFalse(changes.changed)
        self.assertEqual(new, original)

    def test_combined_legacy_layout(self) -> None:
        # An old vault file with both the title H1 AND legacy `# Notes` AND
        # H2 tool sections. All three rules fire.
        original = _dedent(
            """
            ---
            meeting-title: "1-1 with Alice"
            ---

            # 1-1 with Alice

            # Notes
            ## General Banter
            * how was the trip
            ## Enhanced Notes

            stale e

            ## Transcript

            stale t
            """
        )
        new, changes = migrate_file(original)
        self.assertTrue(changes.dropped_title_h1)
        self.assertTrue(changes.renamed_legacy_notes_h1)
        self.assertEqual(
            changes.bumped_tool_sections, ["Enhanced Notes", "Transcript"]
        )
        self.assertNotIn("# 1-1 with Alice", new)
        self.assertIn("# Prep Notes", new)
        self.assertIn("## General Banter", new)
        self.assertIn("# Enhanced Notes\n", new)
        self.assertIn("# Transcript\n", new)

    def test_no_frontmatter_safe(self) -> None:
        original = "## Notes\n\nn\n"
        new, changes = migrate_file(original)
        self.assertTrue(changes.changed)
        self.assertIn("# Notes", new)


class MigrateFolderTests(unittest.TestCase):
    def test_walks_recursively_only_returns_changed(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            # File needing migration
            os.makedirs(os.path.join(tmp, "sub"))
            stale_path = os.path.join(tmp, "sub", "stale.md")
            with open(stale_path, "w") as f:
                f.write("---\nmeeting-title: Foo\n---\n\n## Notes\n\nn\n")
            # Already-migrated file (no change). Has Prep Notes alongside,
            # which signals this is post-migration — `# Notes` is a tool
            # section, not the legacy prep wrapper.
            clean_path = os.path.join(tmp, "clean.md")
            with open(clean_path, "w") as f:
                f.write(
                    "---\nmeeting-title: Foo\n---\n\n"
                    "# Prep Notes\n\n# Notes\n\nn\n"
                )
            # Non-markdown — ignored
            with open(os.path.join(tmp, "skip.txt"), "w") as f:
                f.write("not a meeting note")

            results = migrate_folder(tmp, apply=False)
            paths = [r.path for r in results]
            self.assertEqual(len(results), 1)
            self.assertEqual(paths, [stale_path])
            # Dry-run did NOT write
            with open(stale_path) as f:
                self.assertIn("## Notes", f.read())

    def test_skips_obsidian_index_files_starting_with_star(self) -> None:
        # Files like *Summary.md, *Home.md, *Meetings to Pull.md are Obsidian
        # aggregator/index files, not meeting notes. The migration must skip
        # them even when they contain `## Notes`-style headings.
        with tempfile.TemporaryDirectory() as tmp:
            index_path = os.path.join(tmp, "*Meetings to Pull.md")
            with open(index_path, "w") as f:
                f.write("## Notes\n\n- todo\n")
            note_path = os.path.join(tmp, "real-note.md")
            with open(note_path, "w") as f:
                f.write("---\nmeeting-title: Foo\n---\n\n## Notes\n\nn\n")

            results = migrate_folder(tmp, apply=True)
            self.assertEqual(len(results), 1)
            self.assertTrue(results[0].path.endswith("real-note.md"))
            # Index file untouched
            with open(index_path) as f:
                self.assertIn("## Notes", f.read())

    def test_apply_writes_changes(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            p = os.path.join(tmp, "a.md")
            with open(p, "w") as f:
                f.write("---\nmeeting-title: Foo\n---\n\n## Notes\n\nn\n")
            results = migrate_folder(tmp, apply=True)
            self.assertEqual(len(results), 1)
            with open(p) as f:
                content = f.read()
            self.assertIn("# Notes", content)
            self.assertNotIn("## Notes", content)


if __name__ == "__main__":
    unittest.main()
