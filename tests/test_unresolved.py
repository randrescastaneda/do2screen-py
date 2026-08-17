"""All seven unresolved-block categories are covered by fixtures."""

from __future__ import annotations

from pathlib import Path

import pytest

from tests.invariant import assert_no_dropped_lines

FIXTURES = Path(__file__).parent / "fixtures"

EXPECTATIONS = [
    ("unres_macro.do", "macro_or_loop"),
    ("unres_unknown.do", "unknown_command"),
    ("unres_effect.do", "unsupported_effect"),
    ("unres_syntax.do", "unsupported_syntax"),
    ("unres_include.do", "unresolved_include"),
    ("unres_attribution.do", "no_variable_attribution"),
    ("unres_unterminated.do", "unterminated_structure"),
]


@pytest.mark.parametrize(
    "name,reason",
    EXPECTATIONS,
    ids=[name for name, _ in EXPECTATIONS],
)
def test_unresolved_category_present(name, reason):
    fixture = FIXTURES / name
    graph = assert_no_dropped_lines(fixture)
    reasons = {u.reason for u in graph.unresolved}
    assert reason in reasons, f"{name}: expected {reason}, got {sorted(reasons)}"


def test_macro_or_loop_covers_whole_block():
    graph = assert_no_dropped_lines(FIXTURES / "unres_macro.do")
    macro = [u for u in graph.unresolved if u.reason == "macro_or_loop"]
    assert macro
    # The block spans the loop header through the closing brace.
    assert macro[0].range.start_line == 2
    assert macro[0].range.end_line == 5


def test_unresolved_include_has_context():
    graph = assert_no_dropped_lines(FIXTURES / "unres_include.do")
    blocks = [u for u in graph.unresolved if u.reason == "unresolved_include"]
    assert blocks
    assert blocks[0].context.get("reason") == "missing"
    assert blocks[0].context.get("target") == "does_not_exist.do"


def test_unterminated_structures_span_to_eof():
    graph = assert_no_dropped_lines(FIXTURES / "unres_unterminated.do")
    reasons = {u.reason for u in graph.unresolved}
    assert "unterminated_structure" in reasons


def test_no_variable_attribution_covers_drop_all_and_directives():
    graph = assert_no_dropped_lines(FIXTURES / "unres_attribution.do")
    nva = [u for u in graph.unresolved if u.reason == "no_variable_attribution"]
    assert len(nva) >= 2
    directives = [u for u in nva if u.context.get("directive") == ";"]
    assert directives