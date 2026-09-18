"""Strict JSON contract enforcement (PRD s6).

``review_file`` performs one LLM call, validates the response against ``LLMReview``,
and on failure performs exactly ONE repair retry. If the retry is still invalid the
file's review is marked failed -- never reported as succeeded (PRD s4).
"""

from __future__ import annotations

import json
import re
from typing import Tuple

from pydantic import ValidationError

from ..models import FileReviewResult, LLMReview
from .base import LLMError, LLMProvider

_JSON_OBJ_RE = re.compile(r"\{.*\}", re.DOTALL)

_REPAIR_SUFFIX = (
    "\n\nYour previous response was not valid against the required schema.\n"
    "Return ONLY a single JSON object of the exact shape "
    '{"summary": string, "findings": [{"severity","category","file","line","title",'
    '"description","impact","recommendation","suggested_fix","evidence","confidence"}]}. '
    "No prose, no markdown fences. Error was: "
)


def extract_json(text: str) -> str:
    """Pull the first ``{...}`` JSON object out of ``text``, stripping any markdown
    fence. Shared with the judge stage (``judge.contract``), which parses the same
    shape of response from a different model."""
    text = text.strip()
    if text.startswith("```"):
        text = text.strip("`")
        if text.lstrip().lower().startswith("json"):
            text = text.lstrip()[4:]
    m = _JSON_OBJ_RE.search(text)
    return m.group(0) if m else text


def parse_review(raw: str) -> LLMReview:
    """Raise ``ValidationError`` / ``ValueError`` if ``raw`` is not a valid ``LLMReview``."""
    data = json.loads(extract_json(raw))
    return LLMReview.model_validate(data)


def review_file(provider: LLMProvider, system: str, user: str, target_file: str) -> FileReviewResult:
    raw, err = _try(provider, system, user)
    if isinstance(raw, LLMReview):
        return FileReviewResult(file=target_file, status="ok",
                                summary=raw.summary, findings=list(raw.findings))

    # one repair retry
    repair_user = user + _REPAIR_SUFFIX + str(err)[:400]
    raw2, err2 = _try(provider, system, repair_user)
    if isinstance(raw2, LLMReview):
        return FileReviewResult(file=target_file, status="ok", repaired=True,
                                summary=raw2.summary, findings=list(raw2.findings))

    return FileReviewResult(
        file=target_file, status="failed", repaired=True,
        error=f"invalid LLM response after one repair retry: {err2 or err}",
    )


def _try(provider: LLMProvider, system: str, user: str) -> Tuple[object, object]:
    try:
        raw = provider.complete(system, user)
    except LLMError as e:
        return None, e
    try:
        return parse_review(raw), None
    except (json.JSONDecodeError, ValidationError, ValueError, TypeError) as e:
        return None, e
