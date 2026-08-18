"""Golden-file regression over the ported Stata fixtures."""

from __future__ import annotations

from pathlib import Path

import pytest

from tests.conftest import trace_text, write_do

GOLDEN_DIR = Path(__file__).parent / "fixtures" / "stata_golden"


def golden(tmp_path, name: str) -> Path:
    content = (GOLDEN_DIR / name).read_text(encoding="utf-8")
    return write_do(tmp_path, name, content)


@pytest.mark.parametrize(
    "name,variable,expected_lines,expected_ancestors",
    [
        ("golden_income.do", "income", [6, 7], ["wages", "transfers"]),
        ("golden_income.do", "wages", [4, 8], []),
        ("golden_income.do", "transfers", [5], []),
        (
            "golden_rename_label.do",
            "hhsize",
            [5, 6],
            ["household_size"],
        ),
        ("golden_rename_label.do", "household_size", [4], []),
    ],
)
def test_golden_trace(
    tmp_path,
    name,
    variable,
    expected_lines,
    expected_ancestors,
    registry,
):
    content = (GOLDEN_DIR / name).read_text(encoding="utf-8")
    result, _ = trace_text(tmp_path, content, variable)
    assert [r.start_line for r in result.ranges] == expected_lines
    assert result.ancestors == expected_ancestors


def test_golden_income_attribution_inventory(tmp_path, registry):
    content = (GOLDEN_DIR / "golden_income.do").read_text(encoding="utf-8")
    result, _ = trace_text(tmp_path, content, "income")
    kinds = {(a.kind, a.variable) for a in result.attributed_ranges}
    assert ("created", "wages") in kinds
    assert ("created", "transfers") in kinds
    assert ("created", "income") in kinds
    assert ("modified", "income") in kinds
    assert ("dropped", "wages") in kinds
    assert ("referenced", "wages") in kinds


def test_golden_label_excluded_by_default(tmp_path):
    content = (GOLDEN_DIR / "golden_rename_label.do").read_text(encoding="utf-8")
    result, _ = trace_text(tmp_path, content, "hhsize")
    labelled = [a for a in result.attributed_ranges if a.kind == "labelled"]
    assert len(labelled) == 1
    # label events stay in the audit inventory but not in the lifecycle slice
    assert [r.start_line for r in result.ranges] == [5, 6]