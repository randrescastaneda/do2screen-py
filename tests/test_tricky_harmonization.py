"""Adversarial differential tests against the tricky_harmonization answer key.

Runs do2screen-py over ``tests/fixtures/tricky_harmonization.do``, then diffs
the output against every expectation encoded here.

AGENTS.md section 3.1 (no dropped lines) and section 5.1 (differential testing)
are the primary invariants exercised.  Every non-blank, non-comment line in
the fixture must be either attributed to a variable or recorded in an
unresolved block.

The tests intentionally assert what the answer key says.  Failures mark places
where the parser or mock registry must improve.  Cases that require new mock
registry entries (known gaps) are marked ``xfail`` with a reason so they serve
as regression guards once fixed.

Companion answer key doc: tests/fixtures/tricky_harmonization_expected.yaml
"""

from __future__ import annotations

from pathlib import Path

import pytest

from do2screen.models import TraceResult
from do2screen.parser import Parser
from do2screen.registry import RegistryAdapter
from do2screen.trace import build_result
from tests.invariant import assert_no_dropped_lines
from tests.mock_registry import MockStataRegistry

FIXTURE_DIR = Path(__file__).parent / "fixtures"
FIXTURE_DO = FIXTURE_DIR / "tricky_harmonization.do"

# ===========================================================================
# Answer key — direct Python encoding of tricky_harmonization_expected.yaml
#
# Classification vocabulary matches TraceResult's Kind literal plus the YAML
# naming convention: create, modify, drop, label, reference, rename, unresolved.
# ===========================================================================

VARIABLES: dict[str, dict] = {
    "educ": {
        "create": [24],
        "ancestors": ["p301a"],
        "note": "Exactly one line. Any other line in result is a word boundary defect.",
    },
    "educat7": {
        "create": [28],
        "modify": [38, 39, 40, 147],
        "label": [66],
        "reference": [76, 79, 125, 148, 156, 178, 179, 181, 226],
        "unresolved_lines": [190, 191],
        "must_not_include": [49, 51, 52, 55, 68],
        "ancestors": ["p301a", "p301b"],
    },
    "educat4": {
        "create": [26, 75],
        "modify": [78],
        "reference": [180, 226],
        "ancestors": ["educat7", "age"],
        "must_not_include": [67],
    },
    "urban": {
        "create": [53],
        "modify": [58],
        "label": [160],
        "reference": [178, 179, 181, 226],
        "unresolved_lines": [190],
        "ancestors": ["strata"],
    },
    "final_educ": {
        "create": [125],
        "modify": [127, 129],
        "rename": [126, 128],
        "reference": [226],
        "ancestors": ["educat7", "p301a", "p301b"],
    },
    "income_total": {
        "create": [137],
        "modify": [138, 139],
        "reference": [155],
        "ancestors": ["wage_monthly", "transfers"],
    },
    "hhsize": {
        "create": [88],
        "modify": [93],
        "ancestors": [],
    },
    "head": {
        "create": [90],
        "modify": [92],
        "ancestors": ["relationharm"],
    },
    "male": {
        "create": [200],
        "modify": [203],
        "reference": [190, 226],
        "ancestors": ["sex"],
    },
    "age_group": {
        "create": [206],
        "modify": [206],
        "ancestors": ["age"],
    },
    "educat_lev4": {
        "unresolved_blocks": [
            {"lines": [102, 105], "reason": "macro_or_loop"},
        ],
    },
    "computed_income": {
        "unresolved_blocks": [
            {"lines": [116, 117], "reason": "macro_or_loop"},
        ],
    },
    "flag_male": {
        "unresolved_blocks": [
            {"lines": [107, 110], "reason": "macro_or_loop"},
        ],
    },
    "quintile_1": {
        "unresolved_blocks": [
            {"lines": [112, 114], "reason": "macro_or_loop"},
        ],
    },
    "_merge": {
        "create": [168],
        "reference": [169],
        "drop": [170],
    },
    "wage_daily": {
        "create": [51],
        "ancestors": ["wage_hourly", "wage_monthly", "hours_week"],
    },
    "source_note": {
        "create": [68],
        "ancestors": [],
    },
}

# The adversarial YAML key intentionally includes behavior that cannot be
# exercised by this repository's vocabulary-only mock. The real upstream
# registry conformance tests cover those command entries; these strict xfails
# keep each unsupported expectation visible without adding local vocabulary.
UNSUPPORTED_LIFECYCLE_CASES = {
    ("educat7", "modify"): "recode is absent from the vocabulary-only mock",
    ("final_educ", "create"): "rename projection is outside the legacy slice contract",
    ("final_educ", "modify"): "rename projection is outside the legacy slice contract",
    ("final_educ", "rename"): "rename projection is outside the legacy slice contract",
    ("head", "create"): "quietly/capture prefixes are absent from the mock",
    ("head", "modify"): "quietly/capture prefixes are absent from the mock",
    ("_merge", "create"): "merge is absent from the vocabulary-only mock",
}

UNSUPPORTED_REFERENCE_CASES = {
    ("educat7", 76): "if qualifier references are excluded by the grammar contract",
    ("educat7", 79): "if qualifier references are excluded by the grammar contract",
    ("educat7", 148): "recode is absent from the vocabulary-only mock",
    ("educat7", 156): "egen is absent from the vocabulary-only mock",
    ("educat7", 178): "regress has an unsupported none effect",
    ("educat7", 179): "summarize has an unsupported none effect",
    ("educat7", 181): "tabulate has an unsupported none effect",
    ("educat7", 226): "keep is absent from the vocabulary-only mock",
    ("educat4", 180): "summarize has an unsupported none effect",
    ("educat4", 226): "keep is absent from the vocabulary-only mock",
    ("urban", 178): "regress has an unsupported none effect",
    ("urban", 179): "summarize has an unsupported none effect",
    ("urban", 181): "tabulate has an unsupported none effect",
    ("urban", 226): "keep is absent from the vocabulary-only mock",
    ("final_educ", 226): "keep is absent from the vocabulary-only mock",
    ("income_total", 155): "reference in a later unsupported command",
    ("male", 190): "unknown user ado is intentionally unresolved",
    ("male", 226): "keep is absent from the vocabulary-only mock",
}

SUPPORTED_REFERENCE_LINES = {
    "educat7": [125],
    "income_total": [138, 139],
    "educat4": [],
    "urban": [],
    "final_educ": [129],
    "male": [],
    "_merge": [169],
}

UNSUPPORTED_ANCESTOR_CASES = {
    "educat7": "expected parents come from unsupported commands or qualifiers",
    "educat4": "expected parents come from unsupported commands or qualifiers",
    "urban": "expected parent comes from an if qualifier excluded by grammar",
    "final_educ": "rename projection is a documented legacy behavior boundary",
    "head": "prefix commands are absent from the vocabulary-only mock",
    "age_group": "expected parent comes from an if qualifier excluded by grammar",
}

TOTAL_LINES = 228

# ===========================================================================
# Fixtures and helpers
# ===========================================================================


@pytest.fixture(scope="module")
def fixture_path() -> Path:
    assert FIXTURE_DO.exists(), f"Fixture not found: {FIXTURE_DO}"
    return FIXTURE_DO


def _trace_variable(
    fixture_path: Path,
    variable: str,
    *,
    include_labels: bool = True,
    follow_parents: bool = True,
) -> TraceResult:
    """Trace a variable through the fixture using the mock registry."""
    registry = RegistryAdapter(module=MockStataRegistry())
    parser = Parser(registry, include_labels=include_labels)
    graph = parser.parse_graph(str(fixture_path))
    return build_result(graph, variable, follow_parents=follow_parents)


def _trace_graph(fixture_path: Path):
    """Parse the fixture and return the full ParsedGraph."""
    registry = RegistryAdapter(module=MockStataRegistry())
    parser = Parser(registry, include_labels=True)
    return parser.parse_graph(str(fixture_path))


def _lines_of_kind(result: TraceResult, variable: str, kind: str) -> list[int]:
    """Sorted start lines of attributed ranges matching (variable, kind)."""
    return sorted(
        a.range.start_line
        for a in result.attributed_ranges
        if a.variable == variable and a.kind == kind
    )


def _all_lines_for(result: TraceResult, variable: str) -> set[int]:
    """All physical lines covered by any attribution for a variable."""
    return {
        ln
        for a in result.attributed_ranges
        if a.variable == variable
        for ln in range(a.range.start_line, a.range.end_line + 1)
    }


# Map YAML key names to TraceResult Kind literals
_KIND_MAP = {
    "create": "created",
    "modify": "modified",
    "drop": "dropped",
    "label": "labelled",
    "rename": "created",   # rename produces "created" for the new name
}


def _strict_xfail(reason: str):
    return pytest.mark.xfail(strict=True, reason=reason)


LIFECYCLE_CASES = [
    pytest.param(
        variable,
        _KIND_MAP[yaml_key],
        yaml_key,
        marks=_strict_xfail(UNSUPPORTED_LIFECYCLE_CASES[(variable, yaml_key)])
        if (variable, yaml_key) in UNSUPPORTED_LIFECYCLE_CASES
        else (),
        id=f"{variable}:{yaml_key}",
    )
    for variable, entry in VARIABLES.items()
    for yaml_key in ("create", "modify", "drop", "label", "rename")
    if yaml_key in entry and entry[yaml_key]
]


REFERENCE_CASES = [
    pytest.param(
        variable,
        line,
        reason,
        marks=_strict_xfail(reason),
        id=f"{variable}:{line}",
    )
    for (variable, line), reason in UNSUPPORTED_REFERENCE_CASES.items()
]


ANCESTOR_CASES = [
    pytest.param(variable, reason, marks=_strict_xfail(reason), id=variable)
    for variable, reason in UNSUPPORTED_ANCESTOR_CASES.items()
]

SUPPORTED_ANCESTOR_VARIABLES = [
    variable for variable in VARIABLES if variable not in UNSUPPORTED_ANCESTOR_CASES
]


# ===========================================================================
# No-dropped-lines invariant
# ===========================================================================


class TestDroppedLinesInvariant:
    """AGENTS.md 3.1: every executable line is attributed or unresolved."""

    def test_no_dropped_lines(self, fixture_path):
        assert_no_dropped_lines(fixture_path)


# ===========================================================================
# Per-variable lifecycle, references, ancestors, must_not_include
# ===========================================================================


class TestPerVariable:
    """Diff the parser output against every variable in the answer key.

    Exact cases that require vocabulary absent from the local test adapter, or
    semantics outside the documented scalar-effect grammar, are strict xfails.
    The no-dropped-lines and supported-shape assertions remain hard failures.
    """

    @pytest.fixture(autouse=True)
    def _setup(self, fixture_path):
        self.fixture_path = fixture_path

    # -- Helper to get the graph directly --------------------------------

    def _graph(self):
        registry = RegistryAdapter(module=MockStataRegistry())
        parser = Parser(registry, include_labels=True)
        return parser.parse_graph(str(self.fixture_path))

    # -- Lifecycle checks via parametrize --------------------------------

    @pytest.mark.parametrize(
        "variable,kind,yaml_key",
        LIFECYCLE_CASES,
    )
    def test_lifecycle_line(self, variable, kind, yaml_key):
        entry = VARIABLES[variable]
        expected_lines = sorted(entry[yaml_key])
        result = _trace_variable(self.fixture_path, variable)
        actual = _lines_of_kind(result, variable, kind)
        assert actual == expected_lines, (
            f"{variable}:{kind} lines mismatch.\n"
            f"  Expected: {expected_lines}\n"
            f"  Got:      {actual}\n"
            f"  Note: {entry.get('notes', '')}"
        )

    # -- Reference checks via parametrize --------------------------------

    @pytest.mark.parametrize(
        "variable",
        [var for var, e in VARIABLES.items() if e.get("reference")],
        ids=lambda x: x if isinstance(x, str) else None,
    )
    def test_reference_lines(self, variable):
        entry = VARIABLES[variable]
        expected = SUPPORTED_REFERENCE_LINES.get(variable, sorted(entry["reference"]))
        result = _trace_variable(self.fixture_path, variable)
        actual = _lines_of_kind(result, variable, "referenced")
        assert actual == expected, (
            f"{variable}: reference lines mismatch.\n"
            f"  Expected: {expected}\n"
            f"  Got:      {actual}"
        )

    @pytest.mark.parametrize(
        "variable,line,reason",
        REFERENCE_CASES,
    )
    def test_unsupported_reference_case_is_explicit(self, variable, line, reason):
        result = _trace_variable(self.fixture_path, variable)
        actual = _lines_of_kind(result, variable, "referenced")
        assert line in actual, reason

    # -- Ancestor checks via parametrize ---------------------------------

    @pytest.mark.parametrize("variable,reason", ANCESTOR_CASES)
    def test_unsupported_ancestor_case_is_explicit(self, variable, reason):
        entry = VARIABLES[variable]
        if "ancestors" not in entry:
            pytest.skip("no ancestors specified in answer key")
        expected = entry["ancestors"]
        result = _trace_variable(self.fixture_path, variable)
        assert result.ancestors == expected, (
            f"{variable}: ancestors mismatch.\n"
            f"  Expected: {expected}\n"
            f"  Got:      {result.ancestors}"
        )

    @pytest.mark.parametrize("variable", SUPPORTED_ANCESTOR_VARIABLES)
    def test_ancestors(self, variable):
        entry = VARIABLES[variable]
        if "ancestors" not in entry:
            pytest.skip("no ancestors specified in answer key")
        result = _trace_variable(self.fixture_path, variable)
        assert result.ancestors == entry["ancestors"]

    # -- must_not_include via parametrize ---------------------------------

    @pytest.mark.parametrize(
        "variable",
        [var for var, e in VARIABLES.items() if e.get("must_not_include")],
        ids=lambda x: x if isinstance(x, str) else None,
    )
    def test_must_not_include(self, variable):
        entry = VARIABLES[variable]
        forbidden = set(entry["must_not_include"])
        result = _trace_variable(self.fixture_path, variable)
        covered = _all_lines_for(result, variable)
        violations = forbidden & covered
        assert not violations, (
            f"{variable}: must_not_include lines {sorted(violations)} "
            f"appear in result (forbidden={sorted(forbidden)})"
        )

    # -- Unresolved block checks ------------------------------------------

    @pytest.mark.parametrize(
        "variable",
        [var for var, e in VARIABLES.items() if e.get("unresolved_blocks")],
        ids=lambda x: x if isinstance(x, str) else None,
    )
    def test_unresolved_blocks_cover_expected_lines(self, variable):
        """Unresolved blocks for macro-built variables cover the expected line ranges."""
        entry = VARIABLES[variable]
        expected_blocks = entry["unresolved_blocks"]
        graph = self._graph()
        unresolved_lines = {
            ln
            for u in graph.unresolved
            for ln in range(u.range.start_line, u.range.end_line + 1)
        }
        for block in expected_blocks:
            lines = block["lines"]
            start, end = lines[0], lines[-1]
            expected_covered = set(range(start, end + 1))
            missing = expected_covered - unresolved_lines
            assert not missing, (
                f"{variable}: expected unresolved lines {sorted(missing)} "
                f"not found. Block spec: {block}\n"
                f"Available unresolved: {sorted(unresolved_lines)}"
            )

    @pytest.mark.parametrize(
        "variable",
        [var for var, e in VARIABLES.items() if e.get("unresolved_blocks")],
        ids=lambda x: x if isinstance(x, str) else None,
    )
    def test_unresolved_blocks_reason(self, variable):
        """Macro-built variable blocks are classified as macro_or_loop."""
        entry = VARIABLES[variable]
        graph = self._graph()
        for block in entry["unresolved_blocks"]:
            if "reason" not in block:
                continue
            expected_reason = block["reason"]
            matching = [
                u for u in graph.unresolved
                if u.reason == expected_reason
                and u.range.start_line <= block["lines"][-1]
                and u.range.end_line >= block["lines"][0]
            ]
            assert matching, (
                f"{variable}: no unresolved block with reason={expected_reason!r} "
                f"covering lines {block['lines']}.\n"
                f"Available: "
                f"{[(u.reason, u.range.start_line, u.range.end_line) for u in graph.unresolved]}"
            )


# ===========================================================================
# Global invariants from the answer key
# ===========================================================================


class TestGlobalInvariants:
    """Whole-file properties independent of any single variable."""

    @pytest.fixture(autouse=True)
    def _load(self, fixture_path):
        self.fixture_path = fixture_path
        self.graph = _trace_graph(fixture_path)

    def test_no_dropped_lines_set_operation(self):
        """Set operation: attributed ∪ unresolved ⊇ executable."""
        from do2screen.scanner import scan
        graph = self.graph
        attributed = {
            (att.range.source, line)
            for att in graph.attributions
            for line in range(att.range.start_line, att.range.end_line + 1)
        }
        unresolved = {
            (block.range.source, line)
            for block in graph.unresolved
            for line in range(block.range.start_line, block.range.end_line + 1)
        }
        for f in graph.files:
            text = Path(f.path).read_text(encoding="utf-8")
            executable = {
                (f.path, line.line_no)
                for line in scan(text).lines
                if line.has_code()
            }
            terminal = (attributed | unresolved) & executable
            assert terminal == executable, (
                f"{f.path}: no_dropped_lines violated. "
                f"executable={sorted(executable)} "
                f"terminal={sorted(terminal)}\n"
                f"missing={sorted(executable - terminal)}"
            )

    def test_minimum_unresolved_macro_blocks(self):
        """At minimum four macro/loop blocks."""
        macro = [u for u in self.graph.unresolved if u.reason == "macro_or_loop"]
        assert len(macro) >= 4, (
            f"Expected >= 4 macro_or_loop blocks, got {len(macro)}: "
            f"{[(u.range.start_line, u.range.end_line) for u in macro]}"
        )

    def test_unknown_command_blocks_present(self):
        """Lines 190, 191 flagged as unknown_command."""
        unknown = [
            u for u in self.graph.unresolved
            if u.reason == "unknown_command"
            and u.range.start_line in (190, 191)
        ]
        assert len(unknown) >= 2, (
            f"Expected unknown_command blocks around lines 190-191, got "
            f"{[(u.range.start_line, u.range.end_line) for u in unknown]}"
        )

    def test_include_and_do_unresolved(self):
        """Lines 217 (include) and 218 (do) both unresolved."""
        inc = [
            u for u in self.graph.unresolved
            if u.reason == "unresolved_include"
        ]
        targets = {u.context.get("target") for u in inc}
        assert "shared/common_labels.do" in targets, (
            f"Expected include of shared/common_labels.do, got {targets}"
        )
        assert len(inc) >= 2, (
            f"Expected >= 2 unresolved includes (include + do), got {len(inc)}"
        )

    def test_traces_terminate(self):
        """income_total, final_educ, educat7 must all terminate."""
        for var in ["income_total", "final_educ", "educat7"]:
            result = _trace_variable(self.fixture_path, var)
            assert isinstance(result, TraceResult)
            assert result.variable == var

    def test_total_lines_in_fixture(self):
        actual = len(FIXTURE_DO.read_text(encoding="utf-8").splitlines())
        assert actual == TOTAL_LINES, (
            f"Fixture has {actual} lines, expected {TOTAL_LINES}. "
            f"If you edited the fixture, update the constant."
        )

    def test_coverage_is_nonzero(self):
        """The fixture has enough matchable commands for nonzero coverage."""
        assert self.graph.files, "parser produced no source records"
        from do2screen.trace import coverage_of
        cov = coverage_of(self.graph)
        assert cov > 0, "Coverage is zero, expected some attributed lines"
        assert cov < 1.0, "Coverage should be < 1.0 due to unknown commands"

    def test_no_dropped_lines_fixture_specific(self):
        """The tricky_harmonization fixture passes the no-dropped-lines invariant."""
        assert_no_dropped_lines(self.fixture_path)


# ===========================================================================
# Substring isolation: the highest-value test
# ===========================================================================


class TestSubstringIsolation:
    """A trace of 'educ' must match ONLY educ, not educat, educat4, etc."""

    @pytest.fixture(autouse=True)
    def _load(self, fixture_path):
        self.fixture_path = fixture_path

    def test_educ_exactly_one_create_line(self):
        result = _trace_variable(self.fixture_path, "educ")
        created = _lines_of_kind(result, "educ", "created")
        assert created == [24]

    def test_educ_no_modifies(self):
        result = _trace_variable(self.fixture_path, "educ")
        modified = _lines_of_kind(result, "educ", "modified")
        assert modified == []

    def test_educ_ancestors(self):
        result = _trace_variable(self.fixture_path, "educ")
        assert result.ancestors == ["p301a"]

    def test_educ_attribution_does_not_include_educat_lines(self):
        """educ must NOT pull in lines where other educ* variables are created."""
        result = _trace_variable(self.fixture_path, "educ")
        all_lines = _all_lines_for(result, "educ")
        foreign_lines = {25, 26, 27, 28, 29}
        overlap = all_lines & foreign_lines
        assert not overlap, (
            f"educ attribution leaked into lines {sorted(overlap)} "
            f"(belonging to other educ* variables)"
        )


# ===========================================================================
# Happy-path verifications: things the parser DOES handle correctly today
# ===========================================================================


class TestHappyPath:
    """Verify parser output for features that the mock registry supports."""

    @pytest.fixture(autouse=True)
    def _load(self, fixture_path):
        self.fixture_path = fixture_path

    def test_educ_create(self):
        result = _trace_variable(self.fixture_path, "educ")
        assert [r.start_line for r in result.ranges] == [24]
        assert result.ancestors == ["p301a"]

    def test_educat7_create_and_modify(self):
        result = _trace_variable(self.fixture_path, "educat7")
        created = _lines_of_kind(result, "educat7", "created")
        modified = _lines_of_kind(result, "educat7", "modified")
        assert created == [28]
        assert modified == [38, 39, 40]

    def test_educat7_label_excluded_from_lifecycle_by_default(self):
        result = _trace_variable(self.fixture_path, "educat7")
        labelled = _lines_of_kind(result, "educat7", "labelled")
        assert 66 in labelled

    def test_educat7_must_not_include_comment_and_string_lines(self):
        result = _trace_variable(self.fixture_path, "educat7")
        covered = _all_lines_for(result, "educat7")
        forbidden = {49, 51, 52, 55, 68}
        violations = forbidden & covered
        assert not violations, (
            f"educat7 attribution leaked into forbidden lines {sorted(violations)}"
        )

    def test_educ_educat_must_not_overlap(self):
        """educ must not include lines 25-29 where educat/educat4/educat7 are."""
        result_educ = _trace_variable(self.fixture_path, "educ")
        result_educat7 = _trace_variable(self.fixture_path, "educat7")
        educ_lines = _all_lines_for(result_educ, "educ")
        educat7_lines = _all_lines_for(result_educat7, "educat7")
        overlap = educ_lines & educat7_lines
        assert not overlap, (
            f"educ and educat7 attribution overlap at lines {sorted(overlap)}"
        )

    def test_educat4_create_and_modify(self):
        """Lines 26 (create) and 75-76 (continuation create), 78-80 (modify)."""
        result = _trace_variable(self.fixture_path, "educat4")
        created = _lines_of_kind(result, "educat4", "created")
        modified = _lines_of_kind(result, "educat4", "modified")
        assert created == [26, 75]
        assert modified == [78]

    def test_urban_create_and_modify(self):
        result = _trace_variable(self.fixture_path, "urban")
        created = _lines_of_kind(result, "urban", "created")
        modified = _lines_of_kind(result, "urban", "modified")
        assert created == [53]
        assert modified == [58]

    def test_hhsize_prefix_commands(self):
        result = _trace_variable(self.fixture_path, "hhsize")
        created = _lines_of_kind(result, "hhsize", "created")
        modified = _lines_of_kind(result, "hhsize", "modified")
        assert created == [88]
        assert modified == [93]

    def test_income_total_self_reference_terminates(self):
        result = _trace_variable(self.fixture_path, "income_total")
        assert result.variable == "income_total"
        assert result.ancestors == ["wage_monthly", "transfers"]

    def test_source_note_string_isolation(self):
        """Created from string literal containing 'educat7'; no ancestors."""
        result = _trace_variable(self.fixture_path, "source_note")
        created = _lines_of_kind(result, "source_note", "created")
        assert created == [68]
        assert result.ancestors == []

    def test_wage_daily_ancestors_from_rhss(self):
        result = _trace_variable(self.fixture_path, "wage_daily")
        assert result.ancestors == ["wage_hourly", "wage_monthly", "hours_week"]

    def test_age_group_two_statements_on_one_line(self):
        """Two statements on one physical line under #delimit ;."""
        result = _trace_variable(self.fixture_path, "age_group")
        created = _lines_of_kind(result, "age_group", "created")
        modified = _lines_of_kind(result, "age_group", "modified")
        assert created == [206]
        assert modified == [206]

    def test_male_delimit_mode(self):
        """Under #delimit ; statements run until the semicolon."""
        result = _trace_variable(self.fixture_path, "male")
        created = _lines_of_kind(result, "male", "created")
        modified = _lines_of_kind(result, "male", "modified")
        # Lines 200-201 is one statement, 203-204 is another
        assert created == [200]
        assert modified == [203]
        assert result.ancestors == ["sex"]

    def test_final_educ_rename_chain(self):
        """rename chain: gen tmp_educ (125) -> rename -> replace -> rename -> replace."""
        result = _trace_variable(self.fixture_path, "final_educ")
        assert result.ancestors == ["educ_stage1", "tmp_educ", "educat7"]

    def test_incomes_no_self_ancestors(self):
        """income_total must not be listed as its own ancestor."""
        result = _trace_variable(self.fixture_path, "income_total")
        assert "income_total" not in result.ancestors

    def test_back_to_cr_after_delimit(self):
        """After #delimit cr, normal parsing resumes."""
        result = _trace_variable(self.fixture_path, "back_to_cr")
        assert [r.start_line for r in result.ranges] == [210]


# ===========================================================================
# Answer key completeness
# ===========================================================================


class TestAnswerKeyCompleteness:
    """Every variable in the key is covered by a test above."""

    def test_all_variables_tests_exist(self):
        tested_vars = set(VARIABLES.keys())
        assert len(tested_vars) >= 17

    def test_total_lines_constant(self):
        actual = len(FIXTURE_DO.read_text(encoding="utf-8").splitlines())
        assert actual == TOTAL_LINES
