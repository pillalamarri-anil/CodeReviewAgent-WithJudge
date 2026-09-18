"""Write ``review-report.json`` -- always produced (PRD s4 step 9)."""

from __future__ import annotations

import json
from pathlib import Path

from ..models import ReviewReport


def write_report(report: ReviewReport, path: str) -> str:
    p = Path(path)
    if p.parent and not p.parent.exists():
        p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps(report.model_dump(mode="json"), indent=2, sort_keys=False) + "\n",
                 encoding="utf-8")
    return str(p)
