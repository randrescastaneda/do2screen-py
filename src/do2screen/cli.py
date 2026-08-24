"""Command-line interface for JSON and Markdown provenance output.

``do2screen PATH VARIABLE [--no-follow-parents] [--labels] [--format FORMAT]
[--indent N]``

Project modes use ``--variable`` with exactly one of ``--dir``, ``--files``,
or ``--manifest``.

Writes exactly one ``TraceResult`` JSON document, or one Markdown provenance
document when ``--format markdown`` is selected, to stdout on success. Project
diagnostics are included in JSON and Markdown; they are not printed as errors.
Exit codes are 0 for complete or partial project results, 1 for unreadable
single-file input, registry incompatibility, or a project with no readable
roots, and 2 for invalid invocation/schema.
"""

from __future__ import annotations

import argparse
import json
import os
import re
import sys

from do2screen.provenance import render_markdown
from do2screen.registry import RegistryIncompatibilityError
from do2screen.trace import trace, trace_directory, trace_files, trace_manifest

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
    parser.add_argument("path", nargs="?", help="Path to the Stata do file.")
    parser.add_argument("variable", nargs="?", help="Variable name to trace.")
    inputs = parser.add_mutually_exclusive_group()
    inputs.add_argument("--dir", dest="directory", help="Trace a directory corpus.")
    inputs.add_argument(
        "--files",
        nargs="+",
        help="Trace an explicitly ordered list of source files.",
    )
    inputs.add_argument(
        "--manifest",
        help="Trace files listed by a manifest V1 JSON file.",
    )
    parser.add_argument(
        "--variable",
        dest="project_variable",
        help="Variable to trace in project input modes.",
    )
    parser.add_argument(
        "--recursive",
        action="store_true",
        help="Recursively discover source files with --dir.",
    )
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
    parser.add_argument(
        "--format",
        choices=("json", "markdown"),
        default="json",
        help="Output format (default: json).",
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    """Run the ``do2screen`` CLI.

    Args:
        argv: Optional argument list; ``None`` reads ``sys.argv[1:]``.

    Returns:
        Exit code: ``0`` for a legacy result or complete/partial project
        result, ``1`` for an unreadable input, project registry incompatibility,
        or a project with no readable roots, and ``2`` for invalid arguments or
        manifest schema. Successful invocations write exactly one
        ``TraceResult`` JSON document to stdout. Project diagnostics are part of
        that JSON; human-readable failures and warnings go to stderr.

    The legacy form is ``do2screen PATH VARIABLE``. Project forms use
    ``--variable`` with exactly one of ``--dir``, ``--files``, or ``--manifest``.
    """
    parser = build_parser()
    args = parser.parse_args(argv)

    project_mode = any(
        value is not None for value in (args.directory, args.files, args.manifest)
    )
    if project_mode:
        if args.path is not None or args.variable is not None:
            parser.error("positional PATH VARIABLE cannot be combined with project input flags")
        if args.project_variable is None:
            parser.error("--variable is required with a project input flag")
        variable = args.project_variable
        if args.recursive and args.directory is None:
            parser.error("--recursive is valid only with --dir")
    else:
        if args.project_variable is not None:
            parser.error("--variable requires --dir, --files, or --manifest")
        if args.recursive:
            parser.error("--recursive requires --dir")
        if args.path is None or args.variable is None:
            parser.error("PATH and VARIABLE are required in legacy mode")
        variable = args.variable

    if not _VARIABLE_RE.match(variable):
        print(
            f"do2screen: error: invalid variable name: {variable!r}",
            file=sys.stderr,
        )
        return 2

    try:
        if project_mode:
            if args.directory is not None:
                result = trace_directory(
                    args.directory,
                    variable,
                    recursive=args.recursive,
                    follow_parents=not args.no_follow_parents,
                    include_labels=args.labels,
                )
            elif args.files is not None:
                result = trace_files(
                    args.files,
                    variable,
                    follow_parents=not args.no_follow_parents,
                    include_labels=args.labels,
                )
            else:
                assert args.manifest is not None
                result = trace_manifest(
                    args.manifest,
                    variable,
                    follow_parents=not args.no_follow_parents,
                    include_labels=args.labels,
                )
            if not result.sources:
                for diagnostic in result.project_diagnostics:
                    print(
                        f"do2screen: error: {diagnostic.message or diagnostic.code}",
                        file=sys.stderr,
                    )
                return 1
        else:
            assert args.path is not None
            if not os.path.exists(args.path):
                print(f"do2screen: error: path does not exist: {args.path}", file=sys.stderr)
                return 1
            if not os.path.isfile(args.path):
                print(f"do2screen: error: not a file: {args.path}", file=sys.stderr)
                return 1
            result = trace(
                args.path,
                variable,
                follow_parents=not args.no_follow_parents,
                include_labels=args.labels,
            )
    except RegistryIncompatibilityError as exc:
        print(f"do2screen: error: registry incompatibility: {exc}", file=sys.stderr)
        return 1
    except OSError as exc:
        print(f"do2screen: error: {exc}", file=sys.stderr)
        return 1
    except ValueError as exc:
        print(f"do2screen: error: {exc}", file=sys.stderr)
        return 2

    if args.format == "markdown":
        print(render_markdown(result))
    else:
        indent = max(0, args.indent)
        payload = json.loads(result.model_dump_json())
        print(json.dumps(payload, indent=indent))
    return 0


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
