"""Tiny structured stream logger for the live demo (PRD s11 step 4).

Every stage prints one line to stderr so the Jenkins / Actions log reads as a
narrative: diff parsed -> N files -> context built -> LLM call -> M findings -> K
after validation -> published.
"""

from __future__ import annotations

import sys
import time

_START = time.monotonic()


def _elapsed() -> str:
    return f"{time.monotonic() - _START:6.1f}s"


def log(stage: str, message: str = "") -> None:
    line = f"[{_elapsed()}] {stage}"
    if message:
        line += f": {message}"
    print(line, file=sys.stderr, flush=True)


def step(message: str) -> None:
    log("STEP", message)


def warn(message: str) -> None:
    log("WARN", message)


def error(message: str) -> None:
    log("ERROR", message)
