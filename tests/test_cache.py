"""Tests for cache parsing."""

import json
import os
import tempfile
import unittest

from granola_sync.cache import (
    find_cache_file,
    get_meeting_by_id,
    load_cache,
    load_meetings,
    search_meetings,
    _build_folder_map,
    _extract_cache_enhanced_notes,
    _parse_document,
)
from granola_sync.models import parse_datetime

FIXTURES_DIR = os.path.join(os.path.dirname(__file__), "fixtures")


class TestFindCacheFile(unittest.TestCase):
    def test_finds_cache_file(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            path = os.path.join(tmpdir, "cache-v6.json")
            with open(path, "w") as f:
                json.dump({"cache": {"version": 5, "state": {}}}, f)
            result = find_cache_file(tmpdir)
            self.assertEqual(result, path)

    def test_returns_none_for_empty_dir(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            result = find_cache_file(tmpdir)
            self.assertIsNone(result)

    def test_detects_encrypted_file(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            path = os.path.join(tmpdir, "cache-v6.json")
            with open(path, "wb") as f:
                f.write(b"\x00\x01\x02encrypted data")
            result = find_cache_file(tmpdir)
            self.assertIsNone(result)

    def test_newest_by_mtime(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            old = os.path.join(tmpdir, "cache-v5.json")
            new = os.path.join(tmpdir, "cache-v6.json")
            with open(old, "w") as f:
                json.dump({"cache": {"version": 4, "state": {}}}, f)
            with open(new, "w") as f:
                json.dump({"cache": {"version": 5, "state": {}}}, f)
            # Touch new file to ensure it's newer
            os.utime(new, None)
            result = find_cache_file(tmpdir)
            self.assertEqual(result, new)


class TestLoadCache(unittest.TestCase):
    def test_normal_structure(self):
        with tempfile.NamedTemporaryFile(mode="w", suffix=".json", delete=False) as f:
            json.dump({"cache": {"version": 5, "state": {"documents": {}}}}, f)
            path = f.name
        try:
            state = load_cache(path)
            self.assertIn("documents", state)
        finally:
            os.unlink(path)

    def test_double_encoded(self):
        inner = json.dumps({"version": 5, "state": {"documents": {"abc": {}}}})
        with tempfile.NamedTemporaryFile(mode="w", suffix=".json", delete=False) as f:
            json.dump({"cache": inner}, f)
            path = f.name
        try:
            state = load_cache(path)
            self.assertIn("documents", state)
            self.assertIn("abc", state["documents"])
        finally:
            os.unlink(path)

    def test_missing_state_raises(self):
        with tempfile.NamedTemporaryFile(mode="w", suffix=".json", delete=False) as f:
            json.dump({"cache": {"version": 5}}, f)
            path = f.name
        try:
            with self.assertRaises(ValueError):
                load_cache(path)
        finally:
            os.unlink(path)


class TestParseDocument(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        with open(os.path.join(FIXTURES_DIR, "sample_document.json")) as f:
            cls.doc = json.load(f)

    def test_basic_fields(self):
        meeting = _parse_document("test-id", self.doc, {}, {})
        self.assertEqual(meeting.id, "test-id")
        self.assertEqual(meeting.title, "Weekly Team Standup")
        self.assertIsNotNone(meeting.created_at)

    def test_participants(self):
        meeting = _parse_document("test-id", self.doc, {}, {})
        self.assertIsNotNone(meeting.creator)
        self.assertEqual(meeting.creator.name, "Alice Smith")
        self.assertEqual(meeting.creator.email, "alice@example.com")
        self.assertEqual(len(meeting.attendees), 3)
        names = [a.name for a in meeting.attendees]
        self.assertIn("Bob Jones", names)

    def test_calendar_event(self):
        meeting = _parse_document("test-id", self.doc, {}, {})
        self.assertIsNotNone(meeting.calendar)
        self.assertIsNotNone(meeting.calendar.start)
        self.assertIsNotNone(meeting.calendar.end)
        self.assertEqual(meeting.calendar.timezone, "America/Chicago")

    def test_date_prefers_calendar(self):
        meeting = _parse_document("test-id", self.doc, {}, {})
        # date should be from calendar start, not created_at
        self.assertEqual(meeting.date, meeting.calendar.start)

    def test_notes_markdown(self):
        meeting = _parse_document("test-id", self.doc, {}, {})
        self.assertTrue(len(meeting.notes_markdown) > 0)
        self.assertIn("Agenda", meeting.notes_markdown)

    def test_prosemirror_notes(self):
        meeting = _parse_document("test-id", self.doc, {}, {})
        self.assertIsNotNone(meeting.notes_prosemirror)
        self.assertEqual(meeting.notes_prosemirror["type"], "doc")

    def test_folder_from_map(self):
        folder_map = {"test-id": "My Folder"}
        meeting = _parse_document("test-id", self.doc, folder_map, {})
        self.assertEqual(meeting.folder, "My Folder")

    def test_folder_empty_when_unmapped(self):
        meeting = _parse_document("test-id", self.doc, {}, {})
        self.assertEqual(meeting.folder, "")

    def test_participant_names_property(self):
        meeting = _parse_document("test-id", self.doc, {}, {})
        names = meeting.participant_names
        self.assertIn("Alice Smith", names)
        self.assertIn("Bob Jones", names)


class TestBuildFolderMap(unittest.TestCase):
    def test_cross_reference(self):
        state = {
            "documentLists": {
                "list-1": ["doc-a", "doc-b"],
                "list-2": ["doc-c"],
            },
            "documentListsMetadata": {
                "list-1": {"title": "Folder One"},
                "list-2": {"title": "Folder Two"},
            },
        }
        result = _build_folder_map(state)
        self.assertEqual(result["doc-a"], "Folder One")
        self.assertEqual(result["doc-b"], "Folder One")
        self.assertEqual(result["doc-c"], "Folder Two")

    def test_empty_state(self):
        self.assertEqual(_build_folder_map({}), {})

    def test_missing_metadata(self):
        state = {
            "documentLists": {"list-1": ["doc-a"]},
            "documentListsMetadata": {},
        }
        result = _build_folder_map(state)
        self.assertEqual(result, {})


class TestSearchAndGet(unittest.TestCase):
    def setUp(self):
        from granola_sync.models import Meeting
        self.meetings = [
            Meeting(id="aaa-111", title="Weekly Standup"),
            Meeting(id="bbb-222", title="Sprint Planning"),
            Meeting(id="ccc-333", title="Architecture Review"),
        ]

    def test_search_case_insensitive(self):
        results = search_meetings(self.meetings, "standup")
        self.assertEqual(len(results), 1)
        self.assertEqual(results[0].id, "aaa-111")

    def test_search_partial(self):
        results = search_meetings(self.meetings, "sprint")
        self.assertEqual(len(results), 1)

    def test_search_no_results(self):
        results = search_meetings(self.meetings, "nonexistent")
        self.assertEqual(len(results), 0)

    def test_get_by_full_id(self):
        result = get_meeting_by_id(self.meetings, "bbb-222")
        self.assertIsNotNone(result)
        self.assertEqual(result.title, "Sprint Planning")

    def test_get_by_prefix(self):
        result = get_meeting_by_id(self.meetings, "aaa")
        self.assertIsNotNone(result)
        self.assertEqual(result.id, "aaa-111")

    def test_get_not_found(self):
        result = get_meeting_by_id(self.meetings, "zzz")
        self.assertIsNone(result)


class TestExtractCacheEnhancedNotes(unittest.TestCase):
    def test_overview_preferred(self):
        doc = {
            "overview": "Overview text.",
            "summary": "Summary text.",
        }
        self.assertEqual(_extract_cache_enhanced_notes(doc), "Overview text.")

    def test_summary_fallback(self):
        doc = {"overview": "", "summary": "Summary only."}
        self.assertEqual(_extract_cache_enhanced_notes(doc), "Summary only.")

    def test_chapters_formatted(self):
        doc = {
            "chapters": [
                {"title": "Intro", "summary": "We started the meeting."},
                {"title": "Decisions", "summary": "We agreed on X."},
            ]
        }
        result = _extract_cache_enhanced_notes(doc)
        self.assertIn("### Intro", result)
        self.assertIn("We started the meeting.", result)
        self.assertIn("### Decisions", result)

    def test_all_null_returns_empty(self):
        doc = {"overview": None, "summary": None, "chapters": None}
        self.assertEqual(_extract_cache_enhanced_notes(doc), "")

    def test_empty_dict_returns_empty(self):
        self.assertEqual(_extract_cache_enhanced_notes({}), "")


class TestParseDatetime(unittest.TestCase):
    def test_iso_with_z(self):
        dt = parse_datetime("2026-03-15T14:00:00.000Z")
        self.assertIsNotNone(dt)
        self.assertEqual(dt.year, 2026)
        self.assertEqual(dt.month, 3)
        self.assertEqual(dt.hour, 14)

    def test_iso_with_offset(self):
        dt = parse_datetime("2026-03-15T09:00:00-05:00")
        self.assertIsNotNone(dt)
        self.assertEqual(dt.hour, 9)

    def test_none_input(self):
        self.assertIsNone(parse_datetime(None))

    def test_empty_string(self):
        self.assertIsNone(parse_datetime(""))

    def test_invalid_format(self):
        self.assertIsNone(parse_datetime("not-a-date"))


if __name__ == "__main__":
    unittest.main()
