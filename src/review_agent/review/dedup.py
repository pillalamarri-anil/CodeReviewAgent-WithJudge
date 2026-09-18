"""Finding dedup / merge (PRD s4 step 6).

Key = ``file + line-bucket(5) + category + normalized title``. Findings that collide
are merged: highest severity wins, highest confidence wins, evidence is unioned. (LLM
+ static merge is the same operation; static analysis is P1.)
"""

from __future__ import annotations

import re
from typing import Iterable, List

from ..models import Finding, Severity

_SEVERITY_RANK = {Severity.CRITICAL: 3, Severity.HIGH: 2, Severity.MEDIUM: 1, Severity.LOW: 0}
_LINE_BUCKET = 5


def _normalize_title(title: str) -> str:
    return re.sub(r"[^a-z0-9]+", " ", title.lower()).strip()


def _key(f: Finding):
    return (f.file, f.line // _LINE_BUCKET, f.category, _normalize_title(f.title))


def _merge(a: Finding, b: Finding) -> Finding:
    primary, other = (a, b) if _SEVERITY_RANK[a.severity] >= _SEVERITY_RANK[b.severity] else (b, a)
    data = primary.model_dump()
    data["confidence"] = max(a.confidence, b.confidence)
    if other.evidence.strip() and other.evidence.strip() not in primary.evidence:
        data["evidence"] = f"{primary.evidence}\n---\n{other.evidence}".strip()
    return Finding.model_validate(data)


def dedupe_findings(findings: Iterable[Finding]) -> List[Finding]:
    merged: dict = {}
    order: List = []
    for f in findings:
        k = _key(f)
        if k in merged:
            merged[k] = _merge(merged[k], f)
        else:
            merged[k] = f
            order.append(k)
    return [merged[k] for k in order]
