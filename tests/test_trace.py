"""Trace: ancestry, cycles, coverage, labels, and edge cases."""

from __future__ import annotations

import pytest

from do2screen.trace import trace_files
from tests.conftest import trace_text, write_do


def test_simple_lineage(tmp_path):
    text = "gen y = 2\ngen x = y + 1\n"
    result, path = trace_text(tmp_path, text, "x")
    assert result.variable == "x"
    assert [r.start_line for r in result.ranges] == [2]
    assert result.ancestors == ["y"]
    assert result.ranges[0].source == str(path)
    assert result.ranges[0].source_lines == ["gen x = y + 1"]
    chunk = result.provenance_chunk
    assert chunk is not None
    assert chunk.lineage_variables == ["x", "y"]
    assert [(item.range.start_line, item.effects[0].kind) for item in chunk.statements] == [
        (1, "created"),
        (2, "created"),
    ]
    assert "* [" in chunk.text
    assert "gen y = 2" in chunk.text
    assert "gen x = y + 1" in chunk.text
    assert chunk.standalone_execution == "not_assessed"


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
    assert result.provenance_chunk.lineage_variables == ["x"]
    assert [item.range.start_line for item in result.provenance_chunk.statements] == [2]


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
    assert result.provenance_chunk.lineage_variables == ["missing_var"]
    assert result.provenance_chunk.statements == []
    assert result.provenance_chunk.lineage_variables_without_ranges == ["missing_var"]


def test_labels_excluded_by_default(tmp_path):
    text = 'label variable x "hey"\ngen y = 2\n'
    result, _ = trace_text(tmp_path, text, "x")
    assert result.ranges == []


def test_labels_included_when_requested(tmp_path):
    text = 'label variable x "hey"\ngen y = 2\n'
    result, _ = trace_text(tmp_path, text, "x", include_labels=True)
    assert len(result.ranges) == 1
    assert result.ranges[0].start_line == 1
    assert [item.range.start_line for item in result.provenance_chunk.statements] == [1]


def test_labels_are_selected_in_provenance_only_when_requested(tmp_path):
    text = 'gen x = 1\nlabel variable x "label"\n'
    without_labels, _ = trace_text(tmp_path, text, "x")
    with_labels, _ = trace_text(tmp_path, text, "x", include_labels=True)
    assert [item.range.start_line for item in without_labels.provenance_chunk.statements] == [1]
    assert [item.range.start_line for item in with_labels.provenance_chunk.statements] == [1, 2]


def test_include_chain_attributes_child(tmp_path):
    write_do(tmp_path, "util.do", "gen base = 5\n")
    text = 'include "util.do"\ngen x = base + 1\n'
    result, _ = trace_text(tmp_path, text, "x")
    assert "base" in result.ancestors
    assert [r.start_line for r in result.ranges] == [2]
    assert len(result.sources) == 2
    assert result.sources[1].traversal_index == 1
    assert [item.range.start_line for item in result.provenance_chunk.statements] == [1, 2]
    assert [item.occurrence_sequence for item in result.provenance_chunk.statements] == [2, 1]


def test_legacy_repeated_include_keeps_current_nonreplay_behavior(tmp_path):
    write_do(tmp_path, "util.do", "gen base = 5\n")
    result, _ = trace_text(
        tmp_path,
        'include "util.do"\ngen x = base\ninclude "util.do"\nreplace x = base\n',
        "x",
    )
    assert [item.range.start_line for item in result.provenance_chunk.statements] == [1, 2, 4]
    assert sum("gen base" in item for item in result.provenance_chunk.text.split("\n\n")) == 1


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


def test_source_lines_preserve_crlf_and_bom_decoding(tmp_path):
    path = tmp_path / "physical.do"
    path.write_bytes(b"\xef\xbb\xbfgen x = 1\r\nreplace x = 2\r\n")
    result, _ = trace_text(tmp_path, "gen x = 1\nreplace x = 2\n", "x")
    # The helper above uses a separate file; exercise the public parser directly
    # for the physical CRLF/BOM representation.
    from do2screen.parser import Parser
    from do2screen.registry import RegistryAdapter
    from do2screen.trace import build_result
    from tests.mock_registry import MockStataRegistry

    graph = Parser(RegistryAdapter(module=MockStataRegistry())).parse_graph(str(path))
    physical = build_result(graph, "x", follow_parents=True)
    assert physical.ranges[0].source_lines == ["gen x = 1"]
    assert physical.ranges[1].source_lines == ["replace x = 2"]


def test_source_lines_are_present_on_unresolved_ranges(tmp_path):
    path = tmp_path / "unresolved.do"
    path.write_text("gen x = 1\nnot_a_command y\n", encoding="utf-8")
    from do2screen.parser import Parser
    from do2screen.registry import RegistryAdapter
    from do2screen.trace import build_result
    from tests.mock_registry import MockStataRegistry

    graph = Parser(RegistryAdapter(module=MockStataRegistry())).parse_graph(str(path))
    result = build_result(graph, "x", follow_parents=True)
    unresolved = next(block for block in result.unresolved_blocks if block.range.start_line == 2)
    assert unresolved.range.source_lines == ["not_a_command y"]


def test_source_lines_preserve_continuation_physical_range(tmp_path):
    path = tmp_path / "continuation.do"
    path.write_text("gen x = 1 + ///\n  2\n", encoding="utf-8")

    from do2screen.parser import Parser
    from do2screen.registry import RegistryAdapter
    from do2screen.trace import build_result
    from tests.mock_registry import MockStataRegistry

    graph = Parser(RegistryAdapter(module=MockStataRegistry())).parse_graph(str(path))
    result = build_result(graph, "x", follow_parents=True)
    assert result.ranges[0].start_line == 1
    assert result.ranges[0].end_line == 2
    assert result.ranges[0].source_lines == ["gen x = 1 + ///", "  2"]


def test_source_lines_preserve_semicolon_multiline_range(tmp_path):
    path = tmp_path / "delimiter.do"
    path.write_text(
        "#delimit ;\nreplace x = 1 +\n  2;\n#delimit cr\n",
        encoding="utf-8",
    )

    from do2screen.parser import Parser
    from do2screen.registry import RegistryAdapter
    from do2screen.trace import build_result
    from tests.mock_registry import MockStataRegistry

    graph = Parser(RegistryAdapter(module=MockStataRegistry())).parse_graph(str(path))
    result = build_result(graph, "x", follow_parents=True)
    modified = next(item for item in result.attributed_ranges if item.kind == "modified")
    assert modified.range.start_line == 2
    assert modified.range.end_line == 3
    assert modified.range.source_lines == ["replace x = 1 +", "  2;"]
    statement = next(
        item for item in result.provenance_chunk.statements if item.range.start_line == 2
    )
    assert statement.range.source_lines == ["replace x = 1 +", "  2;"]
    assert "2;" in result.provenance_chunk.text


def test_source_lines_preserve_replacement_characters(tmp_path, capsys):
    path = tmp_path / "replacement.do"
    path.write_bytes(b"gen x = 1\n\xffunknown y\n")
    from do2screen.parser import Parser
    from do2screen.registry import RegistryAdapter
    from do2screen.trace import build_result
    from tests.mock_registry import MockStataRegistry

    graph = Parser(RegistryAdapter(module=MockStataRegistry())).parse_graph(str(path))
    result = build_result(graph, "x", follow_parents=True)
    assert result.unresolved_blocks[0].range.source_lines == ["\ufffdunknown y"]
    assert "warning" in capsys.readouterr().err


def test_trace_files_rejects_empty_input():
    with pytest.raises(ValueError, match="at least one"):
        trace_files([], "x")
