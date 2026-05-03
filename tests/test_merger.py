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

            ## Prep Notes

            - Discuss roadmap
            - Ask about Q3 OKRs

            ## Notes

            ## Enhanced Notes

            ## Transcript
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

            # Weekly Sync

            ## Prep Notes

            ## Notes

            Real notes content.

            ## Enhanced Notes

            AI summary.

            ## Transcript

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

            ## Prep Notes

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

            # Client Intro

            ## Notes

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

            ## Prep Notes

            prep stuff
            """
        )
        new_render = _dedent(
            """
            ---
            meeting-title: Standup
            ---

            ## Notes

            cached notes

            ## Enhanced Notes

            summary

            ## Transcript

            transcript text
            """
        )
        merged = merge_files(existing, new_render)

        self.assertIn("prep stuff", merged)
        self.assertIn("cached notes", merged)
        self.assertIn("summary", merged)
        self.assertIn("transcript text", merged)

        # Order: Prep Notes (user) first, then canonical tool order
        idx_prep = merged.index("## Prep Notes")
        idx_notes = merged.index("## Notes")
        idx_enh = merged.index("## Enhanced Notes")
        idx_tx = merged.index("## Transcript")
        self.assertLess(idx_prep, idx_notes)
        self.assertLess(idx_notes, idx_enh)
        self.assertLess(idx_enh, idx_tx)

    def test_legacy_h1_notes_preamble_preserved(self) -> None:
        # A pre-merge note style: H1 "# Notes" with prep content, then H2
        # tool sections waiting to be filled.
        existing = _dedent(
            """
            ---
            meeting-title: 1-1 with Alice
            ---

            # Notes

            ## General Banter

            * how was the trip

            ## Enhanced Notes

            ## Transcript
            """
        )
        new_render = _dedent(
            """
            ---
            meeting-title: 1-1 with Alice
            ---

            # 1-1 with Alice

            ## Notes

            cached notes

            ## Enhanced Notes

            summary

            ## Transcript

            transcript
            """
        )
        merged = merge_files(existing, new_render)

        # Legacy H1 + sub-H2 prep content preserved verbatim
        self.assertIn("# Notes", merged)
        self.assertIn("## General Banter", merged)
        self.assertIn("* how was the trip", merged)
        # Tool sections that DID exist (Enhanced Notes, Transcript) replaced
        self.assertIn("summary", merged)
        self.assertIn("transcript", merged)
        # Tool section that did NOT exist (## Notes) gets appended
        self.assertIn("cached notes", merged)
        # New H1 from incoming render is dropped (existing preamble wins)
        self.assertNotIn("# 1-1 with Alice", merged)

    def test_repull_replaces_stale_tool_content(self) -> None:
        existing = _dedent(
            """
            ---
            meeting-title: Standup
            ---

            ## Notes

            stale notes

            ## Enhanced Notes

            stale summary

            ## Transcript

            stale transcript
            """
        )
        new_render = _dedent(
            """
            ---
            meeting-title: Standup
            ---

            ## Notes

            fresh notes

            ## Enhanced Notes

            fresh summary

            ## Transcript

            fresh transcript
            """
        )
        merged = merge_files(existing, new_render)

        for stale in ("stale notes", "stale summary", "stale transcript"):
            self.assertNotIn(stale, merged)
        for fresh in ("fresh notes", "fresh summary", "fresh transcript"):
            self.assertIn(fresh, merged)

    def test_existing_file_without_frontmatter_gets_full_frontmatter(self) -> None:
        existing = "## Prep Notes\n\nstuff\n"
        new_render = _dedent(
            """
            ---
            date: 2026-05-01
            meeting-title: Foo
            ---

            ## Notes

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

            ## Prep Notes

            user prep

            ## Enhanced Notes

            ## Transcript
            """
        )
        new_render = _dedent(
            """
            ---
            meeting-title: 1-1
            ---

            ## Notes

            cached notes

            ## Enhanced Notes

            summary

            ## Transcript

            transcript
            """
        )
        merged = merge_files(existing, new_render)
        idx_notes = merged.index("## Notes")
        idx_enh = merged.index("## Enhanced Notes")
        idx_tx = merged.index("## Transcript")
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

            ## Notes

            ## Prep Notes

            prep at the bottom

            ## Enhanced Notes

            ## Transcript
            """
        )
        new_render = _dedent(
            """
            ---
            meeting-title: Test
            ---

            ## Notes

            new notes

            ## Enhanced Notes

            new enhanced

            ## Transcript

            new transcript
            """
        )
        merged = merge_files(existing, new_render)
        self.assertIn("prep at the bottom", merged)
        self.assertLess(
            merged.index("## Notes"),
            merged.index("## Prep Notes"),
        )


if __name__ == "__main__":
    unittest.main()
