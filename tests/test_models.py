"""Models: construction, validation, and JSON round-trip."""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from do2screen.models import (
    LineRange,
    ProjectDiagnostic,
    ProvenanceStatement,
    RangeAttribution,
    SourceProvenance,
    TraceResult,
    UnresolvedBlock,
    VariableContext,
    VariableEffect,
    VariableIdentity,
    VariableProvenanceChunk,
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
    ub = UnresolvedBlock(
        range=LineRange(source="a.do", start_line=1, end_line=1),
        reason="macro_or_loop",
    )
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


def test_source_lines_and_project_models_round_trip():
    source = _provenance()
    line_range = LineRange(
        source="a.do",
        start_line=2,
        end_line=3,
        source_lines=["gen x = 1", "replace x = 2"],
    )
    context = VariableContext(
        source="a.do",
        first_creation_line=2,
        lifecycle_ranges=[line_range],
        direct_parents=["base"],
        caller_source="caller.do",
        caller_range=LineRange(source="caller.do", start_line=4, end_line=4),
    )
    identity = VariableIdentity(variable="x", contexts=[context])
    diagnostic = ProjectDiagnostic(code="cross_file_unordered", range=line_range)
    result = TraceResult(
        variable="x",
        coverage=1.0,
        source=source,
        sources=[source],
        ranges=[line_range],
        variable_identities=[identity],
        project_diagnostics=[diagnostic],
    )
    loaded = TraceResult.model_validate_json(result.model_dump_json())
    assert loaded == result
    assert loaded.ranges[0].source_lines == ["gen x = 1", "replace x = 2"]
    assert loaded.variable_identities[0].contexts[0].caller_source == "caller.do"


def test_legacy_result_defaults_new_project_fields():
    source = _provenance()
    legacy = {
        "variable": "x",
        "ranges": [],
        "ancestors": [],
        "attributed_ranges": [],
        "unresolved_blocks": [],
        "coverage": 1.0,
        "sources": [source.model_dump()],
        "source": source.model_dump(),
    }
    result = TraceResult.model_validate(legacy)
    assert result.input_mode is None
    assert result.project_files == []
    assert result.variable_identities == []
    assert result.manifest_path is None
    assert result.project_diagnostics == []
    assert result.provenance_chunk is None
    assert result.ranges == []


def test_provenance_models_are_frozen_and_round_trip():
    source = _provenance()
    line_range = LineRange(
        source="a.do",
        start_line=1,
        end_line=2,
        source_lines=["gen x = 1 + ///", "  2"],
    )
    statement = ProvenanceStatement(
        range=line_range,
        effects=[VariableEffect(variable="x", kind="created")],
        occurrence_sequence=4,
    )
    chunk = VariableProvenanceChunk(
        variable="x",
        lineage_variables=["x", "external"],
        ordering="execution",
        statements=[statement],
        text="* [a.do:1-2 | x:created | occurrence:4]\n"
        "gen x = 1 + ///\n  2",
        lineage_variables_without_ranges=["external"],
    )
    result = TraceResult(
        variable="x",
        coverage=1.0,
        source=source,
        sources=[source],
        provenance_chunk=chunk,
    )
    loaded = TraceResult.model_validate_json(result.model_dump_json())
    assert loaded == result
    assert loaded.provenance_chunk.standalone_execution == "not_assessed"
    with pytest.raises(ValidationError):
        chunk.variable = "other"  # type: ignore[misc]


def test_provenance_chunk_defaults_are_independent():
    first = VariableProvenanceChunk(variable="first", ordering="execution")
    second = VariableProvenanceChunk(variable="second", ordering="execution")
    first.lineage_variables.append("x")
    assert second.lineage_variables == []
