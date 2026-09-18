"""Knowledge-doc selection: always / glob (front-matter ``applies_to``) / schema.

Ported from ``context_creator.ipynb`` cell 18.
"""

from __future__ import annotations

import re
from typing import List

from .models import FileChange, KnowledgeDoc
from .tokens import count_tokens


def glob_to_regex(pat: str):
    out, i = "^", 0
    while i < len(pat):
        if pat[i:i + 3] == "**/":
            out += "(?:.*/)?"; i += 3; continue
        if pat[i:i + 2] == "**":
            out += ".*"; i += 2; continue
        c = pat[i]
        out += {"*": "[^/]*", "?": "[^/]", ".": r"\."}.get(c, re.escape(c))
        i += 1
    return re.compile(out + "$")


def glob_match(pat: str, path: str) -> bool:
    return glob_to_regex(pat).match(path) is not None


def parse_frontmatter(text: str):
    if not text.startswith("---"):
        return {}, text
    end = text.find("\n---", 3)
    if end == -1:
        return {}, text
    meta, body = {}, text[end + 4:].lstrip("\n")
    for line in text[3:end].strip().split("\n"):
        m = re.match(r"([A-Za-z_]+):\s*(.*)", line.strip())
        if not m:
            continue
        k, v = m.group(1), m.group(2).strip()
        if v.startswith("["):
            meta[k] = [a or b or c for a, b, c in
                       re.findall(r'"([^"]*)"|\'([^\']*)\'|([^,\[\]\s]+)', v)]
        else:
            meta[k] = v.strip("\"'")
    return meta, body


_SCHEMA_PATHS = [r".*/repository/.*", r".*/entity/.*", r".*Repository\.java$",
                 r"src/main/resources/db/.*"]
_SCHEMA_HUNK = re.compile(r"@Entity|@Table|@Query|nativeQuery|"
                          r"\b(SELECT|INSERT|UPDATE|DELETE|CREATE TABLE|ALTER TABLE)\b")


def persistence_touching(changes: List[FileChange]) -> bool:
    for c in changes:
        if any(re.match(rx, c.file, re.IGNORECASE) for rx in _SCHEMA_PATHS):
            return True
        for h in c.hunks:
            text = "\n".join(x[1:] for x in h.lines if x[:1] in "+ ")
            if _SCHEMA_HUNK.search(text):
                return True
    return False


def _kd(path, selector, body):
    body = body.strip()
    return KnowledgeDoc(path, selector, body, count_tokens(body))


def select_docs(repo, changes: List[FileChange], cfg):
    files = repo.list_files()
    changed = [c.file for c in changes]
    out = {"always": [], "glob": [], "schema": [],
           "schema_triggered": False, "schema_missing": False}
    taken = set()

    for base in cfg.always_include_docs:
        brief = base[:-3] + ".brief.md" if base.endswith(".md") else base + ".brief.md"
        pick = brief if repo.read(brief) is not None else base
        txt = repo.read(pick)
        if txt is not None:
            _, body = parse_frontmatter(txt)
            out["always"].append(_kd(pick, "always", body))
        taken.update({pick, base})

    out["schema_triggered"] = persistence_touching(changes)
    if out["schema_triggered"]:
        txt = repo.read(cfg.schema_doc)
        if txt is not None:
            _, body = parse_frontmatter(txt)
            out["schema"].append(_kd(cfg.schema_doc, "schema", body))
        else:
            out["schema_missing"] = True
    taken.add(cfg.schema_doc)

    for p in files:
        if p in taken or not glob_match(cfg.context_docs_glob, p):
            continue
        txt = repo.read(p)
        if txt is None:
            continue
        meta, body = parse_frontmatter(txt)
        pats = meta.get("applies_to") or []
        if isinstance(pats, str):
            pats = [pats]
        if any(glob_match(gp, cp) for gp in pats for cp in changed):
            out["glob"].append(_kd(p, "glob", body))
    out["glob"].sort(key=lambda k: k.path)
    return out
