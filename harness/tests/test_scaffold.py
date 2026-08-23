from __future__ import annotations

import shutil
import subprocess
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import pytest

import harness.co_math.scaffold as scaffold_module
from harness.co_math.project import read_manifest
from harness.co_math.registry import UserConfig, list_registered_projects, save_user_config
from harness.co_math.scaffold import create_project
from harness.co_math.workspace import init_workspace, load_goals


def _configure_home(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> Path:
    config_home = tmp_path / "config"
    projects_home = tmp_path / "projects"
    monkeypatch.setenv("CO_MATH_CONFIG_HOME", str(config_home))
    save_user_config(
        UserConfig(
            projects_home=projects_home,
            allowed_project_roots=(projects_home,),
        )
    )
    return projects_home


@pytest.mark.skipif(shutil.which("git") is None, reason="git is required")
def test_create_project_builds_self_contained_git_project(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    projects_home = _configure_home(tmp_path, monkeypatch)

    result = create_project("ADMM 研究", language="user-readable")

    root = result.project.root
    assert root == (projects_home / "ADMM 研究").resolve()
    assert result.warnings == ()
    assert (root / "co-math.toml").is_file()
    assert (root / "workspace/project/GOALS.yaml").is_file()
    assert (root / ".agents/skills/co-mathematician/SKILL.md").is_file()
    assert (root / "agents/roles/logic_reviewer.md").is_file()
    assert (root / ".codex/config.toml").is_file()
    assert (root / ".claude/agents/logic_reviewer.md").is_file()
    assert (root / ".cursor/rules/co-mathematician.mdc").is_file()
    assert (root / ".opencode/agents/logic_reviewer.md").is_file()
    assert not (root / "harness").exists()
    assert (root / ".git").is_dir()
    assert load_goals(root / "workspace")["language_policy"] == {
        "status": "selected",
        "code": "user-readable",
        "schema_language": "English",
        "project_docs_language": "user_language",
        "notes_language": "user_language",
        "review_language": "user_language",
        "final_output_language": "user_language",
    }
    top_level = subprocess.run(
        ["git", "-C", str(root), "rev-parse", "--show-toplevel"],
        check=True,
        capture_output=True,
        text=True,
    ).stdout.strip()
    assert Path(top_level).resolve() == root


def test_create_project_normalizes_default_directory_and_can_skip_git(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    projects_home = _configure_home(tmp_path, monkeypatch)

    result = create_project("  ＡＤＭＭ 研究  ", initialize_git=False)

    assert result.project.root == (projects_home / "ADMM 研究").resolve()
    assert result.project.manifest.name == "ADMM 研究"
    assert not (result.project.root / ".git").exists()
    goals = load_goals(result.project.workspace)
    assert goals["language_policy"]["status"] == "pending_user_choice"


@pytest.mark.parametrize(
    ("policy", "notes_language", "review_language"),
    [
        ("en", "English", "English"),
        ("user-notes", "user_language", "English"),
        ("user-readable", "user_language", "user_language"),
        ("match", "match_conversation", "match_conversation"),
    ],
)
def test_create_project_records_each_stable_language_policy(
    policy: str,
    notes_language: str,
    review_language: str,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _configure_home(tmp_path, monkeypatch)

    project = create_project(
        f"Language {policy}",
        language=policy,
        initialize_git=False,
    ).project
    language = load_goals(project.workspace)["language_policy"]

    assert language["status"] == "selected"
    assert language["code"] == policy
    assert language["notes_language"] == notes_language
    assert language["review_language"] == review_language


def test_create_project_can_publish_into_an_existing_empty_directory(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _configure_home(tmp_path, monkeypatch)
    target = tmp_path / "empty target"
    target.mkdir()

    result = create_project("Empty Target", path=target, initialize_git=False)

    assert result.project.root == target.resolve()
    assert (target / "co-math.toml").is_file()


def test_create_project_rejects_nonempty_target_without_changing_it(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _configure_home(tmp_path, monkeypatch)
    target = tmp_path / "existing"
    target.mkdir()
    sentinel = target / "keep.txt"
    sentinel.write_text("keep me", encoding="utf-8")

    with pytest.raises(ValueError, match="not empty"):
        create_project("Existing", path=target, initialize_git=False)

    assert sentinel.read_text(encoding="utf-8") == "keep me"
    assert not (target / "co-math.toml").exists()


def test_create_project_rejects_target_and_parent_symlinks(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _configure_home(tmp_path, monkeypatch)
    actual = tmp_path / "actual"
    actual.mkdir()
    target_link = tmp_path / "target-link"
    target_link.symlink_to(actual, target_is_directory=True)
    parent_link = tmp_path / "parent-link"
    parent_link.symlink_to(actual, target_is_directory=True)

    with pytest.raises(ValueError, match="symlink"):
        create_project("Target Link", path=target_link, initialize_git=False)
    with pytest.raises(ValueError, match="symlink"):
        create_project(
            "Parent Link",
            path=parent_link / "child",
            initialize_git=False,
        )


def test_create_project_rejects_nested_project(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _configure_home(tmp_path, monkeypatch)
    outer = tmp_path / "outer"
    outer.mkdir()
    init_workspace(outer / "workspace")
    from harness.co_math.project import new_manifest, write_manifest

    write_manifest(outer, new_manifest("Outer"))

    with pytest.raises(ValueError, match="nested"):
        create_project(
            "Nested",
            path=outer / "nested",
            initialize_git=False,
        )


def test_failed_scaffold_leaves_no_target_or_temporary_directory(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _configure_home(tmp_path, monkeypatch)
    target = tmp_path / "broken"

    def fail_git_init(root: Path) -> None:
        raise RuntimeError(f"git init failed for {root}")

    monkeypatch.setattr(scaffold_module, "_initialize_git", fail_git_init)

    with pytest.raises(RuntimeError, match="git init failed"):
        create_project("Broken", path=target)

    assert not target.exists()
    assert not list(tmp_path.glob(".broken.co-math-tmp-*"))


def test_invalid_language_and_path_traversal_leave_no_project(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _configure_home(tmp_path, monkeypatch)
    invalid_language = tmp_path / "invalid-language"

    with pytest.raises(ValueError, match="Unsupported language policy"):
        create_project(
            "Invalid Language",
            path=invalid_language,
            language="automatic",
            initialize_git=False,
        )
    with pytest.raises(ValueError, match="traversal"):
        create_project(
            "Traversal",
            path=tmp_path / "parent" / ".." / "escape",
            initialize_git=False,
        )

    assert not invalid_language.exists()
    assert not list(tmp_path.glob(".*.co-math-tmp-*"))


def test_two_projects_have_distinct_identity_and_workspace_state(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _configure_home(tmp_path, monkeypatch)

    first = create_project("First", initialize_git=False).project
    second = create_project("Second", initialize_git=False).project
    (first.workspace / "project" / "messages.jsonl").write_text(
        '{"project": "first"}\n', encoding="utf-8"
    )

    assert first.manifest.project_id != second.manifest.project_id
    assert (second.workspace / "project" / "messages.jsonl").read_text(
        encoding="utf-8"
    ) == ""
    assert len(list_registered_projects()) == 2


def test_registry_failure_keeps_published_project_and_returns_warning(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _configure_home(tmp_path, monkeypatch)
    target = tmp_path / "registry-warning"

    def fail_registry(root: Path) -> dict[str, str]:
        raise OSError("registry unavailable")

    monkeypatch.setattr(scaffold_module, "register_project", fail_registry)

    result = create_project(
        "Registry Warning",
        path=target,
        initialize_git=False,
    )

    assert result.project.root == target.resolve()
    assert (target / "co-math.toml").is_file()
    assert result.warnings == (
        "Project created, but registry update failed: registry unavailable. "
        "Run `co-math adopt` to repair the registry.",
    )


def test_concurrent_same_name_creation_has_one_winner(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    projects_home = _configure_home(tmp_path, monkeypatch)

    def attempt() -> tuple[str, str]:
        try:
            result = create_project("Concurrent", initialize_git=False)
            return "created", result.project.manifest.project_id
        except ValueError as exc:
            return "rejected", str(exc)

    with ThreadPoolExecutor(max_workers=2) as executor:
        outcomes = list(executor.map(lambda _: attempt(), range(2)))

    assert [kind for kind, _ in outcomes].count("created") == 1
    assert [kind for kind, _ in outcomes].count("rejected") == 1
    assert (projects_home / "Concurrent" / "co-math.toml").is_file()
    assert not list(projects_home.glob(".Concurrent.co-math-tmp-*"))


def test_read_manifest_matches_create_result(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _configure_home(tmp_path, monkeypatch)

    result = create_project("Identity", initialize_git=False)

    assert read_manifest(result.project.root) == result.project.manifest
