#!/usr/bin/env python3
# Copyright 2025 ArchML Contributors
# SPDX-License-Identifier: Apache-2.0

"""Run all CI checks locally: format, lint, type check, tests, and build."""

import subprocess
import sys
import time

from yachalk import chalk

# ###############
# Public Interface
# ###############

STEPS: list[tuple[str, list[str]]] = [
    ("Format check", ["uv", "run", "ruff", "format", "--check", "src/", "tests/"]),
    ("Lint", ["uv", "run", "ruff", "check", "src/", "tests/"]),
    ("Type check", ["uv", "run", "ty", "check", "src/"]),
    ("Tests", ["uv", "run", "pytest", "--cov=archml", "--cov-report=term-missing"]),
    ("Build", ["uv", "build"]),
]


def main() -> int:
    """Run all CI steps and report results."""
    results: list[tuple[str, bool, float]] = []

    for name, cmd in STEPS:
        sep = chalk.blue("=" * 60)
        print(f"\n{sep}")
        print(chalk.blue(name))
        print(sep)
        start = time.monotonic()
        proc = subprocess.run(cmd, cwd=_repo_root())
        elapsed = time.monotonic() - start
        results.append((name, proc.returncode == 0, elapsed))

    sep = "=" * 60
    print(f"\n{chalk.blue(sep)}")
    print(chalk.blue("  Summary"))
    print(chalk.blue(sep))
    all_passed = True
    for name, passed, elapsed in results:
        if passed:
            status = chalk.green("PASS")
            line = chalk.green(f"  {status}  {name} ({elapsed:.1f}s)")
        else:
            status = chalk.red("FAIL")
            line = chalk.red(f"  {status}  {name} ({elapsed:.1f}s)")
        print(line)
        if not passed:
            all_passed = False

    print()
    return 0 if all_passed else 1


# ################
# Implementation
# ################


def _repo_root() -> str:
    import pathlib

    return str(pathlib.Path(__file__).parent.parent)


if __name__ == "__main__":
    sys.exit(main())
