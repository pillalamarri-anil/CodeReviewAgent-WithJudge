"""Unified-diff parser. Ported verbatim from ``context_creator.ipynb`` cell 10.

The hunk new-file line-number math is test-verified against ``git diff`` -- inline
comments depend on it, so keep this logic byte-for-byte.
"""

from __future__ import annotations

import re
from typing import List, Tuple

from .models import FileChange, Hunk

_HUNK_RE = re.compile(r"^@@ -(\d+)(?:,(\d+))? \+(\d+)(?:,(\d+))? @@")


def parse_unified_diff(diff_text: str) -> List[FileChange]:
    raw, cur = [], None
    h = None
    need_old = need_new = got_old = got_new = 0

    def _new(file_, old):
        return {"file": file_, "old_path": old, "status": "modified", "hunks": []}

    for ln in diff_text.split("\n"):
        if ln.startswith("diff --git "):
            if cur is not None:
                raw.append(cur)
            m = re.match(r"diff --git a/(.+?) b/(.+)$", ln)
            a, b = (m.group(1), m.group(2)) if m else (None, None)
            cur, h = _new(b or a, a), None
        elif cur is None:
            continue
        elif ln.startswith("new file mode"):
            cur["status"], cur["old_path"] = "added", None
        elif ln.startswith("deleted file mode"):
            cur["status"] = "deleted"
        elif ln.startswith("rename from "):
            cur["old_path"], cur["status"] = ln[12:], "renamed"
        elif ln.startswith("rename to "):
            cur["file"], cur["status"] = ln[10:], "renamed"
        elif ln.startswith("--- "):
            h = None
        elif ln.startswith("+++ "):
            p = ln[4:]
            if p != "/dev/null":
                cur["file"] = p[2:] if p.startswith(("a/", "b/")) else p
            h = None
        elif ln.startswith("@@"):
            m = _HUNK_RE.match(ln)
            if not m:
                h = None
                continue
            os_, ol, ns, nl = m.groups()
            h = {"old_start": int(os_), "old_lines": int(ol) if ol else 1,
                 "new_start": int(ns), "new_lines": int(nl) if nl else 1, "lines": []}
            cur["hunks"].append(h)
            need_old, need_new = h["old_lines"], h["new_lines"]
            got_old = got_new = 0
        elif h is not None and (got_old < need_old or got_new < need_new):
            if ln.startswith("\\"):  # "\ No newline at end of file"
                continue
            if ln == "":
                ln = " "
            c0 = ln[0]
            if c0 == " ":
                h["lines"].append(ln); got_old += 1; got_new += 1
            elif c0 == "+":
                h["lines"].append(ln); got_new += 1
            elif c0 == "-":
                h["lines"].append(ln); got_old += 1
            else:
                h = None
        else:
            h = None
    if cur is not None:
        raw.append(cur)

    return [
        FileChange(
            file=d["file"], status=d["status"], old_path=d["old_path"],
            hunks=[Hunk(x["old_start"], x["old_lines"], x["new_start"], x["new_lines"], x["lines"])
                   for x in d["hunks"]],
        )
        for d in raw
    ]


def hunk_added_lines(h: Hunk) -> List[Tuple[int, str]]:
    """Each '+' line in the hunk with its exact line number in the *new* file."""
    out, n = [], h.new_start
    for l in h.lines:
        if l.startswith("+"):
            out.append((n, l[1:])); n += 1
        elif l.startswith("-"):
            pass
        else:
            n += 1
    return out


def hunk_changed_new_lines(h: Hunk) -> List[int]:
    nums = [n for n, _ in hunk_added_lines(h)]
    return nums or [h.new_start]


def hunk_new_line_span(h: Hunk) -> Tuple[int, int]:
    """Inclusive [lo, hi] range of new-file lines the hunk covers (context + added)."""
    lo = h.new_start
    hi = h.new_start + max(h.new_lines, 1) - 1
    return lo, hi
