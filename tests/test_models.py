"""Models: construction, validation, and JSON round-trip."""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from do2screen.models import (
    LineRange,
    RangeAttribution,
    SourceProvenance,
    TraceResult,
    UnresolvedBlock,
    VariableTrace,
)


def _provenance(**overrides):
    fields = {"path": "a.do", "line_count": 3, "used_delimit": False, "traversal_index": 0}
    fields.update(overrides)
    return SourceProvenance(**fields)


def _full_result(**overrides):
    source = _provenance()
    result = TraceResult(
        variable="income",
        ranges=[LineRange(source="a.do", start_line=3, end_line=3)],
        ancestors=["wages"],
        attributed_ranges=[
            RangeAttribution(
                range=LineRange(source="a.do", start_line=1, end_line=1),
                variable="wages",
                kind="created",
            )
        ],
        unresolved_blocks=[],
        coverage=1.0,
        sources=[source],
        source=source,
    )
    result_dict = result.model_dump()
    result_dict.update(overrides)
    return TraceResult(**result_dict)


def test_construct_models():
    prov = _provenance()
    rng = LineRange(source="a.do", start_line=1, end_line=2)
    att = RangeAttribution(range=rng, variable="wages", kind="created")
    vt = VariableTrace(variable="wages", ranges=[rng], parents=["x"], ancestors=["y"])
    assert vt.variable == "wages"
    assert vt.ranges == [rng]
    assert vt.parents == ["x"]
    assert vt.ancestors == ["y"]
    ub = UnresolvedBlock(
        range=LineRange(source="a.do", start_line=5, end_line=5),
        reason="unknown_command",
        context={"token": "foo"},
        statement="foo bar",
    )
    tr = TraceResult(
        variable="income",
        ranges=[rng],
        ancestors=["wages"],
        attributed_ranges=[att],
        unresolved_blocks=[ub],
        coverage=0.5,
        sources=[prov],
        source=prov,
    )
    assert tr.variable == "income"
    assert tr.ranges[0] == rng
    assert tr.ancestors == ["wages"]
    assert tr.attributed_ranges[0] == att
    assert tr.unresolved_blocks[0] == ub
    assert tr.coverage == 0.5
    assert tr.sources == [prov]
    assert tr.source == prov


def test_json_round_trip_no_loss():
    result = _full_result()
    dumped = result.model_dump_json()
    loaded = TraceResult.model_validate_json(dumped)
    assert loaded == result
    # byte-identical re-serialization (determinism)
    assert loaded.model_dump_json() == dumped


def test_empty_collections_round_trip():
    source = _provenance()
    result = TraceResult(
        variable="missing",
        ranges=[],
        ancestors=[],
        attributed_ranges=[],
        unresolved_blocks=[],
        coverage=1.0,
        sources=[source],
        source=source,
    )
    loaded = TraceResult.model_validate_json(result.model_dump_json())
    assert loaded == result
    assert loaded.ranges == []
    assert loaded.ancestors == []


def test_invalid_kind_rejected():
    with pytest.raises(ValidationError):
        RangeAttribution(
            range=LineRange(source="a.do", start_line=1, end_line=1),
            variable="x",
            kind="not_a_kind",
        )


def test_invalid_reason_rejected():
    with pytest.raises(ValidationError):
        UnresolvedBlock(
            range=LineRange(source="a.do", start_line=1, end_line=1),
            reason="wat",
        )


def test_frozen_models_reject_assignment():
    prov = _provenance()
    # Frozen models reject mutation; pydantic v2 raises ValidationError on
    # assignment to a frozen field.
    with pytest.raises(ValidationError):
        prov.path = "other.do"  # type: ignore[misc]


def test_default_factories():
    vt = VariableTrace(variable="x")
    assert vt.ranges == []
    assert vt.parents == []
    assert vt.ancestors == []
    ub = UnresolvedBlock(range=LineRange(source="a.do", start_line=1, end_line=1), reason="macro_or_loop")
    assert ub.context == {}
    assert ub.statement is None


def test_comment_range_optional():
    rng = LineRange(
        source="a.do",
        start_line=4,
        end_line=4,
        comment_start_line=3,
        comment_end_line=3,
    )
    assert rng.comment_start_line == 3
    assert rng.comment_end_line == 3
    plain = LineRange(source="a.do", start_line=1, end_line=1)
    assert plain.comment_start_line is None


def test_path_serialized_as_string():
    source = _provenance(path="nested/a.do")
    dumped = source.model_dump()
    assert isinstance(dumped["path"], str)
    assert dumped["path"] == "nested/a.do"
