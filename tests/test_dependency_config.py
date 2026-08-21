"""Tests for the upstream registry dependency source."""

from __future__ import annotations

import tomllib
from pathlib import Path


def test_registry_extra_tracks_upstream_main() -> None:
    pyproject = Path(__file__).parents[1] / "pyproject.toml"
    data = tomllib.loads(pyproject.read_text(encoding="utf-8"))
    requirements = data["project"]["optional-dependencies"]["registry"]

    assert requirements == [
        "stata-registry @ git+https://github.com/randrescastaneda/stata-command-registry.git@main",
    ]
