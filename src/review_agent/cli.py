"""CLI runner (PRD s2, s9):

    python -m review_agent --repo . --pr $PR --base $BASE --head $HEAD --commit $SHA

Exit code is the quality gate result: 0 = PASS, 1 = CHANGES REQUESTED / hard failure.
"""

from __future__ import annotations

import argparse
import sys

from . import logging as L
from .config import load_settings
from .pipeline import RunInputs, run
from .report.json_report import write_report


def _parse_args(argv):
    p = argparse.ArgumentParser(prog="review-agent", description="AI code review for Java PRs")
    p.add_argument("--repo", default=".", help="path to the local checkout (default: .)")
    p.add_argument("--pr", type=int, default=None, help="pull request number")
    p.add_argument("--base", default=None, help="base branch / ref")
    p.add_argument("--head", default=None, help="head branch / ref")
    p.add_argument("--commit", default=None, help="head commit SHA (for the build status)")
    p.add_argument("--overlay", default="", help="dir of knowledge docs / review-rules.yaml to overlay")
    p.add_argument("--report", default="review-report.json", help="output report path")
    p.add_argument("--status-url", default="", help="URL to link from the commit status")
    pub = p.add_mutually_exclusive_group()
    pub.add_argument("--publish", dest="publish", action="store_true",
                     help="post comments + set commit status on the PR")
    pub.add_argument("--no-publish", dest="publish", action="store_false",
                     help="local run: write the report only (default)")
    p.set_defaults(publish=False)
    find = p.add_mutually_exclusive_group()
    find.add_argument("--show-findings", dest="show_findings", action="store_true",
                      help="print the full per-finding review summary to the console (default)")
    find.add_argument("--no-show-findings", dest="show_findings", action="store_false",
                      help="print only the one-line gate result, not each finding")
    p.set_defaults(show_findings=True)
    return p.parse_args(argv)


def _print_context_summary(summary: dict) -> None:
    """Human-readable 'what did the agent actually look at' block (demo visibility)."""
    if not summary:
        return
    print("\n=== CONTEXT USED ===", file=sys.stderr)

    print(f"Changed files ({len(summary.get('changed_files', []))}):", file=sys.stderr)
    for f in summary.get("changed_files", []):
        print(f"  - {f['file']}  [{f['status']}, {f['language'] or 'unknown'}, "
              f"{f['hunks']} hunk(s)]", file=sys.stderr)

    docs = summary.get("knowledge_docs", [])
    print(f"\nKnowledge docs read ({len(docs)}):", file=sys.stderr)
    for d in docs:
        print(f"  - {d['path']}  (selector: {d['selector']}, {d['tokens']} tok)", file=sys.stderr)
    if not docs:
        print("  (none)", file=sys.stderr)

    print(f"\nReview rules loaded: {summary.get('rules_loaded', 0)}", file=sys.stderr)

    code = summary.get("code_context", [])
    print(f"\nSource files pulled in as supporting code context ({len(code)} snippet(s)):",
          file=sys.stderr)
    for c in code:
        print(f"  - {c['file']}  [{c['reason']}: {c['symbol']}, {c['tokens']} tok]",
              file=sys.stderr)
    if not code:
        print("  (none)", file=sys.stderr)

    print(f"\nUnresolved PR comments included: {summary.get('comments_included', 0)}",
          file=sys.stderr)


_SEV_ORDER = {"CRITICAL": 0, "HIGH": 1, "MEDIUM": 2, "LOW": 3}
_SEV_EMOJI = {"CRITICAL": "🟥", "HIGH": "🟧", "MEDIUM": "🟨", "LOW": "🟦"}


def _print_findings_summary(report) -> None:
    """Full per-finding review summary on the console (demo visibility)."""
    print("\n=== CODE REVIEW SUMMARY ===", file=sys.stderr)
    if report.summary:
        print(report.summary, file=sys.stderr)

    findings = sorted(report.findings,
                      key=lambda f: (_SEV_ORDER[f.severity.value], -f.confidence))
    if not findings:
        print("\nNo issues found on the changed lines.", file=sys.stderr)
    else:
        print(f"\n{len(findings)} finding(s):", file=sys.stderr)
        for f in findings:
            print(f"\n{_SEV_EMOJI[f.severity.value]} {f.severity.value} | {f.category.value} "
                  f"— {f.title}", file=sys.stderr)
            print(f"  {f.file}:{f.line}  (confidence {f.confidence:.2f})", file=sys.stderr)
            print(f"  {f.description.strip()}", file=sys.stderr)
            print(f"  Fix: {f.recommendation.strip()}", file=sys.stderr)

    failed = [fr.file for fr in report.files_reviewed if fr.status == "failed"]
    if failed:
        print("\nFiles that failed LLM review (not reviewed): " + ", ".join(failed),
              file=sys.stderr)

    if report.dropped:
        print(f"\n{len(report.dropped)} finding(s) dropped during validation:", file=sys.stderr)
        for d in report.dropped:
            print(f"  - {d.finding.title} ({d.finding.file}:{d.finding.line}) — {d.reason}",
                  file=sys.stderr)


def main(argv=None) -> int:
    args = _parse_args(argv if argv is not None else sys.argv[1:])
    settings = load_settings()

    inp = RunInputs(
        repo_path=args.repo, pr_id=args.pr, base=args.base, head=args.head,
        commit=args.commit, overlay_dir=args.overlay, publish=args.publish,
        status_url=args.status_url,
    )

    try:
        report = run(settings, inp)
    except Exception as e:
        L.error(f"review failed: {e}")
        return 2

    out = write_report(report, args.report)
    L.step(f"report written: {out}")

    _print_context_summary(report.context_summary)
    if args.show_findings:
        _print_findings_summary(report)

    tu = report.token_usage
    print(f"\nTokens used: {tu.total_tokens} ({tu.prompt_tokens} prompt + "
          f"{tu.completion_tokens} completion) across {tu.calls} LLM call(s)", file=sys.stderr)
    ru, ju = report.review_token_usage, report.judge_token_usage
    print(f"  review: {ru.total_tokens} tok across {ru.calls} call(s)  ·  "
          f"judge: {ju.total_tokens} tok across {ju.calls} call(s)", file=sys.stderr)

    gate = report.gate
    print(f"\n{gate.status}  score={gate.score}/100  "
          f"CRITICAL={gate.counts['CRITICAL']} HIGH={gate.counts['HIGH']} "
          f"MEDIUM={gate.counts['MEDIUM']} LOW={gate.counts['LOW']}", file=sys.stderr)
    for r in gate.reasons:
        print(f"  - {r}", file=sys.stderr)
    return gate.exit_code


if __name__ == "__main__":
    raise SystemExit(main())
