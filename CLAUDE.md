# Granola Sync — Claude Code Instructions

## Project Purpose
Integrate Granola meeting transcription data into the Obsidian knowledge base via Claude Code. Local cache is the primary data source for discovery and user-written notes. MCP provides AI summaries and transcripts not stored in cache.

## Publication Context

This repo is public on GitHub as a portfolio project — a personal tool shared without warranty or support. When Claude makes changes that land in committed files (source, docs, backlog, skills, templates), these rules apply:

**Generalize identifiers before writing:**
- People — use "the user" for whoever invokes the skill; use generic placeholders (Alice, Bob, Jane Doe) in examples; use `@example.com` for every email including the author's.
- Meetings — use generic examples (weekly standup, client intro call, team all-hands, demo, Maven course). If the author mentions a real meeting in conversation, abstract it before writing.
- Clients, employers, colleagues — never named in committed files. Describe the pattern, not the specific relationship.

**Paths:**
- Never commit absolute paths containing usernames. Use `~/` expansion or placeholders like `/path/to/...`.
- `config.json` is gitignored (contains real paths). `config.example.json` is committed with placeholders.

**Tone:**
- Builder's notebook, not marketing copy. Honest about what works and what doesn't.
- No disclaimers beyond "no support / no warranty". Commits describe what and why.

**Backlog additions:**
- Strip specific names and client detail before writing. "Fix the bug where Jane's meeting fails" becomes "fix crash when participant names contain special characters".
- Verbal context from the author stays in conversation/memory, not in committed files.

**License:** MIT. Attribution to the inspired-by repo (`sanisideup/claude-code-granola-sync`) in the README.

## Project Structure
```
granola-sync/
├── CLAUDE.md                              # This file
├── README.md                              # Project overview + usage
├── backlog.md                             # Kanban-style project backlog (Obsidian board plugin)
├── config.json                            # Folder mapping: Granola folders -> Obsidian paths
├── .gitignore
├── docs/
│   └── mcp-shapes.md                     # MCP response schemas (placeholder, validate on first use)
├── skills/
│   └── pull-granola-notes/
│       └── SKILL.md                      # /pull-granola-notes skill (symlinked to ~/.claude/skills/)
├── templates/
│   └── meeting-note-template.md           # Standard meeting note structure with {placeholder} markers
├── src/
│   └── granola_sync/
│       ├── __init__.py                    # Package version
│       ├── __main__.py                    # CLI entry point (list, search, get, render, push)
│       ├── cache.py                       # Cache discovery + parsing + folder mapping
│       ├── config.py                      # Config loading + output path resolution
│       ├── models.py                      # Dataclasses: Meeting, Participant, CalendarEvent, etc.
│       ├── prosemirror.py                 # ProseMirror JSON -> markdown converter
│       ├── renderer.py                    # Template loading + population
│       └── formatters.py                  # CLI output formatting (table, JSON)
└── tests/
    ├── __init__.py
    ├── test_cache.py
    ├── test_cli.py                        # CLI flag tests (file args, collision, dry-run, meeting-data)
    ├── test_config.py
    ├── test_prosemirror.py
    ├── test_renderer.py
    └── fixtures/
        ├── sample_document.json           # Sanitized real document
        └── sample_prosemirror.json        # ProseMirror content sample
```

## CLI Commands
Run from `src/` directory:
```
python3 -m granola_sync list [--json] [--limit N] [--meetings-only]
python3 -m granola_sync search <query> [--json]
python3 -m granola_sync get <meeting_id> [--json]
python3 -m granola_sync render <meeting_id> [--output PATH] [--enhanced-notes TEXT]
                        [--enhanced-notes-file PATH] [--transcript-file PATH]
                        [--meeting-data PATH]
python3 -m granola_sync push <meeting_id> [--enhanced-notes TEXT]
                        [--enhanced-notes-file PATH] [--transcript-file PATH]
                        [--meeting-data PATH] [--force] [--dry-run]
```

### Phase 3 CLI flags
- `--enhanced-notes-file PATH` — read AI summary from file (overrides `--enhanced-notes` string)
- `--transcript-file PATH` — read pre-formatted transcript from file
- `--meeting-data PATH` — JSON file with meeting metadata; skips cache lookup entirely (MCP-only mode)
- `--force` — bypass match search + merge; write a fresh template at the default path, replacing any existing file (push only)
- `--dry-run` — print resolved target path without writing (push only)
- **Match + merge behavior**: push searches the destination folder recursively for an existing note whose `meeting-title` frontmatter matches; that file becomes the target. When the target exists, content is merged — tool-owned H2 sections (`## Notes`, `## Enhanced Notes`, `## Transcript`) replaced, user-owned sections (`## Prep Notes`, custom content) preserved.
- **Multi-match**: when 2+ files match by title, push exits with code 3 and prints `{"multi_match": true, "candidates": [...], "default_path": "..."}` so the caller can disambiguate.

## Key Data Locations
- **Granola local cache:** `~/Library/Application Support/Granola/cache-v*.json` (glob — version may change)
- **Granola MCP endpoint:** `https://mcp.granola.ai/mcp` (configured as user-scope MCP server)
- **Obsidian vault:** user-configured in `config.json` (path varies per user)
- **Meeting notes destination:** Resolved via `config.json` folder mappings, fallback to `default_destination`

## Cache Structure (cache-v6.json)
- `cache.version`: 5 (despite filename saying v6)
- `cache.state.documents`: Dict of meeting documents (count varies per user)
- `cache.state.transcripts`: Dict of transcript arrays (mostly empty — MCP needed)
- `cache.state.documentLists` + `documentListsMetadata`: Folder assignments (cross-reference by list UUID)
- Notes field is `notes` (ProseMirror JSON), not `notes_prosemirror`
- `notes_markdown` available for a majority of docs (author's cache; varies per user); ProseMirror-to-markdown conversion covers the rest
- `overview`, `summary`, `chapters` are all null in cache — MCP needed for AI content
- Cache may become encrypted in future Granola updates. `find_cache_file()` detects this.

## MCP Tools (5 available on Business plan)
- `query_granola_meetings` — natural language query
- `list_meetings` — list with IDs, titles, dates, attendees
- `get_meetings` — search content including transcripts and notes
- `get_meeting_transcript` — raw transcript
- `list_meeting_folders` — folder listing

MCP orchestration is handled by the `/pull-granola-notes` skill, not in Python. The CLI accepts pre-fetched MCP data via `--enhanced-notes-file`, `--transcript-file`, and `--meeting-data` file flags. See `docs/mcp-shapes.md` for MCP response schemas.

## Conventions
- **Absolute paths only** — this tool is invoked from any working directory via global skills
- **Placeholder syntax:** `{placeholder_name}` in templates
- **Filename convention:** `YYYY-MM-DD - Description - Meeting Notes.md`
- **Backlog format:** Kanban-style markdown (Obsidian kanban plugin format)
- **No pip dependencies** — stdlib only (Python 3.10+)

## Running Tests
```bash
cd granola-sync && PYTHONPATH=src python3 -m unittest discover -s tests -v
```

## Skill: `/pull-granola-notes`

Global skill for pulling Granola meetings into Obsidian. Stored at `skills/pull-granola-notes/SKILL.md`, symlinked to `~/.claude/skills/pull-granola-notes`.

Usage: `/pull-granola-notes standup from today` or `/pull-granola-notes` (shows recent meetings to pick from).

Pipeline: find meeting (cache-first, MCP fallback) -> fetch enhanced notes + transcript via MCP -> write temp files -> push via CLI -> cleanup.

## Phase Roadmap
1. **Phase 1 (done):** Global scaffolding — project folder, templates, global skill, MCP config
2. **Phase 2 (done):** Cache parsing + data models + ProseMirror converter + CLI + tests
3. **Phase 3 (done):** `/pull-granola-notes` skill + MCP orchestration + CLI file flags + collision detection
4. **Backlog:** REST API fallback, provider abstraction, auto-sync SessionStart hook, MCP shape validation
