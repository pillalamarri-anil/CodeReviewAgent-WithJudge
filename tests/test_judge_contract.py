import json

from review_agent.judge.contract import judge_review
from review_agent.judge.prompts import user_prompt
from review_agent.llm.mock import MockProvider
from review_agent.models import Category, Finding, Severity

VALID = {
    "summary": "kept one, dropped one duplicate",
    "findings": [{
        "severity": "HIGH", "category": "SECURITY",
        "file": "A.java", "line": 20, "title": "SQL injection",
        "description": "d", "impact": "i", "recommendation": "r",
        "suggested_fix": None, "evidence": "nativeQuery = true", "confidence": 0.9,
    }],
    "dropped": [{
        "finding": {
            "severity": "HIGH", "category": "SECURITY",
            "file": "A.java", "line": 21, "title": "SQL injection (dup)",
            "description": "d", "impact": "i", "recommendation": "r",
            "suggested_fix": None, "evidence": "nativeQuery = true", "confidence": 0.8,
        },
        "reason": "duplicate of another finding",
    }],
}


def _finding(**kw):
    base = dict(
        severity=Severity.HIGH, category=Category.SECURITY, file="A.java", line=20,
        title="SQL injection", description="d", impact="i", recommendation="r",
        evidence="nativeQuery = true", confidence=0.9,
    )
    base.update(kw)
    return Finding(**base)


def test_judge_review_ok():
    p = MockProvider(raw=json.dumps(VALID))
    outcome = judge_review(p, "sys", "user")
    assert outcome.status == "ok" and not outcome.repaired
    assert len(outcome.review.findings) == 1
    assert len(outcome.review.dropped) == 1
    assert outcome.review.dropped[0].reason == "duplicate of another finding"


def test_judge_review_repairs_once_then_ok():
    class FlakyProvider:
        name = "flaky"

        def __init__(self):
            self.n = 0

        def complete(self, system, user):
            self.n += 1
            return "not json at all" if self.n == 1 else json.dumps(VALID)

    p = FlakyProvider()
    outcome = judge_review(p, "sys", "user")
    assert outcome.status == "ok" and outcome.repaired and p.n == 2


def test_judge_review_fails_after_two_bad_responses():
    p = MockProvider(raw="{ still not valid")
    outcome = judge_review(p, "sys", "user")
    assert outcome.status == "failed" and outcome.repaired
    assert "after one repair retry" in outcome.error
    assert outcome.review is None


def test_user_prompt_embeds_candidate_findings_and_context():
    prompt = user_prompt(
        findings=[_finding()],
        context="--- A.java ---\nif (x) { nativeQuery = true; }",
        pr_id=7, repo="org/repo", target_branch="main", source_branch="feat/x",
    )
    assert "SQL injection" in prompt
    assert "nativeQuery = true" in prompt
    assert "#7 on org/repo" in prompt
    # candidate findings are JSON-serialized data, not re-interpreted as format
    # placeholders -- braces from Java source in the context must survive untouched.
    assert "if (x) { nativeQuery = true; }" in prompt
