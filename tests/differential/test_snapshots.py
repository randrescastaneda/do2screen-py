"""Snapshot-based differential tests.

Compare do2screen-py output against committed golden ``r(lines)`` snapshots.
These snapshots encode the reference line sets for the ported fixtures. They
run in CI without a Stata binary. Snapshots were hand-verified against the
port's expected behaviour (no Stata binary was available at capture time); see
``tests/fixtures/stata_golden/README.md`` for provenance.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from tests.conftest import trace_text

SNAPSHOTS = Path(__file__).parent.parent / "differential" / "snapshots"
GOLDEN = Path(__file__).parent.parent / "fixtures" / "stata_golden"

SNAPSHOT_FILES = sorted(SNAPSHOTS.glob("*.json"))


def _load_snapshot(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def test_snapshots_are_committed():
    assert SNAPSHOT_FILES, "no snapshots committed under tests/differential/snapshots/"


@pytest.mark.parametrize("snapshot", SNAPSHOT_FILES, ids=lambda p: p.name)
def test_snapshot_matches(snapshot, tmp_path):
    data = _load_snapshot(snapshot)
    fixture_name = data["fixture"]
    content = (GOLDEN / fixture_name).read_text(encoding="utf-8")
    for variable, expected in data["variables"].items():
        result, _ = trace_text(tmp_path, content, variable)
        actual_lines = [r.start_line for r in result.ranges]
        assert actual_lines == expected["ranges"], (
            f"{variable}: ranges {actual_lines} != {expected['ranges']}"
        )
        assert result.ancestors == expected["ancestors"], (
            f"{variable}: ancestors {result.ancestors} != {expected['ancestors']}"
        )
