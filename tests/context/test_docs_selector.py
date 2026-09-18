from review_agent.config import Settings
from review_agent.context.docs_selector import persistence_touching, select_docs
from review_agent.context.diff_parser import parse_unified_diff
from review_agent.context.languages import annotate_languages
from review_agent.context.repo_view import LocalRepoView

CFG = Settings(_env_file=None)


def _changes(diff, name):
    return annotate_languages(parse_unified_diff(diff(name)))


def test_schema_doc_included_iff_persistence_touching(sample_repo, diff):
    repo = LocalRepoView(sample_repo)

    repo_change = _changes(diff, "repo_change.diff")
    method_edit = _changes(diff, "method_edit.diff")

    assert persistence_touching(repo_change) is True
    assert persistence_touching(method_edit) is False

    d_repo = select_docs(repo, repo_change, CFG)
    d_svc = select_docs(repo, method_edit, CFG)

    assert d_repo["schema_triggered"] and d_repo["schema"]
    assert not d_svc["schema_triggered"] and d_svc["schema"] == []


def test_glob_doc_selected_only_on_applies_to_match(sample_repo, diff):
    repo = LocalRepoView(sample_repo)

    d_repo = select_docs(repo, _changes(diff, "repo_change.diff"), CFG)
    d_svc = select_docs(repo, _changes(diff, "method_edit.diff"), CFG)

    assert sorted(k.path for k in d_repo["glob"]) == ["docs/persistence.md"]
    assert d_svc["glob"] == []  # persistence.md applies_to does not match service/


def test_always_doc_always_present(sample_repo, diff):
    repo = LocalRepoView(sample_repo)
    d = select_docs(repo, _changes(diff, "method_edit.diff"), CFG)
    assert [k.path for k in d["always"]] == ["docs/ARCHITECTURE.md"]
