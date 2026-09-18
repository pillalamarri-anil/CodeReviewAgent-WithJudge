import pathlib

import pytest

from review_agent.config import Settings

FIXTURES = pathlib.Path(__file__).parent / "fixtures"
SAMPLE_JAVA = FIXTURES / "sample-java"
DIFFS = FIXTURES / "diffs"


@pytest.fixture
def sample_repo() -> str:
    return str(SAMPLE_JAVA)


@pytest.fixture
def diff():
    def _load(name: str) -> str:
        return (DIFFS / name).read_text(encoding="utf-8")

    return _load


@pytest.fixture
def settings() -> Settings:
    # _env_file=None -> ignore any real .env on the dev box; deterministic tests.
    return Settings(
        _env_file=None,
        llm_provider="mock",
        min_confidence=0.75,
        max_context_tokens=8000,
        max_critical=0,
        max_high=0,
        max_medium=5,
    )
