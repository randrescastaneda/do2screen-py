"""Shared pytest fixtures and helpers.

All tracing helpers here use the mock registry so the full classification path
runs deterministically without the unpublished ``stata-command-registry``.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from do2screen.parser import Parser
from do2screen.registry import RegistryAdapter
from do2screen.trace import build_result
from tests.mock_registry import MockStataRegistry


@pytest.fixture
def registry():
    return RegistryAdapter(module=MockStataRegistry())


@pytest.fixture
def parser(registry):
    return Parser(registry)


def write_do(tmp_path: Path, name: str, content: str) -> Path:
    path = tmp_path / name
    path.write_text(content, encoding="utf-8")
    return path


def trace_text(
    tmp_path: Path,
    text: str,
    variable: str,
    *,
    follow_parents: bool = True,
    include_labels: bool = False,
    filename: str = "file.do",
):
    """Trace ``variable`` through a temporary do file using the mock registry."""
    path = write_do(tmp_path, filename, text)
    registry = RegistryAdapter(module=MockStataRegistry())
    parser = Parser(registry, include_labels=include_labels)
    graph = parser.parse_graph(str(path))
    return build_result(graph, variable, follow_parents=follow_parents), path
