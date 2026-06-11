# Copyright 2026 ArchML Contributors
# SPDX-License-Identifier: Apache-2.0

"""Tests for transitive remote dependency resolution."""

from collections.abc import Callable, Sequence
from pathlib import Path

import pytest
import yaml

from archml.workspace.config import WorkspaceConfig
from archml.workspace.resolve import (
    DependencyConflictError,
    DependencyResolutionError,
    build_alias_map,
    normalize_path,
    normalize_url,
    resolve_closure,
)
from tests.conftest import GitRepo

# ###############
# Public Interface
# ###############


def _ws_doc(
    name: str,
    *,
    locals_: Sequence[tuple[str, str]] = (),
    gits: Sequence[dict[str, str]] = (),
) -> str:
    """Render an .archml-workspace.yaml document string."""
    source_imports: list[dict[str, str]] = [{"name": n, "local-path": p} for n, p in locals_]
    source_imports.extend(gits)
    return yaml.safe_dump(
        {"name": name, "build-directory": "build", "source-imports": source_imports},
        sort_keys=False,
    )


def _root_config(name: str, gits: list[dict[str, str]]) -> WorkspaceConfig:
    """Build a root WorkspaceConfig with local source plus *gits* git imports."""
    return WorkspaceConfig.model_validate(yaml.safe_load(_ws_doc(name, locals_=[("src", ".")], gits=gits)))


class TestNormalize:
    def test_normalize_url_strips_git_suffix_and_slash(self) -> None:
        assert normalize_url("https://h/r.git") == "https://h/r"
        assert normalize_url("https://h/r/") == "https://h/r"
        assert normalize_url("  https://h/r.git  ") == "https://h/r"

    def test_normalize_path_defaults_to_dot(self) -> None:
        assert normalize_path("") == "."
        assert normalize_path(".") == "."
        assert normalize_path("./a/b/") == "a/b"


class TestResolveClosure:
    def test_single_remote_resolves_identity_from_workspace_name(
        self, make_git_repo: Callable[[str], GitRepo], tmp_path: Path
    ) -> None:
        """A git import resolves to the imported workspace's own name as identity."""
        repo = make_git_repo("pay")
        sha = repo.commit({".archml-workspace.yaml": _ws_doc("payments", locals_=[("lib", "lib")])})

        config = _root_config("myws", [{"name": "pay", "git-repository": str(repo.path), "revision": sha}])
        closure = resolve_closure(config, tmp_path / "sync")

        assert [r.identity for r in closure.repos] == ["payments"]
        assert closure.repos[0].commit == sha
        assert closure.alias_map == {("myws", "pay"): "@payments"}
        assert (tmp_path / "sync" / "payments" / ".archml-workspace.yaml").exists()

    def test_transitive_chain(self, make_git_repo: Callable[[str], GitRepo], tmp_path: Path) -> None:
        """A → B → C transitive git imports are all discovered."""
        repo_c = make_git_repo("c")
        c_sha = repo_c.commit({".archml-workspace.yaml": _ws_doc("cee", locals_=[("lib", "lib")])})

        repo_b = make_git_repo("b")
        b_sha = repo_b.commit(
            {
                ".archml-workspace.yaml": _ws_doc(
                    "bee",
                    locals_=[("lib", "lib")],
                    gits=[{"name": "c", "git-repository": str(repo_c.path), "revision": c_sha}],
                )
            }
        )

        config = _root_config("myws", [{"name": "b", "git-repository": str(repo_b.path), "revision": b_sha}])
        closure = resolve_closure(config, tmp_path / "sync")

        assert {r.identity for r in closure.repos} == {"bee", "cee"}
        assert closure.alias_map[("myws", "b")] == "@bee"
        assert closure.alias_map[("@bee", "c")] == "@cee"

    def test_multiple_workspaces_in_one_repo(self, make_git_repo: Callable[[str], GitRepo], tmp_path: Path) -> None:
        """Two workspaces in one repo, at different paths, resolve to two identities."""
        repo = make_git_repo("mono")
        sha = repo.commit(
            {
                "a/.archml-workspace.yaml": _ws_doc("alpha", locals_=[("lib", "lib")]),
                "b/.archml-workspace.yaml": _ws_doc(
                    "beta",
                    locals_=[("lib", "lib")],
                    gits=[{"name": "al", "git-repository": str(repo.path), "revision": "snap", "path": "a"}],
                ),
            },
            tag="snap",
        )

        config = _root_config(
            "myws",
            [
                {"name": "pa", "git-repository": str(repo.path), "revision": sha, "path": "a"},
                {"name": "pb", "git-repository": str(repo.path), "revision": sha, "path": "b"},
            ],
        )
        closure = resolve_closure(config, tmp_path / "sync")

        assert {r.identity for r in closure.repos} == {"alpha", "beta"}
        assert {(r.identity, r.path) for r in closure.repos} == {("alpha", "a"), ("beta", "b")}
        # beta's own import of alpha unifies to the same identity as the root's alias.
        assert closure.alias_map[("myws", "pa")] == "@alpha"
        assert closure.alias_map[("@beta", "al")] == "@alpha"

    def test_diamond_same_commit_unifies(self, make_git_repo: Callable[[str], GitRepo], tmp_path: Path) -> None:
        """The same (repo, path) at the same commit via two aliases yields one entry."""
        repo = make_git_repo("c")
        sha = repo.commit({".archml-workspace.yaml": _ws_doc("cee", locals_=[("lib", "lib")])}, tag="v1")

        config = _root_config(
            "myws",
            [
                {"name": "x", "git-repository": str(repo.path), "revision": sha},
                {"name": "y", "git-repository": str(repo.path), "revision": "v1"},
            ],
        )
        closure = resolve_closure(config, tmp_path / "sync")

        assert [r.identity for r in closure.repos] == ["cee"]
        assert closure.alias_map[("myws", "x")] == "@cee"
        assert closure.alias_map[("myws", "y")] == "@cee"

    def test_diamond_different_commits_raises_conflict(
        self, make_git_repo: Callable[[str], GitRepo], tmp_path: Path
    ) -> None:
        """The same (repo, path) at different commits raises a conflict listing requirers."""
        repo = make_git_repo("c")
        sha1 = repo.commit({".archml-workspace.yaml": _ws_doc("cee", locals_=[("lib", "lib")])}, tag="v1")
        sha2 = repo.commit({"extra.txt": "x"}, tag="v2")
        assert sha1 != sha2

        config = _root_config(
            "myws",
            [
                {"name": "x", "git-repository": str(repo.path), "revision": "v1"},
                {"name": "y", "git-repository": str(repo.path), "revision": "v2"},
            ],
        )
        with pytest.raises(DependencyConflictError) as exc_info:
            resolve_closure(config, tmp_path / "sync")
        message = str(exc_info.value)
        assert "conflict" in message.lower()
        assert sha1[:8] in message and sha2[:8] in message

    def test_identity_collision_raises(self, make_git_repo: Callable[[str], GitRepo], tmp_path: Path) -> None:
        """Two distinct repos declaring the same workspace name raise an error."""
        repo_a = make_git_repo("a")
        a_sha = repo_a.commit({".archml-workspace.yaml": _ws_doc("dup", locals_=[("lib", "lib")])})
        repo_b = make_git_repo("b")
        b_sha = repo_b.commit({".archml-workspace.yaml": _ws_doc("dup", locals_=[("lib", "lib")])})

        config = _root_config(
            "myws",
            [
                {"name": "a", "git-repository": str(repo_a.path), "revision": a_sha},
                {"name": "b", "git-repository": str(repo_b.path), "revision": b_sha},
            ],
        )
        with pytest.raises(DependencyResolutionError, match="identity 'dup'"):
            resolve_closure(config, tmp_path / "sync")

    def test_resolves_tag_and_branch_revisions(self, make_git_repo: Callable[[str], GitRepo], tmp_path: Path) -> None:
        """Tag and branch revisions resolve to the underlying commit."""
        repo = make_git_repo("c")
        sha = repo.commit({".archml-workspace.yaml": _ws_doc("cee", locals_=[("lib", "lib")])}, tag="v1.0")

        for revision in ("v1.0", "main", "master", sha):
            sync = tmp_path / f"sync-{revision[:4]}"
            try:
                closure = resolve_closure(
                    _root_config("myws", [{"name": "c", "git-repository": str(repo.path), "revision": revision}]),
                    sync,
                )
            except DependencyResolutionError:
                # The default branch may be 'main' or 'master' depending on git config.
                continue
            assert closure.repos[0].commit == sha

    def test_missing_workspace_at_path_raises(self, make_git_repo: Callable[[str], GitRepo], tmp_path: Path) -> None:
        """A path that contains no workspace file raises a resolution error."""
        repo = make_git_repo("c")
        sha = repo.commit({".archml-workspace.yaml": _ws_doc("cee", locals_=[("lib", "lib")])})

        config = _root_config(
            "myws", [{"name": "c", "git-repository": str(repo.path), "revision": sha, "path": "nope"}]
        )
        with pytest.raises(DependencyResolutionError, match="No .archml-workspace.yaml"):
            resolve_closure(config, tmp_path / "sync")


class TestBuildAliasMap:
    def test_reconstructs_alias_map_from_closure(self, make_git_repo: Callable[[str], GitRepo], tmp_path: Path) -> None:
        """build_alias_map rebuilds the same edges resolve_closure produced."""
        repo_c = make_git_repo("c")
        c_sha = repo_c.commit({".archml-workspace.yaml": _ws_doc("cee", locals_=[("lib", "lib")])})
        repo_b = make_git_repo("b")
        b_sha = repo_b.commit(
            {
                ".archml-workspace.yaml": _ws_doc(
                    "bee",
                    locals_=[("lib", "lib")],
                    gits=[{"name": "c", "git-repository": str(repo_c.path), "revision": c_sha}],
                )
            }
        )
        config = _root_config("myws", [{"name": "b", "git-repository": str(repo_b.path), "revision": b_sha}])
        sync = tmp_path / "sync"
        closure = resolve_closure(config, sync)

        rebuilt = build_alias_map(config, sync, closure.repos)
        assert rebuilt == closure.alias_map
