"""Existing PR comments -> ``CommentItem`` list with ``is_ai`` / ``resolved`` flags.

Ported from ``context_creator.ipynb`` cell 22. Consumes the shape returned by
``publish.github_client.GitHubClient.get_pr_comments`` -- ``{"review": [...], "issue": [...]}``.
"""

from __future__ import annotations

from typing import List

from .models import CommentItem

AI_SUMMARY_MARKER = "<!-- ai-review:summary -->"
AI_INLINE_MARKER = "<!-- ai-review:inline -->"

_AI_MARKERS = (
    "\U0001f916 Generated with", "Generated with [Claude Code]",
    "generated with claude code", "<!-- ai-review",
)
_AI_AUTHOR = ("claude", "bot", "github-actions", "[bot]", "dependabot")


def _is_ai(author: str, body: str) -> bool:
    a = (author or "").lower()
    if any(h in a for h in _AI_AUTHOR):
        return True
    b = (body or "").lower()
    return any(m.lower() in b for m in _AI_MARKERS)


def build_comments(raw, resolved_ids=frozenset()) -> List[CommentItem]:
    items: List[CommentItem] = []
    for c in raw.get("review", []):
        author = (c.get("user") or {}).get("login", "")
        body = c.get("body", "") or ""
        items.append(CommentItem(
            file=c.get("path"),
            line=c.get("line") or c.get("original_line"),
            author=author,
            is_ai=_is_ai(author, body),
            resolved=(c.get("id") in resolved_ids) or bool(c.get("_resolved")),
            body=body,
        ))
    for c in raw.get("issue", []):
        author = (c.get("user") or {}).get("login", "")
        body = c.get("body", "") or ""
        items.append(CommentItem(None, None, author, _is_ai(author, body), False, body))
    items.sort(key=lambda x: ((x.file or ""), (x.line or 0), x.author, x.body[:40]))
    return items
