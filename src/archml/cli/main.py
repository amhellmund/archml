# Copyright 2026 ArchML Contributors
# SPDX-License-Identifier: Apache-2.0

"""Entry point for the ArchML command-line interface."""

import argparse
import sys
from pathlib import Path

from archml.compiler.build import CompilerError, compile_files
from archml.validation.checks import validate
from archml.workspace.config import WorkspaceConfigError, load_workspace_config

# ###############
# Public Interface
# ###############


def main() -> None:
    """Run the ArchML CLI."""
    parser = argparse.ArgumentParser(
        prog="archml",
        description="ArchML — architecture modeling tool",
    )
    subparsers = parser.add_subparsers(dest="command", metavar="COMMAND")

    # init subcommand
    init_parser = subparsers.add_parser(
        "init",
        help="Initialize a new ArchML workspace",
        description="Create a new ArchML workspace in a repository.",
    )
    init_parser.add_argument(
        "directory",
        nargs="?",
        default=".",
        help="Directory to initialize the workspace in (default: current directory)",
    )

    # check subcommand
    check_parser = subparsers.add_parser(
        "check",
        help="Check the consistency of the architecture",
        description="Validate architecture files for consistency errors.",
    )
    check_parser.add_argument(
        "directory",
        nargs="?",
        default=".",
        help="Directory containing the ArchML workspace (default: current directory)",
    )

    # serve subcommand
    serve_parser = subparsers.add_parser(
        "serve",
        help="Launch the interactive architecture viewer",
        description="Launch a web-based UI for interactively viewing the architecture.",
    )
    serve_parser.add_argument(
        "directory",
        nargs="?",
        default=".",
        help="Directory containing the ArchML workspace (default: current directory)",
    )
    serve_parser.add_argument(
        "--port",
        type=int,
        default=8050,
        help="Port to run the server on (default: 8050)",
    )
    serve_parser.add_argument(
        "--host",
        default="127.0.0.1",
        help="Host to bind the server to (default: 127.0.0.1)",
    )

    args = parser.parse_args()
    if args.command is None:
        parser.print_help()
        sys.exit(0)

    sys.exit(_dispatch(args))


# ################
# Implementation
# ################


def _dispatch(args: argparse.Namespace) -> int:
    """Dispatch to the appropriate subcommand handler."""
    if args.command == "init":
        return _cmd_init(args)
    if args.command == "check":
        return _cmd_check(args)
    if args.command == "serve":
        return _cmd_serve(args)
    return 0


def _cmd_init(args: argparse.Namespace) -> int:
    """Handle the init subcommand."""
    directory = Path(args.directory).resolve()

    if not directory.exists():
        print(f"Error: directory '{directory}' does not exist.", file=sys.stderr)
        return 1

    workspace_file = directory / ".archml-workspace"

    if workspace_file.exists():
        print(
            f"Error: workspace already exists at '{workspace_file}'.",
            file=sys.stderr,
        )
        return 1

    workspace_content = (
        "# ArchML Workspace Configuration\n"
        "# This file marks the root of an ArchML workspace.\n"
        "\n"
        "[workspace]\n"
        'version = "1"\n'
    )
    workspace_file.write_text(workspace_content, encoding="utf-8")
    print(f"Initialized ArchML workspace at '{workspace_file}'.")
    return 0


def _cmd_check(args: argparse.Namespace) -> int:
    """Handle the check subcommand."""
    directory = Path(args.directory).resolve()

    if not directory.exists():
        print(f"Error: directory '{directory}' does not exist.", file=sys.stderr)
        return 1

    workspace_file = directory / ".archml-workspace"

    if not workspace_file.exists():
        print(
            f"Error: no ArchML workspace found at '{directory}'. Run 'archml init' to initialize a workspace.",
            file=sys.stderr,
        )
        return 1

    archml_files = list(directory.rglob("*.archml"))
    if not archml_files:
        print("No .archml files found in the workspace.")
        return 0

    print(f"Checking {len(archml_files)} architecture file(s)...")

    config_file = directory / ".archml-workspace.yaml"
    if config_file.exists():
        try:
            config = load_workspace_config(config_file)
            build_dir = directory / config.build_directory
        except WorkspaceConfigError as exc:
            print(f"Error: {exc}", file=sys.stderr)
            return 1
    else:
        build_dir = directory / ".archml-build"

    try:
        compiled = compile_files(archml_files, build_dir, directory)
    except CompilerError as exc:
        print(f"Error: {exc}", file=sys.stderr)
        return 1

    total_warnings = 0
    total_errors = 0
    for key, arch_file in compiled.items():
        result = validate(arch_file)
        for warning in result.warnings:
            print(f"Warning in '{key}': {warning.message}")
        for error in result.errors:
            print(f"Error in '{key}': {error.message}", file=sys.stderr)
        total_warnings += len(result.warnings)
        total_errors += len(result.errors)

    if total_errors > 0:
        print(
            f"Found {total_errors} error(s) and {total_warnings} warning(s).",
            file=sys.stderr,
        )
        return 1

    if total_warnings > 0:
        print(f"Found {total_warnings} warning(s). No errors.")
        return 0

    print("No issues found.")
    return 0


def _cmd_serve(args: argparse.Namespace) -> int:
    """Handle the serve subcommand."""
    directory = Path(args.directory).resolve()

    if not directory.exists():
        print(f"Error: directory '{directory}' does not exist.", file=sys.stderr)
        return 1

    workspace_file = directory / ".archml-workspace"

    if not workspace_file.exists():
        print(
            f"Error: no ArchML workspace found at '{directory}'. Run 'archml init' to initialize a workspace.",
            file=sys.stderr,
        )
        return 1

    from archml.webui.app import create_app

    print(f"Serving architecture view at http://{args.host}:{args.port}/")
    app = create_app(directory=directory)
    app.run(host=args.host, port=args.port, debug=False)
    return 0
