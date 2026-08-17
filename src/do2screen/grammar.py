"""Command-agnostic structural grammar and variable-token extraction.

The registry answers *what a word is* (command, prefix, effect). This module
answers *what the shape of the text is*: where a statement starts and ends is
already resolved by :mod:`do2screen.statements`; here we extract, from the
code-only text of a statement, which variable tokens are affected (targets)
and which are input dependencies (sources), independent of the command name.

All string and comment content is already removed from ``code`` by the scanner
and statement assembler, so tokens inside strings never appear here. The
grammar implements the generic shapes described in the plan: assignment,
``gen(identifier)`` option, ordered varlist pairs, plain varlists, label
targets, and drop/remove varlists. It excludes numeric literals, function
names in call position, qualifiers (``if``/``in``), system names, and
factor/time-series prefixes, and it normalizes factor/time-series prefixes on
the variables it keeps.

No Stata command names live here.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field

# -- tokenization -----------------------------------------------------------

_SINGLE_SEPARATORS = set("(){}[],")
_OPERATORS = set("+-*/^")
_COMPARISON = set("=<>!&|~?:")


@dataclass(frozen=True)
class Token:
    """One lexical token of a statement's code-only text."""

    text: str
    start: int
    end: int


def tokenize(code: str) -> list[Token]:
    """Split code-only statement text into tokens.

    Runs of identifier characters (letters, digits, ``_``, ``#``, ``.``,
    ``$``, ``'``, backtick) form single tokens so factor/time-series prefixes
    (``i.var``, ``L.var``) and macro references (``v`x'``, ``$g``) stay whole.
    """
    tokens: list[Token] = []
    i = 0
    n = len(code)
    while i < n:
        ch = code[i]
        if ch.isspace():
            i += 1
            continue
        if ch in _SINGLE_SEPARATORS:
            tokens.append(Token(ch, i, i + 1))
            i += 1
            continue
        if ch in _OPERATORS:
            tokens.append(Token(ch, i, i + 1))
            i += 1
            continue
        if ch in _COMPARISON:
            two = code[i : i + 2]
            if two in ("==", "!=", "<=", ">=", "&&", "||"):
                tokens.append(Token(two, i, i + 2))
                i += 2
                continue
            tokens.append(Token(ch, i, i + 1))
            i += 1
            continue
        j = i
        while (
            j < n
            and code[j] not in _SINGLE_SEPARATORS
            and code[j] not in _OPERATORS
            and code[j] not in _COMPARISON
            and not code[j].isspace()
        ):
            j += 1
        tokens.append(Token(code[i:j], i, j))
        i = j
    return tokens


# -- token classification ---------------------------------------------------

_IDENT_RE = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")
_NUMERIC_RE = re.compile(
    r"^(?:[+-]?[0-9]+(?:\.[0-9]*)?(?:[eE][+-]?[0-9]+)?|\.+)$"
)
_TIME_SERIES_RE = re.compile(r"^[LDSPFbsld][0-9]{0,2}\.")
_FACTOR_RE = re.compile(
    r"^(?:(?:ib|i|c|n|o|fp|s|fc|xi)(?:\([^)]*\)|[0-9]{0,3})?\.)"
)

_OPERATOR_TEXT = set(_OPERATORS) | set("(){}[],#") | {
    "==",
    "!=",
    "<=",
    ">=",
    "&&",
    "||",
}


def is_numeric(token: str) -> bool:
    return bool(_NUMERIC_RE.match(token))


def is_macro(token: str) -> bool:
    """True when the token is or contains a macro reference."""
    return any(ch in token for ch in ("`", "$", "'"))


def _strip_time_series(token: str) -> str:
    while True:
        m = _TIME_SERIES_RE.match(token)
        if not m:
            return token
        token = token[m.end() :]


def _strip_factor(token: str) -> str:
    while True:
        m = _FACTOR_RE.match(token)
        if not m:
            return token
        token = token[m.end() :]


def normalize_vars(token: str) -> list[str]:
    """Return the underlying variable names of a token, or ``[]``.

    Strips time-series and factor-variable prefixes, splits ``#``
    interactions, and keeps only tokens that look like Stata variable names.
    """
    t = _strip_time_series(token)
    t = _strip_factor(t)
    results: list[str] = []
    for part in t.split("#"):
        p = _strip_time_series(part)
        p = _strip_factor(p)
        if _IDENT_RE.match(p):
            results.append(p)
    return results


# -- shapes ---------------------------------------------------------------

@dataclass
class Shape:
    """Structural shape of a statement's code (after the command token).

    Attributes:
        kind: One of ``"assignment"``, ``"gen_option"``, ``"varlist"``,
            ``"macro"``, or ``"none"``.
        targets: Affected (output) variable tokens, normalized.
        sources: Input dependency variable tokens, normalized, first-seen order.
        has_macro: True when any macro reference appears in the statement.
    """

    kind: str
    targets: list[str] = field(default_factory=list)
    sources: list[str] = field(default_factory=list)
    has_macro: bool = False


def _qualifier_start(tokens: list[Token]) -> int:
    """Index of the first top-level ``if``/``in`` qualifier, or len(tokens)."""
    paren = 0
    bracket = 0
    finish = len(tokens)
    for idx, tok in enumerate(tokens):
        if tok.text == "(":
            paren += 1
        elif tok.text == ")":
            paren = max(0, paren - 1)
        elif tok.text == "[":
            bracket += 1
        elif tok.text == "]":
            bracket = max(0, bracket - 1)
        if paren == 0 and bracket == 0 and tok.text in ("if", "in"):
            return idx
    return finish


def _top_level_assign(tokens: list[Token]) -> int:
    """Index of the top-level single ``=`` assignment operator, or -1."""
    paren = 0
    bracket = 0
    brace = 0
    for idx, tok in enumerate(tokens):
        if tok.text == "(":
            paren += 1
        elif tok.text == ")":
            paren = max(0, paren - 1)
        elif tok.text == "[":
            bracket += 1
        elif tok.text == "]":
            bracket = max(0, bracket - 1)
        elif tok.text == "{":
            brace += 1
        elif tok.text == "}":
            brace = max(0, brace - 1)
        if paren == 0 and bracket == 0 and brace == 0 and tok.text == "=":
            return idx
    return -1


def _variable_like_sequence(tokens: list[Token], stop: int) -> list[str]:
    """Variable-like tokens in ``tokens[:stop]``, in first-seen order.

    Excludes function names in call position (identifier followed by ``(``),
    numeric literals, system names (leading ``_``), and macro tokens.
    """
    seen: list[str] = []
    used: set[str] = set()
    for idx, tok in enumerate(tokens[:stop]):
        text = tok.text
        if text in _OPERATOR_TEXT or is_numeric(text) or text == ".":
            continue
        if idx + 1 < len(tokens) and tokens[idx + 1].text == "(":
            # Function name in call position -- not a variable reference.
            continue
        if is_macro(text):
            continue
        if text.startswith("_"):
            continue
        for var in normalize_vars(text):
            if var not in used:
                used.add(var)
                seen.append(var)
    return seen


def _find_gen_option(tokens: list[Token]) -> tuple[str | None, int]:
    """Locate a ``gen(identifier)`` option.

    Returns ``(identifier, index_of_comma_before_it)``; the index is the index
    of the top-level comma separating command arguments from options, or -1.
    """
    paren = 0
    comma_index = -1
    for idx, tok in enumerate(tokens):
        if tok.text == "(":
            paren += 1
        elif tok.text == ")":
            paren = max(0, paren - 1)
        elif tok.text == "," and paren == 0:
            comma_index = idx
        if (
            paren == 0
            and tok.text == "gen"
            and idx + 1 < len(tokens)
            and tokens[idx + 1].text == "("
        ):
            close = idx + 2
            while close < len(tokens) and tokens[close].text != ")":
                close += 1
            if close < len(tokens):
                inner = tokens[idx + 2 : close]
                ident = [t for t in inner if not is_numeric(t.text)]
                if ident and not is_macro(ident[0].text):
                    name = normalize_vars(ident[0].text)
                    if name:
                        return name[0], comma_index
    return None, -1


def analyze(code: str) -> Shape:
    """Analyze a statement's code-only text (command token already removed).

    Never guesses: when no shape matches, returns ``kind="none"`` with no
    targets and no sources. Macro presence is reported separately so the parser
    can emit ``macro_or_loop`` unresolved blocks without expanding anything.
    """
    tokens = tokenize(code)
    has_macro = any(is_macro(tok.text) for tok in tokens)

    # Assignment: LHS identifier before a top-level single ``=``.
    assign_idx = _top_level_assign(tokens)
    if assign_idx >= 0:
        targets: list[str] = []
        for back in range(assign_idx - 1, -1, -1):
            text = tokens[back].text
            if text in _OPERATOR_TEXT or is_numeric(text):
                break
            if is_macro(text) or text.startswith("_"):
                break
            names = normalize_vars(text)
            if names:
                targets = names
                break
        stop = _qualifier_start(tokens)
        rhs_count = max(0, stop - (assign_idx + 1))
        sources = _variable_like_sequence(tokens[assign_idx + 1 :], rhs_count)
        return Shape("assignment", targets=targets, sources=sources, has_macro=has_macro)

    # gen(identifier) option: created variable is the option target.
    gen_name, comma_index = _find_gen_option(tokens)
    if gen_name is not None:
        pre = tokens[:comma_index] if comma_index >= 0 else tokens
        sources = _variable_like_sequence(pre, len(pre))
        return Shape("gen_option", targets=[gen_name], sources=sources, has_macro=has_macro)

    # Plain varlist: variable-like tokens up to the first qualifier.
    stop = _qualifier_start(tokens)
    varlist = _variable_like_sequence(tokens, stop)
    if varlist:
        return Shape("varlist", targets=varlist, sources=[], has_macro=has_macro)
    if has_macro:
        return Shape("macro", targets=[], sources=[], has_macro=True)
    return Shape("none", targets=[], sources=[], has_macro=False)


def split_command(code: str) -> tuple[str | None, str]:
    """Return ``(command_token, rest_code)`` for a statement's code-only text."""
    tokens = tokenize(code)
    if not tokens:
        return None, ""
    cmd = tokens[0].text
    rest = code[tokens[0].end :].lstrip()
    return cmd, rest
