"""End-to-end review pipeline (PRD s4).

diff -> Java context -> LLM (one call per changed file) -> validate -> judge
(cross-file consolidation on a second, typically stronger, model) -> score
-> publish -> report.

Failures are explicit: a file whose LLM call or JSON parse failed is recorded as
``status='failed'`` and never counted as a successful review. The judge is a
refinement layer, not a hard dependency: if its call fails, the pipeline falls back
to the mechanically deduped findings instead of failing the whole review.
"""

from __future__ import annotations

import time
from dataclasses import dataclass
from typing import Dict, List, Optional, Tuple

from . import logging as L
from .context.builder import build_review_context
from .context.diff_parser import hunk_new_line_span
from .context.models import FileChange, PRInfo
from .context.render import render_for_file
from .context.repo_view import LocalRepoView
from .git_ops import commit_messages, current_sha, resolve_sha, unified_diff
from .judge import prompts as judge_prompts
from .judge.contract import judge_review
from .llm.base import build_judge_provider, build_provider, system_prompt, user_prompt
from .llm.contract import review_file
from .models import DroppedFinding, Finding, GateResult, ReviewReport, TokenUsage
from .publish.formatter import inline_comment, summary_comment
from .publish.github_client import GitHubClient, GitHubError
from .review.dedup import dedupe_findings
from .review.scoring import evaluate_gate
from .review.validator import validate_findings

_REVIEWABLE_STATUSES = {"added", "modified", "renamed"}


@dataclass
class RunInputs:
    repo_path: str
    pr_id: Optional[int] = None
    base: Optional[str] = None
    head: Optional[str] = None
    commit: Optional[str] = None
    overlay_dir: str = ""
    publish: bool = False
    status_url: str = ""
    diff_text: Optional[str] = None  # override: skip GitHub / git and use this diff


def _make_client(settings) -> Optional[GitHubClient]:
    owner, repo = settings.github_owner_repo
    if owner and repo and settings.gh_token():
        return GitHubClient(owner, repo, settings.gh_token(), settings.github_api_url)
    return None


def _gather_pr_info(inp: RunInputs, client: Optional[GitHubClient]) -> PRInfo:
    if client and inp.pr_id is not None:
        pr = client.get_pull_request(inp.pr_id)
        msgs = [m.split("\n")[0] for m in client.get_pr_commits(inp.pr_id)]
        return PRInfo(
            id=inp.pr_id,
            title=pr.get("title") or "",
            description=pr.get("body") or "",
            source_branch=(pr.get("head") or {}).get("ref") or inp.head or "",
            target_branch=(pr.get("base") or {}).get("ref") or inp.base or "",
            commit_messages=msgs,
        )
    return PRInfo(
        id=inp.pr_id,
        title="",
        description="",
        source_branch=inp.head or "",
        target_branch=inp.base or "",
        commit_messages=(commit_messages(inp.repo_path, inp.base, inp.head)
                         if inp.base and inp.head else []),
    )


def _resolve_diff(inp: RunInputs, client: Optional[GitHubClient]) -> str:
    if inp.diff_text is not None:
        L.step("using supplied diff text")
        return inp.diff_text
    if client and inp.pr_id is not None:
        L.step(f"fetching PR #{inp.pr_id} diff from GitHub")
        return client.get_diff(inp.pr_id)
    if not (inp.base and inp.head):
        raise ValueError("need --pr (with GitHub creds) or both --base and --head")
    L.step(f"computing local diff {inp.base}...{inp.head}")
    return unified_diff(inp.repo_path, inp.base, inp.head)


def _resolve_commit(inp: RunInputs, client: Optional[GitHubClient], pr_info: PRInfo) -> Optional[str]:
    if inp.commit:
        return inp.commit
    if client and inp.pr_id is not None:
        try:
            return (client.get_pull_request(inp.pr_id).get("head") or {}).get("sha")
        except GitHubError:
            return None
    for attempt in (lambda: resolve_sha(inp.repo_path, inp.head) if inp.head else None,
                    lambda: current_sha(inp.repo_path)):
        try:
            sha = attempt()
            if sha:
                return sha
        except Exception:
            continue
    return None


def _spans_by_file(changes: List[FileChange]) -> Dict[str, list]:
    return {c.file: [hunk_new_line_span(h) for h in c.hunks] for c in changes}


def _context_summary(ctx) -> dict:
    """Everything the LLM actually saw, for the demo / audit trail (not raw content)."""
    return {
        "changed_files": [
            {"file": c.file, "status": c.status, "language": c.language,
             "hunks": len(c.hunks)}
            for c in ctx.changes
        ],
        "rules_loaded": len(ctx.rules),
        "knowledge_docs": [
            {"path": k.path, "selector": k.selector, "tokens": k.tokens}
            for k in ctx.knowledge
        ],
        "code_context": [
            {"file": c.file, "reason": c.reason, "symbol": c.symbol, "tokens": c.tokens}
            for c in ctx.code
        ],
        "comments_included": len(ctx.comments),
    }


def _run_judge(provider, kept: List[Finding], pr_info: PRInfo, repo_slug: str,
               file_inputs: Dict[str, str]) -> Tuple[List[Finding], List[DroppedFinding]]:
    """One LLM call, on ``provider`` (typically a different, stronger model than the
    per-file reviewer), that consolidates ``kept`` across every changed file: merges
    duplicates, correlates the same root cause across files, and drops any finding
    whose evidence doesn't hold up. Falls back to the mechanical dedup on failure --
    the judge refines the findings, it never gates the review on its own availability.
    """
    context = "\n\n".join(f"--- {file} ---\n{text}" for file, text in file_inputs.items())
    system = judge_prompts.system_prompt()
    user = judge_prompts.user_prompt(findings=kept, context=context, pr_id=pr_info.id,
                                     repo=repo_slug, target_branch=pr_info.target_branch,
                                     source_branch=pr_info.source_branch)
    outcome = judge_review(provider, system, user)
    if outcome.status == "failed":
        L.warn(f"judge stage failed, falling back to mechanical dedup: {outcome.error}")
        return dedupe_findings(kept), []
    if outcome.repaired:
        L.step("judge response repaired after one retry")
    return list(outcome.review.findings), list(outcome.review.dropped)


def run(settings, inp: RunInputs) -> ReviewReport:
    started = time.monotonic()
    client = _make_client(settings)
    provider = build_provider(settings)
    L.step(f"LLM provider: {provider.name}")
    judge_provider = build_judge_provider(settings) if settings.judge_enabled else None
    if judge_provider is not None:
        L.step(f"Judge provider: {judge_provider.name}")

    diff_text = _resolve_diff(inp, client)
    pr_info = _gather_pr_info(inp, client)
    raw_comments = client.get_pr_comments(inp.pr_id) if (client and inp.pr_id is not None) else None

    repo = LocalRepoView(inp.repo_path, inp.overlay_dir)
    ctx = build_review_context(pr_info, diff_text, repo, settings, raw_comments)
    L.step(f"diff parsed: {len(ctx.changes)} changed file(s); "
           f"context {ctx.budget.get('used')}/{ctx.budget.get('limit')} tok, "
           f"{len(ctx.budget.get('dropped', []))} dropped")
    L.step("changed files: " + ", ".join(c.file for c in ctx.changes))
    if ctx.knowledge:
        L.step("docs used: " + ", ".join(f"{k.path} ({k.selector})" for k in ctx.knowledge))
    else:
        L.step("docs used: none")
    L.step(f"rules loaded: {len(ctx.rules)}")
    if ctx.code:
        by_reason: Dict[str, int] = {}
        for slice_ in ctx.code:
            by_reason[slice_.reason] = by_reason.get(slice_.reason, 0) + 1
        L.step("code context: " + ", ".join(f"{n} {r}" for r, n in by_reason.items())
               + " -- " + ", ".join(sorted({s.file for s in ctx.code})))

    commit_sha = _resolve_commit(inp, client, pr_info)

    if inp.publish and client and commit_sha:
        _safe(lambda: client.set_build_status(commit_sha, "pending", inp.status_url,
                                              description="AI review running"))

    # --- LLM review: one call per changed file ------------------------
    system = system_prompt()
    owner, repo_name = settings.github_owner_repo
    repo_slug = f"{owner}/{repo_name}" if owner else (settings.github_repository or inp.repo_path)

    file_inputs: Dict[str, str] = {}
    results = []
    for change in ctx.changes:
        if change.status not in _REVIEWABLE_STATUSES or not change.hunks:
            continue
        ctx_text = render_for_file(ctx, change.file)
        file_inputs[change.file] = ctx_text
        up = user_prompt(context=ctx_text, target_file=change.file, pr_id=pr_info.id,
                         repo=repo_slug, target_branch=pr_info.target_branch,
                         source_branch=pr_info.source_branch)
        L.step(f"LLM review: {change.file}")
        before = provider.usage.total_tokens
        res = review_file(provider, system, up, change.file)
        used = provider.usage.total_tokens - before
        if res.status == "failed":
            L.warn(f"{change.file}: {res.error}")
        else:
            L.step(f"{change.file}: {len(res.findings)} raw finding(s)"
                   + (" (repaired)" if res.repaired else ""))
        L.step(f"{change.file}: {used} tok consumed")
        results.append(res)

    raw_findings: List[Finding] = [f for r in results if r.status == "ok" for f in r.findings]
    failed_files = [r.file for r in results if r.status == "failed"]
    all_failed = bool(results) and all(r.status == "failed" for r in results)

    # --- validate (mechanical) -> judge (LLM consolidation) -> score --------
    kept, dropped = validate_findings(raw_findings, ctx.changes, file_inputs, settings.min_confidence)
    L.step(f"validation: {len(raw_findings)} -> {len(kept)} finding(s) ({len(dropped)} dropped)")

    if judge_provider is not None and kept:
        findings, judge_dropped = _run_judge(judge_provider, kept, pr_info, repo_slug, file_inputs)
        dropped = dropped + judge_dropped
        L.step(f"judge: {len(kept)} -> {len(findings)} finding(s) "
               f"({len(judge_dropped)} dropped by judge)")
    else:
        findings = dedupe_findings(kept)
        if len(findings) != len(kept):
            L.step(f"dedup: {len(kept)} -> {len(findings)} finding(s)")

    gate = evaluate_gate(findings, settings)
    if all_failed:
        gate = GateResult(status="CHANGES REQUESTED", exit_code=1, score=gate.score,
                          counts=gate.counts,
                          reasons=gate.reasons + ["every changed file failed LLM review"])
    L.step(f"gate: {gate.status} (score {gate.score}, exit {gate.exit_code})")

    review_usage = TokenUsage(**provider.usage.__dict__)
    judge_usage = TokenUsage(**judge_provider.usage.__dict__) if judge_provider is not None else TokenUsage()
    token_usage = TokenUsage(
        prompt_tokens=review_usage.prompt_tokens + judge_usage.prompt_tokens,
        completion_tokens=review_usage.completion_tokens + judge_usage.completion_tokens,
        total_tokens=review_usage.total_tokens + judge_usage.total_tokens,
        calls=review_usage.calls + judge_usage.calls,
    )
    L.step(f"token usage: {token_usage.total_tokens} tok "
           f"({token_usage.prompt_tokens} prompt + {token_usage.completion_tokens} completion) "
           f"across {token_usage.calls} LLM call(s) "
           f"[review {review_usage.total_tokens} + judge {judge_usage.total_tokens}]")

    report = ReviewReport(
        repo=repo_slug, pr=pr_info.id, base=pr_info.target_branch, head=pr_info.source_branch,
        commit=commit_sha, provider=provider.name,
        review_ok=not failed_files,
        summary=_overall_summary(results, gate),
        files_reviewed=results, findings=findings, dropped=dropped, gate=gate,
        duration_seconds=round(time.monotonic() - started, 2),
        context_budget=ctx.budget,
        context_summary=_context_summary(ctx),
        token_usage=token_usage,
        review_token_usage=review_usage,
        judge_token_usage=judge_usage,
    )

    if inp.publish and client:
        _publish(client, pr_info, commit_sha, findings, gate, provider.name, failed_files,
                 inp.status_url, _spans_by_file(ctx.changes), token_usage)
    elif inp.publish:
        L.warn("--publish set but no GitHub client (need GITHUB_TOKEN + GITHUB_REPOSITORY); skipping")

    L.step(f"done in {report.duration_seconds}s")
    return report


def _overall_summary(results, gate: GateResult) -> str:
    parts = [r.summary for r in results if r.status == "ok" and r.summary]
    return (f"{gate.status} — risk {gate.score}/100. " + " ".join(parts)).strip()


def _publish(client, pr_info, commit_sha, findings, gate, provider_name, failed_files,
             status_url, spans_by_file, token_usage: TokenUsage):
    if pr_info.id is not None:
        unplaced: List[Finding] = []
        for f in findings:
            placeable = commit_sha and any(lo <= f.line <= hi
                                           for lo, hi in spans_by_file.get(f.file, []))
            if placeable:
                try:
                    client.post_inline_comment(pr_info.id, commit_sha, f.file, f.line,
                                               inline_comment(f))
                    continue
                except GitHubError as e:
                    L.warn(f"inline comment failed for {f.file}:{f.line}: {e}")
            unplaced.append(f)
        body = summary_comment(findings, gate, provider=provider_name,
                               failed_files=failed_files, unplaced=unplaced,
                               token_usage=token_usage)
        _safe(lambda: client.post_summary_comment(pr_info.id, body))
        L.step("posted summary + inline comments")
    else:
        L.warn("no PR id -> commit status only")

    if commit_sha:
        state = "success" if gate.exit_code == 0 else "failure"
        _safe(lambda: client.set_build_status(
            commit_sha, state, status_url, description=f"{gate.status} · risk {gate.score}/100"))


def _safe(fn):
    try:
        return fn()
    except Exception as e:  # publishing must never crash the run
        L.warn(f"publish step failed: {e}")
        return None
