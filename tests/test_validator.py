from review_agent.context.diff_parser import parse_unified_diff
from review_agent.models import Category, Finding, Severity
from review_agent.review.validator import validate_findings


def _finding(**kw):
    base = dict(
        severity=Severity.HIGH, category=Category.BUG,
        file="src/main/java/com/example/service/OrderService.java", line=20,
        title="N+1 query in loop", description="findById per iteration",
        impact="slow", recommendation="batch fetch",
        evidence="orderRepository.findById(id).orElseThrow()", confidence=0.9,
    )
    base.update(kw)
    return Finding(**base)


def _changes(diff):
    return parse_unified_diff(diff("method_edit.diff"))


def _inputs(diff):
    return {
        "src/main/java/com/example/service/OrderService.java":
            "context...\n            Order order = orderRepository.findById(id).orElseThrow();\n"
    }


def test_keeps_valid_finding(diff):
    kept, dropped = validate_findings([_finding()], _changes(diff), _inputs(diff), 0.75)
    assert len(kept) == 1 and not dropped


def test_drops_finding_on_file_not_in_change_set(diff):
    f = _finding(file="src/main/java/com/example/Other.java")
    kept, dropped = validate_findings([f], _changes(diff), _inputs(diff), 0.75)
    assert not kept and "not in changed set" in dropped[0].reason


def test_drops_finding_outside_hunk(diff):
    kept, dropped = validate_findings([_finding(line=999)], _changes(diff), _inputs(diff), 0.75)
    assert not kept and "not inside any changed hunk" in dropped[0].reason


def test_drops_unevidenced_finding(diff):
    kept, dropped = validate_findings([_finding(evidence="this never appears")],
                                     _changes(diff), _inputs(diff), 0.75)
    assert not kept and "verbatim" in dropped[0].reason


def test_drops_low_confidence_non_protected(diff):
    kept, dropped = validate_findings([_finding(confidence=0.4)],
                                     _changes(diff), _inputs(diff), 0.75)
    assert not kept and "MIN_CONFIDENCE" in dropped[0].reason


def test_keeps_low_confidence_critical(diff):
    f = _finding(severity=Severity.CRITICAL, confidence=0.3)
    kept, dropped = validate_findings([f], _changes(diff), _inputs(diff), 0.75)
    assert len(kept) == 1 and not dropped


def test_keeps_low_confidence_security(diff):
    f = _finding(category=Category.SECURITY, severity=Severity.MEDIUM, confidence=0.2)
    kept, _ = validate_findings([f], _changes(diff), _inputs(diff), 0.75)
    assert len(kept) == 1
