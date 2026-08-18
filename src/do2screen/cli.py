"""JSON-only command-line interface.

``do2screen PATH VARIABLE [--no-follow-parents] [--labels] [--indent N]``

Writes exactly one ``TraceResult`` JSON document to stdout and any diagnostics
to stderr. Exit codes: 0 on success, 2 on usage/argument errors, and 1 on
unreadable files or registry incompatibility. Deterministic and offline.
"""

from __future__ import annotations

import argparse
import json
import os
import re
import sys

from do2screen.registry import RegistryIncompatibilityError
from do2screen.trace import trace

#: Rejects variable arguments that cannot name a Stata variable.
_VARIABLE_RE = re.compile(r"^[^ \t\n\r,;()=]+$")


def build_parser() -> argparse.ArgumentParser:
    """Build the argument parser for the ``do2screen`` command."""
    parser = argparse.ArgumentParser(
        prog="do2screen",
        description=(
            "Trace how a variable is built inside a Stata do file, reporting "
            "physical source line ranges."
        ),
    )
    parser.add_argument("path", help="Path to the Stata do file.")
    parser.add_argument("variable", help="Variable name to trace.")
    parser.add_argument(
        "--no-follow-parents",
        action="store_true",
        help="Do not resolve ancestor variables (leaves `ancestors` empty).",
    )
    parser.add_argument(
        "--labels",
        action="store_true",
        help="Include label lifecycle events in the traced slices.",
    )
    parser.add_argument(
        "--indent",
        type=int,
        default=2,
        help="JSON indentation level (default: 2).",
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    """Run the ``do2screen`` CLI.

    Args:
        argv: Optional argument list; ``None`` reads ``sys.argv[1:]``.

    Returns:
        Exit code: ``0`` success, ``1`` unreadable file or registry
        incompatibility, ``2`` invalid arguments. Writes exactly one
        ``TraceResult`` JSON document to stdout and diagnostics to stderr.
    """
    parser = build_parser()
    args = parser.parse_args(argv)

    if not _VARIABLE_RE.match(args.variable):
        print(
            f"do2screen: error: invalid variable name: {args.variable!r}",
            file=sys.stderr,
        )
        return 2
    if not os.path.exists(args.path):
        print(f"do2screen: error: path does not exist: {args.path}", file=sys.stderr)
        return 1
    if not os.path.isfile(args.path):
        print(f"do2screen: error: not a file: {args.path}", file=sys.stderr)
        return 1

    try:
        result = trace(
            args.path,
            args.variable,
            follow_parents=not args.no_follow_parents,
            include_labels=args.labels,
        )
    except RegistryIncompatibilityError as exc:
        print(f"do2screen: error: registry incompatibility: {exc}", file=sys.stderr)
        return 1
    except OSError as exc:
        print(f"do2screen: error: {exc}", file=sys.stderr)
        return 1

    indent = max(0, args.indent)
    payload = json.loads(result.model_dump_json())
    print(json.dumps(payload, indent=indent))
    return 0


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
