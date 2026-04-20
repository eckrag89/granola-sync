"""Convert ProseMirror document JSON to Markdown."""

from __future__ import annotations

import sys
from typing import Optional


def prosemirror_to_markdown(doc: Optional[dict]) -> str:
    """Convert a ProseMirror document to markdown.

    Args:
        doc: ProseMirror document dict with "type": "doc" and "content" array.

    Returns:
        Markdown string. Empty string if doc is None or has no content.
    """
    if not doc or not isinstance(doc, dict):
        return ""

    content = doc.get("content")
    if not content or not isinstance(content, list):
        return ""

    blocks = []
    for node in content:
        result = _convert_node(node, depth=0)
        if result is not None:
            blocks.append(result)

    return "\n\n".join(blocks).strip()


def _convert_node(node: dict, depth: int = 0) -> Optional[str]:
    """Convert a single ProseMirror node to markdown."""
    if not isinstance(node, dict):
        return None

    node_type = node.get("type", "")
    handler = _NODE_HANDLERS.get(node_type)

    if handler:
        return handler(node, depth)

    if node_type and node_type not in ("doc",):
        print(f"granola-sync: unknown ProseMirror node type: {node_type}", file=sys.stderr)

    # Fallback: try to convert children
    return _convert_children_as_blocks(node)


def _convert_text(node: dict, depth: int = 0) -> Optional[str]:
    """Convert a text node, applying marks."""
    text = node.get("text", "")
    if not text:
        return None

    marks = node.get("marks", [])
    for mark in marks:
        mark_type = mark.get("type", "")
        if mark_type == "bold":
            text = f"**{text}**"
        elif mark_type == "italic":
            text = f"*{text}*"
        elif mark_type == "link":
            href = mark.get("attrs", {}).get("href", "")
            if href:
                text = f"[{text}]({href})"

    return text


def _convert_paragraph(node: dict, depth: int = 0) -> Optional[str]:
    """Convert a paragraph node."""
    inline = _convert_inline_content(node)
    return inline if inline is not None else ""


def _convert_heading(node: dict, depth: int = 0) -> Optional[str]:
    """Convert a heading node."""
    level = node.get("attrs", {}).get("level", 1)
    level = max(1, min(6, level))
    inline = _convert_inline_content(node) or ""
    return f"{'#' * level} {inline}"


def _convert_bullet_list(node: dict, depth: int = 0) -> Optional[str]:
    """Convert a bulletList node."""
    items = node.get("content", [])
    lines = []
    for item in items:
        if isinstance(item, dict) and item.get("type") == "listItem":
            lines.append(_convert_list_item(item, prefix="- ", depth=depth))
    return "\n".join(lines) if lines else None


def _convert_ordered_list(node: dict, depth: int = 0) -> Optional[str]:
    """Convert an orderedList node."""
    items = node.get("content", [])
    start = node.get("attrs", {}).get("start", 1) or 1
    lines = []
    for i, item in enumerate(items):
        if isinstance(item, dict) and item.get("type") == "listItem":
            lines.append(_convert_list_item(item, prefix=f"{start + i}. ", depth=depth))
    return "\n".join(lines) if lines else None


def _convert_list_item(node: dict, prefix: str, depth: int = 0) -> str:
    """Convert a listItem node with proper indentation for nesting."""
    indent = "  " * depth
    content = node.get("content", [])

    parts = []
    first_block = True
    for child in content:
        if not isinstance(child, dict):
            continue
        child_type = child.get("type", "")

        if child_type in ("bulletList", "orderedList"):
            # Nested list — increase depth
            nested = _convert_node(child, depth=depth + 1)
            if nested:
                parts.append(nested)
        elif child_type == "paragraph":
            inline = _convert_inline_content(child) or ""
            if first_block:
                parts.insert(0, f"{indent}{prefix}{inline}")
                first_block = False
            else:
                parts.append(f"{indent}  {inline}")
        else:
            # Other block types inside list item
            converted = _convert_node(child, depth=depth)
            if converted:
                parts.append(f"{indent}  {converted}")

    if first_block:
        # No paragraph found — empty list item
        parts.insert(0, f"{indent}{prefix}")

    return "\n".join(parts)


def _convert_inline_content(node: dict) -> Optional[str]:
    """Convert inline content (text nodes with marks) of a block node."""
    content = node.get("content")
    if not content or not isinstance(content, list):
        return None

    parts = []
    for child in content:
        if not isinstance(child, dict):
            continue
        if child.get("type") == "text":
            converted = _convert_text(child)
            if converted:
                parts.append(converted)

    return "".join(parts) if parts else None


def _convert_children_as_blocks(node: dict) -> Optional[str]:
    """Fallback: convert children as block-level nodes."""
    content = node.get("content")
    if not content or not isinstance(content, list):
        return None

    blocks = []
    for child in content:
        result = _convert_node(child)
        if result is not None:
            blocks.append(result)

    return "\n\n".join(blocks) if blocks else None


_NODE_HANDLERS = {
    "text": _convert_text,
    "paragraph": _convert_paragraph,
    "heading": _convert_heading,
    "bulletList": _convert_bullet_list,
    "orderedList": _convert_ordered_list,
}
