"""Trace: ancestry, cycles, coverage, labels, and edge cases."""

from __future__ import annotations

from tests.conftest import trace_text, write_do


def test_simple_lineage(tmp_path):
    text = "gen y = 2\ngen x = y + 1\n"
    result, path = trace_text(tmp_path, text, "x")
    assert result.variable == "x"
    assert [r.start_line for r in result.ranges] == [2]
    assert result.ancestors == ["y"]
    assert result.ranges[0].source == str(path)


def test_recursive_ancestors(tmp_path):
    text = (
        "gen a = 1\n"
        "gen b = a + 1\n"
        "gen c = b + 1\n"
        "gen x = c + 1\n"
    )
    result, _ = trace_text(tmp_path, text, "x")
    assert "a" in result.ancestors
    assert "b" in result.ancestors
    assert "c" in result.ancestors
    # depth-first first-reference order: c, b, a
    assert result.ancestors[:3] == ["c", "b", "a"]


def test_shared_parents_dedup_ancestors(tmp_path):
    text = (
        "gen base = 1\n"
        "gen a = base + 1\n"
        "gen b = base + 2\n"
        "gen x = a + b\n"
    )
    result, _ = trace_text(tmp_path, text, "x")
    assert result.ancestors.count("base") == 1
    assert result.ancestors[0] == "a"
    assert "base" in result.ancestors


def test_cycle_terminates(tmp_path):
    text = (
        "gen a = b + 1\n"
        "gen b = a + 1\n"
        "gen x = a + 1\n"
    )
    result, _ = trace_text(tmp_path, text, "x")
    # terminates without infinite recursion; each variable present once
    assert result.ancestors[:2] == ["a", "b"]
    assert len(result.ancestors) == 2


def test_follow_parents_false(tmp_path):
    text = "gen y = 2\ngen x = y + 1\n"
    result, _ = trace_text(tmp_path, text, "x", follow_parents=False)
    assert result.ancestors == []
    assert [r.start_line for r in result.ranges] == [2]


def test_coverage_full(tmp_path):
    text = "gen x = 1\n"
    result, _ = trace_text(tmp_path, text, "x")
    assert result.coverage == 1.0


def test_coverage_with_unresolved(tmp_path):
    text = "gen x = 1\nmyado foo\n"
    result, _ = trace_text(tmp_path, text, "x")
    # 1 of 2 executable lines is attributed.
    assert abs(result.coverage - 0.5) < 1e-9


def test_zero_executable_lines_coverage_sentinel(tmp_path):
    text = "* only a comment\n"
    result, _ = trace_text(tmp_path, text, "anything")
    assert result.coverage == 1.0


def test_target_not_found(tmp_path):
    text = "gen y = 2\n"
    result, _ = trace_text(tmp_path, text, "missing_var")
    assert result.ranges == []
    assert result.ancestors == []
    # the audit inventory and unresolved blocks still reflect the file
    assert result.attributed_ranges
    assert result.coverage == 1.0


def test_labels_excluded_by_default(tmp_path):
    text = 'label variable x "hey"\ngen y = 2\n'
    result, _ = trace_text(tmp_path, text, "x")
    assert result.ranges == []


def test_labels_included_when_requested(tmp_path):
    text = 'label variable x "hey"\ngen y = 2\n'
    result, _ = trace_text(tmp_path, text, "x", include_labels=True)
    assert len(result.ranges) == 1
    assert result.ranges[0].start_line == 1


def test_include_chain_attributes_child(tmp_path):
    write_do(tmp_path, "util.do", "gen base = 5\n")
    text = 'include "util.do"\ngen x = base + 1\n'
    result, _ = trace_text(tmp_path, text, "x")
    assert "base" in result.ancestors
    assert [r.start_line for r in result.ranges] == [2]
    assert len(result.sources) == 2
    assert result.sources[1].traversal_index == 1


def test_deterministic_output(tmp_path):
    text = "gen y = 2\ngen x = y + 1\n"
    r1, _ = trace_text(tmp_path, text, "x")
    r2, _ = trace_text(tmp_path, text, "x")
    assert r1.model_dump_json() == r2.model_dump_json()


def test_deep_chain_does_not_overflow_stack(tmp_path):
    # A long sequential dependency chain must terminate without RecursionError.
    lines = ["gen v0 = 1"]
    for i in range(1, 1500):
        lines.append(f"gen v{i} = v{i - 1} + 1")
    text = "\n".join(lines) + "\n"
    result, _ = trace_text(tmp_path, text, "v1499")
    assert result.ancestors[0] == "v1498"
    assert "v0" in result.ancestors
    assert len(result.ancestors) == 1499


def test_include_coverage_is_source_aware(tmp_path):
    # Coverage is keyed by (source, line): an attributed child line at line 1
    # must not mask an unattributed root line at line 1.
    write_do(tmp_path, "lib.do", "gen bonus = 100\nreplace bonus = bonus * 2\n")
    result, _ = trace_text(
        tmp_path, 'include "lib.do"\ngen income = bonus + 1\n', "income"
    )
    # executable pairs: (root,1),(root,2),(lib,1),(lib,2) = 4
    # covered:          (root,2),(lib,1),(lib,2)              = 3
    assert abs(result.coverage - 0.75) < 1e-9
