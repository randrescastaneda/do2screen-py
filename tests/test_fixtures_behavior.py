"""Behaviour assertions over the fixture corpus.

Guards against silent regressions that the line-partition invariant alone would
miss: string/factor/qualifier exclusion, abbreviation handling, drops,
renames, delimiters, continuations, and unresolved categories.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from tests.conftest import trace_text

FIXTURES = Path(__file__).parent / "fixtures"

# (fixture, variable, expected lifecycle start-lines, expected ancestors / [] )
EXPECTATIONS = [
    ("sample.do", "income", [4], ["wages", "transfers"]),
    ("sample.do", "total_income", [5, 6], ["income", "wages", "transfers"]),
    ("lineage.do", "primary", [4, 5], ["adult", "person"]),
    ("lineage.do", "adult", [3], ["person"]),
    ("shared.do", "out", [5], ["child_a", "base", "child_b"]),
    ("cycle.do", "c", [4], ["a", "b"]),
    ("cycle.do", "a", [2], ["b"]),
    ("abbrev.do", "b", [3, 4], ["a"]),
    ("labels.do", "income", [3], []),
    ("labels.do", "other", [5], ["income"]),
    ("rename.do", "new_name", [4], ["old_name"]),
    ("genopt.do", "avg_wage", [3], ["groupmean"]),
    ("genopt.do", "groupmean", [4], []),
    ("drops.do", "dropme", [3, 5], []),
    ("drops.do", "also_drop", [4, 5], []),
    ("prefixes.do", "rank", [3, 5], []),
    ("comments.do", "q", [3], []),
    ("comments.do", "r", [7], ["q"]),
    ("comments.do", "s", [8], ["r", "q"]),
    ("continuation.do", "base", [2, 4], []),
    ("continuation.do", "out", [6], ["base"]),
    ("delimit.do", "d2", [4, 5], []),
    ("delimit.do", "d3", [7, 9], []),
    ("delimit.do", "d4", [11], ["d3"]),
    ("factors.do", "age", [2, 6], []),
    ("factors.do", "rate", [8, 9], ["wi", "weight"]),
    ("factors.do", "factorsum", [11], ["age", "region"]),
]


@pytest.mark.parametrize(
    "name,variable,expected_lines,expected_ancestors",
    EXPECTATIONS,
    ids=[f"{n}:{v}" for n, v, _, _ in EXPECTATIONS],
)
def test_fixture_behaviour(tmp_path, name, variable, expected_lines, expected_ancestors):
    content = (FIXTURES / name).read_text(encoding="utf-8")
    result, _ = trace_text(tmp_path, content, variable)
    assert [r.start_line for r in result.ranges] == expected_lines, (
        f"{name}:{variable} lines"
    )
    assert result.ancestors == expected_ancestors, (
        f"{name}:{variable} ancestors"
    )


def test_strings_fixture_ignores_names_inside_strings(tmp_path):
    content = (FIXTURES / "strings.do").read_text(encoding="utf-8")
    result, _ = trace_text(tmp_path, content, "out")
    variables = {a.variable for a in result.attributed_ranges}
    # "wages", "income", "incl" etc. appear only inside string literals.
    assert "wages" not in variables
    assert "transfers" not in variables
    assert result.ancestors == ["inc"]
    assert [r.start_line for r in result.ranges] == [6]


def test_factor_qualifier_exclusions_do_not_leak(tmp_path):
    content = (FIXTURES / "factors.do").read_text(encoding="utf-8")
    result, _ = trace_text(tmp_path, content, "adj")
    # The `in` qualifier and subscripts exclude the literal range tokens.
    assert result.ancestors == ["age"]
    # age is not modified by the replace guarded by `if region == 1`'s RHS.
    result_age, _ = trace_text(tmp_path, content, "age")
    assert [r.start_line for r in result_age.ranges] == [2, 6]


def test_unresolved_fixture_reasons(tmp_path):
    expectations = {
        "unres_macro.do": "macro_or_loop",
        "unres_unknown.do": "unknown_command",
        "unres_effect.do": "unsupported_effect",
        "unres_syntax.do": "unsupported_syntax",
        "unres_include.do": "unresolved_include",
        "unres_attribution.do": "no_variable_attribution",
        "unres_unterminated.do": "unterminated_structure",
    }
    for name, reason in expectations.items():
        content = (FIXTURES / name).read_text(encoding="utf-8")
        result, _ = trace_text(tmp_path, content, "anything")
        reasons = {u.reason for u in result.unresolved_blocks}
        assert reason in reasons, f"{name}: {reason} not produced ({reasons})"