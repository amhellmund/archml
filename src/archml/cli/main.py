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
        "name",
        help="Mnemonic name for the workspace source import",
    )
    init_parser.add_argument(
        "workspace_dir",
        help="Directory to initialize the workspace in",
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

_DEFAULT_BUILD_DIR = ".archml-build"


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
    name = args.name
    if not name:
        print("Error: mnemonic name cannot be empty.", file=sys.stderr)
        return 1

    workspace_dir = Path(args.workspace_dir).resolve()
    workspace_dir.mkdir(parents=True, exist_ok=True)

    workspace_yaml = workspace_dir / ".archml-workspace.yaml"
    if workspace_yaml.exists():
        print(
            f"Error: workspace already exists at '{workspace_yaml}'.",
            file=sys.stderr,
        )
        return 1

    workspace_marker = workspace_dir / ".archml-workspace"
    if not workspace_marker.exists():
        workspace_marker.write_text(
            "# ArchML Workspace Configuration\n"
            "# This file marks the root of an ArchML workspace.\n"
            "\n"
            "[workspace]\n"
            'version = "1"\n',
            encoding="utf-8",
        )

    workspace_yaml.write_text(
        f"build-directory: {_DEFAULT_BUILD_DIR}\n"
        "source-imports:\n"
        f"  - name: {name}\n"
        "    local-path: .\n",
        encoding="utf-8",
    )

    print(f"Initialized ArchML workspace '{name}' at '{workspace_dir}'.")
    return 0


def _cmd_check(args: argparse.Namespace) -> int:
    """Handle the check subcommand."""
    from archml.workspace.config import LocalPathImport

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

    # Load optional extended workspace configuration for source imports and build dir.
    workspace_yaml = directory / ".archml-workspace.yaml"
    build_dir = directory / _DEFAULT_BUILD_DIR
    # The empty-string key represents the workspace root for non-mnemonic imports.
    source_import_map: dict[str, Path] = {"": directory}

    if workspace_yaml.exists():
        try:
            config = load_workspace_config(workspace_yaml)
        except WorkspaceConfigError as exc:
            print(f"Error: {exc}", file=sys.stderr)
            return 1

        build_dir = directory / config.build_directory

        for imp in config.source_imports:
            if isinstance(imp, LocalPathImport):
                source_import_map[imp.name] = (directory / imp.local_path).resolve()
            # GitPathImport requires repository fetching which is not yet supported.

    archml_files = [f for f in directory.rglob("*.archml") if build_dir not in f.parents]
    if not archml_files:
        print("No .archml files found in the workspace.")
        return 0

    print(f"Checking {len(archml_files)} architecture file(s)...")
    try:
        compiled = compile_files(archml_files, build_dir, source_import_map)
    except CompilerError as exc:
        print(f"Error: {exc}", file=sys.stderr)
        return 1

    has_errors = False
    for arch_file in compiled.values():
        result = validate(arch_file)
        for warning in result.warnings:
            print(f"Warning: {warning.message}")
        for error in result.errors:
            print(f"Error: {error.message}", file=sys.stderr)
            has_errors = True

    if has_errors:
        return 1

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
