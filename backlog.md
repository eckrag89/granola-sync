---

kanban-plugin: board

---

## Opportunities

- [ ] Direct Obsidian plugin integration
- [ ] Pre-meeting note creation for Granola — create structured doc before meeting starts so Granola populates into it
- [ ] Leverage Jupyter Notebooks for meeting analytics dashboard
- [ ] Multi-template support — personal/work/project templates, config-driven section list, derived sections (action items extraction, summary block, etc.)

## Backlog

- [ ] Publish-readiness: remove/anonymize all personal data (names, emails, file paths in test fixtures, docs, examples)
- [ ] Publish-readiness: README documentation polished and clear enough to ship publicly
- [ ] Publish-readiness: no hard-coded absolute paths — config and docs must work after a fresh clone on another machine (saw a few hard-coded paths that would break portability)
- [ ] REST API data source — `GET /v1/notes/{id}` as resilient fallback when cache encryption breaks the reader
- [ ] Provider abstraction — common interface for cache reader, MCP client, and REST API client
- [ ] Auto-sync on session start (SessionStart hook) — sync meetings since last session automatically
- [ ] Content review/formatting skill — format and style-check meeting notes to match preferences
- [ ] Logging module — structured logging for sync operations and debugging

## First Run Feedback (2026-04-18)


## In Progress


## Done

- [x] Phase 1: Global scaffolding — project folder, templates, global skill, MCP config
- [x] Phase 2: Cache parsing + MCP data retrieval — cache reader, ProseMirror converter, data models, CLI, config, renderer, formatters, tests
- [x] Phase 3: `/pull-granola-notes` skill + MCP orchestration — CLI file flags, collision detection, dry-run, MCP-only mode, skill creation + symlink
- [x] ProseMirror parser — recursive tree walker for all node types found in real data
- [x] Speaker labels — transcript formatting with microphone/system speaker grouping
- [x] Error handling — per-document error handling, encryption detection, graceful cache failures
- [x] JSON safety — double-encoded JSON handling, structure validation
- [x] YAML escaping — title escaping for colons, quotes, special chars
- [x] UTF-8 encoding — all file I/O uses utf-8 encoding
- [x] Optimized default paths / smart path suggestion — config.json folder mapping with auto-resolution
- [x] First-run feedback: custom destination folder and filename via `--output-folder` / `--output-title` + natural-language skill parsing (with MUST-ask-when-ambiguous)
- [x] First-run feedback: empty Notes renders `_(no notes taken)_` placeholder instead of broken-looking empty heading
- [x] First-run feedback: large-transcript MCP path — CLI unwraps `{id, title, transcript}` JSON envelope and normalizes inline `Me:`/`Them:` markers
- [x] First-run feedback: MCP-first participants rule via `--participants` flag; skill extracts full attendee list from `<known_participants>` and passes it through
- [x] First-run feedback: removed Goals/Context sections from default template
- [x] First-run feedback: cache path now extracts AI summary from `overview` / `summary` / `chapters` fields for Enhanced Notes
- [x] First-run feedback: speaker labels changed to `**You:**` / `**Other:**` across cache and MCP transcript paths
- [x] First-run feedback: post-push verification — skill reads file, reports actual per-section state (populated/empty with reason)
- [x] First-run feedback: MUST/STOP directives replace soft "warn the user" language in skill prompt
- [x] First-run feedback: multi-match lists always show dates; relative-query re-confirm only when target lands in duplicate-title cluster and resolution is non-deterministic
- [x] First-run feedback: pre-push stop only when all three content sections would be empty
- [x] First-run feedback: template stays a file; multi-template support deferred to Opportunities
- [x] MCP response shapes validated against real Meeting 4/5 data; documented in `docs/mcp-shapes.md` (XML-like pseudo-markup, large-response JSON envelope format)
- [x] First-run feedback: large-roster prompt (>20 participants) — skill stops and offers all / just creator / custom-list options before building the push command (SKILL.md step 5a)
- [x] First-run feedback: permission allowlist — user-scoped `~/.claude/settings.json` pre-approves 5 read-only granola MCP tools + 3 read-only CLI subcommands (list/search/get); push, temp writes, and heredoc verification still prompt; documented in README "Permission allowlist" section


%% kanban:settings
```
{"kanban-plugin":"board","list-collapse":[false,false,false,false]}
```
%%
