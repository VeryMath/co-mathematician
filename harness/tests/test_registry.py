from __future__ import annotations

import json
from pathlib import Path

import pytest

from harness.co_math.project import new_manifest, write_manifest
from harness.co_math.registry import (
    UserConfig,
    config_home,
    list_registered_projects,
    load_user_config,
    register_project,
    registry_path,
    save_user_config,
)
from harness.co_math.workspace import init_workspace


def _make_project(
    root: Path,
    *,
    name: str = "Test Project",
    project_id: str | None = None,
) -> Path:
    root.mkdir(parents=True)
    init_workspace(root / "workspace")
    write_manifest(root, new_manifest(name, project_id=project_id))
    return root


def test_missing_user_config_returns_defaults_without_writing(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    home = tmp_path / "config"
    monkeypatch.setenv("CO_MATH_CONFIG_HOME", str(home))

    config = load_user_config()

    assert config_home() == home.resolve()
    assert config.projects_home == (Path.home() / "CoMathProjects").resolve()
    assert config.allowed_project_roots == (config.projects_home,)
    assert not home.exists()


def test_user_config_round_trip_uses_resolved_allowed_roots(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("CO_MATH_CONFIG_HOME", str(tmp_path / "config"))
    projects = tmp_path / "projects"
    archive = tmp_path / "archive"
    projects.mkdir()
    archive.mkdir()

    written = save_user_config(
        UserConfig(
            projects_home=projects,
            allowed_project_roots=(projects, archive, projects),
        )
    )

    assert written.projects_home == projects.resolve()
    assert written.allowed_project_roots == (projects.resolve(), archive.resolve())
    assert load_user_config() == written
    raw = json.loads((config_home() / "config.json").read_text(encoding="utf-8"))
    assert raw == {
        "schema_version": 1,
        "projects_home": str(projects.resolve()),
        "allowed_project_roots": [str(projects.resolve()), str(archive.resolve())],
    }


def test_user_config_requires_projects_home_inside_an_allowed_root(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("CO_MATH_CONFIG_HOME", str(tmp_path / "config"))
    projects = tmp_path / "projects"
    other = tmp_path / "other"
    projects.mkdir()
    other.mkdir()

    with pytest.raises(ValueError, match="projects_home"):
        save_user_config(
            UserConfig(projects_home=projects, allowed_project_roots=(other,))
        )


def test_registry_is_pointer_only_and_reports_stale_projects(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("CO_MATH_CONFIG_HOME", str(tmp_path / "config"))
    project = _make_project(tmp_path / "project")

    register_project(project, opened_at="2026-08-23T01:00:00Z")

    raw = json.loads(registry_path().read_text(encoding="utf-8"))
    assert raw["schema_version"] == 1
    assert len(raw["projects"]) == 1
    assert set(raw["projects"][0]) == {
        "project_id",
        "manifest_path",
        "registered_at",
        "last_opened_at",
    }
    assert "goals" not in raw["projects"][0]
    entry = list_registered_projects()[0]
    assert entry["manifest_path"] == str(project / "co-math.toml")
    assert entry["name"] == "Test Project"
    assert entry["registry_status"] == "valid"

    project.rename(tmp_path / "moved")

    stale = list_registered_projects()[0]
    assert stale["registry_status"] == "stale"
    assert stale["name"] is None


def test_registry_registration_is_idempotent_and_updates_last_opened(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("CO_MATH_CONFIG_HOME", str(tmp_path / "config"))
    project = _make_project(tmp_path / "project")

    first = register_project(project, opened_at="2026-08-23T01:00:00Z")
    second = register_project(project, opened_at="2026-08-23T02:00:00Z")

    assert first["registered_at"] == second["registered_at"]
    assert second["last_opened_at"] == "2026-08-23T02:00:00Z"
    assert len(list_registered_projects()) == 1


def test_registry_rejects_duplicate_id_at_a_different_path(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("CO_MATH_CONFIG_HOME", str(tmp_path / "config"))
    project_id = "67f2956d-0196-4f49-9fae-0c44b5173ec5"
    first = _make_project(tmp_path / "first", project_id=project_id)
    second = _make_project(tmp_path / "second", project_id=project_id)
    register_project(first)

    with pytest.raises(ValueError, match="already registered"):
        register_project(second)
    with pytest.raises(ValueError, match="already registered"):
        register_project(second, replace_stale=True)


def test_registry_rejects_changed_identity_at_the_same_path(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("CO_MATH_CONFIG_HOME", str(tmp_path / "config"))
    project = _make_project(tmp_path / "project")
    register_project(project)
    write_manifest(project, new_manifest("Replacement Identity"))

    with pytest.raises(ValueError, match="different project id"):
        register_project(project)


def test_registry_reports_invalid_manifest_without_deleting_entry(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("CO_MATH_CONFIG_HOME", str(tmp_path / "config"))
    project = _make_project(tmp_path / "project")
    registered = register_project(project)
    (project / "co-math.toml").write_text("schema_version = 999\n", encoding="utf-8")

    entries = list_registered_projects()

    assert len(entries) == 1
    assert entries[0]["project_id"] == registered["project_id"]
    assert entries[0]["registry_status"] == "invalid"
    assert "Missing manifest fields" in entries[0]["error"]


def test_registry_rejects_invalid_registry_schema(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("CO_MATH_CONFIG_HOME", str(tmp_path / "config"))
    registry_path().parent.mkdir(parents=True)
    registry_path().write_text(
        json.dumps({"schema_version": 2, "projects": []}), encoding="utf-8"
    )

    with pytest.raises(ValueError, match="registry schema_version"):
        list_registered_projects()
