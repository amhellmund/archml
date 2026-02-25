# Copyright 2026 ArchML Contributors
# SPDX-License-Identifier: Apache-2.0

"""Tests for the ArchML web UI application."""

from pathlib import Path

import dash
import pytest

from archml.webui.app import create_app

# ###############
# Public Interface
# ###############


def test_create_app_returns_dash_instance(tmp_path: Path) -> None:
    """create_app returns a Dash application instance."""
    app = create_app(directory=tmp_path)
    assert isinstance(app, dash.Dash)


def test_create_app_has_layout(tmp_path: Path) -> None:
    """create_app returns an app with a non-None layout."""
    app = create_app(directory=tmp_path)
    assert app.layout is not None


def test_create_app_title(tmp_path: Path) -> None:
    """create_app sets the application title."""
    app = create_app(directory=tmp_path)
    assert app.title == "ArchML Architecture Viewer"
