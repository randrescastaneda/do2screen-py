"""Parse one Stata source into physical ranges and structural events.

The parser owns lexical statement boundaries and generic variable grammar. The
registry supplies command vocabulary and effects. ``parse_graph`` retains the
legacy depth-first include behavior; project tracing uses ``parse_file`` to
obtain one immutable physical-source record and replays its events separately.
"""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from typing import Any

from do2screen import grammar
from do2screen.models import (
    LineRange,
    RangeAttribution,
    SourceProvenance,
    UnresolvedBlock,
)
from do2screen.registry import RegistryAdapter, RegistryIncompatibilityError
from do2screen.scanner import read_source, scan
from do2screen.statements import Statement, assemble

_MAX_INCLUDE_DEPTH = 64
_UNSUPPORTED_EFFECTS = ("none", "restructures")


@dataclass
class ParsedEvent:
    """One immutable event in physical source order."""

    range: LineRange
    attributions: list[RangeAttribution] = field(default_factory=list)
    unresolved: UnresolvedBlock | None = None
    include_target: str | None = None
    kind: str = "records"
    command: str | None = None
    effect: str | None = None
    parent_variables: list[str] = field(default_factory=list)


@dataclass
class ParsedFile:
    """All persisted records and replayable events for one physical source."""

    path: str
    provenance: SourceProvenance
    attributions: list[RangeAttribution] = field(default_factory=list)
    lifecycle: dict[str, list[LineRange]] = field(default_factory=dict)
    parents: dict[str, list[str]] = field(default_factory=dict)
    unresolved: list[UnresolvedBlock] = field(default_factory=list)
    executable_lines: list[int] = field(default_factory=list)
    attributed_lines: set[int] = field(default_factory=set)
    unresolved_lines: set[int] = field(default_factory=set)
    source_lines: list[str] = field(default_factory=list)
    events: list[ParsedEvent] = field(default_factory=list)
    include_calls: list[tuple[Statement, str]] = field(default_factory=list)


@dataclass
class ParsedGraph:
    """Legacy merged graph for a root source and its includes."""

    root_path: str
    files: list[ParsedFile] = field(default_factory=list)
    attributions: list[RangeAttribution] = field(default_factory=list)
    lifecycle: dict[str, list[LineRange]] = field(default_factory=dict)
    parents: dict[str, list[str]] = field(default_factory=dict)
    unresolved: list[UnresolvedBlock] = field(default_factory=list)
    executable_lines: list[int] = field(default_factory=list)
    attributed_lines: set[int] = field(default_factory=set)
    unresolved_lines: set[int] = field(default_factory=set)
    block_comment_unterminated: bool = False


class Parser:
    """Parse sources against a registry adapter."""

    def __init__(
        self,
        registry: RegistryAdapter,
        *,
        include_labels: bool = False,
        require_source_driver: bool = False,
    ) -> None:
        self.registry = registry
        self.include_labels = include_labels
        self.require_source_driver = require_source_driver
        self._active_paths: set[str] = set()

    def parse_graph(self, root_path: str | os.PathLike[str]) -> ParsedGraph:
        """Parse a root source and its legacy depth-first include graph."""
        self._active_paths = set()
        root = str(root_path)
        graph = ParsedGraph(root_path=root)
        self._parse_file_into(root, graph, traversal_index=0)
        graph.attributions = _flatten(graph.files, "attributions")
        graph.executable_lines = _flatten(graph.files, "executable_lines")
        graph.attributed_lines = {
            line
            for parsed in graph.files
            for line in parsed.attributed_lines
        }
        graph.unresolved_lines = {
            line
            for parsed in graph.files
            for line in parsed.unresolved_lines
        }
        for parsed in graph.files:
            for variable, ranges in parsed.lifecycle.items():
                graph.lifecycle.setdefault(variable, []).extend(ranges)
            for variable, parents in parsed.parents.items():
                for parent in parents:
                    if parent not in graph.parents.setdefault(variable, []):
                        graph.parents[variable].append(parent)
            graph.unresolved.extend(parsed.unresolved)
        return graph

    def parse_file(self, path: str | os.PathLike[str]) -> ParsedFile:
        """Parse one physical source without traversing include targets."""
        graph = ParsedGraph(root_path=str(path))
        self._active_paths = set()
        return self._parse_file_into(
            str(path), graph, traversal_index=0, recurse_includes=False
        )

    def _parse_file_into(
        self,
        path: str,
        graph: ParsedGraph,
        *,
        traversal_index: int,
        depth: int = 0,
        recurse_includes: bool = True,
    ) -> ParsedFile:
        text = read_source(path)
        scanned = scan(text)
        statements, brace_blocks, _, used_delimit, unterminated_comment = assemble(
            scanned
        )
        norm_path = os.path.normpath(path)
        canonical = os.path.realpath(norm_path)
        self._active_paths.add(canonical)
        physical_lines = [line.text for line in scanned.lines]
        provenance = SourceProvenance(
            path=norm_path,
            line_count=len(physical_lines),
            used_delimit=used_delimit,
            traversal_index=traversal_index,
        )
        parsed = ParsedFile(
            path=norm_path,
            provenance=provenance,
            executable_lines=scanned.executable_line_numbers(),
            source_lines=physical_lines,
        )
        graph.files.append(parsed)

        last_line = max(len(physical_lines), 1)
        claims = self._structure_claims(
            statements,
            brace_blocks,
            unterminated_comment,
            last_line,
        )
        if unterminated_comment is not None:
            graph.block_comment_unterminated = True
        covered = [(start, end) for start, end, _, _ in claims]
        for start, end, reason, context in claims:
            self._record_range_unresolved(
                parsed,
                start_line=start,
                end_line=end,
                reason=reason,
                context=context,
            )

        include_targets: list[tuple[Statement, str]] = []
        for statement in statements:
            if _statement_overlaps(statement, covered):
                continue
            if statement.band == "directive":
                if any(
                    other is not statement
                    and other.band == "statement"
                    and other.start_line == statement.start_line
                    for other in statements
                ):
                    continue
                self._record_unresolved(
                    parsed,
                    statement,
                    "no_variable_attribution",
                    {"directive": statement.directive or ""},
                )
                continue
            self._classify_statement(parsed, statement, include_targets)

        parsed.include_calls = list(include_targets)
        if recurse_includes:
            self._traverse_includes(
                parsed,
                graph,
                include_targets,
                depth=depth,
            )
        else:
            self._active_paths.discard(canonical)

        _normalize_terminal_records(parsed)
        return parsed

    def _structure_claims(
        self,
        statements: list[Statement],
        brace_blocks: list[Any],
        unterminated_comment: int | None,
        last_line: int,
    ) -> list[tuple[int, int, str, dict[str, str]]]:
        claims: list[tuple[int, int, str, dict[str, str]]] = []
        for block in brace_blocks:
            if block.end_line is None:
                continue
            members = [
                statement
                for statement in statements
                if block.start_line <= statement.start_line <= block.end_line
            ]
            if any(self._contains_macro(statement.code) for statement in members):
                claims.append(
                    (
                        block.start_line,
                        block.end_line,
                        "macro_or_loop",
                        {"enclosing_block": f"{block.start_line}-{block.end_line}"},
                    )
                )
        for block in brace_blocks:
            if block.end_line is None:
                claims.append(
                    (
                        block.start_line,
                        max(block.start_line, last_line),
                        "unterminated_structure",
                        {"structure": "brace_block"},
                    )
                )
        if unterminated_comment is not None:
            claims.append(
                (
                    unterminated_comment,
                    last_line,
                    "unterminated_structure",
                    {"structure": "block_comment"},
                )
            )
        return _merge_claims(claims)

    def _traverse_includes(
        self,
        parsed: ParsedFile,
        graph: ParsedGraph,
        include_targets: list[tuple[Statement, str]],
        *,
        depth: int,
    ) -> None:
        base_dir = os.path.dirname(parsed.path)
        for statement, target in include_targets:
            if not target or self._contains_include_macro(target):
                self._record_unresolved(
                    parsed,
                    statement,
                    "unresolved_include",
                    {"target": target, "reason": "macro_or_missing"},
                )
                continue
            child_path = self._resolve_path(target, base_dir)
            child_canonical = os.path.realpath(child_path)
            if child_canonical in self._active_paths:
                self._record_unresolved(
                    parsed,
                    statement,
                    "unresolved_include",
                    {"target": target, "reason": "cycle_or_repeat"},
                )
                continue
            if not os.path.isfile(child_path):
                self._record_unresolved(
                    parsed,
                    statement,
                    "unresolved_include",
                    {"target": target, "reason": "missing"},
                )
                continue
            if depth >= _MAX_INCLUDE_DEPTH:
                self._record_unresolved(
                    parsed,
                    statement,
                    "unresolved_include",
                    {"target": target, "reason": "depth_exceeded"},
                )
                continue
            self._record_unresolved(
                parsed,
                statement,
                "no_variable_attribution",
                {"include": target, "resolved": "true"},
            )
            self._parse_file_into(
                child_path,
                graph,
                traversal_index=len(graph.files),
                depth=depth + 1,
            )

    def _classify_statement(
        self,
        parsed: ParsedFile,
        statement: Statement,
        include_targets: list[tuple[Statement, str]],
    ) -> None:
        if not self.registry.available:
            self._record_unresolved(
                parsed,
                statement,
                "unknown_command",
                {"registry": "unavailable"},
            )
            return
        try:
            command_token, rest = self._split_command(statement.code)
            if command_token is None:
                self._record_unresolved(
                    parsed,
                    statement,
                    "unsupported_syntax",
                    {"reason": "no_command_token"},
                )
                return
            canonical = self.registry.canonical_command(command_token)
        except RegistryIncompatibilityError as exc:
            self._record_unresolved(
                parsed,
                statement,
                "unknown_command",
                {"registry_error": str(exc)[:200]},
            )
            return
        if canonical is None:
            self._record_unresolved(
                parsed,
                statement,
                "unknown_command",
                {"token": command_token},
            )
            return

        if self._call_is_include(canonical):
            target = self._include_path(statement) or ""
            include_targets.append((statement, target))
            parsed.events.append(
                ParsedEvent(
                    range=self._line_range(
                        parsed,
                        statement.start_line,
                        statement.end_line,
                        statement,
                    ),
                    include_target=target,
                    kind="include",
                )
            )
            return

        try:
            effect = self.registry.variable_effect(canonical)
        except RegistryIncompatibilityError as exc:
            self._record_unresolved(
                parsed,
                statement,
                "unsupported_effect",
                {"registry_error": str(exc)[:200]},
            )
            return

        shape = grammar.analyze(rest)
        if shape.has_macro or self._contains_macro(statement.code):
            self._record_unresolved(
                parsed,
                statement,
                "macro_or_loop",
                {"enclosing_block": "none"},
            )
            return
        if effect in _UNSUPPORTED_EFFECTS and not (
            effect == "restructures" and shape.kind == "restructure"
        ):
            self._record_unresolved(
                parsed,
                statement,
                "unsupported_effect",
                {"command": canonical, "effect": effect},
            )
            return

        dispositions = self._apply_effect(effect, shape)
        if dispositions is None:
            self._record_unresolved(
                parsed,
                statement,
                "unsupported_syntax",
                {"command": canonical, "effect": effect, "shape": shape.kind},
            )
            return
        targets, sources = dispositions
        if not targets and not sources:
            self._record_unresolved(
                parsed,
                statement,
                "no_variable_attribution",
                {"command": canonical},
            )
            return
        self._apply_attribution(
            parsed,
            statement,
            targets,
            sources,
            command=canonical,
            effect=effect,
        )

    def _apply_effect(
        self,
        effect: str,
        shape: grammar.Shape,
    ) -> tuple[list[tuple[str, str]], list[str]] | None:
        """Map a registry effect and a generic grammar shape to records."""
        if effect == "creates":
            if shape.kind == "assignment":
                return _pairs(shape.targets, "created"), shape.sources
            if shape.kind == "gen_option":
                if self._option_has_effect(shape.option_name, "creates"):
                    return _pairs(shape.targets, "created"), shape.sources
                return None
            if shape.kind == "varlist" and len(shape.targets) == 2:
                return [(shape.targets[1], "created")], [shape.targets[0]]
            return None
        if effect == "modifies":
            if shape.kind == "assignment":
                return _pairs(shape.targets, "modified"), shape.sources
            if shape.kind == "mapping":
                if shape.generated_targets and self._option_has_effect(
                    shape.option_name, "creates"
                ):
                    return _pairs(shape.generated_targets, "created"), shape.targets
                return _pairs(shape.targets, "modified"), []
            if shape.kind == "varlist":
                return _pairs(shape.targets, "modified"), shape.qualifier_sources
            return None
        if effect == "renames":
            if shape.kind == "varlist" and len(shape.targets) == 2:
                return [(shape.targets[1], "created")], [shape.targets[0]]
            return None
        if effect == "removes":
            if shape.kind == "varlist":
                return _pairs(shape.targets, "dropped"), shape.qualifier_sources
            return ([], [])
        if effect == "labels":
            if shape.kind == "label" and shape.targets:
                return [(shape.targets[0], "labelled")], shape.sources
            if shape.kind == "label":
                return ([], [])
            return None
        if effect == "restructures":
            if shape.kind == "restructure":
                return _pairs(shape.targets, "created"), []
            return None
        return None

    def _option_has_effect(self, option: str | None, effect: str) -> bool:
        """Resolve a structural option through the upstream registry."""
        if option is None:
            return False
        try:
            canonical = self.registry.canonical_command(option)
            return (
                canonical is not None
                and self.registry.variable_effect(canonical) == effect
            )
        except RegistryIncompatibilityError:
            return False

    def _apply_attribution(
        self,
        parsed: ParsedFile,
        statement: Statement,
        targets: list[tuple[str, str]],
        sources: list[str],
        *,
        command: str,
        effect: str,
    ) -> None:
        line_range = self._line_range(
            parsed,
            statement.start_line,
            statement.end_line,
            statement,
        )
        event_attributions: list[RangeAttribution] = []
        for variable, kind in targets:
            attribution = RangeAttribution(
                range=line_range,
                variable=variable,
                kind=kind,
            )
            parsed.attributions.append(attribution)
            event_attributions.append(attribution)
            parsed.attributed_lines.update(
                range(statement.start_line, statement.end_line + 1)
            )
            if kind != "labelled" or self.include_labels:
                parsed.lifecycle.setdefault(variable, []).append(line_range)
            for source in sources:
                if source not in parsed.parents.setdefault(variable, []):
                    parsed.parents[variable].append(source)
        for source in sources:
            attribution = RangeAttribution(
                range=line_range,
                variable=source,
                kind="referenced",
            )
            parsed.attributions.append(attribution)
            event_attributions.append(attribution)
            parsed.attributed_lines.update(
                range(statement.start_line, statement.end_line + 1)
            )
        parsed.events.append(
            ParsedEvent(
                range=line_range,
                attributions=event_attributions,
                kind="records",
                command=command,
                effect=effect,
                parent_variables=list(sources),
            )
        )

    def _call_is_include(self, canonical: str) -> bool:
        if self.require_source_driver:
            return self.registry.is_include(canonical)
        try:
            return self.registry.is_include(canonical)
        except RegistryIncompatibilityError:
            return False

    def _include_path(self, statement: Statement) -> str | None:
        """Extract a quoted or unquoted include target from one statement."""
        text = statement.raw
        index = 0
        in_block_comment = False
        in_line_comment = False
        while index < len(text):
            if in_line_comment:
                break
            if in_block_comment:
                if text[index : index + 2] == "*/":
                    in_block_comment = False
                    index += 2
                else:
                    index += 1
                continue
            if text[index : index + 2] == "/*":
                in_block_comment = True
                index += 2
                continue
            if text[index : index + 2] == "//":
                in_line_comment = True
                break
            if text[index : index + 2] == '`"':
                close = text.find('"\'', index + 2)
                if close >= 0:
                    return text[index + 2 : close]
                return text[index + 2 :]
            if text[index] == '"':
                close = text.find('"', index + 1)
                if close >= 0:
                    return text[index + 1 : close]
                return text[index + 1 :]
            index += 1
        _, rest = self._split_command(statement.code)
        if rest.strip():
            return rest.strip().split(None, 1)[0].rstrip(",")
        return None

    def _split_command(self, code: str) -> tuple[str | None, str]:
        """Strip registry-defined prefixes and return command plus remainder."""
        tokens = grammar.tokenize(code)
        if not tokens:
            return None, ""
        index = 0
        while index < len(tokens):
            token = tokens[index].text
            if token == ":":
                index += 1
                continue
            if not self.registry.is_prefix(token):
                break
            next_index = index + 1
            colon_index = next(
                (
                    position
                    for position in range(next_index, len(tokens))
                    if tokens[position].text == ":"
                ),
                None,
            )
            index = (
                colon_index + 1 if colon_index is not None else next_index
            )
        if index >= len(tokens):
            return None, ""
        command = tokens[index].text
        return command, code[tokens[index].end :].lstrip()

    def _record_unresolved(
        self,
        parsed: ParsedFile,
        statement: Statement,
        reason: str,
        context: dict[str, str],
    ) -> None:
        line_range = self._line_range(
            parsed,
            statement.start_line,
            statement.end_line,
            statement,
        )
        block = UnresolvedBlock(
            range=line_range,
            reason=reason,  # type: ignore[arg-type]
            context=context,
            statement=statement.code,
        )
        parsed.unresolved.append(block)
        parsed.unresolved_lines.update(
            range(statement.start_line, statement.end_line + 1)
        )
        parsed.events.append(
            ParsedEvent(range=line_range, unresolved=block, kind="unresolved")
        )

    def _record_range_unresolved(
        self,
        parsed: ParsedFile,
        *,
        start_line: int,
        end_line: int,
        reason: str,
        context: dict[str, str],
        statement: str | None = None,
    ) -> None:
        line_range = self._line_range(parsed, start_line, end_line)
        block = UnresolvedBlock(
            range=line_range,
            reason=reason,  # type: ignore[arg-type]
            context=context,
            statement=statement,
        )
        parsed.unresolved.append(block)
        parsed.unresolved_lines.update(range(start_line, end_line + 1))
        parsed.events.append(
            ParsedEvent(range=line_range, unresolved=block, kind="unresolved")
        )

    def _line_range(
        self,
        parsed: ParsedFile,
        start_line: int,
        end_line: int,
        statement: Statement | None = None,
    ) -> LineRange:
        return LineRange(
            source=parsed.path,
            start_line=start_line,
            end_line=end_line,
            comment_start_line=(statement.comment_start_line if statement else None),
            comment_end_line=(statement.comment_end_line if statement else None),
            source_lines=_source_slice(parsed.source_lines, start_line, end_line),
        )

    @staticmethod
    def _contains_macro(text: str) -> bool:
        return any(character in text for character in ("`", "$", "'"))

    @staticmethod
    def _contains_include_macro(text: str) -> bool:
        return "`" in text or "$" in text

    @staticmethod
    def _resolve_path(target: str, base_dir: str) -> str:
        return target if os.path.isabs(target) else os.path.join(base_dir, target)


def _pairs(items: list[str], kind: str) -> list[tuple[str, str]]:
    return [(item, kind) for item in items]


def _looks_like_match_spec(tokens: list[Any], colon_index: int) -> bool:
    """Return whether a colon belongs to a numeric/identifier match token."""
    if colon_index == 0 or colon_index + 1 >= len(tokens):
        return False
    left = tokens[colon_index - 1].text
    right = tokens[colon_index + 1].text
    left_is_match_part = grammar.is_numeric(left) or (
        len(left) == 1 and left.isalpha()
    )
    right_is_match_part = grammar.is_numeric(right) or (
        len(right) == 1 and right.isalpha()
    )
    return left_is_match_part and right_is_match_part


def _statement_overlaps(
    statement: Statement,
    intervals: list[tuple[int, int]],
) -> bool:
    return any(
        statement.start_line <= end and statement.end_line >= start
        for start, end in intervals
    )


def _merge_claims(
    claims: list[tuple[int, int, str, dict[str, str]]]
) -> list[tuple[int, int, str, dict[str, str]]]:
    merged: list[tuple[int, int, str, dict[str, str]]] = []
    for claim in sorted(claims, key=lambda value: (value[0], value[1])):
        if not merged or claim[0] > merged[-1][1]:
            merged.append(claim)
            continue
        start, end, reason, context = merged[-1]
        merged[-1] = (start, max(end, claim[1]), reason, context)
    return merged


def _source_slice(source_lines: list[str], start_line: int, end_line: int) -> list[str]:
    if start_line < 1 or end_line < start_line:
        return []
    return list(source_lines[start_line - 1 : end_line])


def _range_slice(line_range: LineRange, start_line: int, end_line: int) -> LineRange:
    offset = start_line - line_range.start_line
    return LineRange(
        source=line_range.source,
        start_line=start_line,
        end_line=end_line,
        comment_start_line=(
            line_range.comment_start_line
            if start_line == line_range.start_line
            else None
        ),
        comment_end_line=(
            line_range.comment_end_line
            if start_line == line_range.start_line
            else None
        ),
        source_lines=line_range.source_lines[
            offset : offset + end_line - start_line + 1
        ],
    )


def _intervals(
    start_line: int,
    end_line: int,
    blocked: set[int],
) -> list[tuple[int, int]]:
    result: list[tuple[int, int]] = []
    start: int | None = None
    for line in range(start_line, end_line + 1):
        if line in blocked:
            if start is not None:
                result.append((start, line - 1))
                start = None
        elif start is None:
            start = line
    if start is not None:
        result.append((start, end_line))
    return result


def _normalize_terminal_records(parsed: ParsedFile) -> None:
    """Make persisted unresolved records disjoint from attributions.

    Physical ranges have no column coordinates. If two semicolon-separated
    statements share a line, an attribution owns that physical line and any
    unresolved statement on the same line is retained only for its remaining
    physical lines. The result is derived from persisted records, not parser
    bookkeeping.
    """
    attributed: set[int] = set()
    for attribution in parsed.attributions:
        if attribution.range.source != parsed.path:
            continue
        attributed.update(
            range(attribution.range.start_line, attribution.range.end_line + 1)
        )
    claimed = set(attributed)
    normalized: list[UnresolvedBlock] = []
    replacements: dict[int, list[UnresolvedBlock]] = {}
    for block in parsed.unresolved:
        if block.range.source != parsed.path:
            normalized.append(block)
            replacements[id(block)] = [block]
            continue
        pieces: list[UnresolvedBlock] = []
        for start, end in _intervals(
            block.range.start_line,
            block.range.end_line,
            claimed,
        ):
            piece = UnresolvedBlock(
                range=_range_slice(block.range, start, end),
                reason=block.reason,
                context=dict(block.context),
                statement=block.statement,
            )
            pieces.append(piece)
            normalized.append(piece)
            claimed.update(range(start, end + 1))
        replacements[id(block)] = pieces
    parsed.unresolved = normalized
    parsed.attributed_lines = attributed
    parsed.unresolved_lines = {
        line
        for block in normalized
        for line in range(block.range.start_line, block.range.end_line + 1)
    }
    normalized_events: list[ParsedEvent] = []
    for event in parsed.events:
        if event.unresolved is None:
            normalized_events.append(event)
            continue
        pieces = replacements.get(id(event.unresolved), [])
        normalized_events.extend(
            ParsedEvent(
                range=piece.range,
                unresolved=piece,
                kind=event.kind,
                command=event.command,
                effect=event.effect,
                include_target=event.include_target,
                attributions=list(event.attributions),
                parent_variables=list(event.parent_variables),
            )
            for piece in pieces
        )
    parsed.events = normalized_events


def _flatten(files: list[ParsedFile], attribute: str) -> list[Any]:
    result: list[Any] = []
    for parsed in files:
        result.extend(getattr(parsed, attribute))
    return result
