"""Assemble a token-budgeted ``ReviewContext`` from already-fetched PR inputs.

Ported / refactored from ``context_creator.ipynb`` cell 24. Unlike the notebook this
does **no** network I/O -- the caller fetches the diff / PR metadata / comments (via
``GitHubClient`` or local git) and passes a ``repo`` view. Keeps the builder
deterministic and unit-testable offline (context-prep PRD acceptance criteria).
"""

from __future__ import annotations

from typing import List, Optional

from .comments_provider import build_comments
from .diff_parser import hunk_changed_new_lines, parse_unified_diff
from .docs_selector import select_docs
from .fallback_extractor import extract_fallback
from .java_extractor import extract_java, java_index
from .languages import annotate_languages
from .models import CodeSlice, PRInfo, ReviewContext
from .rules_loader import load_rules
from .tokens import Budget, count_tokens


def _dedupe(items):
    seen, out = set(), []
    for it in items:
        key = (it[0], it[2], it[3])
        if key in seen:
            continue
        seen.add(key)
        out.append(it)
    return out


def build_review_context(
    pr_info: PRInfo,
    diff_text: str,
    repo,
    cfg,
    raw_comments: Optional[dict] = None,
    resolved_ids=frozenset(),
) -> ReviewContext:
    raw_comments = raw_comments or {"review": [], "issue": []}
    changes = annotate_languages(parse_unified_diff(diff_text))

    budget = Budget(cfg.max_context_tokens)
    ctx = ReviewContext(pr=pr_info, changes=changes)

    # 1 -- change set (always, never dropped)
    budget.charge(sum(count_tokens("\n".join(h.lines)) for c in changes for h in c.hunks))

    # 2 -- rules
    rules = load_rules(repo, cfg)
    if rules and budget.add(count_tokens("\n".join(rules)), "rules"):
        ctx.rules = rules

    # gather all code slices once
    enclosing, referenced, tests = [], [], []
    jindex = java_index(repo)
    for c in changes:
        if c.status == "deleted":
            continue
        src = repo.read(c.file)
        changed_lines = sorted({n for h in c.hunks for n in hunk_changed_new_lines(h)})
        if c.language == "java" and src:
            e, r, t = extract_java(c.file, src, changed_lines, repo, jindex, cfg)
            enclosing += e
            referenced += r
            tests += t
        elif src:
            enclosing += extract_fallback(c.file, src, c.hunks, cfg)

    # 3 -- enclosing method / class per hunk
    for _reason, path, sym, content in _dedupe(enclosing):
        tk = count_tokens(content)
        if budget.add(tk, f"code:enclosing {sym}"):
            ctx.code.append(CodeSlice(path, "enclosing", sym, content, tk))

    # 4 -- unresolved PR comments on changed files
    comments = build_comments(raw_comments, resolved_ids)
    changed_fs = {c.file for c in changes}
    primary = [x for x in comments if x.file in changed_fs and not x.resolved]
    rest = [x for x in comments if x not in primary]
    for cm in primary:
        if budget.add(count_tokens(cm.body), f"comment {cm.author}"):
            ctx.comments.append(cm)

    # 5 -- always docs
    docs = select_docs(repo, changes, cfg)
    for kd in docs["always"]:
        if budget.add(kd.tokens, f"knowledge:always {kd.path}"):
            ctx.knowledge.append(kd)

    # 6 -- schema doc (iff persistence-touching)
    if docs["schema_triggered"]:
        if docs["schema"]:
            for kd in docs["schema"]:
                if budget.add(kd.tokens, f"knowledge:schema {kd.path}"):
                    ctx.knowledge.append(kd)
        else:
            budget.drop(f"knowledge:schema {cfg.schema_doc}",
                        "persistence-touching change but doc not in repo")

    # 7 -- glob docs (MAX_KNOWLEDGE_TOKENS cap)
    kn = sum(k.tokens for k in ctx.knowledge)
    for kd in docs["glob"]:
        if kn + kd.tokens > cfg.max_knowledge_tokens:
            budget.drop(f"knowledge:glob {kd.path}", "MAX_KNOWLEDGE_TOKENS cap")
            continue
        if budget.add(kd.tokens, f"knowledge:glob {kd.path}"):
            ctx.knowledge.append(kd)
            kn += kd.tokens

    # 8 -- referenced type signatures (MAX_CODE_TOKENS cap)
    cd = sum(s.tokens for s in ctx.code)
    for _reason, path, sym, content in _dedupe(referenced):
        tk = count_tokens(content)
        if cd + tk > cfg.max_code_tokens:
            budget.drop(f"code:referenced {sym}", "MAX_CODE_TOKENS cap")
            continue
        if budget.add(tk, f"code:referenced {sym}"):
            ctx.code.append(CodeSlice(path, "referenced", sym, content, tk))
            cd += tk

    # 9 -- test classes
    for _reason, path, sym, content in _dedupe(tests):
        tk = count_tokens(content)
        if budget.add(tk, f"code:test {sym}"):
            ctx.code.append(CodeSlice(path, "test", sym, content, tk))

    # 10 -- PR title / description / commits (section is mandatory in render)
    intent = "\n".join([pr_info.title, pr_info.description, *pr_info.commit_messages])
    if not budget.add(count_tokens(intent), "pr-intent"):
        budget.drop("pr-intent", "rendered anyway (section is mandatory)")

    # 11 -- remaining comments
    for cm in rest:
        if budget.add(count_tokens(cm.body), f"comment(other) {cm.author}"):
            ctx.comments.append(cm)

    ctx.comments.sort(key=lambda c: ((c.file or ""), (c.line or 0), c.author, c.body[:40]))
    ctx.budget = budget.as_dict()
    return ctx
