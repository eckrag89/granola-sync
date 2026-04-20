"""Tests for ProseMirror to Markdown conversion."""

import json
import os
import unittest

from granola_sync.prosemirror import prosemirror_to_markdown

FIXTURES_DIR = os.path.join(os.path.dirname(__file__), "fixtures")


class TestProseMirrorToMarkdown(unittest.TestCase):
    """Test the ProseMirror converter against fixture data."""

    @classmethod
    def setUpClass(cls):
        with open(os.path.join(FIXTURES_DIR, "sample_prosemirror.json")) as f:
            cls.sample_doc = json.load(f)

    def test_full_document_conversion(self):
        result = prosemirror_to_markdown(self.sample_doc)
        self.assertIn("# Meeting Notes", result)
        self.assertIn("## Key Discussion Points", result)
        self.assertIn("**three critical items**", result)
        self.assertIn("*revised deployment schedule*", result)
        self.assertIn("[project plan](https://example.com/project-plan)", result)

    def test_headings(self):
        doc = {
            "type": "doc",
            "content": [
                {"type": "heading", "attrs": {"level": 1}, "content": [{"type": "text", "text": "H1"}]},
                {"type": "heading", "attrs": {"level": 2}, "content": [{"type": "text", "text": "H2"}]},
                {"type": "heading", "attrs": {"level": 3}, "content": [{"type": "text", "text": "H3"}]},
            ],
        }
        result = prosemirror_to_markdown(doc)
        self.assertIn("# H1", result)
        self.assertIn("## H2", result)
        self.assertIn("### H3", result)

    def test_paragraph_plain(self):
        doc = {
            "type": "doc",
            "content": [
                {"type": "paragraph", "content": [{"type": "text", "text": "Hello world"}]},
            ],
        }
        self.assertEqual(prosemirror_to_markdown(doc), "Hello world")

    def test_paragraph_with_marks(self):
        doc = {
            "type": "doc",
            "content": [
                {
                    "type": "paragraph",
                    "content": [
                        {"type": "text", "text": "This is "},
                        {"type": "text", "marks": [{"type": "bold"}], "text": "bold"},
                        {"type": "text", "text": " and "},
                        {"type": "text", "marks": [{"type": "italic"}], "text": "italic"},
                    ],
                },
            ],
        }
        result = prosemirror_to_markdown(doc)
        self.assertEqual(result, "This is **bold** and *italic*")

    def test_link_mark(self):
        doc = {
            "type": "doc",
            "content": [
                {
                    "type": "paragraph",
                    "content": [
                        {
                            "type": "text",
                            "marks": [{"type": "link", "attrs": {"href": "https://example.com"}}],
                            "text": "click here",
                        },
                    ],
                },
            ],
        }
        result = prosemirror_to_markdown(doc)
        self.assertEqual(result, "[click here](https://example.com)")

    def test_bullet_list(self):
        doc = {
            "type": "doc",
            "content": [
                {
                    "type": "bulletList",
                    "content": [
                        {"type": "listItem", "content": [{"type": "paragraph", "content": [{"type": "text", "text": "Item one"}]}]},
                        {"type": "listItem", "content": [{"type": "paragraph", "content": [{"type": "text", "text": "Item two"}]}]},
                    ],
                },
            ],
        }
        result = prosemirror_to_markdown(doc)
        self.assertIn("- Item one", result)
        self.assertIn("- Item two", result)

    def test_ordered_list(self):
        doc = {
            "type": "doc",
            "content": [
                {
                    "type": "orderedList",
                    "attrs": {"start": 1},
                    "content": [
                        {"type": "listItem", "content": [{"type": "paragraph", "content": [{"type": "text", "text": "First"}]}]},
                        {"type": "listItem", "content": [{"type": "paragraph", "content": [{"type": "text", "text": "Second"}]}]},
                    ],
                },
            ],
        }
        result = prosemirror_to_markdown(doc)
        self.assertIn("1. First", result)
        self.assertIn("2. Second", result)

    def test_nested_bullet_list(self):
        doc = {
            "type": "doc",
            "content": [
                {
                    "type": "bulletList",
                    "content": [
                        {
                            "type": "listItem",
                            "content": [
                                {"type": "paragraph", "content": [{"type": "text", "text": "Parent"}]},
                                {
                                    "type": "bulletList",
                                    "content": [
                                        {"type": "listItem", "content": [{"type": "paragraph", "content": [{"type": "text", "text": "Child"}]}]},
                                    ],
                                },
                            ],
                        },
                    ],
                },
            ],
        }
        result = prosemirror_to_markdown(doc)
        self.assertIn("- Parent", result)
        self.assertIn("  - Child", result)

    def test_full_fixture_nested_lists(self):
        """Verify the full fixture converts nested lists correctly."""
        result = prosemirror_to_markdown(self.sample_doc)
        self.assertIn("- Alice to send the updated proposal by Friday", result)
        self.assertIn("  - Specifically the authentication flow", result)
        self.assertIn("  - And the rate limiting configuration", result)

    def test_full_fixture_ordered_list(self):
        result = prosemirror_to_markdown(self.sample_doc)
        self.assertIn("1. Complete the security audit", result)
        self.assertIn("2. Migrate the staging environment", result)
        self.assertIn("3. Deploy to production", result)

    def test_empty_document(self):
        self.assertEqual(prosemirror_to_markdown(None), "")
        self.assertEqual(prosemirror_to_markdown({}), "")
        self.assertEqual(prosemirror_to_markdown({"type": "doc"}), "")
        self.assertEqual(prosemirror_to_markdown({"type": "doc", "content": []}), "")

    def test_empty_paragraph(self):
        doc = {
            "type": "doc",
            "content": [
                {"type": "paragraph", "attrs": {"id": "test"}},
            ],
        }
        result = prosemirror_to_markdown(doc)
        self.assertEqual(result, "")

    def test_heading_with_bold_mark(self):
        doc = {
            "type": "doc",
            "content": [
                {
                    "type": "heading",
                    "attrs": {"level": 1},
                    "content": [{"type": "text", "marks": [{"type": "bold"}], "text": "Bold Heading"}],
                },
            ],
        }
        result = prosemirror_to_markdown(doc)
        self.assertEqual(result, "# **Bold Heading**")

    def test_trailing_link_in_paragraph(self):
        """Verify the fixture's trailing link paragraph."""
        result = prosemirror_to_markdown(self.sample_doc)
        self.assertIn("[deployment runbook](https://example.com/wiki/runbook)", result)
        self.assertIn("See the", result)
        self.assertIn("for full steps.", result)


if __name__ == "__main__":
    unittest.main()
