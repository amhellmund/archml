#!/usr/bin/env python3
# Copyright 2026 ArchML Contributors
# SPDX-License-Identifier: Apache-2.0
"""Build the JS viewer and copy artifacts to src/archml/static/.

Run from the repository root:

    python tools/build_js.py

Requires Node.js >= 18 and npm on PATH.
"""

from __future__ import annotations

import shutil
import subprocess
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).parent.parent
JS_DIR = REPO_ROOT / "src" / "archml" / "export" / "js"
STATIC_DIR = REPO_ROOT / "src" / "archml" / "static"


def run(cmd: list[str], cwd: Path) -> None:
    print(f"$ {' '.join(cmd)}")
    result = subprocess.run(cmd, cwd=cwd)
    if result.returncode != 0:
        sys.exit(result.returncode)


def main() -> None:
    print("=== ArchML JS build ===")
    STATIC_DIR.mkdir(parents=True, exist_ok=True)

    run(["npm", "ci"], JS_DIR)
    run(["npm", "run", "build:lib"], JS_DIR)
    run(["npm", "run", "build:html"], JS_DIR)

    # Rename the singlefile output to the canonical template name.
    for candidate in ("index.html", "archml-viewer-template.html"):
        built_html = STATIC_DIR / candidate
        if built_html.exists() and candidate == "index.html":
            template = STATIC_DIR / "archml-viewer-template.html"
            shutil.move(str(built_html), str(template))
            print(f"Renamed {built_html.name} → {template.name}")

    # Copy diagram CSS (source of truth for SVG embedding).
    css_src = JS_DIR / "src" / "archml-diagram.css"
    css_dst = STATIC_DIR / "archml-diagram.css"
    shutil.copy(str(css_src), str(css_dst))
    print("Copied archml-diagram.css → static/")

    print("\nArtifacts in src/archml/static/:")
    for f in sorted(STATIC_DIR.iterdir()):
        size = f.stat().st_size
        print(f"  {f.name:40s}  {size:>9,} bytes")

    print("\n=== Build complete ===")


if __name__ == "__main__":
    main()
