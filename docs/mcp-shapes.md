# Granola MCP Response Shapes

Status: **Validated 2026-04-18** against real meeting data.

**Key finding:** all tools except `list_meeting_folders` return XML-like pseudo-markup strings (not JSON). Skill must extract tag contents via regex.

---

## `list_meeting_folders`

Returns clean JSON:

```json
{
  "count": 5,
  "folders": [
    {
      "id": "uuid",
      "title": "Folder Name",
      "description": null,
      "note_count": 23
    }
  ]
}
```

---

## `list_meetings`

Returns XML-like pseudo-markup. No JSON envelope.

```
<meetings_data from="Apr 18, 2026" to="Apr 18, 2026" count="2">
<meeting id="c17ca955-..." title="Weekly Team Standup" date="Apr 18, 2026 9:00 AM">
    <known_participants>
    Alice Smith (note creator) <alice@example.com>, Bob Jones <bob@example.com>, ...
    </known_participants>
  </meeting>
<meeting id="b42190d1-..." title="Client Intro Call" date="Apr 18, 2026 4:00 PM">
    <known_participants>
    Alice Smith (note creator) <alice@example.com>
    </known_participants>
  </meeting>
</meetings_data>
```

**Attributes on `<meeting>`:** `id`, `title`, `date`.
**Date format:** `"MMM DD, YYYY H:MM AM/PM"` (local time, not ISO).
**`<known_participants>`:** one comma-separated line of `Name <email>` pairs. The note creator is tagged `"(note creator)"`. When multiple participants, list is complete.

---

## `query_granola_meetings`

Returns natural-language response text with numbered citation links `[[0]](url)` that reference meeting notes. Not useful for structured extraction — use `list_meetings` / `get_meetings` when you need data.

**Important:** the docstring requires preserving these citations in any response shown to the user. The skill does not pass MCP query output back to the user, so this rule does not apply inside the push pipeline.

---

## `get_meetings`

Same `<meetings_data>` / `<meeting>` envelope as `list_meetings`, but each `<meeting>` additionally includes:

```
<private_notes>
...user-written meeting notes (plain text, often no line breaks)...
</private_notes>
<summary>
...AI-generated markdown summary with headings (### Heading), bullet lists...
</summary>
```

**`<private_notes>`:** raw text, may lack newlines between bullets (appears to be all whitespace-collapsed). Useful as a Notes-section fallback when cache is unavailable, but cache's ProseMirror/markdown is better formatted when present.

**`<summary>`:** well-formed markdown (`### Section`, bullet lists, links). This is the field to use for Enhanced Notes.

**Participants richness:** verified — MCP returns full attendee list (150+ for a webinar), while the cache for the same meeting often only contains the note creator. This confirms the MCP-first participants rule.

---

## `get_meeting_transcript`

**Small response (under token limit):** returns transcript text directly as the tool result.

**Large response (over token limit):** saves to disk. Error message includes the file path. The saved file is a JSON envelope:

```json
{
  "id": "uuid",
  "title": "Meeting title",
  "transcript": " Them: Recording in progress. I see you. Me: Thanks. ..."
}
```

- **File format:** JSON (despite the error message saying "Format: Plain text" — verified 2026-04-18)
- **Inner `transcript` field:** a single run-on string. Speakers labeled inline as `Me:` (microphone) and `Them:` (system/remote). No line breaks between turns.

The CLI handles this envelope + normalization inside `_read_transcript_file` — the skill can pass the saved path directly via `--transcript-file` without unwrapping it first.

---

## Extraction Reference

The skill uses inline Python to pull tag contents. Pattern templates:

```python
# Summary (AI notes)
re.search(r"<summary>(.*?)</summary>", text, re.DOTALL)

# Participants — strip emails + "(note creator)" marker
re.search(r"<known_participants>(.*?)</known_participants>", text, re.DOTALL)
# then: [re.sub(r"\s*<[^>]+>", "", p).replace("(note creator)", "").strip()
#        for p in raw.split(",")]

# Private notes (fallback for Notes section when cache is empty)
re.search(r"<private_notes>(.*?)</private_notes>", text, re.DOTALL)
```

---

## Validation Checklist

- [x] `list_meetings` — confirmed XML pseudo-markup, per-meeting attributes, participant format
- [x] `query_granola_meetings` — not used in pipeline; documented citation requirement
- [x] `get_meetings` — identified `<summary>` for Enhanced Notes, `<private_notes>` as fallback
- [x] `get_meeting_transcript` — confirmed large-response JSON envelope + inline `Me:`/`Them:` markers
- [x] `list_meeting_folders` — confirmed JSON shape, folder names match cache
