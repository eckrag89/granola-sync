"""CLI entry point for granola-sync.

Usage:
    python3 -m granola_sync list [--json] [--limit N] [--meetings-only]
    python3 -m granola_sync search <query> [--json]
    python3 -m granola_sync get <meeting_id> [--json]
    python3 -m granola_sync render <meeting_id> [--output PATH] [--enhanced-notes TEXT]
                            [--enhanced-notes-file PATH] [--transcript-file PATH]
                            [--meeting-data PATH]
    python3 -m granola_sync push <meeting_id> [--enhanced-notes TEXT]
                            [--enhanced-notes-file PATH] [--transcript-file PATH]
                            [--meeting-data PATH] [--force] [--dry-run]
"""

from __future__ import annotations

import argparse
import json
import os
import re
import sys

from .cache import get_meeting_by_id, load_meetings, search_meetings
from .config import Config, resolve_output_path
from .formatters import meetings_to_json, meetings_to_table
from .models import CalendarEvent, Meeting, Participant, parse_datetime
from .prosemirror import prosemirror_to_markdown
from .renderer import render_meeting_note


def _read_file_arg(path: str) -> str:
    """Read content from a file path argument. Returns empty string on error."""
    try:
        with open(path, "r", encoding="utf-8") as f:
            return f.read()
    except (OSError, IOError) as e:
        print(f"Warning: could not read {path}: {e}", file=sys.stderr)
        return ""


def _read_transcript_file(path: str) -> str:
    """Read a transcript file, unwrapping MCP's large-response JSON envelope and
    normalizing Granola's inline speaker markers.

    When `mcp__granola__get_meeting_transcript` exceeds its token limit, the server
    saves the response to disk wrapped as `{"id": ..., "title": ..., "transcript":
    <str or list>}`. The inner string uses Granola's `Me:` / `Them:` markers with
    no line breaks between turns; this function splits on those markers and emits
    the `**You:** / **Other:**` convention used elsewhere.
    """
    content = _read_file_arg(path)
    if not content:
        return ""
    stripped = content.lstrip()
    if stripped.startswith("{"):
        try:
            parsed = json.loads(stripped)
        except (json.JSONDecodeError, ValueError):
            parsed = None
        if isinstance(parsed, dict) and "transcript" in parsed:
            inner = parsed.get("transcript")
            if isinstance(inner, str):
                return _normalize_transcript_text(inner)
            if isinstance(inner, list):
                return _format_mcp_transcript_entries(inner)
            return content
    return _normalize_transcript_text(content)


def _normalize_transcript_text(text: str) -> str:
    """Split Granola's inline `Me:`/`Them:` run-on transcript into speaker-labeled
    lines. Leaves text untouched when no such markers are present (e.g. cache
    transcripts already formatted, or text with existing `**You:**` / `**Other:**`
    prefixes from earlier processing)."""
    text = text.strip()
    if not text:
        return ""
    if not re.search(r"\b(Me|Them):", text):
        return text
    # Split on whitespace-preceded "Me:" / "Them:" markers, keeping the marker
    parts = re.split(r"(?=(?:^|\s)(?:Me|Them):)", text)
    lines: list[str] = []
    for part in parts:
        part = part.strip()
        if not part:
            continue
        m = re.match(r"^(Me|Them):\s*(.*)", part, re.DOTALL)
        if m:
            speaker = "You" if m.group(1) == "Me" else "Other"
            body = m.group(2).strip()
            if body:
                lines.append(f"**{speaker}:** {body}")
        else:
            lines.append(part)
    return "\n\n".join(lines)


def _format_mcp_transcript_entries(entries: list) -> str:
    """Format a structured MCP transcript list into speaker-labeled markdown.

    Entries are expected as dicts; pulls `speaker`/`source` and `text`/`content`
    with best-effort defaults so unknown shapes still render readable output.
    """
    lines: list[str] = []
    for entry in entries:
        if not isinstance(entry, dict):
            continue
        speaker = (
            entry.get("speaker")
            or entry.get("source")
            or entry.get("role")
            or "Speaker"
        )
        text = entry.get("text") or entry.get("content") or ""
        speaker = str(speaker).strip() or "Speaker"
        text = str(text).strip()
        if not text:
            continue
        # Normalize cache-style sources to the You/Other convention
        if speaker.lower() == "microphone":
            speaker = "You"
        elif speaker.lower() == "system":
            speaker = "Other"
        lines.append(f"**{speaker}:** {text}")
    return "\n\n".join(lines)


def _load_meeting_from_file(path: str) -> Meeting | None:
    """Construct a Meeting from a JSON metadata file (MCP-only mode).

    Expected JSON shape matches `get --json` output:
    {id, title, date, participants, folder, channel}
    """
    try:
        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f)
    except (OSError, json.JSONDecodeError) as e:
        print(f"Error reading meeting data file: {e}", file=sys.stderr)
        return None

    participants = data.get("participants", [])
    attendees = []
    creator = None
    if participants:
        creator = Participant(name=participants[0])
        attendees = [Participant(name=p) for p in participants[1:]]

    calendar = None
    date_str = data.get("date", "")
    if date_str:
        dt = parse_datetime(date_str + "T00:00:00Z") if "T" not in date_str else parse_datetime(date_str)
        if dt:
            calendar = CalendarEvent(start=dt)

    return Meeting(
        id=data.get("id", ""),
        title=data.get("title", ""),
        folder=data.get("folder", ""),
        creator=creator,
        attendees=attendees,
        calendar=calendar,
    )


def _resolve_render_args(args) -> tuple[str, str]:
    """Resolve enhanced notes and transcript from file or string flags.

    File flags take precedence over string flags.
    Returns (enhanced_notes, transcript_override).
    """
    enhanced_notes = args.enhanced_notes
    if hasattr(args, "enhanced_notes_file") and args.enhanced_notes_file:
        file_content = _read_file_arg(args.enhanced_notes_file)
        if file_content:
            enhanced_notes = file_content

    transcript_override = ""
    if hasattr(args, "transcript_file") and args.transcript_file:
        transcript_override = _read_transcript_file(args.transcript_file)

    return enhanced_notes, transcript_override


def _add_render_flags(parser: argparse.ArgumentParser) -> None:
    """Add shared render flags to a subparser (render + push)."""
    parser.add_argument("--enhanced-notes", default="", help="AI summary text")
    parser.add_argument("--enhanced-notes-file", help="Read AI summary from file (overrides --enhanced-notes)")
    parser.add_argument("--transcript-file", help="Read transcript from file")
    parser.add_argument("--meeting-data", help="JSON file with meeting metadata (MCP-only mode, skips cache)")
    parser.add_argument(
        "--participants",
        help=(
            "Override participant list. Accepts a JSON array of names or a "
            "comma-separated string. Used for MCP-first participant rule when "
            "cache has incomplete attendees."
        ),
    )


def _parse_participants_flag(value: str | None) -> list[str] | None:
    """Parse --participants argument. JSON array first, fallback to comma-separated."""
    if not value:
        return None
    try:
        parsed = json.loads(value)
        if isinstance(parsed, list):
            return [str(x).strip() for x in parsed if str(x).strip()]
    except (json.JSONDecodeError, ValueError):
        pass
    return [p.strip() for p in value.split(",") if p.strip()]


def _apply_participants_override(meeting: Meeting, names: list[str]) -> None:
    """Replace meeting.creator + meeting.attendees with a flat override list.

    First entry becomes creator, remainder become attendees. Emails are lost; the
    override path is driven by MCP responses which provide names only.
    """
    if not names:
        return
    meeting.creator = Participant(name=names[0])
    meeting.attendees = [Participant(name=n) for n in names[1:]]


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="granola_sync",
        description="Granola meeting data sync to Obsidian",
    )
    sub = parser.add_subparsers(dest="command")

    # list
    p_list = sub.add_parser("list", help="List meetings from cache")
    p_list.add_argument("--json", action="store_true", help="Output as JSON")
    p_list.add_argument("--limit", type=int, default=20, help="Max meetings to show")
    p_list.add_argument(
        "--meetings-only",
        action="store_true",
        help="Exclude non-meeting documents",
    )

    # search
    p_search = sub.add_parser("search", help="Search meetings by title")
    p_search.add_argument("query", help="Search query")
    p_search.add_argument("--json", action="store_true", help="Output as JSON")

    # get
    p_get = sub.add_parser("get", help="Get a specific meeting by ID")
    p_get.add_argument("meeting_id", help="Meeting UUID (or prefix)")
    p_get.add_argument("--json", action="store_true", help="Output as JSON")

    # render
    p_render = sub.add_parser("render", help="Render meeting note to stdout or file")
    p_render.add_argument("meeting_id", help="Meeting UUID (or prefix)")
    p_render.add_argument("--output", "-o", help="Write to file instead of stdout")
    _add_render_flags(p_render)

    # push
    p_push = sub.add_parser("push", help="Push meeting note to Obsidian via config")
    p_push.add_argument("meeting_id", help="Meeting UUID (or prefix)")
    _add_render_flags(p_push)
    p_push.add_argument(
        "--output-folder",
        default="",
        help="Override destination folder (absolute path). Bypasses config folder mappings.",
    )
    p_push.add_argument(
        "--output-title",
        default="",
        help='Override filename base. Final file is "{value}.md". Bypasses the default "{date} - {title} - Meeting Notes" pattern.',
    )
    p_push.add_argument("--force", action="store_true", help="Overwrite existing file without collision check")
    p_push.add_argument("--dry-run", action="store_true", help="Print output path without writing")

    args = parser.parse_args(argv)

    if not args.command:
        parser.print_help()
        return 1

    # MCP-only mode: --meeting-data bypasses cache entirely
    if args.command in ("render", "push") and args.meeting_data:
        return _cmd_with_meeting_data(args)

    # Load meetings from cache
    meetings = load_meetings()
    if not meetings:
        print("No meetings found. Is the Granola cache available?", file=sys.stderr)
        return 1

    if args.command == "list":
        return _cmd_list(meetings, args)
    elif args.command == "search":
        return _cmd_search(meetings, args)
    elif args.command == "get":
        return _cmd_get(meetings, args)
    elif args.command == "render":
        return _cmd_render(meetings, args)
    elif args.command == "push":
        return _cmd_push(meetings, args)

    return 0


def _cmd_list(meetings, args) -> int:
    if args.meetings_only:
        meetings = [m for m in meetings if m.meeting_type == "meeting"]

    if args.json:
        limited = meetings[: args.limit] if args.limit > 0 else meetings
        print(meetings_to_json(limited))
    else:
        print(meetings_to_table(meetings, limit=args.limit))
    return 0


def _cmd_search(meetings, args) -> int:
    results = search_meetings(meetings, args.query)
    if not results:
        print(f'No meetings matching "{args.query}"', file=sys.stderr)
        return 1
    if args.json:
        print(meetings_to_json(results))
    else:
        print(meetings_to_table(results))
    return 0


def _cmd_get(meetings, args) -> int:
    meeting = get_meeting_by_id(meetings, args.meeting_id)
    if not meeting:
        print(f"Meeting not found: {args.meeting_id}", file=sys.stderr)
        return 1

    if args.json:
        print(json.dumps(_meeting_detail(meeting), indent=2, ensure_ascii=False))
    else:
        _print_meeting_detail(meeting)
    return 0


def _cmd_render(meetings, args) -> int:
    meeting = get_meeting_by_id(meetings, args.meeting_id)
    if not meeting:
        print(f"Meeting not found: {args.meeting_id}", file=sys.stderr)
        return 1

    participants_override = _parse_participants_flag(getattr(args, "participants", None))
    if participants_override:
        _apply_participants_override(meeting, participants_override)

    enhanced_notes, transcript_override = _resolve_render_args(args)
    rendered = render_meeting_note(
        meeting,
        enhanced_notes=enhanced_notes,
        transcript_override=transcript_override,
    )

    if args.output:
        os.makedirs(os.path.dirname(os.path.abspath(args.output)), exist_ok=True)
        with open(args.output, "w", encoding="utf-8") as f:
            f.write(rendered)
        print(f"Written to: {args.output}", file=sys.stderr)
    else:
        print(rendered)
    return 0


def _cmd_push(meetings, args) -> int:
    meeting = get_meeting_by_id(meetings, args.meeting_id)
    if not meeting:
        print(f"Meeting not found: {args.meeting_id}", file=sys.stderr)
        return 1

    return _do_push(meeting, args)


def _cmd_with_meeting_data(args) -> int:
    """Handle render/push when --meeting-data is provided (MCP-only mode)."""
    meeting = _load_meeting_from_file(args.meeting_data)
    if not meeting:
        return 1

    participants_override = _parse_participants_flag(getattr(args, "participants", None))
    if participants_override:
        _apply_participants_override(meeting, participants_override)

    if args.command == "render":
        enhanced_notes, transcript_override = _resolve_render_args(args)
        rendered = render_meeting_note(
            meeting,
            enhanced_notes=enhanced_notes,
            transcript_override=transcript_override,
        )
        if args.output:
            os.makedirs(os.path.dirname(os.path.abspath(args.output)), exist_ok=True)
            with open(args.output, "w", encoding="utf-8") as f:
                f.write(rendered)
            print(f"Written to: {args.output}", file=sys.stderr)
        else:
            print(rendered)
        return 0

    elif args.command == "push":
        return _do_push(meeting, args)

    return 1


def _do_push(meeting: Meeting, args) -> int:
    """Shared push logic for cache-based and MCP-only modes."""
    config = Config.load()
    output_path = resolve_output_path(
        meeting,
        config,
        folder_override=getattr(args, "output_folder", "") or "",
        title_override=getattr(args, "output_title", "") or "",
    )

    # Dry-run: print path and exit
    if args.dry_run:
        print(output_path)
        return 0

    # Collision detection
    if not args.force and os.path.exists(output_path):
        collision = {
            "collision": True,
            "existing_path": output_path,
            "meeting_id": meeting.id,
            "meeting_title": meeting.title,
        }
        print(json.dumps(collision, ensure_ascii=False))
        return 2

    enhanced_notes, transcript_override = _resolve_render_args(args)
    rendered = render_meeting_note(
        meeting,
        enhanced_notes=enhanced_notes,
        transcript_override=transcript_override,
    )

    os.makedirs(os.path.dirname(output_path), exist_ok=True)
    with open(output_path, "w", encoding="utf-8") as f:
        f.write(rendered)

    print(f"Pushed to: {output_path}")
    return 0


def _meeting_detail(meeting) -> dict:
    """Build a detailed dict for JSON output."""
    notes = meeting.notes_markdown
    if not notes and meeting.notes_prosemirror:
        notes = prosemirror_to_markdown(meeting.notes_prosemirror)
    if not notes:
        notes = meeting.notes_plain

    return {
        "id": meeting.id,
        "title": meeting.title,
        "date": meeting.date_str,
        "type": meeting.meeting_type,
        "folder": meeting.folder,
        "participants": meeting.participant_names,
        "channel": meeting.channel,
        "has_notes": meeting.has_cached_notes,
        "has_transcript": meeting.has_cached_transcript,
        "notes_source": (
            "markdown"
            if meeting.notes_markdown
            else "prosemirror"
            if meeting.notes_prosemirror
            else "plain"
            if meeting.notes_plain
            else "none"
        ),
        "notes_preview": (notes[:200] + "\u2026") if len(notes) > 200 else notes,
        "transcript_entries": len(meeting.transcript),
        "duration_minutes": meeting.duration_minutes,
    }


def _print_meeting_detail(meeting) -> None:
    """Print human-readable meeting detail."""
    detail = _meeting_detail(meeting)
    print(f"Title:        {meeting.title}")
    print(f"Date:         {detail['date']}")
    print(f"Type:         {detail['type'] or '\u2014'}")
    print(f"Folder:       {detail['folder'] or '\u2014'}")
    print(f"Channel:      {detail['channel'] or '\u2014'}")
    print(f"Participants: {', '.join(detail['participants']) or '\u2014'}")
    print(f"Notes:        {detail['notes_source']} ({'yes' if detail['has_notes'] else 'no'})")
    print(f"Transcript:   {detail['transcript_entries']} entries")
    if detail["duration_minutes"]:
        print(f"Duration:     {detail['duration_minutes']} min")
    print(f"ID:           {meeting.id}")
    if detail["notes_preview"]:
        print(f"\n--- Notes Preview ---\n{detail['notes_preview']}")


if __name__ == "__main__":
    sys.exit(main())
