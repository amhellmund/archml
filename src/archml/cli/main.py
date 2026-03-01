# Copyright 2026 ArchML Contributors
# SPDX-License-Identifier: Apache-2.0

"""Entry point for the ArchML command-line interface."""

import argparse
import sys
from pathlib import Path

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
    from archml.compiler.build import CompilerError, compile_files
    from archml.workspace.config import LocalPathImport, WorkspaceConfigError, load_workspace_config

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
        compile_files(archml_files, build_dir, source_import_map)
    except CompilerError as exc:
        print(f"Error: {exc}", file=sys.stderr)
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
