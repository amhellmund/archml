#!/usr/bin/env python3
# Copyright 2025 ArchML Contributors
# SPDX-License-Identifier: Apache-2.0

"""Update the version in pyproject.toml and vscode-extension/package.json."""

import json
import pathlib
import re
import sys

# ###############
# Public Interface
# ###############


def main() -> int:
    """Update versions to the value provided as a command-line argument."""
    if len(sys.argv) != 2:
        print(f"Usage: {sys.argv[0]} <version>", file=sys.stderr)
        return 1

    version = sys.argv[1]
    if not re.fullmatch(r"\d+\.\d+\.\d+", version):
        print(f"Error: version must be in X.Y.Z format, got '{version}'", file=sys.stderr)
        return 1

    root = _repo_root()
    _update_pyproject(root / "pyproject.toml", version)
    _update_package_json(root / "vscode-extension" / "package.json", version)
    print(f"Updated versions to {version}")
    return 0


# ################
# Implementation
# ################


def _repo_root() -> pathlib.Path:
    return pathlib.Path(__file__).parent.parent


def _update_pyproject(path: pathlib.Path, version: str) -> None:
    text = path.read_text()
    updated = re.sub(
        r'^(version\s*=\s*")[^"]+(")',
        rf"\g<1>{version}\2",
        text,
        count=1,
        flags=re.MULTILINE,
    )
    path.write_text(updated)
    print(f"  {path.relative_to(_repo_root())}")


def _update_package_json(path: pathlib.Path, version: str) -> None:
    data = json.loads(path.read_text())
    data["version"] = version
    path.write_text(json.dumps(data, indent=2) + "\n")
    print(f"  {path.relative_to(_repo_root())}")


if __name__ == "__main__":
    sys.exit(main())
