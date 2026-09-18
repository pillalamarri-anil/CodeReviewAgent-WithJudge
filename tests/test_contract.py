import json

import pytest

from review_agent.llm.contract import parse_review, review_file
from review_agent.llm.mock import MockProvider

VALID = {
    "summary": "one issue",
    "findings": [{
        "severity": "HIGH", "category": "PERFORMANCE",
        "file": "A.java", "line": 20, "title": "N+1",
        "description": "d", "impact": "i", "recommendation": "r",
        "suggested_fix": None, "evidence": "findById(id)", "confidence": 0.9,
    }],
}


def test_parse_valid():
    r = parse_review(json.dumps(VALID))
    assert r.summary == "one issue" and len(r.findings) == 1


def test_parse_strips_markdown_fence():
    r = parse_review("```json\n" + json.dumps(VALID) + "\n```")
    assert len(r.findings) == 1


def test_review_file_ok():
    p = MockProvider(raw=json.dumps(VALID))
    res = review_file(p, "sys", "user with the file \"A.java\"", "A.java")
    assert res.status == "ok" and not res.repaired and len(res.findings) == 1


def test_review_file_repairs_once_then_ok():
    class FlakyProvider:
        name = "flaky"

        def __init__(self):
            self.n = 0

        def complete(self, system, user):
            self.n += 1
            return "not json at all" if self.n == 1 else json.dumps(VALID)

    p = FlakyProvider()
    res = review_file(p, "sys", "user", "A.java")
    assert res.status == "ok" and res.repaired and p.n == 2


def test_review_file_fails_after_two_bad_responses():
    p = MockProvider(raw="{ still not valid")
    res = review_file(p, "sys", "user", "A.java")
    assert res.status == "failed" and res.repaired
    assert "after one repair retry" in res.error
