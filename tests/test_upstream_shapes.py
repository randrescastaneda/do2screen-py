"""Grammar/effect regressions exercised with the installed upstream registry."""

from __future__ import annotations

import importlib.util

import pytest

from do2screen.parser import Parser
from do2screen.registry import RegistryAdapter

requires_registry = pytest.mark.skipif(
    importlib.util.find_spec("stata_registry") is None,
    reason="stata_registry is not installed",
)


@requires_registry
@pytest.mark.parametrize(
    "text,expected",
    [
        ("recode x (1 2 = 1)", [("x", "modified")]),
        (
            "recode x (1 2 = 1), generate(y)",
            [("y", "created"), ("x", "referenced")],
        ),
        (
            "egen y = total(x), by(group)",
            [("y", "created"), ("x", "referenced"), ("group", "referenced")],
        ),
        ("destring x, generate(y)", [("y", "created"), ("x", "referenced")]),
        ("encode x, gen(y)", [("y", "created"), ("x", "referenced")]),
        ("merge 1:1 id using other.dta", [("_merge", "created")]),
        ("merge m:1 id using other.dta, nogen", []),
    ],
)
def test_upstream_effect_shapes(tmp_path, text, expected):
    path = tmp_path / "source.do"
    path.write_text(text + "\n", encoding="utf-8")
    graph = Parser(RegistryAdapter()).parse_graph(str(path))
    assert [(item.variable, item.kind) for item in graph.attributions] == expected


@requires_registry
def test_upstream_stacked_prefixes(tmp_path):
    path = tmp_path / "source.do"
    path.write_text("quietly capture bysort region: generate x = 1\n", encoding="utf-8")
    graph = Parser(RegistryAdapter()).parse_graph(str(path))
    assert [(item.variable, item.kind) for item in graph.attributions] == [
        ("x", "created")
    ]
