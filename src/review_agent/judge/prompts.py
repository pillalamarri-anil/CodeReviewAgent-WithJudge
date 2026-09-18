"""Prompt building for the judge stage (consolidation, cross-file correlation, and
evidence-sufficiency validation over the per-file reviewer's findings)."""

from __future__ import annotations

import json
from typing import List

from ..llm.base import load_prompt
from ..models import Finding


def system_prompt() -> str:
    return load_prompt("judge_system.txt")


def user_prompt(*, findings: List[Finding], context: str, pr_id, repo: str,
                target_branch: str, source_branch: str) -> str:
    candidate = json.dumps([f.model_dump(mode="json") for f in findings], indent=2)
    return load_prompt("judge_review.txt").format(
        candidate_findings=candidate,
        context=context,
        pr_id=pr_id if pr_id is not None else "?",
        repo=repo or "?",
        target_branch=target_branch or "?",
        source_branch=source_branch or "?",
    )
