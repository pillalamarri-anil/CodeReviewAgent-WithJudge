import json

from review_agent.config import Settings
from review_agent.context.builder import build_review_context
from review_agent.context.models import PRInfo
from review_agent.context.render import render, render_for_file
from review_agent.context.repo_view import LocalRepoView

CFG = Settings(_env_file=None)


def _pr():
    return PRInfo(id=7, title="Add findNewOrders query", description="native query",
                  source_branch="feat/new-orders", target_branch="main",
                  commit_messages=["Add findNewOrders query"])


def _build(sample_repo, diff_text):
    repo = LocalRepoView(sample_repo)
    return build_review_context(_pr(), diff_text, repo, CFG)


def test_render_is_byte_identical_across_builds(sample_repo, diff):
    d = diff("repo_change.diff")
    a = _build(sample_repo, d)
    b = _build(sample_repo, d)
    assert render(a) == render(b)
    assert json.dumps(a.to_dict(), sort_keys=True) == json.dumps(b.to_dict(), sort_keys=True)


def test_budget_never_exceeds_limit(sample_repo, diff):
    ctx = _build(sample_repo, diff("repo_change.diff"))
    assert ctx.budget["used"] <= ctx.budget["limit"]


def test_context_carries_rules_and_schema(sample_repo, diff):
    ctx = _build(sample_repo, diff("repo_change.diff"))
    assert any("BigDecimal" in r for r in ctx.rules)
    assert any(k.selector == "schema" for k in ctx.knowledge)
    text = render_for_file(ctx, "src/main/java/com/example/repository/OrderRepository.java")
    assert "REVIEW RULES" in text and "findNewOrders" in text


def test_tiny_budget_records_drops(sample_repo, diff):
    repo = LocalRepoView(sample_repo)
    tiny = Settings(_env_file=None, max_context_tokens=200)
    ctx = build_review_context(_pr(), diff("repo_change.diff"), repo, tiny)
    assert ctx.budget["dropped"]
    assert ctx.budget["used"] <= ctx.budget["limit"]
