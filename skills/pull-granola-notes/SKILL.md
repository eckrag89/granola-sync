---
name: pull-granola-notes
description: Pull a Granola meeting into Obsidian with notes, AI summary, and transcript
argument-hint: standup from today | client intro call | last team all-hands, save to Projects/Foo as "Weekly Sync"
allowed-tools: Read, Write(/tmp/granola-sync-*), Bash, mcp__granola__list_meetings, mcp__granola__query_granola_meetings, mcp__granola__get_meetings, mcp__granola__get_meeting_transcript, mcp__granola__list_meeting_folders
---

# Pull Granola Meeting Notes

Pull ALL available meeting data (private notes, AI summary, transcript, metadata) into a single Obsidian note. Python CLI handles data assembly and path resolution; this skill handles meeting identification, MCP fetching, and post-push verification.

## Important Paths

All paths below are relative to `<REPO_ROOT>` — resolve it once at the start of each invocation (see Pipeline Step 0).

- **CLI:** `cd "<REPO_ROOT>/src" && python3 -m granola_sync <subcommand>`
- **Config:** `<REPO_ROOT>/config.json`
- **MCP shapes reference:** `<REPO_ROOT>/docs/mcp-shapes.md`

## Argument Parsing

`$ARGUMENTS` is free-form natural language. Extract three things:

1. **Meeting selector** — words describing which meeting (e.g. "standup from today", "team all-hands from last Tuesday")
2. **Destination folder** (optional) — phrases like "save to ...", "into ..." → resolve to an absolute path
3. **Title override** (optional) — phrases like "as \"...\"", "titled ..." → use as filename base

**MUST ask when ambiguous.** If the destination folder is vague ("somewhere appropriate"), or the selector resolves to multiple meetings and the wording doesn't make the intended one unambiguous, STOP and ask before acting. Do not guess.

When only a meeting selector is given (most common case), skip destination/title — the CLI's config resolves the default.

## Pipeline

### 0. Resolve repo root [MUST run first]

Claude runs this once at the start of every invocation and captures the output as `<REPO_ROOT>`. Every subsequent command below substitutes `<REPO_ROOT>` with the captured absolute path.

```bash
(cd -P ~/.claude/skills/pull-granola-notes && cd ../.. && pwd)
```

This follows the skill symlink back to the real repo location, so it works for any user who has symlinked the skill into `~/.claude/skills/`.

### A. Find the meeting

1. Run: `cd "<REPO_ROOT>/src" && python3 -m granola_sync search "<selector>" --json`
2. Parse the JSON array. Each result has `id`, `title`, `date`, `folder`.
3. Handle counts:
   - **0 results (exit 1):** Fall back to MCP `list_meetings` or `query_granola_meetings` with the selector. If MCP also returns nothing, STOP and tell the user no meetings matched.
   - **1 result:** Use it.
   - **2+ results:** Show a numbered list to the user **with the date on every entry** (format: `1. 2026-04-18 — Title`). Ask the user to pick by number. MUST include dates even when titles look distinct — duplicate titles make dateless lists fragile.

### A.1 Relative-query safety

When `<selector>` is a relative phrase ("the one before that", "same as last time", "around that time"), AND the resolved target meeting sits inside a cluster of two or more meetings sharing the same title, AND the resolution is not a deterministic walk from unambiguous context (e.g. "most recent X" followed by "the one before that" IS deterministic), then:

- **MUST re-confirm before pushing.** Show the resolved match as `Title — YYYY-MM-DD HH:MM` plus the count of title-siblings, and ask "push this one?" Wait for the user's answer.
- **MUST NOT silently pick one** when the resolution is genuinely ambiguous.

### B. Fetch MCP data

4. Call `mcp__granola__get_meetings` with `meeting_ids: ["<id>"]`. Response is XML-like pseudo-markup — see `docs/mcp-shapes.md`.
5. Extract the three relevant tag bodies with Python:

   ```bash
   python3 <<'PY'
   import re, json
   text = """<paste MCP response here>"""
   def extract(tag):
       m = re.search(rf"<{tag}>(.*?)</{tag}>", text, re.DOTALL)
       return m.group(1).strip() if m else ""
   summary = extract("summary")
   participants_raw = extract("known_participants")
   names, creator = [], None
   for p in participants_raw.split(","):
       clean = re.sub(r"\s*<[^>]+>", "", p).strip()
       is_creator = "(note creator)" in clean
       clean = clean.replace("(note creator)", "").strip()
       if clean:
           names.append(clean)
           if is_creator:
               creator = clean
   print(json.dumps({"summary": summary, "participants": names, "creator": creator}))
   PY
   ```

   Capture `summary` → Enhanced Notes. Capture `participants` → candidate list for `--participants`. Capture `creator` → used by the large-roster check below.

5a. **Large-roster check [MUST].** If `len(participants) > 20`, STOP before building the push command and ask the user to pick one of three options:

    1. **Include all** — pass the full list to `--participants`.
    2. **Just the note creator** (`<creator name>`) — pass `[creator]` to `--participants`. If `creator` is `None`, omit this option and say so.
    3. **Custom** — the user supplies the list, possibly abbreviated (e.g., `"lecturer and class"`, `"me + team + client"`). Use the user's reply verbatim as the participants array; MUST NOT attempt to expand abbreviations against the MCP list.

    Show the count and the first few names so the user has context: `"MCP returned 47 participants (e.g. Alice, Bob, Carol, ...). Include all / just creator (Alice) / custom?"`. If count ≤ 20, skip this step and use the full list.

6. Call `mcp__granola__get_meeting_transcript` with `meeting_id: "<id>"`. **Always call MCP for transcripts** — cache transcripts are empty or incomplete for most meetings; MCP is the authoritative source regardless of what `has_transcript` shows in the cache record. Do not skip this call based on cache state.
   - **Small response (fits inline):** save the returned text to `/tmp/granola-sync-transcript-<id8>.md`.
   - **Large response (exceeds token limit):** the tool result will reference a saved file path. Use that path directly as `--transcript-file` — **MUST NOT** reparse it; the CLI unwraps the JSON envelope and normalizes `Me:`/`Them:` markers.
   - **MCP error or timeout:** leave transcript empty and note the failure in the final report.

### C. Write temp files

7. Write the extracted `summary` to `/tmp/granola-sync-enhanced-<id8>.md`.
8. Write the JSON meeting-data file to `/tmp/granola-sync-meeting-<id8>.json` ONLY when the cache search in step A returned nothing (MCP-only mode). Shape:
   ```json
   {"id": "...", "title": "...", "date": "YYYY-MM-DD",
    "participants": ["name1", "name2"], "folder": ""}
   ```
   When cache had the meeting, SKIP this step — CLI uses the cache record and `--participants` overrides the attendee list.

### D. Pre-push checks

9. **MUST stop if all three content sections would be empty.** Check:
   - Enhanced Notes: `summary` from step 5 is empty-ish (< 20 chars meaningful)
   - Notes: cache search in step A showed the meeting, but private_notes in MCP are empty AND cache had no notes (run `python3 -m granola_sync get <id> --json` and check `has_notes`)
   - Transcript: MCP returned empty or failed

   If ALL three empty, STOP and tell the user exactly what's missing. Ask whether to push anyway (`--force` via explicit confirmation) or abort.

   If only one or two sections are empty, proceed — warn nothing here; the post-push verification (step F) reports the actual state.

10. Dry-run collision check:
    ```bash
    cd "<REPO_ROOT>/src" && python3 -m granola_sync push <id> --dry-run \
      [--meeting-data /tmp/granola-sync-meeting-<id8>.json] \
      [--output-folder "<absolute path>"] \
      [--output-title "<name>"]
    ```
    The command prints the resolved path. Check collision:
    ```bash
    test -e "<printed path>" && echo COLLISION || echo OK
    ```
    If COLLISION: ask the user — overwrite (`--force`), rename (append ` (2)` before `.md`), or skip.

### E. Push

11. Push with all inputs:
    ```bash
    cd "<REPO_ROOT>/src" && python3 -m granola_sync push <id> \
      --enhanced-notes-file /tmp/granola-sync-enhanced-<id8>.md \
      --transcript-file <transcript path from step 6> \
      --participants '<json array from step 5>' \
      [--meeting-data /tmp/granola-sync-meeting-<id8>.json] \
      [--output-folder "<absolute path>"] \
      [--output-title "<name>"] \
      [--force]
    ```
    Capture the `Pushed to: <path>` line.

### F. Post-push verification [MUST]

12. **MUST read the written file and verify each section has non-trivial content.** Do NOT report success based on CLI exit code alone — that only confirms the file was written, not that it was populated.

    ```bash
    python3 <<'PY'
    import re, json, sys
    path = "<pushed path>"
    with open(path) as f:
        body = f.read()
    sections = {}
    for name, heading in [("notes", "## Notes"),
                          ("enhanced_notes", "## Enhanced Notes"),
                          ("transcript", "## Transcript")]:
        m = re.search(rf"{re.escape(heading)}\n+(.*?)(?=\n## |\Z)", body, re.DOTALL)
        content = (m.group(1) if m else "").strip()
        if not content or content == "_(no notes taken)_":
            sections[name] = ("empty", len(content))
        else:
            sections[name] = ("populated", len(content))
    print(json.dumps(sections))
    PY
    ```

13. Report to the user using **actual** states, not assumed:

    ```
    Pushed to: <path>
    - Notes: populated (1234 chars) | empty — <reason>
    - Enhanced Notes: populated (5678 chars) | empty — <reason>
    - Transcript: populated (89012 chars) | empty — <reason>
    Data sources: cache | MCP | both
    Participants: <count> (source: MCP | cache)
    ```

    Where `<reason>` is specific (e.g. `empty — cache had no summary and MCP summary was blank`, `empty — MCP transcript call failed`).

14. **MUST NOT claim a section is populated without verification.** If the file read fails, say so explicitly.

### G. Cleanup

15. Delete every `/tmp/granola-sync-*` file created in this run, including on error paths.

## Failure Handling

- Both cache and MCP unavailable → STOP after step A.
- MCP `get_meetings` fails → enhanced notes empty; still push if other sections have content; report "empty — MCP get_meetings failed" in step 13.
- MCP `get_meeting_transcript` fails → transcript empty; same handling.
- Unexpected XML tag missing (e.g. `<summary>` not in response) → treat as empty for that field, note in report.
- CLI exit code 2 on push → collision path, handle per step 10.
- Any CLI exit code other than 0 or 2 → STOP, show stderr, do not report success.

## Notes

- All paths must be absolute.
- The CLI handles path resolution, filename generation, YAML escaping, and template rendering. Do not hand-build the output path.
- Cache record is authoritative for private notes (ProseMirror/markdown-rendered). MCP `<private_notes>` is a fallback only when cache is unavailable.
- `$ARGUMENTS` may be empty: show recent meetings with `list --limit 10 --json` and ask the user to pick.
- Multi-template support is a future feature; for now there is one template at `templates/meeting-note-template.md`.
