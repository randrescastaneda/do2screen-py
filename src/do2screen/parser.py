"""Source parser: statements -> classification -> attribution.

Orchestrates scanner -> statements -> grammar for a single file and for the
resolved include/nested-do graph. Summary of the disposition of every
executable line:

- A statement whose command resolves in the registry and whose generic shape
  agrees with the command's ``variable_effect`` produces one or more
  :class:`~do2screen.models.RangeAttribution` records (lifecycle targets plus
  ``referenced`` dependency inputs).
- A statement that cannot be classified is reported as an unresolved block with
  one of the seven reasons, never silently dropped:
  ``unknown_command``, ``unsupported_effect``, ``unsupported_syntax``,
  ``macro_or_loop``, ``unresolved_include``, ``no_variable_attribution``, or
  ``unterminated_structure``.

Conventions:

- ``#delimit`` directives and resolvable include/``do`` calls have no variable
  target, so they are recorded as ``no_variable_attribution`` unresolved blocks
  (the include additionally traverses its target).
- A missing, macro-built, or unresolvable include target yields
  ``unresolved_include`` at the caller.
- A macro reference (backtick/local, ``$`` global, or macro-built token) yields
  ``macro_or_loop`` covering the nearest enclosing brace block when one
  exists, else the statement itself.
- Unterminated ``{`` blocks and unterminated ``/*`` comments yield
  ``unterminated_structure`` from the opening construct through EOF.
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

#: Effects that model no supported variable behaviour in the generic grammar.
_UNSUPPORTED_EFFECTS = ("none", "restructures")

#: Defensive cap on include/do nesting depth (avoids unbounded recursion on
#: pathological files; reported as ``unresolved_include`` when exceeded).
_MAX_INCLUDE_DEPTH = 64


@dataclass
class ParsedFile:
    """Full parse of one source file."""

    path: str
    provenance: SourceProvenance
    attributions: list[RangeAttribution] = field(default_factory=list)
    lifecycle: dict[str, list[LineRange]] = field(default_factory=dict)
    parents: dict[str, list[str]] = field(default_factory=dict)
    unresolved: list[UnresolvedBlock] = field(default_factory=list)
    executable_lines: list[int] = field(default_factory=list)
    attributed_lines: set[int] = field(default_factory=set)
    unresolved_lines: set[int] = field(default_factory=set)


@dataclass
class ParsedGraph:
    """Merged parse of a root source and its resolved includes."""

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
    """Parses files and their include graphs against a registry adapter."""

    def __init__(
        self,
        registry: RegistryAdapter,
        *,
        include_labels: bool = False,
    ) -> None:
        self.registry = registry
        self.include_labels = include_labels
        self._active_paths: set[str] = set()

    # -- public -----------------------------------------------------------

    def parse_graph(self, root_path: str | os.PathLike[str]) -> ParsedGraph:
        """Parse the root file and, depth-first, all resolvable includes."""
        self._active_paths = set()
        root = str(root_path)
        graph = ParsedGraph(root_path=root)
        self._parse_file_into(root, graph, traversal_index=0)
        graph.attributions = _flatten(graph.files, "attributions")
        graph.executable_lines = _flatten(graph.files, "executable_lines")
        graph.attributed_lines = (
            set().union(*(f.attributed_lines for f in graph.files))
            if graph.files
            else set()
        )
        graph.unresolved_lines = (
            set().union(*(f.unresolved_lines for f in graph.files))
            if graph.files
            else set()
        )
        for f in graph.files:
            for var, ranges in f.lifecycle.items():
                graph.lifecycle.setdefault(var, []).extend(ranges)
            for var, parents in f.parents.items():
                for parent in parents:
                    if parent not in graph.parents.setdefault(var, []):
                        graph.parents[var].append(parent)
            graph.unresolved.extend(f.unresolved)
        return graph

    # -- internals --------------------------------------------------------

    def _parse_file_into(
        self,
        path: str,
        graph: ParsedGraph,
        *,
        traversal_index: int,
        depth: int = 0,
    ) -> ParsedFile:
        text = read_source(path)
        scan_result = scan(text)
        statements, brace_blocks, _, used_delimit, unterminated_comment = assemble(
            scan_result
        )
        norm_path = os.path.normpath(path)
        canonical = os.path.realpath(norm_path)
        self._active_paths.add(canonical)
        line_count = len(text.splitlines())
        provenance = SourceProvenance(
            path=norm_path,
            line_count=line_count,
            used_delimit=used_delimit,
            traversal_index=traversal_index,
        )
        parsed = ParsedFile(
            path=norm_path,
            provenance=provenance,
            executable_lines=scan_result.executable_line_numbers(),
        )
        graph.files.append(parsed)

        last_line = max(line_count, 1)
        covered_blocks: list[tuple[int, int | None]] = []
        include_targets: list[tuple[Statement, str]] = []

        # Claim macro-bearing brace blocks as one unit BEFORE classifying their
        # members. This keeps the executable-line partition disjoint: no
        # statement inside a macro block is ever attributed individually, even
        # when a non-macro statement precedes the macro one in the same block.
        for block in brace_blocks:
            if block.end_line is None:
                continue
            members = [
                s
                for s in statements
                if block.start_line <= s.start_line <= block.end_line
            ]
            if any(self._contains_macro(s.code) for s in members):
                covered_blocks.append((block.start_line, block.end_line))
                self._record_range_unresolved(
                    parsed,
                    start_line=block.start_line,
                    end_line=block.end_line,
                    reason="macro_or_loop",
                    context={
                        "enclosing_block": f"{block.start_line}-{block.end_line}"
                    },
                )

        # Claim unterminated structures (open ``{`` blocks and unterminated
        # ``/*`` comments) BEFORE classifying members, so the opening line's
        # already-executable code is never both attributed and unresolved.
        for block in brace_blocks:
            if block.end_line is None:
                covered_blocks.append((block.start_line, None))
                self._record_range_unresolved(
                    parsed,
                    start_line=block.start_line,
                    end_line=max(last_line, block.start_line),
                    reason="unterminated_structure",
                    context={"structure": "brace_block"},
                )
        if unterminated_comment is not None:
            covered_blocks.append((unterminated_comment, None))
            parsed.unresolved_lines.update(range(unterminated_comment, last_line + 1))
            parsed.unresolved.append(
                UnresolvedBlock(
                    range=LineRange(
                        source=norm_path,
                        start_line=unterminated_comment,
                        end_line=last_line,
                    ),
                    reason="unterminated_structure",
                    context={"structure": "block_comment"},
                )
            )
            graph.block_comment_unterminated = True

        for stmt in statements:
            if self._is_inside_covered(stmt, covered_blocks):
                continue
            if stmt.band == "directive":
                self._record_unresolved(
                    parsed,
                    stmt,
                    "no_variable_attribution",
                    {"directive": stmt.directive or ""},
                )
                continue
            self._classify_statement(parsed, stmt, include_targets)

        # Recurse into resolvable includes depth-first.
        base_dir = os.path.dirname(norm_path)
        for stmt, target in include_targets:
            if not target or self._contains_macro(target):
                self._record_unresolved(
                    parsed,
                    stmt,
                    "unresolved_include",
                    {"target": target, "reason": "macro_or_missing"},
                )
                continue
            child_path = self._resolve_path(target, base_dir)
            child_canonical = (
                os.path.realpath(child_path)
                if os.path.exists(child_path)
                else child_path
            )
            if child_canonical in self._active_paths:
                self._record_unresolved(
                    parsed,
                    stmt,
                    "unresolved_include",
                    {"target": target, "reason": "cycle_or_repeat"},
                )
                continue
            if not os.path.isfile(child_path):
                self._record_unresolved(
                    parsed,
                    stmt,
                    "unresolved_include",
                    {"target": target, "reason": "missing"},
                )
                continue
            if depth >= _MAX_INCLUDE_DEPTH:
                self._record_unresolved(
                    parsed,
                    stmt,
                    "unresolved_include",
                    {"target": target, "reason": "depth_exceeded"},
                )
                continue
            self._record_unresolved(
                parsed,
                stmt,
                "no_variable_attribution",
                {"include": target, "resolved": "true"},
            )
            self._parse_file_into(
                child_path, graph, traversal_index=len(graph.files), depth=depth + 1
            )

        return parsed

    def _resolve_path(self, target: str, base_dir: str) -> str:
        if os.path.isabs(target):
            return target
        return os.path.join(base_dir, target)

    def _is_inside_covered(
        self, stmt: Statement, covered_blocks: list[tuple[int, int | None]]
    ) -> bool:
        for start, end in covered_blocks:
            if end is None:
                if stmt.start_line >= start:
                    return True
            elif start <= stmt.start_line <= end:
                return True
        return False

    def _contains_macro(self, text: str) -> bool:
        """True when text carries a macro reference (backtick, ``$``, ``'``)."""
        return any(ch in text for ch in ("`", "$", "'"))

    def _classify_statement(
        self,
        parsed: ParsedFile,
        stmt: Statement,
        include_targets: list[tuple[Statement, str]],
    ) -> None:
        # --- registry degraded or unknown command --------------------
        if not self.registry.available:
            self._record_unresolved(
                parsed,
                stmt,
                "unknown_command",
                {"registry": "unavailable"},
            )
            return

        try:
            cmd_token, rest = self._split_command(stmt.code)
        except RegistryIncompatibilityError as exc:
            self._record_unresolved(
                parsed,
                stmt,
                "unknown_command",
                {"registry_error": str(exc)[:200]},
            )
            return

        if cmd_token is None:
            self._record_unresolved(
                parsed, stmt, "unsupported_syntax", {"reason": "no_command_token"}
            )
            return

        canonical = self.registry.canonical_command(cmd_token)
        if canonical is None:
            self._record_unresolved(
                parsed, stmt, "unknown_command", {"token": cmd_token}
            )
            return

        # include / nested do -------------------------------------------------
        if self._call_is_include(canonical):
            include_targets.append((stmt, self._include_path(stmt) or ""))
            return

        # effect -----------------------------------------------------------------
        try:
            effect = self.registry.variable_effect(canonical)
        except RegistryIncompatibilityError as exc:
            self._record_unresolved(
                parsed,
                stmt,
                "unsupported_effect",
                {"registry_error": str(exc)[:200]},
            )
            return

        if effect in _UNSUPPORTED_EFFECTS:
            self._record_unresolved(
                parsed,
                stmt,
                "unsupported_effect",
                {"command": canonical, "effect": effect},
            )
            return

        shape = grammar.analyze(rest)

        # A macro reference outside any pre-claimed brace block produces a
        # statement-scope macro_or_loop. Macro references inside a brace block
        # were already claimed as one unresolved block covering the whole block
        # in ``_parse_file_into``, so those lines never reach classification.
        if shape.has_macro or self._contains_macro(stmt.code):
            self._record_unresolved(
                parsed,
                stmt,
                "macro_or_loop",
                {"enclosing_block": "none"},
            )
            return

        # effect + shape application -------------------------------------------
        dispositions = self._apply_effect(canonical, effect, shape)
        if dispositions is None:
            self._record_unresolved(
                parsed,
                stmt,
                "unsupported_syntax",
                {"command": canonical, "effect": effect, "shape": shape.kind},
            )
            return

        targets, sources = dispositions
        if not targets and not sources:
            self._record_unresolved(
                parsed,
                stmt,
                "no_variable_attribution",
                {"command": canonical},
            )
            return

        self._apply_attribution(parsed, stmt, targets, sources)

    def _apply_attribution(
        self,
        parsed: ParsedFile,
        stmt: Statement,
        targets: list[tuple[str, str]],
        sources: list[str],
    ) -> None:
        """Record lifecycle target and dependency-reference attributions."""
        line_range = LineRange(
            source=parsed.path,
            start_line=stmt.start_line,
            end_line=stmt.end_line,
            comment_start_line=stmt.comment_start_line,
            comment_end_line=stmt.comment_end_line,
        )
        for var, kind in targets:
            parsed.attributions.append(
                RangeAttribution(range=line_range, variable=var, kind=kind)
            )
            parsed.attributed_lines.update(range(stmt.start_line, stmt.end_line + 1))
            if kind != "labelled" or self.include_labels:
                parsed.lifecycle.setdefault(var, []).append(line_range)
            for source in sources:
                if source not in parsed.parents.setdefault(var, []):
                    parsed.parents[var].append(source)
        for source in sources:
            parsed.attributions.append(
                RangeAttribution(range=line_range, variable=source, kind="referenced")
            )
            parsed.attributed_lines.update(range(stmt.start_line, stmt.end_line + 1))

    def _apply_effect(
        self, command: str, effect: str, shape: grammar.Shape
    ) -> tuple[list[tuple[str, str]], list[str]] | None:
        """Map effect + shape to (targets, sources), or None when unsupported.

        ``command`` is unused for behaviour, matching the command-agnostic
        design; it is kept so callers can record diagnostics.
        """
        if effect == "creates":
            if shape.kind in ("assignment", "gen_option"):
                return (_pairs(shape.targets, "created"), shape.sources)
            if shape.kind == "varlist" and len(shape.targets) == 2:
                # ordered pair: second side is the created target
                return ([(shape.targets[1], "created")], [shape.targets[0]])
            return None
        if effect == "modifies":
            if shape.kind in ("assignment", "gen_option"):
                return (_pairs(shape.targets, "modified"), shape.sources)
            if shape.kind == "varlist":
                return (_pairs(shape.targets, "modified"), [])
            return None
        if effect == "renames":
            if shape.kind == "varlist" and len(shape.targets) == 2:
                return ([(shape.targets[1], "created")], [shape.targets[0]])
            return None
        if effect == "removes":
            if shape.kind == "varlist":
                return (_pairs(shape.targets, "dropped"), [])
            # e.g. ``drop _all`` -- no extractable variable target.
            return ([], [])
        if effect == "labels":
            # label target: the locally grammatical variable position is the
            # final variable-like token (subcommand keyword precedes it).
            if shape.kind == "varlist" and shape.targets:
                return ([(shape.targets[-1], "labelled")], [])
            return None
        return None

    # -- helpers ---------------------------------------------------------

    def _call_is_include(self, canonical: str) -> bool:
        try:
            return bool(self.registry.is_include(canonical))
        except Exception:  # noqa: BLE001 - degrade on any API mismatch
            return False

    def _include_path(self, stmt: Statement) -> str | None:
        """Extract an include target path.

        Prefers the first quoted (standard or compound) string literal in the
        statement's raw text; falls back to the first code token after the
        command for legal Stata unquoted include targets (``include lib.do``).
        """
        text = stmt.raw
        n = len(text)
        i = 0
        while i < n:
            ch = text[i]
            if ch == '"':
                j = i + 1
                parts: list[str] = []
                while j < n:
                    if text[j] == '"':
                        return "".join(parts)
                    parts.append(text[j])
                    j += 1
                return "".join(parts)
            if ch == "`" and text[i + 1 : i + 2] == '"':
                j = i + 2
                parts = []
                while j < n:
                    if text[j : j + 2] == '"\'':
                        return "".join(parts)
                    parts.append(text[j])
                    j += 1
                return "".join(parts)
            i += 1
        # No quoted literal: try an unquoted target in the code-only text.
        cmd, rest = self._split_command(stmt.code)
        if cmd is not None and rest.strip():
            tokens = grammar.tokenize(rest)
            if tokens:
                candidate = tokens[0].text
                if not candidate.startswith("_"):
                    return candidate
        return None

    def _split_command(self, code: str) -> tuple[str | None, str]:
        """Strip prefixes via the registry; return (command_token, rest)."""
        tokens = grammar.tokenize(code)
        if not tokens:
            return None, ""
        idx = 0
        while idx < len(tokens):
            t = tokens[idx]
            if t.text == ":":
                idx += 1
                continue
            if self.registry.is_prefix(t.text):
                idx += 1
                j = idx
                while j < len(tokens) and tokens[j].text != ":":
                    j += 1
                if j < len(tokens):
                    idx = j + 1
                    continue
                break
            break
        if idx >= len(tokens):
            return None, ""
        cmd = tokens[idx].text
        rest = code[tokens[idx].end :].lstrip()
        return cmd, rest

    def _record_unresolved(
        self,
        parsed: ParsedFile,
        stmt: Statement,
        reason: str,
        context: dict[str, str],
    ) -> None:
        parsed.unresolved_lines.update(range(stmt.start_line, stmt.end_line + 1))
        parsed.unresolved.append(
            UnresolvedBlock(
                range=LineRange(
                    source=parsed.path,
                    start_line=stmt.start_line,
                    end_line=stmt.end_line,
                    comment_start_line=stmt.comment_start_line,
                    comment_end_line=stmt.comment_end_line,
                ),
                reason=reason,  # type: ignore[arg-type]
                context=context,
                statement=stmt.code,
            )
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
        parsed.unresolved_lines.update(range(start_line, end_line + 1))
        parsed.unresolved.append(
            UnresolvedBlock(
                range=LineRange(
                    source=parsed.path,
                    start_line=start_line,
                    end_line=end_line,
                ),
                reason=reason,  # type: ignore[arg-type]
                context=context,
                statement=statement,
            )
        )


def _pairs(items: list[str], kind: str) -> list[tuple[str, str]]:
    return [(item, kind) for item in items]


def _flatten(files: list[ParsedFile], attr: str) -> list[Any]:
    out: list[Any] = []
    for f in files:
        out.extend(getattr(f, attr))
    return out
