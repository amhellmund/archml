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

    # sync-remote subcommand
    sync_remote_parser = subparsers.add_parser(
        "sync-remote",
        help="Download configured remote git repositories",
        description=(
            "Download remote git repositories listed in the workspace configuration "
            "to the configured sync directory at the commits pinned in the lockfile."
        ),
    )
    sync_remote_parser.add_argument(
        "directory",
        nargs="?",
        default=".",
        help="Directory containing the ArchML workspace (default: current directory)",
    )

    # update-remote subcommand
    update_remote_parser = subparsers.add_parser(
        "update-remote",
        help="Update remote git repository commits in the lockfile",
        description=(
            "Resolve branch or tag references to their latest commit SHAs and "
            "write the results to the lockfile. Commit-hash revisions are pinned as-is."
        ),
    )
    update_remote_parser.add_argument(
        "directory",
        nargs="?",
        default=".",
        help="Directory containing the ArchML workspace (default: current directory)",
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
    if args.command == "sync-remote":
        return _cmd_sync_remote(args)
    if args.command == "update-remote":
        return _cmd_update_remote(args)
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
    from archml.workspace.config import GitPathImport, LocalPathImport

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
    sync_dir = directory / ".archml-remotes"
    # The empty-string key represents the workspace root for non-mnemonic imports.
    source_import_map: dict[str, Path] = {"": directory}

    if workspace_yaml.exists():
        try:
            config = load_workspace_config(workspace_yaml)
        except WorkspaceConfigError as exc:
            print(f"Error: {exc}", file=sys.stderr)
            return 1

        build_dir = directory / config.build_directory
        sync_dir = directory / config.remote_sync_directory

        for imp in config.source_imports:
            if isinstance(imp, LocalPathImport):
                source_import_map[imp.name] = (directory / imp.local_path).resolve()
            elif isinstance(imp, GitPathImport):
                repo_dir = (sync_dir / imp.name).resolve()
                if repo_dir.exists():
                    source_import_map[f"@{imp.name}"] = repo_dir
                    # Also expose mnemonics defined in the remote repo's own workspace config
                    # so that @repo/mnemonic/path/to/file imports resolve correctly.
                    remote_workspace_yaml = repo_dir / ".archml-workspace.yaml"
                    if remote_workspace_yaml.exists():
                        try:
                            remote_config = load_workspace_config(remote_workspace_yaml)
                            for remote_imp in remote_config.source_imports:
                                if isinstance(remote_imp, LocalPathImport):
                                    mnemonic_path = (repo_dir / remote_imp.local_path).resolve()
                                    source_import_map[f"@{imp.name}/{remote_imp.name}"] = mnemonic_path
                        except WorkspaceConfigError as exc:
                            print(
                                f"Warning: could not load workspace config from remote '{imp.name}': {exc}"
                            )

    archml_files = [
        f
        for f in directory.rglob("*.archml")
        if build_dir not in f.parents and sync_dir not in f.parents
    ]
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


def _cmd_sync_remote(args: argparse.Namespace) -> int:
    """Handle the sync-remote subcommand."""
    from archml.workspace.config import GitPathImport
    from archml.workspace.git_ops import GitError, clone_at_commit, get_current_commit
    from archml.workspace.lockfile import LOCKFILE_NAME, LockfileError, load_lockfile

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

    workspace_yaml = directory / ".archml-workspace.yaml"
    if not workspace_yaml.exists():
        print("No workspace configuration found. Nothing to sync.")
        return 0

    try:
        config = load_workspace_config(workspace_yaml)
    except WorkspaceConfigError as exc:
        print(f"Error: {exc}", file=sys.stderr)
        return 1

    git_imports = [imp for imp in config.source_imports if isinstance(imp, GitPathImport)]
    if not git_imports:
        print("No remote git repositories configured. Nothing to sync.")
        return 0

    lockfile_path = directory / LOCKFILE_NAME
    if not lockfile_path.exists():
        print(
            "Error: lockfile not found. Run 'archml update-remote' to create the lockfile.",
            file=sys.stderr,
        )
        return 1

    try:
        lockfile = load_lockfile(lockfile_path)
    except LockfileError as exc:
        print(f"Error: {exc}", file=sys.stderr)
        return 1

    locked_by_name = {entry.name: entry for entry in lockfile.locked_revisions}
    sync_dir = directory / config.remote_sync_directory

    has_errors = False
    for imp in git_imports:
        if imp.name not in locked_by_name:
            print(
                f"Error: '{imp.name}' is not in the lockfile. Run 'archml update-remote' first.",
                file=sys.stderr,
            )
            has_errors = True
            continue

        pinned_commit = locked_by_name[imp.name].commit
        target_dir = sync_dir / imp.name

        try:
            current = get_current_commit(target_dir)
        except GitError as exc:
            print(f"Error: cannot check current state of '{imp.name}': {exc}", file=sys.stderr)
            has_errors = True
            continue

        if current == pinned_commit:
            print(f"  {imp.name}: already at {pinned_commit[:8]}")
            continue

        print(f"  {imp.name}: syncing to {pinned_commit[:8]}...")
        try:
            clone_at_commit(imp.git_repository, pinned_commit, target_dir)
            print(f"  {imp.name}: done.")
        except GitError as exc:
            print(f"Error: failed to sync '{imp.name}': {exc}", file=sys.stderr)
            has_errors = True

    return 1 if has_errors else 0


def _cmd_update_remote(args: argparse.Namespace) -> int:
    """Handle the update-remote subcommand."""
    from archml.workspace.config import GitPathImport
    from archml.workspace.git_ops import GitError, is_commit_hash, resolve_commit
    from archml.workspace.lockfile import (
        LOCKFILE_NAME,
        Lockfile,
        LockfileError,
        LockedRevision,
        load_lockfile,
        save_lockfile,
    )

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

    workspace_yaml = directory / ".archml-workspace.yaml"
    if not workspace_yaml.exists():
        print("No workspace configuration found. Nothing to update.")
        return 0

    try:
        config = load_workspace_config(workspace_yaml)
    except WorkspaceConfigError as exc:
        print(f"Error: {exc}", file=sys.stderr)
        return 1

    git_imports = [imp for imp in config.source_imports if isinstance(imp, GitPathImport)]
    if not git_imports:
        print("No remote git repositories configured. Nothing to update.")
        return 0

    lockfile_path = directory / LOCKFILE_NAME
    if lockfile_path.exists():
        try:
            lockfile = load_lockfile(lockfile_path)
        except LockfileError as exc:
            print(f"Error: {exc}", file=sys.stderr)
            return 1
    else:
        lockfile = Lockfile()

    locked_by_name = {entry.name: entry for entry in lockfile.locked_revisions}

    has_errors = False
    for imp in git_imports:
        if is_commit_hash(imp.revision):
            commit = imp.revision
            print(f"  {imp.name}: pinned at {commit[:8]} (commit hash, no update needed)")
        else:
            print(f"  {imp.name}: resolving '{imp.revision}'...")
            try:
                commit = resolve_commit(imp.git_repository, imp.revision)
                print(f"  {imp.name}: resolved to {commit[:8]}")
            except GitError as exc:
                print(f"Error: failed to resolve '{imp.name}': {exc}", file=sys.stderr)
                has_errors = True
                continue

        locked_by_name[imp.name] = LockedRevision(
            name=imp.name,
            git_repository=imp.git_repository,
            revision=imp.revision,
            commit=commit,
        )

    if has_errors:
        return 1

    lockfile.locked_revisions = list(locked_by_name.values())
    try:
        save_lockfile(lockfile, lockfile_path)
    except LockfileError as exc:
        print(f"Error: {exc}", file=sys.stderr)
        return 1

    print(f"Lockfile updated: {lockfile_path}")
    return 0
