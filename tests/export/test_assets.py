# Copyright 2026 ArchML Contributors
# SPDX-License-Identifier: Apache-2.0

"""Tests for image asset resolution and copying in the static viewer."""

from __future__ import annotations

from pathlib import Path

from archml.export.assets import ImageAssetResolver

# ###############
# Helpers
# ###############

# A 1x1 transparent PNG.
_PNG_BYTES = bytes.fromhex(
    "89504e470d0a1a0a0000000d49484452000000010000000108060000001f15c4"
    "890000000a49444154789c6360000002000154a24f5d0000000049454e44ae426082"
)


def _resolver(tmp_path: Path, *, file_dir: Path | None = None) -> ImageAssetResolver:
    file_dir = file_dir if file_dir is not None else tmp_path
    return ImageAssetResolver(
        source_dirs={"main": file_dir},
        workspace_root=tmp_path,
        assets_dir=tmp_path / "out_assets",
        url_prefix="out_assets",
    )


# ###############
# Tests
# ###############


def test_file_relative_image_copied_and_rewritten(tmp_path: Path) -> None:
    """A file-relative image is copied and its src is rewritten to the assets URL."""
    (tmp_path / "diagrams").mkdir()
    (tmp_path / "diagrams" / "flow.png").write_bytes(_PNG_BYTES)
    resolver = _resolver(tmp_path)

    result = resolver.rewrite("main", "Intro ![flow](./diagrams/flow.png) done.")

    assert "![flow](out_assets/" in result
    assert "diagrams/flow.png" not in result
    assert resolver.copied_count == 1
    copied = list((tmp_path / "out_assets").iterdir())
    assert len(copied) == 1
    assert copied[0].name.endswith("_flow.png")
    assert copied[0].read_bytes() == _PNG_BYTES


def test_workspace_root_image_resolved(tmp_path: Path) -> None:
    """A leading-/ path resolves against the workspace root, not the file dir."""
    file_dir = tmp_path / "sub" / "pkg"
    file_dir.mkdir(parents=True)
    (tmp_path / "assets").mkdir()
    (tmp_path / "assets" / "logo.svg").write_bytes(b"<svg></svg>")
    resolver = _resolver(tmp_path, file_dir=file_dir)

    result = resolver.rewrite("main", "![logo](/assets/logo.svg)")

    assert "![logo](out_assets/" in result
    assert resolver.copied_count == 1


def test_http_and_data_urls_untouched(tmp_path: Path) -> None:
    """Remote and data: image URLs are left unchanged and nothing is copied."""
    resolver = _resolver(tmp_path)
    md = "![a](https://example.com/a.png) ![b](data:image/png;base64,xx)"

    assert resolver.rewrite("main", md) == md
    assert resolver.copied_count == 0
    assert resolver.warnings == []


def test_missing_image_left_unchanged_with_warning(tmp_path: Path) -> None:
    """A missing image is left as-is and a warning is recorded."""
    resolver = _resolver(tmp_path)

    result = resolver.rewrite("main", "![x](./nope.png)")

    assert result == "![x](./nope.png)"
    assert resolver.copied_count == 0
    assert len(resolver.warnings) == 1
    assert "not found" in resolver.warnings[0]


def test_path_traversal_outside_workspace_skipped(tmp_path: Path) -> None:
    """An image that escapes the workspace root is skipped with a warning."""
    workspace = tmp_path / "ws"
    workspace.mkdir()
    outside = tmp_path / "secret.png"
    outside.write_bytes(_PNG_BYTES)
    resolver = ImageAssetResolver(
        source_dirs={"main": workspace},
        workspace_root=workspace,
        assets_dir=workspace / "out_assets",
        url_prefix="out_assets",
    )

    result = resolver.rewrite("main", "![x](../secret.png)")

    assert result == "![x](../secret.png)"
    assert resolver.copied_count == 0
    assert "outside the workspace" in resolver.warnings[0]


def test_unsupported_extension_skipped(tmp_path: Path) -> None:
    """A referenced non-image file is skipped with a warning."""
    (tmp_path / "notes.txt").write_text("hello")
    resolver = _resolver(tmp_path)

    result = resolver.rewrite("main", "![x](./notes.txt)")

    assert result == "![x](./notes.txt)"
    assert resolver.copied_count == 0
    assert "unsupported extension" in resolver.warnings[0]


def test_same_image_copied_once(tmp_path: Path) -> None:
    """The same image referenced twice is copied a single time."""
    (tmp_path / "a.png").write_bytes(_PNG_BYTES)
    resolver = _resolver(tmp_path)

    resolver.rewrite("main", "![one](./a.png)")
    resolver.rewrite("main", "![two](a.png)")

    assert resolver.copied_count == 1
    assert len(list((tmp_path / "out_assets").iterdir())) == 1
