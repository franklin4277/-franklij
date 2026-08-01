"""Terminal display utilities — was mini_agent/utils/terminal_utils.py.

Handles ANSI codes, emoji, East Asian wide characters.
"""
from __future__ import annotations

import re
import unicodedata

# Compile once for performance
_ANSI_ESCAPE_RE = re.compile(r"\x1b\[[0-9;]*m")

# Common emoji range
_EMOJI_START = 0x1F300
_EMOJI_END = 0x1FAFF


def calculate_display_width(text: str) -> int:
    """Visible terminal columns of text. Handles ANSI, emoji, CJK wide chars, combining."""
    clean = _ANSI_ESCAPE_RE.sub("", text)
    width = 0
    for char in clean:
        if unicodedata.combining(char):
            continue
        cp = ord(char)
        if _EMOJI_START <= cp <= _EMOJI_END:
            width += 2
            continue
        eaw = unicodedata.east_asian_width(char)
        width += 2 if eaw in ("W", "F") else 1
    return width


def truncate_with_ellipsis(text: str, max_width: int, ellipsis: str = "…") -> str:
    """Truncate text to max_width, append ellipsis if needed."""
    if max_width <= 0:
        return ""
    if calculate_display_width(text) <= max_width:
        return text
    plain = _ANSI_ESCAPE_RE.sub("", text)
    ell_w = calculate_display_width(ellipsis)
    if max_width <= ell_w:
        return plain[:max_width]
    available = max_width - ell_w
    out, cur = "", 0
    for char in plain:
        w = calculate_display_width(char)
        if cur + w > available:
            break
        out += char
        cur += w
    return out + ellipsis


def pad_to_width(text: str, target_width: int, align: str = "left", fill_char: str = " ") -> str:
    """Pad text to target width. align: 'left' | 'right' | 'center'."""
    cur = calculate_display_width(text)
    if cur >= target_width:
        return text
    pad = target_width - cur
    if align == "left":
        return text + fill_char * pad
    if align == "right":
        return fill_char * pad + text
    if align == "center":
        left = pad // 2
        return fill_char * left + text + fill_char * (pad - left)
    raise ValueError(f"invalid align: {align}")


__all__ = ["calculate_display_width", "truncate_with_ellipsis", "pad_to_width"]