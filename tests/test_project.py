"""Project-wide tracing, occurrence replay, and context-qualified lineage."""

from __future__ import annotations

import errno
import json

from do2screen.ingest import directory_spec, files_spec, manifest_spec
from do2screen.parser import Parser
from do2screen.project import (
    assert_project_records_complete,
    build_project_graph,
    trace_project,
)
from do2screen.provenance import render_markdown
from do2screen.registry import RegistryAdapter
from tests.mock_registry import MockStataRegistry


def write_source(tmp_path, name: str, text: str):
    path = tmp_path / name
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")
    return path


def project_trace(spec, variable: str, **kwargs):
    return trace_project(
        spec,
        variable,
        registry=RegistryAdapter(module=MockStataRegistry()),
        **kwargs,
    )


def test_ordered_files_merge_lifecycle_and_ancestors(tmp_path):
    first = write_source(tmp_path, "01_clean.do", "gen base = 1\n")
    second = write_source(tmp_path, "02_build.do", "gen x = base + 1\nreplace x = x + 2\n")

    result = project_trace(files_spec([first, second]), "x")

    assert result.input_mode == "files"
    assert result.project_files == [str(first.resolve()), str(second.resolve())]
    assert [range_.start_line for range_ in result.ranges] == [1, 2]
    assert [range_.source for range_ in result.ranges] == [str(second.resolve())] * 2
    assert result.ancestors == ["base"]
    assert result.ranges[0].source_lines == ["gen x = base + 1"]
    assert result.provenance_chunk.ordering == "execution"
    assert [item.range.start_line for item in result.provenance_chunk.statements] == [1, 1, 2]
    assert [item.range.source for item in result.provenance_chunk.statements] == [
        str(first.resolve()),
        str(second.resolve()),
        str(second.resolve()),
    ]
    project = build_project_graph(
        files_spec([first, second]),
        registry=RegistryAdapter(module=MockStataRegistry()),
    )
    assert_project_records_complete(project)


def test_include_occurrences_are_replayed_at_call_sites_and_cached(tmp_path, monkeypatch):
    child = write_source(tmp_path, "lib.do", "gen base = 1\n")
    root = write_source(
        tmp_path,
        "main.do",
        'gen before = 0\ninclude "lib.do"\n'
        'gen x = base + before\ninclude "lib.do"\n'
        "replace x = base\n",
    )
    calls = []
    original = Parser.parse_file

    def counted(self, path):
        calls.append(str(path))
        return original(self, path)

    monkeypatch.setattr(Parser, "parse_file", counted)
    result = project_trace(files_spec([root]), "x")

    assert calls.count(str(root.resolve())) == 1
    assert calls.count(str(child.resolve())) == 1
    assert [range_.start_line for range_ in result.ranges] == [3, 5]
    assert result.ancestors == ["base", "before"]
    assert len(result.sources) == 2
    base_statements = [
        item
        for item in result.provenance_chunk.statements
        if item.effects[0].variable == "base"
    ]
    assert [item.occurrence_sequence for item in base_statements] == [2, 3]
    assert [item.range.start_line for item in result.provenance_chunk.statements] == [1, 1, 3, 1, 5]
    project = build_project_graph(
        files_spec([root]),
        registry=RegistryAdapter(module=MockStataRegistry()),
    )
    assert_project_records_complete(project)


def test_include_occurrence_stream_distinguishes_repeat_from_recursion(tmp_path):
    child = write_source(tmp_path, "lib.do", "gen base = 1\n")
    root = write_source(
        tmp_path,
        "main.do",
        'include "lib.do"\ninclude "lib.do"\n',
    )
    project = build_project_graph(
        files_spec([root]),
        registry=RegistryAdapter(module=MockStataRegistry()),
    )
    child_occurrences = [
        occurrence
        for occurrence in project.occurrences
        if occurrence.source == str(child.resolve())
    ]
    assert len(child_occurrences) == 2
    assert child_occurrences[0].caller_range.start_line == 1
    assert child_occurrences[1].caller_range.start_line == 2
    assert not any(
        block.context.get("reason") == "cycle"
        for block in project.unresolved
    )


def test_same_line_include_calls_keep_each_outcome(tmp_path):
    write_source(tmp_path, "real.do", "gen real = 1\n")
    root = write_source(
        tmp_path,
        "main.do",
        '#delimit ; include "real.do"; include "missing.do"; #delimit cr\n',
    )
    project = build_project_graph(
        files_spec([root]),
        registry=RegistryAdapter(module=MockStataRegistry()),
    )
    blocks = [
        block
        for block in project.unresolved
        if block.range.source == str(root.resolve())
        and block.range.start_line == 1
        and "include_calls" in block.context
    ]
    calls = [
        item
        for block in blocks
        for item in json.loads(block.context["include_calls"])
    ]
    assert {item["target"] for item in calls} == {"real.do", "missing.do"}
    assert {item["reason"] for item in calls} == {"resolved", "missing"}


def test_recursive_include_is_terminal_and_does_not_replay_child(tmp_path):
    first = write_source(tmp_path, "a.do", 'include "b.do"\ngen a = 1\n')
    second = write_source(tmp_path, "b.do", 'include "a.do"\ngen b = 1\n')
    project = build_project_graph(
        files_spec([first]),
        registry=RegistryAdapter(module=MockStataRegistry()),
    )
    assert len(project.occurrences) == 2
    assert any(
        block.context.get("reason") == "cycle"
        for block in project.unresolved
    )
    assert str(second.resolve()) in project.project_files


def test_repeated_explicit_root_occurrences_reuse_one_physical_parse(tmp_path, monkeypatch):
    root = write_source(tmp_path, "root.do", "gen x = 1\n")
    calls = []
    original = Parser.parse_file

    def counted(self, path):
        calls.append(str(path))
        return original(self, path)

    monkeypatch.setattr(Parser, "parse_file", counted)
    result = project_trace(files_spec([root, root]), "x")

    assert calls == [str(root.resolve())]
    assert len(result.ranges) == 2
    assert result.project_files == [str(root.resolve())]


def test_directory_include_outside_root_is_not_traversed(tmp_path):
    outside = tmp_path.parent / "outside_project.do"
    write_source(tmp_path.parent, outside.name, "gen secret = 1\n")
    write_source(tmp_path, "main.do", f'include "../{outside.name}"\n')

    result = project_trace(directory_spec(tmp_path), "secret")

    assert result.sources == [result.sources[0]] if result.sources else []
    assert str(outside.resolve()) not in result.project_files
    assert any(
        block.reason == "unresolved_include"
        and block.context.get("reason") == "outside_project"
        for block in result.unresolved_blocks
    )


def test_project_graph_records_real_source_lines_for_every_terminal_range(tmp_path):
    root = write_source(
        tmp_path,
        "main.do",
        "* comment\ngen x = 1\nunknown_command x\n",
    )
    project = build_project_graph(
        files_spec([root]),
        registry=RegistryAdapter(module=MockStataRegistry()),
    )
    assert_project_records_complete(project)
    expected = {
        2: "gen x = 1",
        3: "unknown_command x",
    }
    for attribution in project.attributions:
        line_range = attribution.range
        assert len(line_range.source_lines) == line_range.end_line - line_range.start_line + 1
        assert line_range.source_lines == [
            expected[line]
            for line in range(line_range.start_line, line_range.end_line + 1)
        ]
    for block in project.unresolved:
        line_range = block.range
        assert len(line_range.source_lines) == line_range.end_line - line_range.start_line + 1
        assert line_range.source_lines == [
            "* comment",
            "gen x = 1",
            "unknown_command x",
        ][line_range.start_line - 1 : line_range.end_line]


def test_unordered_reference_after_drop_is_reported(tmp_path):
    write_source(
        tmp_path,
        "drop_then_use.do",
        "gen base = 1\ndrop base\ngen x = base + 1\n",
    )

    result = project_trace(directory_spec(tmp_path), "x")

    assert result.ancestors == []
    assert any(
        diagnostic.code == "unbound_reference"
        and diagnostic.variable == "base"
        for diagnostic in result.project_diagnostics
    )


def test_directory_include_outside_missing_path_is_reported_as_containment(tmp_path):
    root = write_source(tmp_path, "main.do", 'include "../does_not_exist.do"\n')

    result = project_trace(directory_spec(tmp_path), "x")

    assert str(root.resolve()) in result.project_files
    assert any(
        block.reason == "unresolved_include"
        and block.context.get("reason") == "outside_project"
        for block in result.unresolved_blocks
    )


def test_unordered_directory_reports_cross_file_reference_without_ancestor(tmp_path):
    creator = write_source(tmp_path, "a.do", "gen base = 1\n")
    consumer = write_source(tmp_path, "b.do", "gen x = base + 1\n")

    result = project_trace(directory_spec(tmp_path), "x")

    assert result.ranges
    assert result.ancestors == []
    diagnostics = [
        diagnostic
        for diagnostic in result.project_diagnostics
        if diagnostic.code == "cross_file_unordered"
    ]
    assert diagnostics
    assert diagnostics[0].variable == "base"
    assert str(creator.resolve()) in diagnostics[0].candidate_sources
    assert diagnostics[0].source == str(consumer.resolve())
    assert result.provenance_chunk.ordering == "per_source"
    assert result.provenance_chunk.lineage_variables == ["x"]
    assert result.provenance_chunk.lineage_variables_without_ranges == []


def test_unordered_directory_chunk_includes_explicit_warning(tmp_path):
    write_source(tmp_path, "a.do", "gen x = 1\n")
    result = project_trace(directory_spec(tmp_path), "x")

    markdown = render_markdown(result)
    assert result.provenance_chunk.ordering == "per_source"
    assert "Warning: no global execution sequence is known" in markdown


def test_unordered_directory_retains_within_source_dependency(tmp_path):
    source = write_source(
        tmp_path,
        "a.do",
        "gen base = 1\ngen x = base + 1\n",
    )
    write_source(tmp_path, "b.do", "gen base = 2\n")

    result = project_trace(directory_spec(tmp_path), "x")

    assert result.ancestors == ["base"]
    assert not any(
        diagnostic.code == "cross_file_unordered"
        and diagnostic.source == str(source.resolve())
        and diagnostic.variable == "base"
        and diagnostic.context.get("referencing_source") == str(source.resolve())
        and diagnostic.range is not None
        and diagnostic.range.start_line == 2
        for diagnostic in result.project_diagnostics
    )


def test_unordered_include_chain_keeps_declared_include_order(tmp_path):
    child = write_source(tmp_path, "lib.do", "gen base = 1\n")
    root = write_source(tmp_path, "main.do", 'include "lib.do"\ngen x = base + 1\n')

    result = project_trace(files_spec([root]), "x")

    assert result.ancestors == ["base"]
    assert not any(
        diagnostic.code == "cross_file_unordered"
        for diagnostic in result.project_diagnostics
    )
    assert str(child.resolve()) in result.project_files


def test_ordered_redefinition_binds_to_latest_active_context(tmp_path):
    first = write_source(tmp_path, "a.do", "gen income = 1\n")
    second = write_source(tmp_path, "b.do", "gen income = 2\n")
    third = write_source(tmp_path, "c.do", "gen x = income + 1\n")

    result = project_trace(files_spec([first, second, third]), "x")

    assert result.ancestors == ["income"]
    income = next(
        identity
        for identity in result.variable_identities
        if identity.variable == "income"
    )
    assert [context.source for context in income.contexts] == [
        str(first.resolve()),
        str(second.resolve()),
    ]


def test_ordered_redefinition_uses_latest_context_parents(tmp_path):
    first = write_source(tmp_path, "a.do", "gen old_parent = 1\ngen a = old_parent\n")
    second = write_source(tmp_path, "b.do", "gen new_parent = 2\ngen a = new_parent\n")
    third = write_source(tmp_path, "c.do", "gen x = a\n")

    result = project_trace(files_spec([first, second, third]), "x")

    assert result.ancestors == ["a", "new_parent"]
    selected = [
        (item.range.source, item.range.start_line)
        for item in result.provenance_chunk.statements
    ]
    assert selected == [
        (str(second.resolve()), 1),
        (str(second.resolve()), 2),
        (str(third.resolve()), 1),
    ]
    assert str(first.resolve()) not in result.provenance_chunk.text
    assert "old_parent" not in result.provenance_chunk.text


def test_project_target_without_creation_still_has_lifecycle_statement(tmp_path):
    source = write_source(tmp_path, "modify.do", "replace external = 1\n")
    result = project_trace(files_spec([source]), "external")
    assert result.ranges
    assert result.provenance_chunk.lineage_variables == ["external"]
    assert [item.range.start_line for item in result.provenance_chunk.statements] == [1]


def test_project_external_ancestor_without_lifecycle_range_is_explicit(tmp_path):
    source = write_source(tmp_path, "external.do", "gen x = external_input + 1\n")
    result = project_trace(files_spec([source]), "x")
    assert result.ancestors == ["external_input"]
    assert result.provenance_chunk.lineage_variables_without_ranges == ["external_input"]
    assert [item.range.start_line for item in result.provenance_chunk.statements] == [1]


def test_ordered_rename_chain_keeps_generic_parent_edges(tmp_path):
    first = write_source(tmp_path, "a.do", "gen base = 1\ngen old = base\n")
    second = write_source(tmp_path, "b.do", "rename old new\n")
    third = write_source(tmp_path, "c.do", "gen x = new\n")

    result = project_trace(files_spec([first, second, third]), "x")

    assert result.ancestors == ["new", "old", "base"]


def test_unreadable_include_is_cached_and_keeps_os_error_fact(tmp_path, monkeypatch):
    root = write_source(
        tmp_path,
        "main.do",
        'include "child.do"\ninclude "child.do"\n',
    )
    child = write_source(tmp_path, "child.do", "gen x = 1\n")
    calls: list[str] = []
    original = Parser.parse_file

    def failing_child(self, path):
        calls.append(str(path))
        if str(path) == str(child.resolve()):
            raise PermissionError(errno.EACCES, "permission denied", str(path))
        return original(self, path)

    monkeypatch.setattr(Parser, "parse_file", failing_child)
    result = project_trace(files_spec([root]), "x")

    assert calls.count(str(child.resolve())) == 1
    include_blocks = [
        block
        for block in result.unresolved_blocks
        if block.reason == "unresolved_include"
    ]
    assert len(include_blocks) == 2
    assert all(block.context.get("reason") == "unreadable" for block in include_blocks)
    assert all("permission denied" in block.context.get("error", "") for block in include_blocks)


def test_ordered_reference_before_and_after_drop_is_diagnostic(tmp_path):
    first = write_source(
        tmp_path,
        "first.do",
        "gen a = 1\ngen before = a\ndrop a\ngen after = a\n",
    )
    result = project_trace(files_spec([first]), "after")
    assert result.ancestors == []
    assert any(
        diagnostic.code == "unbound_reference"
        and diagnostic.variable == "a"
        for diagnostic in result.project_diagnostics
    )


def test_project_identity_carries_include_caller_provenance(tmp_path):
    child = write_source(tmp_path, "lib.do", "gen base = 1\n")
    root = write_source(tmp_path, "main.do", 'include "lib.do"\n')
    result = project_trace(files_spec([root]), "base")
    identity = next(item for item in result.variable_identities if item.variable == "base")
    context = identity.contexts[0]
    assert context.source == str(child.resolve())
    assert context.caller_source == str(root.resolve())
    assert context.caller_range.start_line == 1


def test_unordered_duplicate_definition_is_reported_without_reference(tmp_path):
    first = write_source(tmp_path, "a.do", "gen income = 1\n")
    second = write_source(tmp_path, "b.do", "gen income = 2\n")

    result = project_trace(directory_spec(tmp_path), "income")

    duplicate = [
        diagnostic
        for diagnostic in result.project_diagnostics
        if diagnostic.context.get("kind") == "duplicate_definition"
    ]
    assert duplicate
    assert any(str(first.resolve()) in diagnostic.candidate_sources for diagnostic in duplicate)
    assert any(str(second.resolve()) in diagnostic.candidate_sources for diagnostic in duplicate)


def test_manifest_missing_file_is_nonterminal_and_existing_file_is_traced(tmp_path):
    existing = write_source(tmp_path, "exists.do", "gen x = 1\n")
    manifest = tmp_path / "manifest.json"
    manifest.write_text(
        json.dumps({"version": 1, "files": ["exists.do", "missing.do"]}),
        encoding="utf-8",
    )

    result = project_trace(manifest_spec(manifest), "x")

    assert result.ranges[0].source == str(existing.resolve())
    assert result.project_diagnostics[0].code == "unresolved_manifest_file"
    assert result.project_diagnostics[0].manifest_path == str(manifest.resolve())


def test_ordered_source_provenance_keeps_first_requested_path_on_partial_failure(
    tmp_path, monkeypatch
):
    first = write_source(tmp_path, "first.do", "gen ignored = 1\n")
    second = write_source(tmp_path, "second.do", "gen x = 1\n")
    original = Parser.parse_file

    def failing_first(self, path):
        if str(path) == str(first.resolve()):
            raise PermissionError(errno.EACCES, "permission denied", str(path))
        return original(self, path)

    monkeypatch.setattr(Parser, "parse_file", failing_first)
    result = project_trace(files_spec([first, second]), "x")

    assert result.source.path == str(first.resolve())
    assert result.source.line_count == 0
    assert result.sources[0].path == str(second.resolve())
    assert any(
        diagnostic.code == "unreadable_root"
        for diagnostic in result.project_diagnostics
    )


def test_cross_file_cycle_terminates(tmp_path):
    first = write_source(tmp_path, "a.do", "gen y = 1\ngen x = y + 1\nreplace y = x\n")

    result = project_trace(files_spec([first]), "x")

    assert result.ancestors == ["y"]
    assert result.ancestors == ["y"]


def test_empty_directory_has_coverage_sentinel_and_diagnostic(tmp_path):
    result = project_trace(directory_spec(tmp_path), "missing")
    assert result.coverage == 1.0
    assert result.project_files == []
    assert result.sources == []
    assert result.provenance_chunk.lineage_variables == ["missing"]
    assert result.provenance_chunk.lineage_variables_without_ranges == ["missing"]
    assert result.provenance_chunk.project_diagnostics == result.project_diagnostics


def test_project_records_cover_same_line_delimiter_statements(tmp_path):
    root = write_source(
        tmp_path,
        "same_line.do",
        "#delimit ;gen x = 1;unknown x;\n#delimit cr\n",
    )
    project = build_project_graph(
        files_spec([root]),
        registry=RegistryAdapter(module=MockStataRegistry()),
    )
    assert_project_records_complete(project)
    assert [attribution.range.start_line for attribution in project.attributions] == [1]
