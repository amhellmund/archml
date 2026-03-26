# Copyright 2026 ArchML Contributors
# SPDX-License-Identifier: Apache-2.0

"""Entry point for the ArchML command-line interface."""

import argparse
import re
import sys
from pathlib import Path

from archml.compiler.build import CompilerError, SourceImportKey, compile_files
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

    # Shared parent parser for the workspace directory option, used by all
    # subcommands that operate on an existing workspace.
    _workspace_parent = argparse.ArgumentParser(add_help=False)
    _workspace_parent.add_argument(
        "--workspace",
        "-C",
        default=".",
        metavar="DIR",
        help="Directory containing the ArchML workspace (default: current directory)",
    )

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
    subparsers.add_parser(
        "check",
        parents=[_workspace_parent],
        help="Check the consistency of the architecture",
        description="Validate architecture files for consistency errors.",
    )

    # visualize subcommand
    visualize_parser = subparsers.add_parser(
        "visualize",
        parents=[_workspace_parent],
        help="Generate a diagram for a system or component",
        description="Render a box diagram for the specified architecture entity.",
    )
    visualize_parser.add_argument(
        "entity",
        help="Entity path (e.g. 'SystemA' or 'SystemA::ComponentB'), or 'all' to visualize every top-level entity",
    )
    visualize_parser.add_argument(
        "output",
        help="Output file path for the rendered diagram (e.g. 'diagram.png')",
    )
    visualize_parser.add_argument(
        "--depth",
        type=int,
        default=None,
        metavar="N",
        help=(
            "Maximum nesting depth to expand. "
            "For a single entity: 0 = root only, 1 = direct children, etc. "
            "For 'all': 0 = top-level entities as opaque boxes, 1 = expanded one level, etc. "
            "Omit for full depth (default)."
        ),
    )

    # export subcommand
    export_parser = subparsers.add_parser(
        "export",
        parents=[_workspace_parent],
        help="Export the architecture as a standalone HTML viewer",
        description="Generate a self-contained HTML file with the interactive architecture viewer.",
    )
    export_parser.add_argument(
        "--output",
        "-o",
        default="architecture.html",
        metavar="FILE",
        help="Output file path (default: architecture.html)",
    )
    export_parser.add_argument(
        "--width-optimized",
        action="store_true",
        default=False,
        help=(
            "Combine left and right sidebars into a single left sidebar and add a top bar "
            "with a hamburger toggle. Saves horizontal space for narrow viewports."
        ),
    )

    # sync-remote subcommand
    subparsers.add_parser(
        "sync-remote",
        parents=[_workspace_parent],
        help="Download configured remote git repositories",
        description=(
            "Download remote git repositories listed in the workspace configuration "
            "to the configured sync directory at the commits pinned in the lockfile."
        ),
    )

    # update-remote subcommand
    subparsers.add_parser(
        "update-remote",
        parents=[_workspace_parent],
        help="Update remote git repository commits in the lockfile",
        description=(
            "Resolve branch or tag references to their latest commit SHAs and "
            "write the results to the lockfile. Commit-hash revisions are pinned as-is."
        ),
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


def _template_path() -> Path:
    """Return the path to the bundled viewer HTML template."""
    return Path(__file__).parent.parent / "static" / "archml-viewer-template.html"


def _dispatch(args: argparse.Namespace) -> int:
    """Dispatch to the appropriate subcommand handler."""
    if args.command == "init":
        return _cmd_init(args)
    if args.command == "check":
        return _cmd_check(args)
    if args.command == "visualize":
        return _cmd_visualize(args)
    if args.command == "export":
        return _cmd_export(args)
    if args.command == "sync-remote":
        return _cmd_sync_remote(args)
    if args.command == "update-remote":
        return _cmd_update_remote(args)
    return 0


def _cmd_init(args: argparse.Namespace) -> int:
    """Handle the init subcommand."""
    name = args.name
    if not name:
        print("Error: mnemonic name cannot be empty.", file=sys.stderr)
        return 1
    if not re.match(r"^[a-z][a-z0-9_-]*$", name):
        print(
            f"Error: invalid mnemonic name '{name}': must start with a lowercase letter "
            "followed by lowercase letters, digits, hyphens, or underscores.",
            file=sys.stderr,
        )
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

    workspace_yaml.write_text(
        f"name: {name}\nbuild-directory: {_DEFAULT_BUILD_DIR}\nsource-imports:\n  - name: {name}\n    local-path: .\n",
        encoding="utf-8",
    )

    print(f"Initialized ArchML workspace '{name}' at '{workspace_dir}'.")
    return 0


def _cmd_check(args: argparse.Namespace) -> int:
    """Handle the check subcommand."""
    from archml.workspace.config import GitPathImport, LocalPathImport, find_workspace_root

    directory = Path(args.workspace).resolve()

    if not directory.exists():
        print(f"Error: directory '{directory}' does not exist.", file=sys.stderr)
        return 1

    workspace_yaml = directory / ".archml-workspace.yaml"

    if not workspace_yaml.exists():
        root = find_workspace_root(directory)
        if root is None:
            print(
                f"Error: no ArchML workspace found at '{directory}' or any parent directory."
                "Run 'archml init' to initialize a workspace.",
                file=sys.stderr,
            )
            return 1
        directory = root
        workspace_yaml = directory / ".archml-workspace.yaml"

    try:
        config = load_workspace_config(workspace_yaml)
    except WorkspaceConfigError as exc:
        print(f"Error: {exc}", file=sys.stderr)
        return 1

    build_dir = directory / config.build_directory
    sync_dir = directory / config.remote_sync_directory

    # Build the source import map: SourceImportKey(repo, mnemonic) -> absolute base path.
    # Local mnemonics use config.name as repo; remote repos use "@name".
    source_import_map: dict[SourceImportKey, Path] = {}

    for imp in config.source_imports:
        if isinstance(imp, LocalPathImport):
            source_import_map[SourceImportKey(config.name, imp.name)] = (directory / imp.local_path).resolve()
        elif isinstance(imp, GitPathImport):
            repo_dir = (sync_dir / imp.name).resolve()
            if repo_dir.exists():
                remote_workspace_yaml = repo_dir / ".archml-workspace.yaml"
                if remote_workspace_yaml.exists():
                    try:
                        remote_config = load_workspace_config(remote_workspace_yaml)
                        for remote_imp in remote_config.source_imports:
                            if isinstance(remote_imp, LocalPathImport):
                                mnemonic_path = (repo_dir / remote_imp.local_path).resolve()
                                source_import_map[SourceImportKey(f"@{imp.name}", remote_imp.name)] = mnemonic_path
                    except WorkspaceConfigError as exc:
                        print(f"Warning: could not load workspace config from remote '{imp.name}': {exc}")

    # Scan only files under local mnemonic paths (repo == config.name, i.e. not remote).
    local_mnemonic_paths = {base_path for key, base_path in source_import_map.items() if key.repo == config.name}
    seen_files: set[Path] = set()
    archml_files: list[Path] = []
    for base_path in sorted(local_mnemonic_paths):
        for f in base_path.rglob("*.archml"):
            if f not in seen_files and build_dir not in f.parents and sync_dir not in f.parents:
                seen_files.add(f)
                archml_files.append(f)

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


def _cmd_visualize(args: argparse.Namespace) -> int:
    """Handle the visualize subcommand."""
    from archml.views.layout import compute_layout
    from archml.views.resolver import EntityNotFoundError, resolve_entity
    from archml.views.topology import build_viz_diagram, build_viz_diagram_all
    from archml.workspace.config import LocalPathImport

    directory = Path(args.workspace).resolve()

    if not directory.exists():
        print(f"Error: directory '{directory}' does not exist.", file=sys.stderr)
        return 1

    workspace_yaml = directory / ".archml-workspace.yaml"

    if not workspace_yaml.exists():
        print(
            f"Error: no ArchML workspace found at '{directory}'. Run 'archml init' to initialize a workspace.",
            file=sys.stderr,
        )
        return 1

    try:
        config = load_workspace_config(workspace_yaml)
    except WorkspaceConfigError as exc:
        print(f"Error: {exc}", file=sys.stderr)
        return 1

    build_dir = directory / config.build_directory

    source_import_map: dict[SourceImportKey, Path] = {}
    for imp in config.source_imports:
        if isinstance(imp, LocalPathImport):
            source_import_map[SourceImportKey(config.name, imp.name)] = (directory / imp.local_path).resolve()

    archml_files = [f for f in directory.rglob("*.archml") if build_dir not in f.parents]
    if not archml_files:
        print("No .archml files found in the workspace.", file=sys.stderr)
        return 1

    try:
        compiled = compile_files(archml_files, build_dir, source_import_map)
    except CompilerError as exc:
        print(f"Error: {exc}", file=sys.stderr)
        return 1

    output_path = Path(args.output)

    depth: int | None = args.depth

    if args.entity == "all":
        viz_diagram = build_viz_diagram_all(compiled, depth=depth)
    else:
        try:
            entity = resolve_entity(compiled, args.entity)
        except EntityNotFoundError as exc:
            print(f"Error: {exc}", file=sys.stderr)
            return 1
        global_connects = [c for af in compiled.values() for c in af.connects]
        viz_diagram = build_viz_diagram(entity, depth=depth, global_connects=global_connects)
    try:
        layout_plan = compute_layout(viz_diagram)
    except RuntimeError as exc:
        print(f"Error: {exc}", file=sys.stderr)
        return 1

    from archml.views.diagram import render_diagram

    render_diagram(viz_diagram, layout_plan, output_path)

    print(f"Diagram written to '{output_path}'.")
    return 0


def _cmd_export(args: argparse.Namespace) -> int:
    """Handle the export subcommand."""
    from archml.export import build_viewer_payload
    from archml.workspace.config import LocalPathImport

    template_path = _template_path()
    if not template_path.exists():
        print(
            "Warning: JS viewer not built. Run 'python tools/build_js.py' first.",
            file=sys.stderr,
        )
        return 1

    directory = Path(args.workspace).resolve()

    if not directory.exists():
        print(f"Error: directory '{directory}' does not exist.", file=sys.stderr)
        return 1

    workspace_yaml = directory / ".archml-workspace.yaml"

    if not workspace_yaml.exists():
        print(
            f"Error: no ArchML workspace found at '{directory}'. Run 'archml init' to initialize a workspace.",
            file=sys.stderr,
        )
        return 1

    try:
        config = load_workspace_config(workspace_yaml)
    except WorkspaceConfigError as exc:
        print(f"Error: {exc}", file=sys.stderr)
        return 1

    build_dir = directory / config.build_directory

    source_import_map: dict[SourceImportKey, Path] = {}
    for imp in config.source_imports:
        if isinstance(imp, LocalPathImport):
            source_import_map[SourceImportKey(config.name, imp.name)] = (directory / imp.local_path).resolve()

    archml_files = [f for f in directory.rglob("*.archml") if build_dir not in f.parents]
    if not archml_files:
        print("No .archml files found in the workspace.", file=sys.stderr)
        return 1

    try:
        compiled = compile_files(archml_files, build_dir, source_import_map)
    except CompilerError as exc:
        print(f"Error: {exc}", file=sys.stderr)
        return 1

    payload_json = build_viewer_payload(compiled, width_optimized=args.width_optimized)

    template = template_path.read_text(encoding="utf-8")
    data_tag = f'<script id="archml-data" type="application/json">{payload_json}</script>'
    html = template.replace("<!-- ARCHML_DATA_PLACEHOLDER -->", data_tag)

    output_path = Path(args.output)
    output_path.write_text(html, encoding="utf-8")
    print(f"Architecture viewer written to '{output_path}'.")
    return 0


def _cmd_sync_remote(args: argparse.Namespace) -> int:
    """Handle the sync-remote subcommand."""
    from archml.workspace.config import GitPathImport, find_workspace_root
    from archml.workspace.git_ops import GitError, clone_at_commit, get_current_commit
    from archml.workspace.lockfile import LOCKFILE_NAME, LockfileError, load_lockfile

    directory = Path(args.workspace).resolve()

    if not directory.exists():
        print(f"Error: directory '{directory}' does not exist.", file=sys.stderr)
        return 1

    workspace_yaml = directory / ".archml-workspace.yaml"
    if not workspace_yaml.exists():
        root = find_workspace_root(directory)
        if root is None:
            print(
                f"Error: no ArchML workspace found at '{directory}' or any parent directory."
                "Run 'archml init' to initialize a workspace.",
                file=sys.stderr,
            )
            return 1
        directory = root
        workspace_yaml = directory / ".archml-workspace.yaml"

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
    from archml.workspace.config import GitPathImport, find_workspace_root
    from archml.workspace.git_ops import GitError, is_commit_hash, resolve_commit
    from archml.workspace.lockfile import (
        LOCKFILE_NAME,
        LockedRevision,
        Lockfile,
        LockfileError,
        load_lockfile,
        save_lockfile,
    )

    directory = Path(args.workspace).resolve()

    if not directory.exists():
        print(f"Error: directory '{directory}' does not exist.", file=sys.stderr)
        return 1

    workspace_yaml = directory / ".archml-workspace.yaml"
    if not workspace_yaml.exists():
        root = find_workspace_root(directory)
        if root is None:
            print(
                f"Error: no ArchML workspace found at '{directory}' or any parent directory."
                "Run 'archml init' to initialize a workspace.",
                file=sys.stderr,
            )
            return 1
        directory = root
        workspace_yaml = directory / ".archml-workspace.yaml"

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

        locked_by_name[imp.name] = LockedRevision.model_validate(
            {
                "name": imp.name,
                "git-repository": imp.git_repository,
                "revision": imp.revision,
                "commit": commit,
            }
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
