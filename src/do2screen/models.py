"""Stable public data contract for do2screen-py.

All models are frozen Pydantic v2 models built from JSON-lossless primitives.
Paths are serialized as normalized strings, never :class:`pathlib.Path`.
These models are a public, semver-locked contract: downstream consumers embed
``TraceResult`` in their own persisted records. Adding an optional field is
allowed; renaming, removing, or changing the meaning of an existing field is a
breaking change.

The names here describe only Stata and file structure. No domain vocabulary
from downstream consumers is allowed in field names, descriptions, or values.
"""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

#: Lifecycle effect of an attributed range.
Kind = Literal["created", "modified", "dropped", "labelled", "referenced"]

# Public project input modes. Legacy single-file traces use ``None`` for the
# additive ``TraceResult.input_mode`` field.
ProjectInputMode = Literal["files", "directory", "manifest"]

#: Why a block of code could not be attributed to a variable.
UnresolvedReason = Literal[
    "macro_or_loop",
    "unknown_command",
    "unsupported_effect",
    "unsupported_syntax",
    "unresolved_include",
    "no_variable_attribution",
    "unterminated_structure",
]


class SourceProvenance(BaseModel):
    """Provenance metadata for one traversed source file.

    Attributes:
        path: Normalized filesystem path of the source.
        line_count: Number of physical lines in the source.
        used_delimit: True when the source uses ``#delimit ;`` anywhere.
        traversal_index: Ordered index of this source in depth-first
            traversal order (0 is the root/target source).
    """

    model_config = ConfigDict(frozen=True)

    path: str
    line_count: int
    used_delimit: bool
    traversal_index: int


class LineRange(BaseModel):
    """An inclusive range of physical source lines.

    Attributes:
        source: Path of the source file the range belongs to.
        start_line: First physical line (1-based, inclusive).
        end_line: Last physical line (1-based, inclusive).
        comment_start_line: Optional first line of the contiguous full-line
            comment immediately preceding the statement.
        comment_end_line: Optional last line of that preceding comment.
        source_lines: Decoded physical source lines covered by this inclusive
            range, without line terminators. The list length is
            ``end_line - start_line + 1``.
    """

    model_config = ConfigDict(frozen=True)

    source: str
    start_line: int
    end_line: int
    comment_start_line: int | None = None
    comment_end_line: int | None = None
    source_lines: list[str] = Field(default_factory=list)


class RangeAttribution(BaseModel):
    """One attributed executable statement tied to one variable.

    Attributes:
        range: The physical line range of the statement.
        variable: The variable the statement affects or references.
        kind: Lifecycle or dependency kind of the attribution.
    """

    model_config = ConfigDict(frozen=True)

    range: LineRange
    variable: str
    kind: Kind


class VariableTrace(BaseModel):
    """Everything the tracer learned about one variable.

    Attributes:
        variable: The variable name.
        ranges: Lifecycle line ranges in source order (created, modified,
            dropped, labelled). Dependency-only (``referenced``) records are
            excluded to preserve do2screen (Stata) line-set parity.
        parents: Unique direct dependency variables in first-reference order.
        ancestors: Recursively resolved ancestors (empty when
            ``follow_parents=False``).
    """

    model_config = ConfigDict(frozen=True)

    variable: str
    ranges: list[LineRange] = Field(default_factory=list)
    parents: list[str] = Field(default_factory=list)
    ancestors: list[str] = Field(default_factory=list)


class UnresolvedBlock(BaseModel):
    """A region of recognized-but-unattributed code, reported explicitly.

    Attributes:
        range: Physical line range of the unresolved region.
        reason: One of the seven unresolved categories.
        context: Source/parser facts only (for example the unresolved include
            target path or the enclosing brace block range).
        statement: Optional raw text of the statement, when one exists.
    """

    model_config = ConfigDict(frozen=True)

    range: LineRange
    reason: UnresolvedReason
    context: dict[str, str] = Field(default_factory=dict)
    statement: str | None = None


class VariableContext(BaseModel):
    """One occurrence-qualified definition context for a variable."""

    model_config = ConfigDict(frozen=True)

    source: str
    first_creation_line: int | None = None
    lifecycle_ranges: list[LineRange] = Field(default_factory=list)
    direct_parents: list[str] = Field(default_factory=list)
    occurrence_sequence: int | None = None
    caller_sequence: int | None = None
    caller_source: str | None = None
    caller_range: LineRange | None = None


class VariableIdentity(BaseModel):
    """A variable name and its occurrence-qualified definition contexts."""

    model_config = ConfigDict(frozen=True)

    variable: str
    contexts: list[VariableContext] = Field(default_factory=list)


class ProjectDiagnostic(BaseModel):
    """Non-terminal uncertainty or input fact from a project trace.

    Diagnostics are separate from ``unresolved_blocks``: a diagnostic may have
    no physical range and never changes the parser's terminal line partition.
    """

    model_config = ConfigDict(frozen=True)

    code: str
    message: str | None = None
    source: str | None = None
    manifest_path: str | None = None
    variable: str | None = None
    candidate_sources: list[str] = Field(default_factory=list)
    context: dict[str, str] = Field(default_factory=dict)
    range: LineRange | None = None


class TraceResult(BaseModel):
    """The full result of tracing one variable through one source graph.

    Attributes:
        variable: The traced target variable.
        ranges: Lifecycle ranges of the target variable across all sources.
        ancestors: Recursively resolved ancestors of the target.
        attributed_ranges: Complete ordered audit inventory of every attribution
            (lifecycle and dependency references) for all variables.
        unresolved_blocks: Every region that could not be attributed.
        coverage: Fraction of executable physical lines covered by at least one
            attributed range. Sentinel 1.0 when there are no executable lines.
        sources: Provenance of every traversed source, in traversal order.
        source: Provenance of the root/target source.
        input_mode: Project input mode, or ``None`` for a legacy trace.
        project_files: Canonical physical sources accepted by a project input.
        variable_identities: Occurrence-qualified project definition contexts.
        manifest_path: Canonical manifest path for manifest input, if any.
        project_diagnostics: Non-terminal project uncertainty and input facts.
    """

    model_config = ConfigDict(frozen=True)

    variable: str
    ranges: list[LineRange] = Field(default_factory=list)
    ancestors: list[str] = Field(default_factory=list)
    attributed_ranges: list[RangeAttribution] = Field(default_factory=list)
    unresolved_blocks: list[UnresolvedBlock] = Field(default_factory=list)
    coverage: float
    sources: list[SourceProvenance] = Field(default_factory=list)
    source: SourceProvenance
    input_mode: ProjectInputMode | None = None
    project_files: list[str] = Field(default_factory=list)
    variable_identities: list[VariableIdentity] = Field(default_factory=list)
    manifest_path: str | None = None
    project_diagnostics: list[ProjectDiagnostic] = Field(default_factory=list)
