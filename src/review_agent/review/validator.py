"""Finding validation -- false-positive control (PRD s4 step 5 / s4.5).

Keep a finding only if:
  1. its file is in the changed set
  2. its line falls inside a changed hunk (context lines included) or the supplied context
  3. its ``evidence`` snippet appears verbatim in the input shown to the model
  4. its ``confidence`` >= ``min_confidence``

CRITICAL and SECURITY findings are dropped only on checks 1-3 -- never on confidence
alone.
"""

from __future__ import annotations

import re
from typing import Dict, List, Tuple

from ..context.diff_parser import hunk_new_line_span
from ..context.models import FileChange
from ..models import Category, DroppedFinding, Finding, Severity


def _line_ok(line: int, spans: List[Tuple[int, int]]) -> bool:
    return any(lo <= line <= hi for lo, hi in spans)


def _normalize_ws(text: str) -> str:
    return re.sub(r"\s+", " ", text).strip()


def _evidence_present(evidence: str, haystack: str) -> bool:
    ev = evidence.strip()
    if not ev:
        return False
    if ev in haystack:
        return True
    return _normalize_ws(ev) in _normalize_ws(haystack)  # tolerate indentation only


def validate_findings(
    findings: List[Finding],
    changes: List[FileChange],
    file_inputs: Dict[str, str],
    min_confidence: float,
) -> Tuple[List[Finding], List[DroppedFinding]]:
    changed_files = {c.file for c in changes}
    spans_by_file = {c.file: [hunk_new_line_span(h) for h in c.hunks] for c in changes}
    all_input = "\n".join(file_inputs.values())

    kept: List[Finding] = []
    dropped: List[DroppedFinding] = []

    for f in findings:
        protected = f.severity == Severity.CRITICAL or f.category == Category.SECURITY

        if f.file not in changed_files:
            dropped.append(DroppedFinding(finding=f, reason=f"file '{f.file}' not in changed set"))
            continue

        if not _line_ok(f.line, spans_by_file.get(f.file, [])):
            dropped.append(DroppedFinding(
                finding=f, reason=f"line {f.line} not inside any changed hunk of {f.file}"))
            continue

        haystack = file_inputs.get(f.file) or all_input
        if not _evidence_present(f.evidence, haystack):
            dropped.append(DroppedFinding(
                finding=f, reason="evidence snippet does not appear verbatim in the model input"))
            continue

        if not protected and f.confidence < min_confidence:
            dropped.append(DroppedFinding(
                finding=f, reason=f"confidence {f.confidence:.2f} < MIN_CONFIDENCE {min_confidence:.2f}"))
            continue

        kept.append(f)

    return kept, dropped
