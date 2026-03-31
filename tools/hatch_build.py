# Copyright 2026 ArchML Contributors
# SPDX-License-Identifier: Apache-2.0

"""Hatchling build hook: build the JS viewer before packaging the wheel."""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

from hatchling.builders.hooks.plugin.interface import BuildHookInterface

# ###############
# Public Interface
# ###############


class CustomBuildHook(BuildHookInterface):
    """Run the JS viewer build before the wheel is assembled."""

    _STATIC_ARTIFACTS = (
        "archml-viewer.js",
        "archml-viewer-template.html",
        "archml-diagram.css",
    )

    def initialize(self, version: str, build_data: dict) -> None:
        """Build the JS viewer artifacts into src/archml/static/."""
        repo_root = Path(__file__).parent.parent
        js_dir = repo_root / "src" / "archml" / "export" / "js"
        static_dir = repo_root / "src" / "archml" / "static"

        if not js_dir.exists():
            # Building from an sdist: static files must already be present.
            missing = [f for f in self._STATIC_ARTIFACTS if not (static_dir / f).exists()]
            if missing:
                raise RuntimeError(f"JS viewer artifacts missing from static/: {missing}")
        else:
            build_js = repo_root / "tools" / "build_js.py"
            result = subprocess.run([sys.executable, str(build_js)], cwd=repo_root)
            if result.returncode != 0:
                raise RuntimeError("JS viewer build failed")

        # Ensure generated (untracked) artifacts are included in the sdist.
        for name in self._STATIC_ARTIFACTS:
            path = static_dir / name
            if path.exists():
                build_data.setdefault("artifacts", []).append(str(path.relative_to(repo_root)))
