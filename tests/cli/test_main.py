# Copyright 2026 ArchML Contributors
# SPDX-License-Identifier: Apache-2.0

"""Tests for the ArchML CLI entry point."""

from archml.cli.main import main


def test_main_runs() -> None:
    """Smoke test: main() executes without raising an exception."""
    main()
