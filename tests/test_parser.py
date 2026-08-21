"""Parser: command classification, include resolution, attribution."""

from __future__ import annotations

from pathlib import Path

from do2screen.parser import Parser
from do2screen.registry import RegistryAdapter
from tests.conftest import write_do
from tests.invariant import assert_no_dropped_lines
from tests.mock_registry import MockStataRegistry


def parse(tmp_path: Path, text: str, filename: str = "main.do"):
    path = write_do(tmp_path, filename, text)
    registry = RegistryAdapter(module=MockStataRegistry())
    return Parser(registry).parse_graph(str(path)), path


def reasons(graph):
    return [u.reason for u in graph.unresolved]


def test_create_attribution(tmp_path):
    graph, _ = parse(tmp_path, "gen wages = 1000\n")
    assert graph.lifecycle["wages"]
    assert graph.lifecycle["wages"][0].start_line == 1
    kind = graph.attributions[0].kind
    assert kind == "created"


def test_replace_attribution_and_sources(tmp_path):
    graph, _ = parse(tmp_path, "gen x = 1\nreplace x = y + 2\n")
    # replace x = y + 2 -> line 2 modified x, referenced y
    mods = [a for a in graph.attributions if a.kind == "modified"]
    assert len(mods) == 1
    assert mods[0].variable == "x"
    assert mods[0].range.start_line == 2
    refs = [a for a in graph.attributions if a.kind == "referenced"]
    assert any(a.variable == "y" for a in refs)
    assert graph.parents["x"] == ["y"]


def test_rename_pair(tmp_path):
    graph, _ = parse(tmp_path, "rename old new\n")
    created = [a for a in graph.attributions if a.kind == "created"]
    refs = [a for a in graph.attributions if a.kind == "referenced"]
    assert created[0].variable == "new"
    assert refs[0].variable == "old"
    assert graph.parents["new"] == ["old"]


def test_drop_varlist(tmp_path):
    graph, _ = parse(tmp_path, "drop a b c\n")
    dropped = [a for a in graph.attributions if a.kind == "dropped"]
    assert [a.variable for a in dropped] == ["a", "b", "c"]
    assert "a" in graph.lifecycle
    assert "b" in graph.lifecycle


def test_label_attribution(tmp_path):
    text = 'label variable income "Total income"\n'
    graph, _ = parse(tmp_path, text)
    labels = [a for a in graph.attributions if a.kind == "labelled"]
    assert len(labels) == 1
    assert labels[0].variable == "income"
    # Default: label events excluded from lifecycle slices.
    assert "income" not in graph.lifecycle

    parser = Parser(RegistryAdapter(module=MockStataRegistry()), include_labels=True)
    g2 = parser.parse_graph(str(write_do(tmp_path, "incl.do", text)))
    assert g2.lifecycle["income"]


def test_abbreviated_command(tmp_path):
    graph, _ = parse(tmp_path, "g x = 1\n")
    assert "x" in graph.lifecycle


def test_command_that_cannot_abbreviate_is_unknown(tmp_path):
    # `re` is not a valid abbreviation of replace.
    graph, _ = parse(tmp_path, "re x = 1\n")
    assert reasons(graph) == ["unknown_command"]
    assert graph.lifecycle == {}


def test_unknown_user_ado(tmp_path):
    graph, _ = parse(tmp_path, "myUserAdo a b\n")
    assert "unknown_command" in reasons(graph)


def test_unsupported_effect_none(tmp_path):
    graph, _ = parse(tmp_path, "summarize x\n")
    assert "unsupported_effect" in reasons(graph)


def test_unsupported_effect_restructures(tmp_path):
    graph, _ = parse(tmp_path, "reshape long x, i(id) j(j)\n")
    assert "unsupported_effect" in reasons(graph)


def test_gen_option_creates_target(tmp_path):
    graph, _ = parse(tmp_path, "generate group, gen(m)\n")
    # gen(m) on a creates command: m is created; group is a source.
    created = [a for a in graph.attributions if a.kind == "created"]
    assert [a.variable for a in created] == ["m"]


def test_prefix_bysort(tmp_path):
    graph, _ = parse(tmp_path, "bysort region: gen x = 1\n")
    assert "x" in graph.lifecycle
    assert graph.lifecycle["x"][0].start_line == 1


def test_macro_loop_unbraced_unresolved(tmp_path):
    graph, _ = parse(tmp_path, "gen v`x'ty = 1\n")
    assert "macro_or_loop" in reasons(graph)
    block = next(u for u in graph.unresolved if u.reason == "macro_or_loop")
    assert block.range.start_line == 1
    assert block.range.end_line == 1


def test_macro_loop_braced_blocks(tmp_path):
    text = (
        "foreach x in 1 2 {\n"
        "gen v`x' = 1\n"
        "}\n"
    )
    graph, _ = parse(tmp_path, text)
    macro = [u for u in graph.unresolved if u.reason == "macro_or_loop"]
    assert macro, reasons(graph)
    # The block covers the header through the closing brace.
    assert macro[0].range.start_line == 1
    assert macro[0].range.end_line == 3
    # The inner create line is absorbed by the block (no separate attribution).
    assert graph.lifecycle == {}


def test_no_variable_attribution_drop_all(tmp_path):
    graph, _ = parse(tmp_path, "drop _all\n")
    assert "no_variable_attribution" in reasons(graph)


def test_include_resolves(tmp_path):
    write_do(tmp_path, "lib.do", "gen bonus = 100\n")
    text = 'include "lib.do"\ngen income = bonus + 1\n'
    graph, _ = parse(tmp_path, text)
    # The child's create line is attributed.
    assert "bonus" in graph.lifecycle
    assert graph.lifecycle["bonus"][0].start_line == 1
    # The include statement itself is recorded with no variable attribution.
    assert "no_variable_attribution" in reasons(graph)
    # The includer still attributes income.
    assert "income" in graph.lifecycle
    # Two source files in provenance, child has traversal index 1.
    assert len(graph.files) == 2
    child = graph.files[1]
    assert child.provenance.traversal_index == 1


def test_include_missing(tmp_path):
    text = 'include "nope.do"\n'
    graph, _ = parse(tmp_path, text)
    assert "unresolved_include" in reasons(graph)
    block = next(u for u in graph.unresolved if u.reason == "unresolved_include")
    assert block.context.get("reason") == "missing"


def test_include_cycle(tmp_path):
    write_do(tmp_path, "a.do", 'include "b.do"\nget = 1\n')
    write_do(tmp_path, "b.do", 'include "a.do"\nget2 = 1\n')
    registry = RegistryAdapter(module=MockStataRegistry())
    graph = Parser(registry).parse_graph(str(tmp_path / "a.do"))
    assert "unresolved_include" in reasons(graph)


def test_unterminated_brace_block(tmp_path):
    text = "foreach x in 1 2 {\nreplace v`x' = 1\n"
    graph, _ = parse(tmp_path, text)
    assert "unterminated_structure" in reasons(graph)
    block = next(u for u in graph.unresolved if u.reason == "unterminated_structure")
    assert block.context.get("structure") == "brace_block"


def test_unterminated_block_comment(tmp_path):
    text = "gen a = 1\n/* never closed\nmore\n"
    graph, _ = parse(tmp_path, text)
    assert "unterminated_structure" in reasons(graph)
    block = next(u for u in graph.unresolved if u.reason == "unterminated_structure")
    assert block.context.get("structure") == "block_comment"


def test_registry_degraded_mode_marks_unknown(tmp_path, monkeypatch):
    path = write_do(tmp_path, "m.do", "gen x = 1\nreplace x = 2\n")
    monkeypatch.setattr(
        "do2screen.registry._load_module",
        lambda: (None, "simulated missing registry"),
    )
    registry = RegistryAdapter()  # explicitly simulated absence -> degraded
    graph = Parser(registry).parse_graph(str(path))
    assert reasons(graph) == ["unknown_command", "unknown_command"]
    assert graph.lifecycle == {}


def test_comment_range_propagated_to_attribution(tmp_path):
    text = "* header\ngen x = 1\n"
    graph, _ = parse(tmp_path, text)
    att = graph.attributions[0]
    assert att.range.comment_start_line == 1
    assert att.range.comment_end_line == 1


def test_delimit_directive_no_variable_attribution(tmp_path):
    text = "#delimit ;\ngen a = 1;\n"
    graph, _ = parse(tmp_path, text)
    directives = [
        u for u in graph.unresolved if u.reason == "no_variable_attribution"
    ]
    assert directives
    assert directives[0].context.get("directive") == ";"
    # The executable a = 1 line is attributed.
    assert "a" in graph.lifecycle


def test_unquoted_include_resolves(tmp_path):
    write_do(tmp_path, "lib.do", "gen bonus = 100\n")
    text = "include lib.do\ngen income = bonus + 1\n"
    graph, _ = parse(tmp_path, text)
    assert "bonus" in graph.lifecycle
    assert "income" in graph.lifecycle


def test_creates_ordered_pair(tmp_path):
    graph, _ = parse(tmp_path, "clonevar a b\n")
    created = [a for a in graph.attributions if a.kind == "created"]
    referenced = [a for a in graph.attributions if a.kind == "referenced"]
    assert [a.variable for a in created] == ["b"]
    assert [a.variable for a in referenced] == ["a"]
    assert graph.parents["b"] == ["a"]


def test_modifies_varlist(tmp_path):
    graph, _ = parse(tmp_path, "replace x y\n")
    modified = [a for a in graph.attributions if a.kind == "modified"]
    assert [a.variable for a in modified] == ["x", "y"]


def test_delimit_tail_not_swallowed(tmp_path):
    text = "#delimit ;gen a = 1;replace b = 2;\n#delimit cr\ngen x = a + b\n"
    graph, _ = parse(tmp_path, text)
    assert "a" in graph.lifecycle
    assert "b" in graph.lifecycle
    assert graph.lifecycle["a"][0].start_line == 1
    assert graph.lifecycle["b"][0].start_line == 1


def test_macro_block_with_non_macro_predecessor(tmp_path):
    text = (
        "foreach x in 1 2 {\n"
        "gen plain = 1\n"
        "gen v`x' = 1\n"
        "}\n"
        "gen after = 1\n"
    )
    graph, _ = parse(tmp_path, text)
    reasons = {u.reason for u in graph.unresolved}
    assert "macro_or_loop" in reasons
    # The non-macro line inside the macro block is absorbed, never attributed
    # AND unresolved: the partition stays disjoint (AGENTS.md 3.1).
    assert "plain" not in graph.lifecycle
    assert_no_dropped_lines(write_do(tmp_path, "macro_pre.do", text))
