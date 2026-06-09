# Copyright 2026 ArchML Contributors
# SPDX-License-Identifier: Apache-2.0

"""Image asset resolution and copying for the static ArchML HTML viewer.

Entity ``description`` blocks are Markdown and may reference images that live
alongside the ``.farchml`` source files, e.g. ``![flow](./diagrams/flow.png)``.
The static viewer is a plain HTML file, so those images are copied into an
assets directory next to the output HTML and the Markdown image ``src`` is
rewritten to a relative URL pointing into that directory.

Path resolution rules (mirrored by the JS renderer's safety checks):

- ``http://`` / ``https://`` / ``data:`` URLs (and any other scheme) are left
  untouched.
- A leading ``/`` anchors the path at the workspace root.
- Any other path is resolved relative to the directory of the ``.farchml`` file
  that owns the description.

Images that cannot be resolved (missing file, unsupported extension, or a path
that escapes the workspace root) are left unchanged and recorded as warnings.
"""

from __future__ import annotations

import hashlib
import re
import shutil
from pathlib import Path

# ###############
# Public Interface
# ###############

ALLOWED_IMAGE_EXTENSIONS: frozenset[str] = frozenset(
    {".png", ".jpg", ".jpeg", ".gif", ".svg", ".webp", ".avif", ".bmp", ".ico"}
)


class ImageAssetResolver:
    """Rewrites Markdown image references and copies the images into an assets dir.

    Instances are stateful: :meth:`rewrite` lazily creates *assets_dir* on the
    first successful copy, deduplicates copies of the same source file, and
    accumulates :attr:`warnings` for the caller to report.

    Attributes:
        source_dirs: Mapping from canonical file key to the directory of the
            ``.farchml`` source file owning that description.
        workspace_root: Absolute path the leading-``/`` and traversal guard
            resolve against.
        assets_dir: Directory the images are copied into (created lazily).
        url_prefix: Relative URL prefix prepended to copied asset filenames.
        copied_count: Number of distinct images copied so far.
        warnings: Human-readable messages for images that were left unchanged.
    """

    def __init__(
        self,
        source_dirs: dict[str, Path],
        workspace_root: Path,
        assets_dir: Path,
        url_prefix: str,
    ) -> None:
        self.source_dirs = source_dirs
        self.workspace_root = workspace_root.resolve()
        self.assets_dir = assets_dir
        self.url_prefix = url_prefix
        self.copied_count = 0
        self.warnings: list[str] = []
        # Maps an absolute source image path to its copied asset filename so the
        # same image referenced multiple times is copied only once.
        self._copied: dict[Path, str] = {}

    def rewrite(self, file_key: str, description: str) -> str:
        """Return *description* with resolvable image ``src`` values rewritten.

        Args:
            file_key: Canonical key of the file owning this description; used to
                resolve file-relative image paths via :attr:`source_dirs`.
            description: The Markdown description text.

        Returns:
            The description with copied images repointed at the assets URL.
            Unresolvable or remote images are returned unchanged.
        """

        def _replace(match: re.Match[str]) -> str:
            alt, src = match.group(1), match.group(2).strip()
            url = self._resolve_and_copy(file_key, src)
            if url is None:
                return match.group(0)
            return f"![{alt}]({url})"

        return _IMAGE_RE.sub(_replace, description)

    # ################
    # Implementation
    # ################

    def _resolve_and_copy(self, file_key: str, src: str) -> str | None:
        """Resolve *src*, copy the image, and return its assets URL (or None)."""
        # Leave remote / scheme-qualified URLs untouched.
        if _SCHEME_RE.match(src):
            return None

        if src.startswith("/"):
            candidate = (self.workspace_root / src.lstrip("/")).resolve()
        else:
            base = self.source_dirs.get(file_key)
            if base is None:
                self.warnings.append(f"{file_key}: no source directory for image '{src}'")
                return None
            candidate = (base / src).resolve()

        # Guard against path traversal outside the workspace root.
        if self.workspace_root not in candidate.parents and candidate != self.workspace_root:
            self.warnings.append(f"{file_key}: image '{src}' resolves outside the workspace; skipped")
            return None

        if candidate.suffix.lower() not in ALLOWED_IMAGE_EXTENSIONS:
            self.warnings.append(f"{file_key}: image '{src}' has an unsupported extension; skipped")
            return None

        if not candidate.is_file():
            self.warnings.append(f"{file_key}: image '{src}' not found at '{candidate}'; skipped")
            return None

        name = self._copied.get(candidate)
        if name is None:
            digest = hashlib.sha1(str(candidate).encode("utf-8")).hexdigest()[:16]
            name = f"{digest}_{candidate.name}"
            self.assets_dir.mkdir(parents=True, exist_ok=True)
            shutil.copy2(candidate, self.assets_dir / name)
            self._copied[candidate] = name
            self.copied_count += 1

        return f"{self.url_prefix}/{name}"


# ################
# Implementation
# ################

# Markdown image syntax: ![alt](src). The src capture stops at the first ')'.
_IMAGE_RE = re.compile(r"!\[([^\]]*)\]\(([^)]+)\)")

# Anything that looks like a URL scheme (e.g. "http:", "data:", "mailto:").
_SCHEME_RE = re.compile(r"^[a-zA-Z][a-zA-Z0-9+.\-]*:")
