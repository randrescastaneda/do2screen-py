"""Tests for publishable dependency metadata."""

from __future__ import annotations

from pathlib import Path

import tomllib


def test_dependency_metadata_has_no_direct_urls() -> None:
    pyproject = Path(__file__).parents[1] / "pyproject.toml"
    data = tomllib.loads(pyproject.read_text(encoding="utf-8"))
    project = data["project"]
    requirements = list(project["dependencies"])
    for extra in project["optional-dependencies"].values():
        requirements.extend(extra)

    assert all(" @ " not in requirement for requirement in requirements)
