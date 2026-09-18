from review_agent.models import Category, Finding, Severity
from review_agent.review.dedup import dedupe_findings


def _f(**kw):
    base = dict(
        severity=Severity.MEDIUM, category=Category.BUG, file="A.java", line=20,
        title="N+1 query in loop", description="d", impact="i", recommendation="r",
        evidence="e1", confidence=0.8,
    )
    base.update(kw)
    return Finding(**base)


def test_merges_near_duplicates_same_bucket():
    a = _f(line=20, title="N+1 query in loop", evidence="e1", confidence=0.8)
    b = _f(line=22, title="N + 1  QUERY in loop!", evidence="e2", confidence=0.95,
           severity=Severity.HIGH)
    out = dedupe_findings([a, b])
    assert len(out) == 1
    m = out[0]
    assert m.severity == Severity.HIGH          # highest severity wins
    assert m.confidence == 0.95                  # highest confidence wins
    assert "e1" in m.evidence and "e2" in m.evidence


def test_keeps_distinct_findings():
    a = _f(line=20, category=Category.BUG, title="loop bug")
    b = _f(line=20, category=Category.SECURITY, title="sql injection")
    c = _f(line=80, category=Category.BUG, title="loop bug")
    assert len(dedupe_findings([a, b, c])) == 3


def test_order_preserved():
    a = _f(line=10, title="first")
    b = _f(line=50, title="second")
    out = dedupe_findings([a, b, _f(line=11, title="First")])
    assert [f.title for f in out] == ["first", "second"]
