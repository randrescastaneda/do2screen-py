"""No-dropped-lines invariant over every fixture file.

Every non-blank, non-comment line in a parsed file must end up in exactly one
of two places: attributed to a variable, or recorded in ``unresolved_blocks``.
This module asserts that partition over every do file under ``tests/fixtures``,
plus the coverage definition.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from tests.invariant import assert_coverage_match, assert_no_dropped_lines

FIXTURES = Path(__file__).parent / "fixtures"

# All do files under tests/fixtures/ (including the ported golden fixtures) are
# subject to the no-dropped-lines invariant.
FIXTURE_FILES = sorted(FIXTURES.rglob("*.do"))

__all__ = ["FIXTURES", "FIXTURE_FILES"]


def test_fixture_corpus_is_not_empty():
    assert len(FIXTURE_FILES) >= 10


@pytest.mark.parametrize("fixture", FIXTURE_FILES, ids=lambda p: p.name)
def test_no_dropped_lines(fixture):
    assert_no_dropped_lines(fixture)


@pytest.mark.parametrize("fixture", FIXTURE_FILES, ids=lambda p: p.name)
def test_coverage_matches_direct_computation(fixture):
    assert_coverage_match(fixture)


@pytest.mark.parametrize(
    "name,reason",
    [
        ("unres_openbrace_code.do", "unterminated_structure"),
        ("unres_midline_comment.do", "unterminated_structure"),
    ],
)
def test_unterminated_with_attributed_proximity_stays_disjoint(name, reason):
    fixture = FIXTURES / name
    graph = assert_no_dropped_lines(fixture)
    reasons = {u.reason for u in graph.unresolved}
    assert reason in reasons, f"{name}: {reasons}"
    # AGENTS.md 3.1: executable lines belong to exactly one disposition.
    from tests.invariant import (
        attributed_lines_from_records,
        unresolved_lines_from_records,
    )

    attr = attributed_lines_from_records(graph)
    unres = unresolved_lines_from_records(graph)
    assert not (attr & unres), f"{name}: attributed also unresolved"