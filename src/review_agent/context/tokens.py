"""Deterministic token estimate + a budget ledger that records every drop.

Ported from ``context_creator.ipynb`` cell 4. Offline, no tiktoken -- ~4 chars/token.
"""

from __future__ import annotations

import math
from typing import Any, Dict, List


def count_tokens(text: str) -> int:
    """Offline, deterministic approximation of a BPE tokenizer (~4 chars / token)."""
    if not text:
        return 0
    return math.ceil(len(text) / 4)


class Budget:
    def __init__(self, limit: int):
        self.limit = limit
        self.used = 0
        self.dropped: List[str] = []

    def can_fit(self, tokens: int) -> bool:
        return self.used + tokens <= self.limit

    def charge(self, tokens: int) -> None:
        """Mandatory content -- never dropped, always counted."""
        self.used += tokens

    def add(self, tokens: int, label: str) -> bool:
        if self.can_fit(tokens):
            self.used += tokens
            return True
        self.dropped.append(f"{label} -- {tokens} tok, over MAX_CONTEXT_TOKENS")
        return False

    def drop(self, label: str, reason: str) -> None:
        self.dropped.append(f"{label} -- {reason}")

    def as_dict(self) -> Dict[str, Any]:
        return {"limit": self.limit, "used": self.used, "dropped": list(self.dropped)}
