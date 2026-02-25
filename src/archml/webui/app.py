# Copyright 2026 ArchML Contributors
# SPDX-License-Identifier: Apache-2.0

"""Dash-based web UI for interactive architecture viewing."""

from pathlib import Path

import dash
from dash import html

# ###############
# Public Interface
# ###############


def create_app(directory: Path) -> dash.Dash:
    """Create and configure the ArchML web UI application."""
    app = dash.Dash(
        __name__,
        title="ArchML Architecture Viewer",
    )
    app.layout = _build_layout(directory)
    return app


# ################
# Implementation
# ################


def _build_layout(directory: Path) -> html.Div:
    """Build the application layout."""
    return html.Div(
        [
            html.H1("ArchML Architecture Viewer"),
            html.P(f"Workspace: {directory}"),
            html.Hr(),
            html.P(
                "Architecture views will be rendered here as the parser and "
                "model components are implemented.",
                style={"color": "#666"},
            ),
        ],
        style={"fontFamily": "sans-serif", "padding": "2rem"},
    )
