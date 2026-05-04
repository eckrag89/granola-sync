---
name: prep-meeting-note
description: Create a prep-meeting note for an upcoming Outlook calendar event so granola-sync can later merge into it.
argument-hint: 1-1 with Alice tomorrow into 1-1's/Alice | weekly sync next Tuesday save to Projects/Foo as "Weekly Sync"
allowed-tools: Bash, Read, mcp__claude_ai_Microsoft_365__outlook_calendar_search
---

# Prep Meeting Note

Look up an upcoming meeting in Outlook, confirm with the user, then create an Obsidian prep note pre-populated with frontmatter from the calendar event. The resulting file is matched by `/pull-granola-notes` after the meeting (via `meeting-title` + `date` frontmatter) so the granola pull merges into it instead of creating a duplicate.

## Outlook only

This skill calls the Microsoft 365 MCP server (`outlook_calendar_search`). Other calendar sources are not supported. To swap in another provider, replace the search step with the equivalent MCP call and adapt the field extraction in step B.

## Section ownership (carries over from /pull-granola-notes)

The prep note is intentionally minimal: frontmatter plus a single `## Prep Notes` heading. When granola-sync later pulls the meeting, the merger appends `## Notes` / `## Enhanced Notes` / `## Transcript` in canonical order without disturbing what the user wrote under `## Prep Notes`.

## Important Paths

All paths below are relative to `<REPO_ROOT>` — resolve it once at the start of each invocation (see Pipeline Step 0).

- **CLI:** `cd "<REPO_ROOT>/src" && python3 -m granola_sync prep ...`
- **Config:** `<REPO_ROOT>/config.json`

## Argument Parsing

`$ARGUMENTS` is free-form natural language. Extract three things:

1. **Meeting selector** — words describing which calendar event (e.g. "1-1 with Alice tomorrow", "weekly sync next Tuesday")
2. **Destination folder** (optional) — phrases like "into ...", "save to ...", "in ..." → resolve to an absolute path
3. **Title override** (optional) — phrases like 'as "..."', "titled ..." → use as filename base

**MUST ask when ambiguous.** If the destination folder is vague, or the selector resolves to multiple candidate events and the wording doesn't make the intended one unambiguous, STOP and ask before acting. Do not guess. Only date + meeting-title proximity is auto-filled — the destination folder is structural and must be intentional.

## Pipeline

### 0. Resolve repo root [MUST run first]

```bash
(cd -P ~/.claude/skills/prep-meeting-note && cd ../.. && pwd)
```

Capture the output as `<REPO_ROOT>`. Substitute it everywhere below.

### A. Find the calendar event

1. Call `mcp__claude_ai_Microsoft_365__outlook_calendar_search` with:
   - `query`: a tight subject substring derived from the selector (e.g. "1-1 Alice", "weekly sync"). Avoid date words in the query — use the date filters instead.
   - `afterDateTime` / `beforeDateTime`: when the selector implies a date (today, tomorrow, next Tuesday, May 8th), pass those bounds. Otherwise default to the next 30 days.
   - `limit`: 10
2. Parse the response. Each event has `subject`, `start`, `end`, `attendees`, `id` (or a URI containing it).
3. Handle counts:
   - **0 results:** STOP. Tell the user no events matched the selector + date window. Ask them to refine (broader window, different terms).
   - **1 result:** Show `Subject — YYYY-MM-DD HH:MM — N attendees` and ask "Create prep note for this?" Wait for confirmation.
   - **2+ results:** Numbered list with date on every entry: `1. 2026-05-08 14:00 — Subject (3 attendees)`. Ask the user to pick.

### B. Extract the fields the CLI needs

For the chosen event, capture:

- **subject** → `--title`
- **start.dateTime** → `--date` as YYYY-MM-DD (drop the time component; the matcher only compares date prefixes)
- **attendees** → name list. Prefer display name over email. Drop the user's own email address (the search result's organizer / you are implicit). Pass as a JSON array to `--attendees`.
- **id** → `--outlook-event-id`. Stored in frontmatter for future use as a stronger match key (today's matcher only uses title + date).

If the search response only carries partial event data and `id` is not surfaced, derive it from the event URI in the result.

### C. Resolve the destination folder

If the user supplied a destination in `$ARGUMENTS`, use that as `--output-folder` (absolute path).

If not, ask. **Do NOT silently fall back to `default_destination`.** Prep notes are structural — the user almost always knows where they belong (e.g. `Meeting Notes/1-1's/Alice/`, `Projects/Foo/Meeting Notes/`). Suggest the `default_destination` from `<REPO_ROOT>/config.json` as the last-resort fallback when the user has no opinion.

### D. Call the CLI

```bash
cd "<REPO_ROOT>/src" && python3 -m granola_sync prep \
  --title "<subject>" \
  --date "<YYYY-MM-DD>" \
  --attendees '<JSON array>' \
  --outlook-event-id "<id>" \
  --output-folder "<absolute path>" \
  [--output-title "<filename base>"]
```

### E. Handle the response

Exit codes:

- **0**: Prints `Created prep note at: <path>`. Done — report the path to the user.
- **4**: Existing prep note found at the destination. Prints JSON:
  ```json
  {"existing": true, "candidates": ["..."], "default_path": "...", "meeting_title": "...", "date": "..."}
  ```
  STOP and ask the user. Three options to offer:
    1. **Open the existing note** — report the path, no write happens.
    2. **Overwrite** — re-run with `--force` (warns: any prep content already in the file is replaced).
    3. **Save alongside** — re-run with `--output-title "<custom name>"` so the resolved filename differs from the existing one.
- **Any other non-zero exit**: STOP, surface stderr, do not claim success.

### F. Report

Confirm to the user with the absolute path that was created (or the existing path if they chose to keep it). Mention the populated frontmatter fields briefly so they can spot anything wrong: `meeting-title`, `date`, attendee count, `outlook-event-id` set yes/no.

## Failure Handling

- M365 MCP unavailable / unauthenticated → STOP after step A; tell the user to check the M365 MCP connection.
- Selector matches 0 events → STOP; ask user to refine, do not guess.
- User refuses to specify a destination folder when `$ARGUMENTS` doesn't include one → STOP; do not write to `default_destination` without explicit confirmation.
- CLI exit code 4 → handled per step E.
- Any other non-zero CLI exit → STOP, show stderr.

## Notes

- All paths must be absolute when passed to the CLI.
- `--outlook-event-id` is stored in frontmatter today but not used as a match key — title + date is the v1 contract. Storing it now means future matcher upgrades can use it without re-touching prep notes.
- The created file body is just `## Prep Notes`. Granola-sync's merger appends `## Notes` / `## Enhanced Notes` / `## Transcript` in canonical order on the first pull.
- `$ARGUMENTS` may be empty: ask the user what meeting to prep for. Do not list the calendar.
