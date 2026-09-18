"""OpenAI provider -- the real LLM used in the live demo (PRD s6, s13).

Reasoning-family models (``gpt-5``, ``o1``, ``o3``, ``o4``, ...) use a different chat
completions contract than ``gpt-4o``: they reject ``max_tokens`` (must be
``max_completion_tokens``), reject a non-default ``temperature``, and spend part of
the completion budget on hidden reasoning tokens before any visible output -- so they
need ``reasoning_effort`` and a larger token budget. ``max_completion_tokens`` is
accepted by both families, so it is used unconditionally; ``temperature`` /
``reasoning_effort`` are chosen per family.
"""

from __future__ import annotations

from .base import LLMError, Usage

_REASONING_MODEL_PREFIXES = ("gpt-5", "o1", "o3", "o4")


def _is_reasoning_model(model: str) -> bool:
    return model.lower().startswith(_REASONING_MODEL_PREFIXES)


class OpenAIProvider:
    def __init__(self, settings, *, model: str = None, max_tokens: int = None, name: str = "openai"):
        model = model or settings.openai_model
        missing = [
            k for k, v in {
                "OPENAI_API_KEY": settings.openai_key(),
                "OPENAI_MODEL": model,
            }.items() if not v
        ]
        if missing:
            raise LLMError(f"openai provider missing config: {', '.join(missing)}")

        try:
            from openai import OpenAI
        except ImportError as e:  # pragma: no cover
            raise LLMError("the 'openai' package is required for LLM_PROVIDER=openai") from e

        self.name = name
        self._model = model
        self._max_tokens = max_tokens or settings.llm_max_tokens
        self._reasoning_effort = settings.llm_reasoning_effort
        self.usage = Usage()
        self._client = OpenAI(
            api_key=settings.openai_key(),
            base_url=settings.openai_base_url or None,
            timeout=settings.llm_timeout_seconds,
            max_retries=2,
        )

    def complete(self, system: str, user: str) -> str:
        kwargs = dict(
            model=self._model,
            max_completion_tokens=self._max_tokens,
            response_format={"type": "json_object"},
            messages=[
                {"role": "system", "content": system},
                {"role": "user", "content": user},
            ],
        )
        if _is_reasoning_model(self._model):
            kwargs["reasoning_effort"] = self._reasoning_effort
        else:
            kwargs["temperature"] = 0

        try:
            resp = self._client.chat.completions.create(**kwargs)
        except Exception as e:  # openai raises many subclasses; treat all as call failure
            raise LLMError(f"OpenAI call failed: {e}") from e

        if resp.usage is not None:
            self.usage.add(resp.usage.prompt_tokens, resp.usage.completion_tokens)

        choice = (resp.choices or [None])[0]
        content = getattr(getattr(choice, "message", None), "content", None)
        if not content:
            raise LLMError("OpenAI returned an empty response")
        return content
