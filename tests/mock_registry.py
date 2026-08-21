"""A stub implementation of the ``stata_registry`` contract for tests.

The optional upstream ``stata-command-registry`` dependency is not required for
unit tests, so tests exercise the parser against this mock. It implements the
documented adapter contract:
``canonical_command``, ``is_prefix``, ``variable_effect``, plus the optional
``is_include`` extension. It intentionally mirrors the abbreviation rules that
matter for the acceptance tests (for example ``generate`` abbreviates to
``g``/``ge``/``gen`` while ``replace`` cannot be abbreviated).
"""

from __future__ import annotations

#: canonical command -> variable_effect
_COMMANDS = {
    "generate": "creates",
    "clonevar": "creates",
    "replace": "modifies",
    "rename": "renames",
    "drop": "removes",
    "label": "labels",
    "summarize": "none",
    "reshape": "restructures",
}

#: token abbreviation -> canonical command
_ABBREVIATIONS = {
    "g": "generate",
    "ge": "generate",
    "gen": "generate",
}

_PREFIXES = {"by", "bysort"}

_INCLUDES = {"include", "do", "run"}


class MockStataRegistry:
    """Deterministic stand-in for ``stata_registry``."""

    def __repr__(self) -> str:
        return "<MockStataRegistry>"

    def canonical_command(self, token: str) -> str | None:
        if token in _COMMANDS:
            return token
        if token in _ABBREVIATIONS:
            return _ABBREVIATIONS[token]
        if token in _INCLUDES:
            return token
        return None

    def is_prefix(self, token: str) -> bool:
        return token in _PREFIXES

    def variable_effect(self, command: str) -> str:
        canonical = self.canonical_command(command)
        if canonical is None:
            raise LookupError(f"unknown command: {command!r}")
        if canonical in _INCLUDES:
            raise LookupError(f"include driver has no variable effect: {command!r}")
        return _COMMANDS[canonical]

    def is_include(self, command: str) -> bool:
        return command in _INCLUDES
