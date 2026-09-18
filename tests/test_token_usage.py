"""Token usage is tracked per LLM call and rolled up onto the report (PR-level total)."""

import json

from review_agent import pipeline as pipeline_mod
from review_agent.llm.mock import MockProvider
from review_agent.pipeline import RunInputs, run

from .test_pipeline_mock import REPO_FILE, _settings


def test_mock_provider_accumulates_usage_across_calls():
    p = MockProvider(raw=json.dumps({"summary": "ok", "findings": []}))
    p.complete("sys", "user one")
    p.complete("sys", "user two")

    assert p.usage.calls == 2
    assert p.usage.prompt_tokens > 0
    assert p.usage.completion_tokens > 0
    assert p.usage.total_tokens == p.usage.prompt_tokens + p.usage.completion_tokens


def test_run_reports_total_token_usage(monkeypatch, sample_repo, diff):
    monkeypatch.setattr(pipeline_mod, "build_provider",
                        lambda s: MockProvider(responses={}))

    report = run(_settings(), RunInputs(
        repo_path=sample_repo, base="main", head="feat/x",
        diff_text=diff("repo_change.diff"), publish=False,
    ))

    reviewed = [fr for fr in report.files_reviewed if fr.status == "ok"]
    assert report.token_usage.calls == len(reviewed) > 0
    assert report.token_usage.total_tokens > 0
    assert report.token_usage.total_tokens == (
        report.token_usage.prompt_tokens + report.token_usage.completion_tokens
    )
