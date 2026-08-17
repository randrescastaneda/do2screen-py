"""Command-agnostic grammar: shape extraction and token rules."""

from __future__ import annotations

from do2screen import grammar


def test_assignment_target_and_sources():
    shape = grammar.analyze("x = y + z")
    assert shape.kind == "assignment"
    assert shape.targets == ["x"]
    assert shape.sources == ["y", "z"]
    assert shape.has_macro is False


def test_assignment_multiple_sources_dedup_first_seen():
    shape = grammar.analyze("x = y + z + y")
    assert shape.sources == ["y", "z"]


def test_assignment_excludes_numeric_literals():
    shape = grammar.analyze("x = 1 + 2.5 + y")
    assert shape.sources == ["y"]


def test_assignment_excludes_function_call_name():
    shape = grammar.analyze("x = log(y) + max(z, 1)")
    assert "log" not in shape.sources
    assert "max" not in shape.sources
    assert shape.sources == ["y", "z"]


def test_assignment_excludes_qualifier_after_if():
    shape = grammar.analyze("x = y if z == 1")
    assert shape.sources == ["y"]
    shape2 = grammar.analyze("x = a in 1/5")
    assert shape2.sources == ["a"]


def test_assignment_excludes_system_names():
    shape = grammar.analyze("x = _n + y")
    assert shape.sources == ["y"]


def test_gen_option_target():
    shape = grammar.analyze("x, gen(m)")
    assert shape.kind == "gen_option"
    assert shape.targets == ["m"]
    assert shape.sources == ["x"]


def test_varlist_shape():
    shape = grammar.analyze("a b c")
    assert shape.kind == "varlist"
    assert shape.targets == ["a", "b", "c"]
    assert shape.sources == []


def test_pair_varlist_two_tokens():
    shape = grammar.analyze("old new")
    assert shape.kind == "varlist"
    assert shape.targets == ["old", "new"]


def test_empty_code_is_none():
    shape = grammar.analyze("")
    assert shape.kind == "none"
    assert shape.targets == []


def test_macro_detected_without_expansion():
    shape = grammar.analyze("v`x' = 1")
    assert shape.has_macro is True
    assert any("`" in t.text for t in grammar.tokenize("v`x' = 1"))
    shape2 = grammar.analyze("$g = y")
    assert shape2.has_macro is True


def test_factor_prefix_stripping():
    assert grammar.normalize_vars("i.educ") == ["educ"]
    assert grammar.normalize_vars("ib2.region") == ["region"]
    assert grammar.normalize_vars("c.age#i.sex") == ["age", "sex"]


def test_time_series_prefix_stripping():
    assert grammar.normalize_vars("L.x") == ["x"]
    assert grammar.normalize_vars("L2.x") == ["x"]
    assert grammar.normalize_vars("D.x") == ["x"]


def test_variable_names_inside_strings_are_not_tokens():
    # The scanner already removed string content; verify the grammar sees none.
    shape = grammar.analyze("x =  ")
    assert shape.kind == "assignment"
    assert shape.targets == ["x"]
    assert shape.sources == []


def test_split_command_and_rest():
    cmd, rest = grammar.split_command("generate x = 1")
    assert cmd == "generate"
    assert rest == "x = 1"


def test_tokenize_factor_interactions():
    toks = [t.text for t in grammar.tokenize("i.a#c.b")]
    assert toks == ["i.a#c.b"]


def test_assignment_ignores_internal_operators():
    shape = grammar.analyze("x = y == z")
    assert shape.kind == "assignment"
    assert shape.sources == ["y", "z"]
