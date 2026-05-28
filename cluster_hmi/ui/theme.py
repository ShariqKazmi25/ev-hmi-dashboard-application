from __future__ import annotations

import tkinter as tk
import tkinter.font as tkfont


BG = "#000000"
PANEL = "#07090C"
PANEL_ALT = "#0B0E12"
PANEL_SHADOW = "#020304"
OUTLINE = "#F2F4F8"
OUTLINE_SOFT = "#323841"
TEXT = "#FFFFFF"
TEXT_SOFT = "#A7AFBB"
TEXT_MUTED = "#6D7582"
ACCENT = "#D8E5F7"
WARNING = "#FFB347"
WARNING_SOFT = "#2B1D0A"
OK = "#3A404B"

_FONT_CACHE: dict[tuple[int, str], str] = {}
_DISPLAY_CANDIDATES = [
    "Bahnschrift SemiCondensed",
    "Bahnschrift",
    "Aptos Display",
    "Segoe UI",
    "Helvetica",
    "Arial",
]
_TEXT_CANDIDATES = [
    "Aptos",
    "Segoe UI",
    "Helvetica",
    "Arial",
]


def font_family(widget: tk.Misc, role: str = "text") -> str:
    root = widget.winfo_toplevel()
    cache_key = (id(root), role)
    if cache_key in _FONT_CACHE:
        return _FONT_CACHE[cache_key]

    try:
        available = set(tkfont.families(root))
    except tk.TclError:
        available = set()

    candidates = _DISPLAY_CANDIDATES if role == "display" else _TEXT_CANDIDATES
    for name in candidates:
        if name in available:
            _FONT_CACHE[cache_key] = name
            return name

    fallback = "TkDefaultFont"
    _FONT_CACHE[cache_key] = fallback
    return fallback
