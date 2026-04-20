"""Configuration loading and output path resolution."""

from __future__ import annotations

import json
import os
import re
from dataclasses import dataclass, field
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from .models import Meeting

# Default config path — project root
_DEFAULT_CONFIG_PATH = os.path.join(
    os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))),
    "config.json",
)


@dataclass
class Config:
    folder_mappings: dict[str, str] = field(default_factory=dict)
    default_destination: str = ""

    @classmethod
    def load(cls, path: str = _DEFAULT_CONFIG_PATH) -> Config:
        """Load config from JSON file. Returns defaults if file missing."""
        if not os.path.isfile(path):
            return cls()
        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f)
        return cls(
            folder_mappings=data.get("folder_mappings", {}),
            default_destination=data.get("default_destination", ""),
        )


def resolve_output_path(
    meeting: Meeting,
    config: Config,
    folder_override: str = "",
    title_override: str = "",
) -> str:
    """Resolve the Obsidian destination path for a meeting.

    Directory lookup order:
    1. folder_override (absolute path from skill, e.g. natural-language resolution)
    2. meeting.folder in config.folder_mappings
    3. config.default_destination
    4. Current working directory (last resort)

    Filename: "{date} - {title} - Meeting Notes.md" by default, or
    "{title_override}.md" when title_override is set (skill passes the base name it
    wants, extension added here).
    """
    if folder_override:
        directory = os.path.expanduser(folder_override)
    elif meeting.folder and meeting.folder in config.folder_mappings:
        directory = config.folder_mappings[meeting.folder]
    elif config.default_destination:
        directory = config.default_destination
    else:
        directory = os.getcwd()

    if title_override:
        safe_base = _safe_filename(title_override)
        filename = f"{safe_base}.md"
    else:
        date_str = meeting.date_str or "undated"
        safe_title = _safe_filename(meeting.title or "Untitled")
        filename = f"{date_str} - {safe_title} - Meeting Notes.md"

    return os.path.join(directory, filename)


def _safe_filename(title: str) -> str:
    """Sanitize a meeting title for use as a filename."""
    # Remove characters unsafe for filenames
    safe = re.sub(r'[<>:"/\\|?*]', "", title)
    # Collapse whitespace
    safe = re.sub(r"\s+", " ", safe).strip()
    # Truncate to reasonable length
    return safe[:80]
