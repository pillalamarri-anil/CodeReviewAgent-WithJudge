from review_agent.config import Settings
from review_agent.context.java_extractor import extract_java, java_index, java_signatures
from review_agent.context.repo_view import LocalRepoView

CFG = Settings(_env_file=None)
SVC = "src/main/java/com/example/service/OrderService.java"


def test_enclosing_method_extracted_no_unrelated_bodies(sample_repo):
    repo = LocalRepoView(sample_repo)
    src = repo.read(SVC)
    jindex = java_index(repo)

    enclosing, referenced, tests = extract_java(SVC, src, [18, 21], repo, jindex, CFG)

    syms = {s[2] for s in enclosing}
    assert "OrderService.totalForCustomer" in syms
    joined = "\n".join(s[3] for s in enclosing)
    assert "BigDecimal totalForCustomer" in joined
    # the other method's body must not be pulled in
    assert "placeOrder" not in joined


def test_referenced_types_are_signatures_only(sample_repo):
    repo = LocalRepoView(sample_repo)
    src = repo.read(SVC)
    jindex = java_index(repo)

    # line 11 names the OrderRepository type; line 20 names Order
    _, referenced, _ = extract_java(SVC, src, [11, 20], repo, jindex, CFG)
    ref_syms = {s[2] for s in referenced}
    assert "OrderRepository" in ref_syms

    body = next(s[3] for s in referenced if s[2] == "OrderRepository")
    assert "interface OrderRepository" in body
    assert "findById" in body
    # signature only -- no method body statements
    assert "orElseThrow" not in body
    assert "BigDecimal.ZERO" not in body


def test_java_signatures_drops_bodies(sample_repo):
    repo = LocalRepoView(sample_repo)
    sig = java_signatures(repo.read(SVC))
    assert "class OrderService" in sig
    assert "totalForCustomer" in sig
    assert "BigDecimal.ZERO" not in sig
