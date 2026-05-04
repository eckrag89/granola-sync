"""Tests for the section-ownership merger."""

import textwrap
import unittest

from granola_sync.merger import merge_files


def _dedent(s: str) -> str:
    return textwrap.dedent(s).lstrip("\n")


class MergeFilesTests(unittest.TestCase):
    def test_prep_notes_preserved_when_tool_sections_replaced(self) -> None:
        existing = _dedent(
            """
            ---
            date:
            type: client
            attendees: []
            meeting-title: Weekly Sync
            status: draft
            ---

            # Prep Notes

            - Discuss roadmap
            - Ask about Q3 OKRs

            # Notes

            # Enhanced Notes

            # Transcript
            """
        )
        new_render = _dedent(
            """
            ---
            date: 2026-05-01
            meeting-title: Weekly Sync
            attendees:
              - Alice
              - Bob
            type:
            status: draft
            ---

            # Prep Notes

            # Notes

            Real notes content.

            # Enhanced Notes

            AI summary.

            # Transcript

            **You:** Hello.
            """
        )
        merged = merge_files(existing, new_render)

        self.assertIn("- Discuss roadmap", merged)
        self.assertIn("- Ask about Q3 OKRs", merged)
        self.assertIn("Real notes content.", merged)
        self.assertIn("AI summary.", merged)
        self.assertIn("**You:** Hello.", merged)

    def test_user_frontmatter_preserved_tool_fields_updated(self) -> None:
        existing = _dedent(
            """
            ---
            date:
            type: client
            attendees: []
            meeting-title:
            outlook-event-id: AAMkAGI=
            status: reviewed
            ---

            # Prep Notes

            prep
            """
        )
        new_render = _dedent(
            """
            ---
            date: 2026-05-01
            meeting-title: Client Intro
            attendees:
              - Alice
            type:
            status: draft
            ---

            # Notes

            n
            """
        )
        merged = merge_files(existing, new_render)

        # Tool fields updated from incoming
        self.assertIn("date: 2026-05-01", merged)
        self.assertIn("meeting-title: Client Intro", merged)
        self.assertIn("- Alice", merged)
        # User-set fields preserved (not overwritten by tool defaults)
        self.assertIn("type: client", merged)
        self.assertIn("status: reviewed", merged)
        # User-added fields preserved
        self.assertIn("outlook-event-id: AAMkAGI=", merged)

    def test_missing_tool_sections_are_appended_in_canonical_order(self) -> None:
        existing = _dedent(
            """
            ---
            meeting-title: Standup
            ---

            # Prep Notes

            prep stuff
            """
        )
        new_render = _dedent(
            """
            ---
            meeting-title: Standup
            ---

            # Notes

            cached notes

            # Enhanced Notes

            summary

            # Transcript

            transcript text
            """
        )
        merged = merge_files(existing, new_render)

        self.assertIn("prep stuff", merged)
        self.assertIn("cached notes", merged)
        self.assertIn("summary", merged)
        self.assertIn("transcript text", merged)

        # Order: Prep Notes (user) first, then canonical tool order
        idx_prep = merged.index("# Prep Notes")
        idx_notes = merged.index("# Notes")
        idx_enh = merged.index("# Enhanced Notes")
        idx_tx = merged.index("# Transcript")
        self.assertLess(idx_prep, idx_notes)
        self.assertLess(idx_notes, idx_enh)
        self.assertLess(idx_enh, idx_tx)

    def test_user_h2_subheadings_preserved_under_their_h1_section(self) -> None:
        # User content under # Prep Notes uses H2/H3 sub-headings. The merger
        # treats everything inside # Prep Notes as one user-owned blob —
        # sub-headings are not splitters and ride along with their parent.
        existing = _dedent(
            """
            ---
            meeting-title: 1-1 with Alice
            ---

            # Prep Notes

            ## General Banter

            * how was the trip

            ## PG&E Action Items

            * cleanup prototype

            # Enhanced Notes

            stale enhanced
            """
        )
        new_render = _dedent(
            """
            ---
            meeting-title: 1-1 with Alice
            ---

            # Enhanced Notes

            fresh enhanced
            """
        )
        merged = merge_files(existing, new_render)

        # All user H2 sub-headings under # Prep Notes preserved verbatim
        self.assertIn("## General Banter", merged)
        self.assertIn("* how was the trip", merged)
        self.assertIn("## PG&E Action Items", merged)
        self.assertIn("* cleanup prototype", merged)
        # Tool section content replaced
        self.assertIn("fresh enhanced", merged)
        self.assertNotIn("stale enhanced", merged)

    def test_repull_replaces_stale_tool_content(self) -> None:
        existing = _dedent(
            """
            ---
            meeting-title: Standup
            ---

            # Notes

            stale notes

            # Enhanced Notes

            stale summary

            # Transcript

            stale transcript
            """
        )
        new_render = _dedent(
            """
            ---
            meeting-title: Standup
            ---

            # Notes

            fresh notes

            # Enhanced Notes

            fresh summary

            # Transcript

            fresh transcript
            """
        )
        merged = merge_files(existing, new_render)

        for stale in ("stale notes", "stale summary", "stale transcript"):
            self.assertNotIn(stale, merged)
        for fresh in ("fresh notes", "fresh summary", "fresh transcript"):
            self.assertIn(fresh, merged)

    def test_existing_file_without_frontmatter_gets_full_frontmatter(self) -> None:
        existing = "# Prep Notes\n\nstuff\n"
        new_render = _dedent(
            """
            ---
            date: 2026-05-01
            meeting-title: Foo
            ---

            # Notes

            n
            """
        )
        merged = merge_files(existing, new_render)
        self.assertTrue(merged.startswith("---\n"))
        self.assertIn("meeting-title: Foo", merged)
        self.assertIn("stuff", merged)

    def test_missing_notes_lands_before_existing_enhanced_and_transcript(self) -> None:
        # Regression: when an existing prep note has Enhanced Notes + Transcript
        # but no Notes section, the missing Notes must slot in BEFORE Enhanced
        # Notes (canonical order: notes -> enhanced notes -> transcript), not
        # be appended at the end of the file.
        existing = _dedent(
            """
            ---
            meeting-title: 1-1
            ---

            # Prep Notes

            user prep

            # Enhanced Notes

            # Transcript
            """
        )
        new_render = _dedent(
            """
            ---
            meeting-title: 1-1
            ---

            # Notes

            cached notes

            # Enhanced Notes

            summary

            # Transcript

            transcript
            """
        )
        merged = merge_files(existing, new_render)
        idx_notes = merged.index("# Notes")
        idx_enh = merged.index("# Enhanced Notes")
        idx_tx = merged.index("# Transcript")
        self.assertLess(idx_notes, idx_enh)
        self.assertLess(idx_enh, idx_tx)
        self.assertIn("user prep", merged)
        self.assertIn("cached notes", merged)

    def test_user_section_ordering_preserved(self) -> None:
        # User put Prep Notes after Notes section in existing file. We don't
        # reorder — preserve original layout.
        existing = _dedent(
            """
            ---
            meeting-title: Test
            ---

            # Notes

            # Prep Notes

            prep at the bottom

            # Enhanced Notes

            # Transcript
            """
        )
        new_render = _dedent(
            """
            ---
            meeting-title: Test
            ---

            # Notes

            new notes

            # Enhanced Notes

            new enhanced

            # Transcript

            new transcript
            """
        )
        merged = merge_files(existing, new_render)
        self.assertIn("prep at the bottom", merged)
        self.assertLess(
            merged.index("# Notes"),
            merged.index("# Prep Notes"),
        )


class MeetingSummaryHeaderSectionTests(unittest.TestCase):
    """# Meeting Summary is a header section — always lives at the top of
    the body, even when other tool sections sit at the bottom."""

    def test_inserts_at_top_above_existing_prep_notes(self) -> None:
        existing = _dedent(
            """
            ---
            meeting-title: Sync
            ---

            # Prep Notes

            user prep
            """
        )
        new_render = _dedent(
            """
            ---
            meeting-title: Sync
            ---

            # Meeting Summary

            Two-line summary.

            # Notes

            n
            """
        )
        merged = merge_files(existing, new_render)
        self.assertLess(
            merged.index("# Meeting Summary"),
            merged.index("# Prep Notes"),
        )
        self.assertIn("user prep", merged)
        self.assertIn("Two-line summary.", merged)

    def test_inserts_after_free_text_preamble(self) -> None:
        # Free text before any H1 is treated as preamble — Meeting Summary
        # slots in just after it, before the first H1 user section.
        existing = _dedent(
            """
            ---
            meeting-title: Sync
            ---

            Quick context paragraph.

            # Prep Notes

            prep
            """
        )
        new_render = _dedent(
            """
            ---
            meeting-title: Sync
            ---

            # Meeting Summary

            Summary text.

            # Notes

            n
            """
        )
        merged = merge_files(existing, new_render)
        idx_preamble = merged.index("Quick context paragraph.")
        idx_summary = merged.index("# Meeting Summary")
        idx_prep = merged.index("# Prep Notes")
        self.assertLess(idx_preamble, idx_summary)
        self.assertLess(idx_summary, idx_prep)

    def test_repull_replaces_existing_meeting_summary_in_place(self) -> None:
        existing = _dedent(
            """
            ---
            meeting-title: Sync
            ---

            # Meeting Summary

            old summary

            # Prep Notes

            prep
            """
        )
        new_render = _dedent(
            """
            ---
            meeting-title: Sync
            ---

            # Meeting Summary

            new summary

            # Notes

            n
            """
        )
        merged = merge_files(existing, new_render)
        self.assertIn("new summary", merged)
        self.assertNotIn("old summary", merged)
        self.assertIn("prep", merged)

    def test_repull_without_summary_preserves_existing_summary(self) -> None:
        # Re-pull where the skill couldn't generate a summary (transcript
        # failed, etc) must NOT blow away the previous summary.
        existing = _dedent(
            """
            ---
            meeting-title: Sync
            ---

            # Meeting Summary

            preserved summary

            # Prep Notes

            prep
            """
        )
        new_render = _dedent(
            """
            ---
            meeting-title: Sync
            ---

            # Notes

            n
            """
        )
        merged = merge_files(existing, new_render)
        self.assertIn("preserved summary", merged)


if __name__ == "__main__":
    unittest.main()
