"""Environment-driven configuration (PRD s13).

Secrets come only from the environment / Jenkins / GitHub Actions credentials and are
never logged -- ``repr(Settings)`` scrubs them.
"""

from __future__ import annotations

from pathlib import Path
from typing import Optional, Tuple

from pydantic import Field, SecretStr
from pydantic_settings import BaseSettings, SettingsConfigDict

_SECRET_FIELDS = {"openai_api_key", "github_token"}

# This agent's own config/secrets live next to its source, not next to whatever repo
# it's told to review -- so ".env" alone (CWD-relative) silently finds nothing and
# falls back to every default (mock providers, no GitHub creds) when run from
# elsewhere. Load the agent's own .env by absolute path first, then let a CWD-local
# .env (if any) layer on top for a per-invocation override.
_AGENT_ENV_FILE = Path(__file__).resolve().parent.parent.parent / ".env"


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=(str(_AGENT_ENV_FILE), ".env"),
        env_file_encoding="utf-8",
        extra="ignore",
        case_sensitive=False,
    )

    # --- LLM provider ---------------------------------------------------
    llm_provider: str = "mock"
    openai_api_key: Optional[SecretStr] = None
    openai_model: Optional[str] = "gpt-4o"
    openai_base_url: Optional[str] = None
    llm_max_tokens: int = 4000
    llm_timeout_seconds: int = 90
    # gpt-5 / o1 / o3 / o4 spend part of their completion budget on hidden reasoning
    # tokens before any visible output; "low" keeps the judge's latency/cost down for
    # what is fundamentally a verification task, not open-ended reasoning.
    llm_reasoning_effort: str = "low"

    # --- Judge (consolidation / cross-file correlation / evidence check) ---
    # Runs as a second LLM pass, on a different (typically stronger) model, over the
    # validated findings from every changed file at once.
    judge_enabled: bool = True
    judge_provider: str = "mock"
    judge_model: Optional[str] = "gpt-5"
    # higher than llm_max_tokens: the judge sees every file's findings at once, and
    # reasoning-family models spend part of this budget on hidden reasoning tokens.
    judge_max_tokens: int = 8000

    # --- GitHub ------------------------------------------------------
    github_token: Optional[SecretStr] = None
    github_repository: Optional[str] = None  # "owner/repo"
    github_api_url: str = "https://api.github.com"

    # --- Review knobs ---------------------------------------------
    min_confidence: float = 0.75
    max_context_tokens: int = 8000

    # --- Context builder knobs (PRD s5 / context-prep PRD) ------
    max_knowledge_tokens: int = 3500
    max_code_tokens: int = 6000
    always_include_docs: Tuple[str, ...] = ("docs/ARCHITECTURE.md",)
    context_docs_glob: str = "docs/**/*.md"
    schema_doc: str = "docs/schema.md"
    rules_file: str = "review-rules.yaml"
    surrounding_lines: int = 40
    full_method_lines: int = 120
    full_file_max_lines: int = 400

    # --- Quality gate (PRD s7) --------------------------------
    max_critical: int = 0
    max_high: int = 0
    max_medium: int = 5

    # ------------------------------------------------------------------
    @property
    def github_owner_repo(self) -> Tuple[Optional[str], Optional[str]]:
        if not self.github_repository or "/" not in self.github_repository:
            return None, None
        owner, _, repo = self.github_repository.partition("/")
        return owner, repo

    def openai_key(self) -> Optional[str]:
        return self.openai_api_key.get_secret_value() if self.openai_api_key else None

    def gh_token(self) -> Optional[str]:
        return self.github_token.get_secret_value() if self.github_token else None

    def __repr__(self) -> str:  # never leak secrets into logs / tracebacks
        parts = []
        for name, value in self.__dict__.items():
            if name in _SECRET_FIELDS:
                parts.append(f"{name}={'***set***' if value else 'None'}")
            else:
                parts.append(f"{name}={value!r}")
        return f"Settings({', '.join(parts)})"

    __str__ = __repr__


def load_settings(**overrides) -> Settings:
    return Settings(**overrides)
