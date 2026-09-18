"""Non-Java raw slicing. Ported from ``context_creator.ipynb`` cell 16."""

from __future__ import annotations

from typing import List, Tuple

from .models import Hunk

Slice = Tuple[str, str, str, str]


def extract_fallback(path, src, hunks: List[Hunk], cfg) -> List[Slice]:
    if src is None:
        return []
    lines = src.split("\n")
    if len(lines) <= cfg.full_file_max_lines:
        return [("enclosing", path, path, src.rstrip("\n"))]
    out: List[Slice] = []
    for h in hunks:
        lo = h.new_start
        hi = h.new_start + max(h.new_lines, 1) - 1
        a = max(1, lo - cfg.surrounding_lines)
        b = min(len(lines), hi + cfg.surrounding_lines)
        out.append(("enclosing", path, f"{path}:{a}-{b}", "\n".join(lines[a - 1: b])))
    return out
