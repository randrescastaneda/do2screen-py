"""Lossless physical-line scanner and lexical masks.

The scanner reads a Stata do file as text and marks, for every physical line,
which characters are *code* and which are *not code* (string content, comments,
and continuation tails). Masks are same-length strings of ``C`` (code) and
``N`` (non-code) so original offsets are preserved. Statement assembly and
grammar rely on these masks and never consult the registry.

Handled lexical forms:

- Standard double-quoted strings ``"..."``.
- Compound strings ```` `"..."' `` `` (open: backtick + double quote; close:
  double quote + apostrophe). Embedded quotes/apostrophes/backticks/comments
  inside a compound string do not break masking.
- Line comments: ``*`` at statement start, and ``//``.
- ``///`` continuation markers (the three slashes are code; the rest of the
  physical line after them is ignored).
- Inline and multiline block comments ``/* ... */``.
"""

from __future__ import annotations

import sys
from dataclasses import dataclass, field
from pathlib import Path

#: Mask character for executable code.
CODE = "C"
#: Mask character for non-code (string/comment) content.
NON = "N"


@dataclass(frozen=True)
class ScannedLine:
    """One physical line with its same-length code mask."""

    text: str
    code_mask: str
    line_no: int

    def has_code(self) -> bool:
        """True when the line contains any non-whitespace code character."""
        return any(
            ch == CODE and not self.text[i].isspace()
            for i, ch in enumerate(self.code_mask)
        )


@dataclass
class ScanResult:
    """Result of scanning a whole source."""

    lines: list[ScannedLine] = field(default_factory=list)
    #: Physical line where an unterminated ``/*`` block comment began, or None.
    unterminated_block_comment_start: int | None = None

    def executable_line_numbers(self) -> list[int]:
        """Physical line numbers with at least one non-whitespace code char."""
        return [line.line_no for line in self.lines if line.has_code()]


def scan(text: str) -> ScanResult:
    """Scan decoded source text into per-line code masks.

    Args:
        text: Decoded source text (BOM already stripped). No network,
            randomness, or environment-dependent behaviour: identical input
            always produces identical output.
    """
    result = ScanResult()
    prev_in_block = False
    block_start: int | None = None
    for idx, raw in enumerate(text.splitlines(), start=1):
        state = _start_line()
        _scan_line(raw, state, in_block_comment_prev=prev_in_block)
        cur_in_block = state["in_block_comment"]
        if cur_in_block and not prev_in_block:
            block_start = idx
        if not cur_in_block:
            block_start = None
        prev_in_block = cur_in_block
        result.lines.append(
            ScannedLine(text=raw, code_mask="".join(state["mask"]), line_no=idx)
        )
    if prev_in_block:
        result.unterminated_block_comment_start = block_start
    return result


def _start_line() -> dict:
    return {"mask": [], "in_block_comment": False}


def _scan_line(
    line: str,
    state: dict,
    *,
    in_block_comment_prev: bool,
) -> None:
    """Fill ``state`` in place with the mask for one line.

    ``state`` persists only within the call; block-comment status crosses lines
    via ``in_block_comment_prev`` / ``state["in_block_comment"]``.
    """
    i = 0
    length = len(line)
    in_string = None  # None | "standard" | "compound"
    line_comment = False
    in_block = in_block_comment_prev
    first_token = True

    mask: list[str] = []

    def non(chars: int) -> None:
        for _ in range(chars):
            mask.append(NON)

    def code(chars: int) -> None:
        for _ in range(chars):
            mask.append(CODE)

    while i < length:
        ch = line[i]
        if in_string == "standard":
            if ch == '"':
                in_string = None
                non(1)
            else:
                non(1)
            i += 1
            continue
        if in_string == "compound":
            if line[i : i + 2] == '"\'':
                in_string = None
                non(2)
                i += 2
            else:
                non(1)
                i += 1
            continue
        if in_block:
            if line[i : i + 2] == "*/":
                in_block = False
                non(2)
                i += 2
            else:
                non(1)
                i += 1
            continue
        if line_comment:
            non(1)
            i += 1
            continue
        # --- code state ---
        if line[i : i + 2] == "/*":
            in_block = True
            non(2)
            first_token = False
            i += 2
            continue
        if line[i : i + 3] == "///":
            # Continuation marker: the slashes are code, the rest is ignored.
            code(3)
            first_token = False
            i += 3
            line_comment = True
            continue
        if line[i : i + 2] == "//":
            line_comment = True
            non(2)
            first_token = False
            i += 2
            continue
        if ch == '"':
            in_string = "standard"
            non(1)
            first_token = False
            i += 1
            continue
        if ch == "`" and line[i + 1 : i + 2] == '"':
            in_string = "compound"
            non(2)
            first_token = False
            i += 2
            continue
        if ch == "*" and first_token:
            # ``*`` beginning a statement starts a full-line comment.
            line_comment = True
            non(1)
            i += 1
            continue
        # Remaining: macro references (backtick/apostrophe locals, $globals) are
        # code; the grammar inspects them structurally without expansion.
        if not ch.isspace():
            first_token = False
        code(1)
        i += 1

    state["in_block_comment"] = in_block
    state["mask"] = mask


def read_source(path: str | Path) -> str:
    """Read and decode a source file deterministically.

    Uses ``utf-8-sig`` (strips a leading Windows BOM) with an ``errors="replace"``
    policy so undecodable bytes never crash the caller. A diagnostic is written
    to stderr once when replacement characters were introduced, so the CLI never
    fails on a malformed file and the caller can still account for the line.
    """
    raw = Path(path).read_bytes()
    text = raw.decode("utf-8-sig", errors="replace")
    if "\ufffd" in text:
        print(
            f"do2screen: warning: {path}: undecodable bytes replaced "
            f"(U+FFFD) while reading",
            file=sys.stderr,
        )
    return text
