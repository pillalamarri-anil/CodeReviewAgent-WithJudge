"""Strict JSON contract enforcement for the judge stage (PRD s4 step 5.5).

``judge_review`` performs one LLM call over the consolidated per-file findings,
validates the response against ``JudgeReview``, and on failure performs exactly ONE
repair retry -- the same contract ``llm.contract.review_file`` uses for the per-file
review. If the retry is still invalid the judge stage is marked failed; the pipeline
then falls back to the pre-judge findings rather than failing the whole review, since
the judge is a refinement layer, never a hard dependency.
"""

from __future__ import annotations

import json
from typing import Tuple

from pydantic import ValidationError

from ..llm.base import LLMError, LLMProvider
from ..llm.contract import extract_json
from ..models import JudgeOutcome, JudgeReview

_REPAIR_SUFFIX = (
    "\n\nYour previous response was not valid against the required schema.\n"
    "Return ONLY a single JSON object of the exact shape "
    '{"summary": string, "findings": [{"severity","category","file","line","title",'
    '"description","impact","recommendation","suggested_fix","evidence","confidence"}],'
    ' "dropped": [{"finding": <finding>, "reason": string}]}. '
    "No prose, no markdown fences. Error was: "
)


def judge_review(provider: LLMProvider, system: str, user: str) -> JudgeOutcome:
    raw, err = _try(provider, system, user)
    if isinstance(raw, JudgeReview):
        return JudgeOutcome(status="ok", review=raw)

    # one repair retry
    repair_user = user + _REPAIR_SUFFIX + str(err)[:400]
    raw2, err2 = _try(provider, system, repair_user)
    if isinstance(raw2, JudgeReview):
        return JudgeOutcome(status="ok", repaired=True, review=raw2)

    return JudgeOutcome(
        status="failed", repaired=True,
        error=f"invalid judge response after one repair retry: {err2 or err}",
    )


def _try(provider: LLMProvider, system: str, user: str) -> Tuple[object, object]:
    try:
        raw = provider.complete(system, user)
    except LLMError as e:
        return None, e
    try:
        data = json.loads(extract_json(raw))
        return JudgeReview.model_validate(data), None
    except (json.JSONDecodeError, ValidationError, ValueError, TypeError) as e:
        return None, e
