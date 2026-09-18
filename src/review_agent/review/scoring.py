"""Deterministic risk score + quality gate (PRD s7).

penalty: CRITICAL 40, HIGH 20, MEDIUM 8, LOW 2
score = clamp(100 - sum(penalty), 0, 100)

gate: any of  crit > MAX_CRITICAL | high > MAX_HIGH | medium > MAX_MEDIUM  -> exit 1.
"""

from __future__ import annotations

from typing import Iterable, List

from ..models import Finding, GateResult, Severity

_PENALTY = {Severity.CRITICAL: 40, Severity.HIGH: 20, Severity.MEDIUM: 8, Severity.LOW: 2}


def severity_counts(findings: Iterable[Finding]) -> dict:
    counts = {s.value: 0 for s in Severity}
    for f in findings:
        counts[f.severity.value] += 1
    return counts


def risk_score(findings: Iterable[Finding]) -> int:
    total = sum(_PENALTY[f.severity] for f in findings)
    return max(0, min(100, 100 - total))


def evaluate_gate(findings: List[Finding], settings) -> GateResult:
    counts = severity_counts(findings)
    score = risk_score(findings)

    reasons: List[str] = []
    if counts["CRITICAL"] > settings.max_critical:
        reasons.append(f"{counts['CRITICAL']} CRITICAL > MAX_CRITICAL {settings.max_critical}")
    if counts["HIGH"] > settings.max_high:
        reasons.append(f"{counts['HIGH']} HIGH > MAX_HIGH {settings.max_high}")
    if counts["MEDIUM"] > settings.max_medium:
        reasons.append(f"{counts['MEDIUM']} MEDIUM > MAX_MEDIUM {settings.max_medium}")

    failed = bool(reasons)
    return GateResult(
        status="CHANGES REQUESTED" if failed else "PASS",
        exit_code=1 if failed else 0,
        score=score,
        counts=counts,
        reasons=reasons,
    )
