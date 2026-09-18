"""LLM provider protocol + prompt loading.

One real provider is used live in the demo (``openai``); ``mock`` exists only for
tests and offline dev (PRD s6).
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Protocol

_PROMPT_DIR = Path(__file__).resolve().parent.parent / "prompts"


class LLMError(RuntimeError):
    """Provider call failed (network, auth, quota, timeout)."""


@dataclass
class Usage:
    """Running token count for one provider instance, across every ``complete()`` call
    (including repair retries -- PRD s6). Providers accumulate into this on each call so
    the pipeline can read a total after the per-file review loop."""

    prompt_tokens: int = 0
    completion_tokens: int = 0
    total_tokens: int = 0
    calls: int = 0

    def add(self, prompt_tokens: int, completion_tokens: int) -> None:
        self.prompt_tokens += prompt_tokens
        self.completion_tokens += completion_tokens
        self.total_tokens += prompt_tokens + completion_tokens
        self.calls += 1


class LLMProvider(Protocol):
    name: str
    usage: Usage

    def complete(self, system: str, user: str) -> str:
        """Return the model's raw text response (expected to be a JSON object)."""


_CATEGORY_PROMPTS = (
    "category_security.txt",
    "category_bug.txt",
    "category_performance.txt",
    "category_test_coverage.txt",
)


def load_prompt(name: str) -> str:
    return (_PROMPT_DIR / name).read_text(encoding="utf-8")


def system_prompt() -> str:
    """Assembled from one common-instructions file plus one file per review category
    (security, bug, performance, test coverage), so each category's checklist can be
    edited independently of the shared framing/output-format instructions."""
    checklists = "\n\n".join(load_prompt(name).strip() for name in _CATEGORY_PROMPTS)
    return load_prompt("common_review.txt").replace("__CATEGORY_CHECKLISTS__", checklists)


def user_prompt(*, context: str, target_file: str, pr_id, repo: str,
                target_branch: str, source_branch: str) -> str:
    return load_prompt("java_review.txt").format(
        context=context,
        target_file=target_file,
        pr_id=pr_id if pr_id is not None else "?",
        repo=repo or "?",
        target_branch=target_branch or "?",
        source_branch=source_branch or "?",
    )


def build_provider(settings):
    provider = (settings.llm_provider or "mock").lower()
    if provider == "mock":
        from .mock import MockProvider

        return MockProvider()
    if provider == "openai":
        from .openai_provider import OpenAIProvider

        return OpenAIProvider(settings)
    raise LLMError(f"unknown LLM_PROVIDER: {settings.llm_provider!r} (use 'openai' or 'mock')")


def build_judge_provider(settings):
    """The judge stage (``judge.contract``) runs on its own provider so it can use a
    different -- typically stronger -- model than the per-file reviewer (PRD: judge
    consolidates/correlates/validates the reviewer's findings)."""
    provider = (settings.judge_provider or "mock").lower()
    if provider == "mock":
        from .mock import MockProvider

        return MockProvider()
    if provider == "openai":
        from .openai_provider import OpenAIProvider

        return OpenAIProvider(settings, model=settings.judge_model,
                              max_tokens=settings.judge_max_tokens, name="openai-judge")
    raise LLMError(f"unknown JUDGE_PROVIDER: {settings.judge_provider!r} (use 'openai' or 'mock')")
