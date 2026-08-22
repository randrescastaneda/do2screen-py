"""Delimiter-aware statement assembly.

The scanner produces per-line code masks. This module groups code into
*statements* honoring Stata's two statement-delimiter modes:

- carriage-return (CR) mode: a statement ends at the end of a physical line
  unless the line ends with a ``///`` continuation marker;
- semicolon (``#delimit ;``) mode: a statement ends at a ``;`` in code outside
  a string or comment; statements may span many lines.

``#delimit ;``, ``#delimit cr``, and ``#delimit clear`` are recognized
structurally and switch modes after the directive's own statement completes.
Balanced brace blocks (``foreach``/``forvalues``/``while``/``mata`` bodies,
matrix literals) are indexed from code-mask braces so the parser can attribute
macro-built unresolved blocks at block granularity.

Each emitted statement carries two views:

- ``code``: the code-only text (string/comment content removed, continuation
  markers stripped) -- what the grammar sees. A variable name inside a string
  simply never appears here.
- ``raw`` / ``raw_mask``: the original text with string/comment content
  preserved and masked -- what the parser uses to extract include paths from
  string literals and to display statement text.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from do2screen.scanner import CODE, ScannedLine, ScanResult

CR = "cr"
SEMICOLON = ";"

#: Directive tokens that reset to carriage-return mode.
_CR_DIRECTIVES = {"cr", "clear"}


@dataclass
class BraceBlock:
    """An indexed brace block in physical line space."""

    start_line: int
    end_line: int | None = None  # None when the block is unterminated


@dataclass
class Statement:
    """One assembled executable statement.

    Attributes:
        code: Code-only text of the member lines (string/comment content and
            continuation markers removed; member segments joined by spaces).
        raw: Original text of the member lines with all content preserved
            (comments/strings kept), joined by spaces.
        raw_mask: Same-length mask for ``raw`` (``C``/``N`` per character).
        start_line: First physical line of the statement.
        end_line: Last physical line of the statement.
        member_lines: Distinct physical line numbers contributing code.
        comment_start_line: First line of the contiguous full-line comment
            immediately preceding the statement, if any.
        comment_end_line: Last line of that preceding comment.
        delimit: Delimiter mode in effect when the statement was terminated.
        brace_stack: Enclosing open brace blocks, outermost first.
        band: ``"directive"`` for ``#delimit`` statements, else ``"statement"``.
        directive: Parsed ``#delimit`` target (``";"``, ``cr``, ``clear``).
    """

    code: str
    raw: str
    raw_mask: str
    start_line: int
    end_line: int
    member_lines: list[int] = field(default_factory=list)
    comment_start_line: int | None = None
    comment_end_line: int | None = None
    delimit: str = CR
    brace_stack: list[BraceBlock] = field(default_factory=list)
    band: str = "statement"
    directive: str | None = None


def _code_only(text: str, mask: str) -> str:
    """Return only the code characters of a (text, mask) pair."""
    return "".join(ch for ch, m in zip(text, mask) if m == CODE)


def _is_comment_line(line: ScannedLine) -> bool:
    """True when a line is a full-line comment (non-blank, no code)."""
    stripped = line.text.strip()
    if not stripped:
        return False
    if line.has_code():
        return False
    return stripped.startswith(("*", "//", "/*"))


def _continuation_info(
    text: str, mask: str
) -> tuple[str, str, bool]:
    """Return (head_text, head_mask, continued).

    Strips a trailing ``///`` continuation marker (and the ignored tail after
    it) when the marker lies at the end of the line's code region.
    """
    i = len(mask)
    while i > 0 and mask[i - 1] != CODE:
        i -= 1
    j = i
    while j > 0 and mask[j - 1] == CODE:
        j -= 1
    code_run = text[j:i]
    if code_run.endswith("///") and len(code_run) >= 3:
        return text[: i - 3], mask[: i - 3], True
    return text, mask, False


def _split_semicolon(
    text: str, mask: str
) -> list[tuple[str, str]]:
    """Split a (text, mask) line at code-level ``;`` terminators.

    Each ``;`` that is CODE ends the current segment. Returns segments without
    the ``;`` characters; transitions between segments mark a termination.
    """
    segments: list[tuple[str, str]] = []
    cur_t: list[str] = []
    cur_m: list[str] = []
    for ch, m in zip(text, mask):
        if m == CODE and ch == ";":
            segments.append(("".join(cur_t), "".join(cur_m)))
            cur_t = []
            cur_m = []
        else:
            cur_t.append(ch)
            cur_m.append(m)
    segments.append(("".join(cur_t), "".join(cur_m)))
    return segments


def assemble(
    scan_result: ScanResult,
) -> tuple[list[Statement], list[BraceBlock], str, bool, int | None]:
    """Assemble statements from a scan result.

    Returns:
        A ``(statements, brace_blocks, final_mode, used_delimit,
        unterminated_block_comment_start)`` tuple. ``brace_blocks`` includes
        unterminated blocks with ``end_line=None``. The final item is the
        physical line where an unterminated ``/*`` block comment began, or
        ``None`` when all block comments are closed.
    """
    statements: list[Statement] = []
    lines = scan_result.lines
    by_line = {line.line_no: i for i, line in enumerate(lines)}

    mode = CR
    used_delimit = False

    pending_code: str | None = None
    pending_raw: list[str] = []
    pending_raw_mask: list[str] = []
    pending_lines: list[int] = []

    def comment_range_before(start_line: int) -> tuple[int | None, int | None]:
        line_no = start_line - 1
        end: int | None = None
        start: int | None = None
        while line_no >= 1:
            idx = by_line.get(line_no)
            if idx is None or not _is_comment_line(lines[idx]):
                break
            if end is None:
                end = line_no
            start = line_no
            line_no -= 1
        return start, end

    def clear_pending() -> None:
        nonlocal pending_code, pending_raw, pending_raw_mask, pending_lines
        pending_code = None
        pending_raw = []
        pending_raw_mask = []
        pending_lines = []

    def emit(
        code: str,
        raw: list[str],
        raw_mask: list[str],
        member_lines: list[int],
        stmt_mode: str,
    ) -> None:
        code = " ".join(code.split())
        if not code:
            return
        raw_text = " ".join(raw)
        raw_mask_text = "N".join(raw_mask) if raw_mask else ""
        start_line = member_lines[0]
        end_line = member_lines[-1]
        cs, ce = comment_range_before(start_line)
        statements.append(
            Statement(
                code=code,
                raw=raw_text,
                raw_mask=raw_mask_text,
                start_line=start_line,
                end_line=end_line,
                member_lines=list(member_lines),
                comment_start_line=cs,
                comment_end_line=ce,
                delimit=stmt_mode,
            )
        )

    def append_cr(
        text: str,
        mask: str,
        line_no: int,
        continued: bool = False,
    ) -> None:
        nonlocal pending_code, pending_raw, pending_raw_mask, pending_lines
        code = _code_only(text, mask)
        if not code.strip():
            return
        if pending_code is None:
            pending_code = code
            pending_raw = [text]
            pending_raw_mask = [mask]
            pending_lines = [line_no]
        else:
            pending_code += " " + code
            pending_raw.append(text)
            pending_raw_mask.append(mask)
            if pending_lines[-1] != line_no:
                pending_lines.append(line_no)
        if not continued:
            emit(pending_code, pending_raw, pending_raw_mask, pending_lines, CR)
            clear_pending()

    def append_semicolon_segment(
        text: str,
        mask: str,
        line_no: int,
        terminated: bool,
    ) -> None:
        nonlocal pending_code, pending_raw, pending_raw_mask, pending_lines
        code = _code_only(text, mask)
        if not code.strip():
            return
        if pending_code is None:
            pending_code = code
            pending_raw = [text]
            pending_raw_mask = [mask]
            pending_lines = [line_no]
        else:
            pending_code += " " + code
            pending_raw.append(text)
            pending_raw_mask.append(mask)
            if pending_lines[-1] != line_no:
                pending_lines.append(line_no)
        if terminated:
            emit(pending_code, pending_raw, pending_raw_mask, pending_lines, SEMICOLON)
            clear_pending()

    def raw_index_after_code(text: str, mask: str, code_count: int) -> int:
        seen = 0
        for index, marker in enumerate(mask):
            if marker == CODE:
                seen += 1
                if seen == code_count:
                    return index + 1
        return len(text)

    def directive_parts(
        text: str,
        mask: str,
    ) -> tuple[str, str, str, str, str, str] | None:
        """Return directive and physical prefix/tail when a piece starts with it."""
        code = _code_only(text, mask)
        stripped = code.lstrip()
        if not stripped.lower().startswith("#delimit"):
            return None
        after = stripped[len("#delimit") :]
        if after and not after[0].isspace() and not after.startswith(";"):
            return None
        leading = len(code) - len(stripped)
        lead_ws = len(after) - len(after.lstrip())
        token_area = after[lead_ws:]
        if token_area.startswith(";"):
            directive = ";"
            token_len = 1
        else:
            directive = token_area.split(None, 1)[0] if token_area.strip() else ""
            token_len = len(directive)
        consumed = leading + len("#delimit") + lead_ws + token_len
        split = raw_index_after_code(text, mask, consumed)
        prefix_text = text[:split]
        prefix_mask = mask[:split]
        tail_text = text[split:]
        tail_mask = mask[split:]
        directive_code = stripped[: len("#delimit") + lead_ws + token_len].strip()
        return directive, prefix_text, prefix_mask, tail_text, tail_mask, directive_code

    def add_directive(
        line_no: int,
        prefix_text: str,
        prefix_mask: str,
        directive: str,
        directive_code: str,
    ) -> None:
        nonlocal mode, used_delimit
        cs, ce = comment_range_before(line_no)
        statements.append(
            Statement(
                code=directive_code,
                raw=prefix_text,
                raw_mask=prefix_mask,
                start_line=line_no,
                end_line=line_no,
                member_lines=[line_no],
                comment_start_line=cs,
                comment_end_line=ce,
                delimit=CR,
                band="directive",
                directive=directive,
            )
        )
        if directive == ";":
            mode = SEMICOLON
            used_delimit = True
        elif directive in _CR_DIRECTIVES:
            mode = CR

    def process_semicolon_piece(text: str, mask: str, line_no: int) -> None:
        """Process semicolon-separated pieces, preserving raw masks and directives."""
        segments = _split_semicolon(text, mask)
        for index, (segment_text, segment_mask) in enumerate(segments):
            terminated = index < len(segments) - 1
            parts = directive_parts(segment_text, segment_mask)
            if parts is not None:
                directive, prefix_text, prefix_mask, tail_text, tail_mask, directive_code = parts
                add_directive(line_no, prefix_text, prefix_mask, directive, directive_code)
                if _code_only(tail_text, tail_mask).strip():
                    if mode == SEMICOLON:
                        process_semicolon_piece(tail_text, tail_mask, line_no)
                    else:
                        append_cr(tail_text, tail_mask, line_no)
                continue
            if mode == SEMICOLON:
                append_semicolon_segment(segment_text, segment_mask, line_no, terminated)
            else:
                append_cr(segment_text, segment_mask, line_no)

    for line in lines:
        head_text, head_mask, continued = _continuation_info(
            line.text, line.code_mask
        )
        if mode == CR:
            parts = directive_parts(head_text, head_mask)
            if parts is not None and pending_code is None:
                directive, prefix_text, prefix_mask, tail_text, tail_mask, directive_code = parts
                add_directive(
                    line.line_no,
                    prefix_text,
                    prefix_mask,
                    directive,
                    directive_code,
                )
                if _code_only(tail_text, tail_mask).strip():
                    if mode == SEMICOLON:
                        process_semicolon_piece(tail_text, tail_mask, line.line_no)
                    else:
                        append_cr(tail_text, tail_mask, line.line_no, continued)
                continue
            append_cr(head_text, head_mask, line.line_no, continued)
        else:
            process_semicolon_piece(head_text, head_mask, line.line_no)

    if pending_code is not None and pending_code.strip():
        emit(pending_code, pending_raw, pending_raw_mask, pending_lines, mode)

    brace_blocks, per_stmt_stacks = _index_braces(statements)
    for stmt, stack in zip(statements, per_stmt_stacks):
        stmt.brace_stack = stack
    return (
        statements,
        brace_blocks,
        mode,
        used_delimit,
        scan_result.unterminated_block_comment_start,
    )


def _index_braces(
    statements: list[Statement],
) -> tuple[list[BraceBlock], list[list[BraceBlock]]]:
    blocks: list[BraceBlock] = []
    stack: list[BraceBlock] = []
    stacks_by_stmt: list[list[BraceBlock]] = []

    for stmt in statements:
        stacks_by_stmt.append(list(stack))
        for ch in stmt.code:
            if ch == "{":
                stack.append(BraceBlock(start_line=stmt.start_line))
            elif ch == "}" and stack:
                opened = stack.pop()
                opened.end_line = stmt.end_line
                blocks.append(opened)
    for opened in stack:
        blocks.append(BraceBlock(start_line=opened.start_line, end_line=None))
    return blocks, stacks_by_stmt
