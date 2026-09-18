"""Deterministic mock provider -- tests and offline dev only (PRD s6, AC11).

Never used in the demo. Given a mapping of ``{path-substring: response}`` it returns
the matching canned JSON; otherwise a clean (no-findings) review. ``response`` may be a
JSON string, or a dict that will be ``json.dumps``-ed.
"""

from __future__ import annotations

import json
import re
from typing import Dict, Optional, Union

from ..context.tokens import count_tokens
from .base import Usage

_TARGET_RE = re.compile(r'the file "([^"]+)"')

Response = Union[str, dict]


class MockProvider:
    name = "mock"

    def __init__(self, responses: Optional[Dict[str, Response]] = None,
                 default: Optional[Response] = None, raw: Optional[str] = None):
        self.responses = responses or {}
        self.default = default
        self.raw = raw
        self.calls = []  # list of (system, user) for assertions
        self.usage = Usage()  # offline estimate (~4 chars/token), same heuristic as the context budget

    def _match(self, user: str) -> Optional[Response]:
        m = _TARGET_RE.search(user)
        target = m.group(1) if m else ""
        for key, resp in self.responses.items():
            if key in target or key in user:
                return resp
        return self.default

    def complete(self, system: str, user: str) -> str:
        self.calls.append((system, user))
        if self.raw is not None:
            text = self.raw
        else:
            resp = self._match(user)
            if resp is None:
                resp = {"summary": "No issues found in the provided context.", "findings": []}
            text = resp if isinstance(resp, str) else json.dumps(resp)
        self.usage.add(count_tokens(system) + count_tokens(user), count_tokens(text))
        return text
