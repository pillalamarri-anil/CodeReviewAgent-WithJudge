from review_agent.context.diff_parser import (
    hunk_added_lines,
    hunk_new_line_span,
    parse_unified_diff,
)
from review_agent.context.languages import annotate_languages


def test_method_edit_hunk_line_numbers(diff):
    changes = annotate_languages(parse_unified_diff(diff("method_edit.diff")))
    assert len(changes) == 1
    c = changes[0]
    assert c.file == "src/main/java/com/example/service/OrderService.java"
    assert c.status == "modified"
    assert c.language == "java"

    (h,) = c.hunks
    assert (h.old_start, h.old_lines, h.new_start, h.new_lines) == (17, 3, 17, 8)

    added = hunk_added_lines(h)
    assert added[0] == (18, "        BigDecimal total = BigDecimal.ZERO;")
    assert added[-1] == (23, "        return total;")
    assert hunk_new_line_span(h) == (17, 24)


def test_added_file_status_and_span(diff):
    (c,) = parse_unified_diff(diff("added_file.diff"))
    assert c.status == "added"
    assert c.old_path is None
    (h,) = c.hunks
    assert h.new_start == 1 and h.new_lines == 34
    assert hunk_added_lines(h)[0] == (1, "package com.example.service;")


def test_repo_change_persistence_markers(diff):
    (c,) = parse_unified_diff(diff("repo_change.diff"))
    assert c.file.endswith("OrderRepository.java")
    (h,) = c.hunks
    assert (h.new_start, h.new_lines) == (15, 5)
    body = "\n".join(h.lines)
    assert "nativeQuery = true" in body
