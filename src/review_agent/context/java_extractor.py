"""Java context extraction with a stdlib brace-scanner (no tree-sitter, no build).

Ported verbatim from ``context_creator.ipynb`` cell 14. Per changed hunk it yields:
  * the enclosing method / class declaration
  * signatures (never bodies) of referenced project types named on changed lines
  * the matching ``<Name>Test`` / ``<Name>IT`` class if present
"""

from __future__ import annotations

import bisect
import os
import re
from typing import List, Tuple

Slice = Tuple[str, str, str, str]  # (reason, path, symbol, content)


def _blank_strings_and_comments(src: str) -> str:
    """src with comment / string / char / text-block contents replaced by spaces,
    preserving length and newlines, so brace scanning is not fooled by punctuation."""
    out, i, n, st = [], 0, len(src), None
    while i < n:
        c, nxt3, nxt2 = src[i], src[i:i + 3], src[i:i + 2]
        if st is None:
            if nxt2 == "//":
                st = "line"; out.append("  "); i += 2; continue
            if nxt2 == "/*":
                st = "block"; out.append("  "); i += 2; continue
            if nxt3 == '"""':
                st = "text"; out.append("   "); i += 3; continue
            if c == '"':
                st = "str"; out.append(" "); i += 1; continue
            if c == "'":
                st = "char"; out.append(" "); i += 1; continue
            out.append(c); i += 1; continue
        if st == "line":
            if c == "\n":
                st = None; out.append("\n")
            else:
                out.append(" ")
            i += 1; continue
        if st == "block":
            if nxt2 == "*/":
                st = None; out.append("  "); i += 2; continue
            out.append("\n" if c == "\n" else " "); i += 1; continue
        if st == "text":
            if nxt3 == '"""':
                st = None; out.append("   "); i += 3; continue
            out.append("\n" if c == "\n" else " "); i += 1; continue
        if st == "str":
            if c == "\\":
                out.append("  "); i += 2; continue
            if c == '"':
                st = None
            out.append("\n" if c == "\n" else " "); i += 1; continue
        if st == "char":
            if c == "\\":
                out.append("  "); i += 2; continue
            if c == "'":
                st = None
            out.append(" "); i += 1; continue
    return "".join(out)


def _classify_header(h: str):
    h = re.sub(r"\s+", " ", h).strip()
    m = re.search(r"\b(class|interface|enum|record)\s+(\w+)", h)
    if m:
        return m.group(1), m.group(2)
    m = re.search(r"(\w+)\s*\(", h)
    if m and ")" in h:
        return "method", m.group(1)
    return "block", ""


def parse_java_blocks(src: str):
    """{kind, name, header_start_line, brace_line, end_line, depth, header_text}
    for every ``{ ... }`` block (1-based line numbers)."""
    scan = _blank_strings_and_comments(src)
    starts, off = [], 0
    for l in src.split("\n"):
        starts.append(off); off += len(l) + 1
    line_of = lambda pos: bisect.bisect_right(starts, pos)

    blocks, stack, depth, anchor = [], [], 0, 0
    for i, c in enumerate(scan):
        if c not in ";{}":
            continue
        if c == "{":
            header = src[anchor:i]
            lead = len(header) - len(header.lstrip())
            kind, name = _classify_header(header)
            b = {"kind": kind, "name": name,
                 "header_start_line": line_of(anchor + lead),
                 "brace_line": line_of(i), "end_line": None,
                 "depth": depth, "header_text": re.sub(r"\s+", " ", header.strip())}
            blocks.append(b); stack.append(b); depth += 1
        elif c == "}":
            depth = max(0, depth - 1)
            if stack:
                stack.pop()["end_line"] = line_of(i)
        anchor = i + 1
    for b in blocks:
        if b["end_line"] is None:
            b["end_line"] = line_of(len(src))
    return blocks


def _annotations_above(lines, header_line):
    out, i = [], header_line - 2
    while i >= 0:
        s = lines[i].strip()
        if s == "":
            i -= 1; continue
        if s.startswith("@") or s.startswith(")") or s.startswith("("):
            out.append(lines[i]); i -= 1; continue
        break
    return list(reversed(out))


def _type_header(lines, tb):
    if not tb:
        return ""
    return "\n".join(_annotations_above(lines, tb["header_start_line"]) +
                     lines[tb["header_start_line"] - 1: tb["brace_line"]])


def _sig_end(lines, brace_line):
    for i in range(brace_line - 1, len(lines)):
        if "{" in lines[i]:
            return i + 1
    return brace_line


def java_signatures(src: str, max_methods: int = 60) -> str:
    """Type declaration + direct member signatures. No method bodies.

    Captures both class methods (``{ ... }`` blocks -> signature only) and abstract /
    interface method declarations and fields (lines ending in ``;`` directly inside the
    root type). Nested-type members are skipped.
    """
    blocks = parse_java_blocks(src)
    lines = src.split("\n")
    scan_lines = _blank_strings_and_comments(src).split("\n")
    types = [b for b in blocks if b["kind"] in ("class", "interface", "enum", "record")]
    if not types:
        return "\n".join(lines[:60])
    root = min(types, key=lambda b: b["header_start_line"])
    pkg = [l for l in lines[:root["header_start_line"] - 1] if l.strip().startswith("package ")]
    ann = _annotations_above(lines, root["header_start_line"])
    head = lines[root["header_start_line"] - 1: root["brace_line"]]

    meth_brace_lines = {
        b["brace_line"]
        for b in blocks
        if b["kind"] == "method" and b["depth"] == root["depth"] + 1
    }

    body: List[str] = []
    depth = 0  # relative brace depth inside the root type body
    pending: List[str] = []
    for i in range(root["brace_line"], root["end_line"] - 1):  # 0-based slice of body lines
        raw = lines[i]
        scan = scan_lines[i] if i < len(scan_lines) else raw
        opens, closes = scan.count("{"), scan.count("}")

        if depth == 0:
            stripped = raw.strip()
            if not stripped:
                pending = []
                continue
            if stripped.startswith("@") or (pending and not opens and not stripped.endswith(";")):
                pending.append(raw)
            elif (i + 1) in meth_brace_lines or opens:
                sig = " ".join(x.strip() for x in pending + [raw]).split("{", 1)[0].strip()
                if sig:
                    body.append("    " + sig + ";")
                pending = []
            elif stripped.endswith(";"):
                decl = " ".join(x.strip() for x in pending + [raw])
                body.append("    " + decl)
                pending = []
            else:
                pending.append(raw)
        depth += opens - closes
        if depth < 0:
            depth = 0
        if len(body) >= max_methods:
            break

    return "\n".join(pkg + [""] + ann + head + body + ["}"]).strip()


def _package_and_imports(src: str):
    pkg, imports = "", {}
    for l in src.split("\n"):
        s = l.strip()
        if s.startswith("package "):
            pkg = s[8:].rstrip(";").strip()
        elif s.startswith("import "):
            fq = s[7:].rstrip(";").strip().replace("static ", "")
            imports[fq.split(".")[-1]] = fq
        elif s.startswith(("public ", "final ", "abstract ", "class ", "interface ",
                           "enum ", "record ", "@")):
            break
    return pkg, imports


def java_index(repo) -> dict:
    idx = {}
    for p in repo.list_files():
        if p.endswith(".java"):
            idx.setdefault(os.path.basename(p)[:-5], p)
    return idx


_CAMEL = re.compile(r"\b([A-Z][A-Za-z0-9_]+)\b")


def extract_java(path, src, changed_lines, repo, jindex, cfg) -> Tuple[List[Slice], List[Slice], List[Slice]]:
    enclosing: List[Slice] = []
    referenced: List[Slice] = []
    tests: List[Slice] = []
    if not src:
        return enclosing, referenced, tests
    blocks = parse_java_blocks(src)
    lines = src.split("\n")
    types = [b for b in blocks if b["kind"] in ("class", "interface", "enum", "record")]
    methods = [b for b in blocks if b["kind"] == "method"]
    root = min(types, key=lambda b: b["header_start_line"]) if types else None
    span = lambda b: (b["header_start_line"], b["end_line"])

    seen = set()
    for lo in (sorted(set(changed_lines)) or ([span(root)[0]] if root else [1])):
        m_in = [b for b in methods if span(b)[0] <= lo <= span(b)[1]]
        enc_m = max(m_in, key=lambda b: b["depth"]) if m_in else None
        t_in = [b for b in types if span(b)[0] <= lo <= span(b)[1]]
        enc_t = max(t_in, key=lambda b: b["depth"]) if t_in else root

        if enc_m:
            s, e = span(enc_m)
            sym = (enc_t["name"] + "." if enc_t else "") + enc_m["name"]
            if ("enclosing", sym) in seen:
                continue
            seen.add(("enclosing", sym))
            hdr = _type_header(lines, enc_t)
            if e - s + 1 <= cfg.full_method_lines:
                body = "\n".join(lines[s - 1: e])
            else:
                a, b2 = max(s, lo - cfg.surrounding_lines), min(e, lo + cfg.surrounding_lines)
                body = ("\n".join(lines[s - 1: _sig_end(lines, enc_m["brace_line"])]) +
                        "\n        // ...\n" + "\n".join(lines[a - 1: b2]))
            enclosing.append(("enclosing", path, sym, (hdr + "\n\n" + body).strip()))
        elif enc_t:
            sym = enc_t["name"]
            if ("enclosing", sym) in seen:
                continue
            seen.add(("enclosing", sym))
            s, e = span(enc_t)
            if e - s + 1 <= cfg.full_method_lines:
                content = "\n".join(_annotations_above(lines, enc_t["header_start_line"]) +
                                    lines[enc_t["header_start_line"] - 1: e])
            else:
                a, b2 = max(1, lo - cfg.surrounding_lines), min(len(lines), lo + cfg.surrounding_lines)
                content = _type_header(lines, enc_t) + "\n    // ...\n" + "\n".join(lines[a - 1: b2])
            enclosing.append(("enclosing", path, sym, content.strip()))

    # referenced project types named on changed lines
    pkg, imports = _package_and_imports(src)
    changed_txt = "\n".join(lines[n - 1] for n in changed_lines if 1 <= n <= len(lines))
    self_name = root["name"] if root else None
    for name in sorted(set(_CAMEL.findall(changed_txt))):
        if name == self_name or name not in jindex:
            continue
        target = jindex[name]
        if name not in imports:
            if not (pkg and ("/" + pkg.replace(".", "/") + "/") in ("/" + target)):
                continue  # not imported, not same package
        tsrc = repo.read(target)
        if tsrc and ("referenced", name) not in seen:
            seen.add(("referenced", name))
            referenced.append(("referenced", target, name, java_signatures(tsrc)))

    # test class
    if root:
        for suf in ("Test", "IT"):
            tn = root["name"] + suf
            if tn in jindex:
                tsrc = repo.read(jindex[tn])
                if not tsrc:
                    continue
                whole = tsrc if len(tsrc.split("\n")) <= cfg.full_file_max_lines else java_signatures(tsrc)
                tests.append(("test", jindex[tn], tn, whole))
    return enclosing, referenced, tests
