"""``ReviewContext`` -> prompt text in a fixed section order.

Ported from ``context_creator.ipynb`` cell 26. ``render()`` emits the whole bundle
(used for the report + debug dry-run); ``render_for_file()`` emits the shared
sections plus exactly one changed file's diff + code, for the per-file LLM call
(PRD s4.4 -- one call per changed file).
"""

from __future__ import annotations

import os
from typing import List

from .models import ReviewContext

_FENCE = {".java": "java", ".py": "python", ".md": "markdown", ".yaml": "yaml",
          ".yml": "yaml", ".xml": "xml", ".sql": "sql"}


def _fence_lang(path: str) -> str:
    return _FENCE.get(os.path.splitext(path)[1], "")


def _shared_sections(ctx: ReviewContext) -> List[str]:
    P: List[str] = []
    # 1 PR intent
    P += ["=== PR INTENT ===",
          f"Title : {ctx.pr.title}",
          f"Branch: {ctx.pr.source_branch} -> {ctx.pr.target_branch}"]
    if ctx.pr.description.strip():
        P += ["", "Description:", ctx.pr.description.strip()]
    if ctx.pr.commit_messages:
        P += ["", "Commits:"] + [f"  - {m}" for m in ctx.pr.commit_messages]

    # 2 Rules
    P += ["", "=== REVIEW RULES (enforce every one) ==="]
    P += [f"  - {r}" for r in ctx.rules] or ["  (none configured)"]

    # 3 Knowledge
    know = [k for k in ctx.knowledge if k.selector in ("always", "glob")]
    schema = [k for k in ctx.knowledge if k.selector == "schema"]
    P += ["", "=== DOMAIN / ARCHITECTURE KNOWLEDGE ==="]
    if know:
        for k in sorted(know, key=lambda k: (k.selector, k.path)):
            P += ["", f"## {k.path}  (selector: {k.selector})", k.content.strip()]
    else:
        P += ["  (no knowledge docs matched)"]

    # 4 Schema
    P += ["", "=== SCHEMA ==="]
    if schema:
        for k in sorted(schema, key=lambda k: k.path):
            P += ["", f"## {k.path}", k.content.strip()]
    else:
        P += ["  (change is not persistence-touching, or schema doc absent)"]

    # 5 Review conversation
    P += ["", "=== REVIEW CONVERSATION SO FAR ==="]
    if ctx.comments:
        for c in ctx.comments:
            loc = f"{c.file}:{c.line}" if c.file else "(general)"
            P += ["", f"[{'AI' if c.is_ai else 'human'}/"
                      f"{'resolved' if c.resolved else 'open'}] {c.author} @ {loc}",
                  c.body.strip()]
    else:
        P += ["  (no prior comments)"]
    return P


def _diff_block(ch) -> List[str]:
    P = [f"--- {ch.file}   [{ch.status}, {ch.language}]"]
    for h in ch.hunks:
        P += [f"@@ -{h.old_start},{h.old_lines} +{h.new_start},{h.new_lines} @@"]
        P += h.lines
    return P


def _code_block(s) -> List[str]:
    return ["", f"## [{s.reason}] {s.symbol}   ({s.file}, ~{s.tokens} tok)",
            "```" + _fence_lang(s.file), s.content.rstrip(), "```"]


def render(ctx: ReviewContext) -> str:
    P = _shared_sections(ctx)

    P += ["", "=== CHANGED FILES (unified diff) ==="]
    for ch in ctx.changes:
        P += [""] + _diff_block(ch)

    P += ["", "=== RELEVANT CODE ==="]
    rank = {"enclosing": 0, "referenced": 1, "test": 2}
    for s in sorted(ctx.code, key=lambda s: (rank.get(s.reason, 9), s.file, s.symbol)):
        P += _code_block(s)

    b = ctx.budget
    P += ["", "=== BUDGET ===", f"limit={b.get('limit')}  used={b.get('used')}"]
    if b.get("dropped"):
        P += ["dropped:"] + [f"  - {d}" for d in b["dropped"]]

    return "\n".join(P) + "\n"


def render_for_file(ctx: ReviewContext, target_file: str) -> str:
    """Shared sections + exactly one changed file's diff and its related code."""
    P = _shared_sections(ctx)

    change = next((c for c in ctx.changes if c.file == target_file), None)
    P += ["", "=== CHANGED FILE UNDER REVIEW (unified diff) ==="]
    if change is not None:
        P += [""] + _diff_block(change)

    related = [s for s in ctx.code
               if s.file == target_file or s.reason in ("referenced", "test")]
    P += ["", "=== RELEVANT CODE ==="]
    rank = {"enclosing": 0, "referenced": 1, "test": 2}
    for s in sorted(related, key=lambda s: (rank.get(s.reason, 9), s.file, s.symbol)):
        P += _code_block(s)

    return "\n".join(P) + "\n"
