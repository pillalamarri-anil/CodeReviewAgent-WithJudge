from review_agent.config import Settings
from review_agent.models import Category, Finding, Severity
from review_agent.review.scoring import evaluate_gate, risk_score, severity_counts


def _f(sev):
    return Finding(severity=sev, category=Category.BUG, file="A.java", line=1,
                   title="t", description="d", impact="i", recommendation="r",
                   evidence="e", confidence=0.9)


GATE = Settings(_env_file=None, max_critical=0, max_high=0, max_medium=5)


def test_penalties_and_clamp():
    assert risk_score([]) == 100
    assert risk_score([_f(Severity.MEDIUM), _f(Severity.LOW)]) == 90  # 100 - 8 - 2
    assert risk_score([_f(Severity.CRITICAL)] * 5) == 0              # clamped at 0


def test_counts():
    c = severity_counts([_f(Severity.HIGH), _f(Severity.HIGH), _f(Severity.LOW)])
    assert c == {"CRITICAL": 0, "HIGH": 2, "MEDIUM": 0, "LOW": 1}


def test_gate_passes_clean():
    g = evaluate_gate([_f(Severity.LOW), _f(Severity.MEDIUM)], GATE)
    assert g.status == "PASS" and g.exit_code == 0


def test_gate_fails_on_high():
    g = evaluate_gate([_f(Severity.HIGH)], GATE)
    assert g.status == "CHANGES REQUESTED" and g.exit_code == 1
    assert "HIGH" in g.reasons[0]


def test_gate_fails_on_too_many_medium():
    g = evaluate_gate([_f(Severity.MEDIUM)] * 6, GATE)
    assert g.exit_code == 1 and "MEDIUM" in g.reasons[0]
