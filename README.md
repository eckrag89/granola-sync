# granola-sync

Sync Granola meeting data into Obsidian via Claude Code. Reads meeting metadata, notes, and transcripts from Granola's local cache and renders them as Obsidian-compatible markdown files.

> **Status:** Personal project, shared for anyone who finds it useful. **macOS-only** — the cache and Obsidian paths are macOS-specific. No support or warranty is provided. Issues and PRs may be read but not necessarily acted on.
>
> **Heads-up:** Granola encrypted its local database in March 2026. The JSON cache file this tool reads is currently still usable, but may become encrypted in a future Granola update. If that happens, this tool's cache path will stop working — see `## Cache encryption risk` below.

## Prerequisites

- macOS (cache and Obsidian paths assume `~/Library/...`)
- Python 3.10+ (stdlib only — no pip dependencies)
- [Granola](https://granola.ai) — the MCP features used by the `/pull-granola-notes` skill require Granola's Business plan
- [Obsidian](https://obsidian.md) vault configured somewhere on disk
- [Claude Code](https://claude.com/claude-code) CLI

## Setup

```bash
# Clone
git clone <repo-url> granola-sync
cd granola-sync

# Create your local config from the example
cp config.example.json config.json
# Edit config.json with your Obsidian vault paths — see Configuration section below

# Symlink the skill for global access from any directory
ln -s "$(pwd)/skills/pull-granola-notes" ~/.claude/skills/pull-granola-notes
```

The symlink means edits to `skills/pull-granola-notes/SKILL.md` are immediately live globally. The skill auto-resolves its repo root via the symlink at runtime, so no path editing is required after cloning.

## Usage

Run from the `src/` directory:

```bash
cd granola-sync/src

# List recent meetings
python3 -m granola_sync list
python3 -m granola_sync list --limit 10 --meetings-only --json

# Search by title
python3 -m granola_sync search "standup"

# View meeting details
python3 -m granola_sync get <meeting_id>

# Render meeting note to stdout
python3 -m granola_sync render <meeting_id>

# Render with AI-enhanced notes (from MCP)
python3 -m granola_sync render <meeting_id> --enhanced-notes "Summary text..."

# Render with notes/transcript from files (used by /pull-granola-notes skill)
python3 -m granola_sync render <meeting_id> \
  --enhanced-notes-file /tmp/enhanced.md \
  --transcript-file /tmp/transcript.md

# Render without cache (MCP-only mode)
python3 -m granola_sync render <meeting_id> \
  --meeting-data /tmp/meeting.json \
  --enhanced-notes-file /tmp/enhanced.md

# Push to Obsidian (auto-resolves path via config.json)
python3 -m granola_sync push <meeting_id>

# Dry-run prints the resolved target path; --force writes a fresh template at
# the default path, bypassing the existing-file merge
python3 -m granola_sync push <meeting_id> --dry-run
python3 -m granola_sync push <meeting_id> --force

# Render to a specific file
python3 -m granola_sync render <meeting_id> --output /path/to/note.md
```

Meeting IDs support prefix matching (e.g., `2418a083` matches the full UUID).

## Architecture

**Data flow:** Granola cache (JSON) -> Python data models -> Markdown template -> Obsidian file

- **Cache reader** (`cache.py`): Discovers and parses `cache-v*.json` from `~/Library/Application Support/Granola/`. Handles double-encoded JSON and detects encrypted caches.
- **ProseMirror converter** (`prosemirror.py`): Converts Granola's rich text editor format to markdown. This is the primary notes extraction path — ~35% of meetings only have ProseMirror notes, not pre-rendered markdown.
- **Config** (`config.json`): Maps Granola folders to Obsidian vault paths. Meetings in unmapped folders go to a default location.
- **Renderer** (`renderer.py`): Populates the meeting note template with data. Notes fallback chain: `notes_markdown` > ProseMirror conversion > `notes_plain`.
- **Matcher** (`matcher.py`): On push, walks the destination folder looking for an existing note whose `meeting-title` frontmatter matches — supports prep-note workflows (write your prep before the meeting; the pull merges into it) and re-pulls without duplication. Multi-match cases return exit code 3 + a JSON candidate list so the caller disambiguates.
- **Merger** (`merger.py`): When the resolved target already exists, the push merges instead of overwriting. Tool-owned H2 sections (`## Notes`, `## Enhanced Notes`, `## Transcript`) are replaced; user-owned content (`## Prep Notes`, custom sections, preamble) is preserved. Frontmatter merges on the same principle: tool-owned fields (`date`, `meeting-title`, `attendees`) update from the new render when non-empty; everything else stays put. Use `--force` for a clean overwrite at the default path.

### Cache encryption risk

Granola encrypted its local database in March 2026. The JSON cache file used by this tool is currently still readable, but this may change. If the cache becomes unreadable, the tool will detect this and fail gracefully. The planned fallback is Granola's REST API (`GET /v1/notes`).

### MCP integration

The Python CLI has zero MCP dependencies. MCP orchestration (for AI summaries and transcripts) is handled by the `/pull-granola-notes` Claude Code skill. The CLI accepts pre-fetched MCP data via file flags (`--enhanced-notes-file`, `--transcript-file`, `--meeting-data`).

When the cache is unavailable, the `--meeting-data` flag allows fully MCP-driven operation -- the skill writes meeting metadata to a temp JSON file and the CLI uses it for rendering and path resolution without touching cache.

## Configuration

`config.json` maps Granola folder names to Obsidian vault paths:

```json
{
  "folder_mappings": {
    "Never Search Alone": "/path/to/obsidian/vault/Never Search Alone/Meeting Notes"
  },
  "default_destination": "/path/to/obsidian/vault/Clippings"
}
```

### Using the skill

From any Claude Code session:
```
/pull-granola-notes standup from today
/pull-granola-notes client intro call
/pull-granola-notes           # shows recent meetings to pick from
```

### Permission allowlist (optional)

The skill is invoked from any working directory, so permission entries must live in user-scoped settings (`~/.claude/settings.json`) to take effect. The entries below pre-approve the read-only calls the skill makes on every run.

```json
{
  "permissions": {
    "allow": [
      "mcp__granola__list_meetings",
      "mcp__granola__list_meeting_folders",
      "mcp__granola__get_meetings",
      "mcp__granola__get_meeting_transcript",
      "mcp__granola__query_granola_meetings",
      "Bash(cd <path-to-granola-sync>/src && python3 -m granola_sync list*)",
      "Bash(cd <path-to-granola-sync>/src && python3 -m granola_sync search *)",
      "Bash(cd <path-to-granola-sync>/src && python3 -m granola_sync get *)"
    ]
  }
}
```

Deliberately **not** allowlisted — still prompts every run:

- `push` subcommand — the final write into the Obsidian vault.
- Temp file writes (`/tmp/granola-sync-*`) — kept prompted to block content-planting attacks (a malicious skill could drop poisoned content that the real skill later picks up).
- Inline `python3 <<'PY'` heredocs used by post-push verification — arbitrary code execution; cannot be safely narrowed.

**Risk accepted by allowlisting the MCP tools user-scoped:** any skill running in any session can silently read your Granola meeting data (list, search, transcripts). Data stays inside Granola without a separate write-out channel, but it enters Claude's context freely. If that's unacceptable, remove the `mcp__granola__*` entries and tolerate per-session prompts instead.

## Dependencies

Python 3.10+ stdlib only. No pip dependencies.

## Tests

```bash
cd granola-sync
PYTHONPATH=src python3 -m unittest discover -s tests -v
```

## Security Considerations

Meeting data is sensitive — notes, transcripts, attendee names, potentially confidential content. This tool reads from your local Granola cache; it does not transmit meeting data externally. The `/pull-granola-notes` skill calls Granola's MCP server (authenticated via your Granola session) to fetch AI summaries and transcripts.

If you enable the optional user-scoped MCP allowlist shown above, **any Claude skill or agent in any session can silently read your meeting data without per-call prompts**. Accept that tradeoff knowingly, or leave the allowlist out and tolerate prompts.

**Note on skill permissions:** the `/pull-granola-notes` skill's frontmatter declares `Read`, `Write(/tmp/granola-sync-*)`, and `Bash` in its `allowed-tools`. Claude Code pre-authorizes those tools during the skill's execution, which is why temp-file writes, the `rm` cleanup step, and CLI Bash invocations run without per-call prompts. `Write` is narrowly scoped to the `/tmp/granola-sync-*` namespace; `Bash` is broad because the post-push verification step runs inline Python heredocs that can't be meaningfully pattern-matched. By invoking the skill, you implicitly trust it with those permissions within its scope — the user-scoped MCP allowlist above is a separate, additional layer.

## License

MIT. See [LICENSE](./LICENSE).

## Attribution

Inspired by [sanisideup/claude-code-granola-sync](https://github.com/sanisideup/claude-code-granola-sync) (MIT). Cache parsing patterns informed by that project — particularly folder mapping via `documentLists`/`documentListsMetadata` cross-reference and double-encoded JSON handling.
