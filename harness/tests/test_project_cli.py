from __future__ import annotations

import hashlib
import json
from pathlib import Path

import pytest

from harness.co_math.cli import main
from harness.co_math.messages import read_messages
from harness.co_math.registry import UserConfig, save_user_config
from harness.co_math.workspace import init_workspace, load_goals, save_goals


def _configure_home(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> Path:
    projects_home = tmp_path / "projects"
    monkeypatch.setenv("CO_MATH_CONFIG_HOME", str(tmp_path / "config"))
    save_user_config(
        UserConfig(projects_home=projects_home, allowed_project_roots=(projects_home,))
    )
    return projects_home


def _create_with_cli(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
    *,
    name: str = "Muon",
) -> dict[str, object]:
    _configure_home(tmp_path, monkeypatch)
    assert (
        main(
            [
                "new",
                name,
                "--language",
                "match",
                "--no-git",
                "--json",
            ]
        )
        == 0
    )
    return json.loads(capsys.readouterr().out)


def _file_hashes(root: Path) -> dict[str, str]:
    return {
        path.relative_to(root).as_posix(): hashlib.sha256(path.read_bytes()).hexdigest()
        for path in sorted(root.rglob("*"))
        if path.is_file() and not path.is_symlink()
    }


def test_cli_new_list_status_and_resume_json(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    created = _create_with_cli(tmp_path, monkeypatch, capsys)

    assert created["name"] == "Muon"
    assert created["status"] == "onboarding"
    assert created["next_gate"] == "onboarding"
    assert Path(str(created["path"])).is_dir()

    assert main(["list", "--json"]) == 0
    listed = json.loads(capsys.readouterr().out)
    assert len(listed) == 1
    assert listed[0]["project_id"] == created["project_id"]
    assert listed[0]["status"] == "onboarding"

    assert main(["status", "--project", str(created["path"]), "--json"]) == 0
    status = json.loads(capsys.readouterr().out)
    assert status["project"]["project_id"] == created["project_id"]
    assert status["status"] == "onboarding"

    assert main(["resume", "--project", str(created["path"]), "--json"]) == 0
    resumed = json.loads(capsys.readouterr().out)
    assert resumed == status


def test_cli_list_projects_stale_registry_pointer(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    created = _create_with_cli(tmp_path, monkeypatch, capsys)
    Path(str(created["path"])).rename(tmp_path / "moved")

    assert main(["list", "--json"]) == 0
    listed = json.loads(capsys.readouterr().out)

    assert listed[0]["status"] == "stale"
    assert listed[0]["project_id"] == created["project_id"]


def test_cli_discovers_project_from_child_for_existing_lifecycle_command(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    created = _create_with_cli(tmp_path, monkeypatch, capsys)
    root = Path(str(created["path"]))
    goals = load_goals(root / "workspace")
    goals["research_question"] = {"status": "approved", "text": "Question"}
    goals["goals"] = [
        {"id": "G1", "title": "Goal", "status": "draft", "workstreams": []}
    ]
    save_goals(root / "workspace", goals)
    child = root / "notes" / "deep"
    child.mkdir(parents=True)
    monkeypatch.chdir(child)

    assert (
        main(
            [
                "approve-goal",
                "--goal-id",
                "G1",
                "--approved-by",
                "user",
                "--approval-id",
                "approval-auto-001",
            ]
        )
        == 0
    )
    capsys.readouterr()

    approved = load_goals(root / "workspace")["goals"][0]
    assert approved["status"] == "approved"


def test_explicit_workspace_overrides_discovered_project(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    created = _create_with_cli(tmp_path, monkeypatch, capsys)
    discovered_root = Path(str(created["path"]))
    explicit_workspace = tmp_path / "legacy-workspace"
    init_workspace(explicit_workspace)
    monkeypatch.chdir(discovered_root)

    assert (
        main(
            [
                "append-message",
                "--workspace",
                str(explicit_workspace),
                "--sender",
                "project_coordinator",
                "--recipient",
                "user",
                "--type",
                "status",
                "--content",
                "explicit workspace",
            ]
        )
        == 0
    )
    capsys.readouterr()

    assert read_messages(explicit_workspace)[0]["content"] == "explicit workspace"
    assert read_messages(discovered_root / "workspace") == []


def test_explicit_workspace_also_controls_default_skill_repo_root(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    first = _create_with_cli(tmp_path, monkeypatch, capsys, name="First")
    assert (
        main(
            [
                "new",
                "Second",
                "--language",
                "match",
                "--no-git",
                "--json",
            ]
        )
        == 0
    )
    second = json.loads(capsys.readouterr().out)
    first_root = Path(str(first["path"]))
    second_root = Path(str(second["path"]))
    unique_skill = second_root / ".agents" / "skills" / "second-only"
    unique_skill.mkdir(parents=True)
    (unique_skill / "SKILL.md").write_text(
        "---\nname: second-only\ndescription: Only in the second project.\n---\n",
        encoding="utf-8",
    )
    monkeypatch.chdir(first_root)

    assert (
        main(
            [
                "refresh-skills",
                "--workspace",
                str(second_root / "workspace"),
                "--json",
            ]
        )
        == 0
    )
    registry = json.loads(capsys.readouterr().out)

    assert "second-only" in {skill["name"] for skill in registry["skills"]}


def test_legacy_workspace_default_still_works_without_manifest(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    monkeypatch.chdir(tmp_path)
    init_workspace(tmp_path / "workspace")

    assert (
        main(
            [
                "append-message",
                "--sender",
                "project_coordinator",
                "--recipient",
                "user",
                "--type",
                "status",
                "--content",
                "legacy default",
            ]
        )
        == 0
    )
    capsys.readouterr()

    assert read_messages(tmp_path / "workspace")[0]["content"] == "legacy default"


def test_cli_adopt_preserves_existing_workspace_files(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    _configure_home(tmp_path, monkeypatch)
    root = tmp_path / "Legacy Project"
    workspace = init_workspace(root / "workspace")
    sentinel = workspace / "project" / "legacy-note.md"
    sentinel.write_text("preserve exactly\n", encoding="utf-8")
    before = _file_hashes(root)

    assert main(["adopt", str(root), "--json"]) == 0
    adopted = json.loads(capsys.readouterr().out)

    assert adopted["name"] == "Legacy Project"
    assert adopted["path"] == str(root.resolve())
    assert adopted["status"] == "onboarding"
    after = _file_hashes(root)
    assert {key: value for key, value in after.items() if key != "co-math.toml"} == before
    assert sentinel.read_text(encoding="utf-8") == "preserve exactly\n"

    assert main(["list", "--json"]) == 0
    listed = json.loads(capsys.readouterr().out)
    assert listed[0]["project_id"] == adopted["project_id"]


def test_cli_doctor_is_read_only_and_reports_valid_project(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    created = _create_with_cli(tmp_path, monkeypatch, capsys)
    root = Path(str(created["path"]))
    before = _file_hashes(root)

    assert main(["doctor", "--project", str(root), "--json"]) == 0
    diagnosis = json.loads(capsys.readouterr().out)

    assert diagnosis["ok"] is True
    assert diagnosis["core_version"] == "0.3.0"
    assert diagnosis["project"]["project_id"] == created["project_id"]
    assert diagnosis["issues"] == []
    assert _file_hashes(root) == before


def test_cli_human_resume_prints_actionable_summary(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    created = _create_with_cli(tmp_path, monkeypatch, capsys)

    assert main(["resume", "--project", str(created["path"])]) == 0
    text = capsys.readouterr().out

    assert "Co-Math project: Muon" in text
    assert "Status: onboarding" in text
    assert "Next gate: onboarding" in text


def test_cli_rejects_unknown_language_without_creating_project(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    projects_home = _configure_home(tmp_path, monkeypatch)

    with pytest.raises(SystemExit):
        main(["new", "Invalid", "--language", "auto"])

    assert not (projects_home / "Invalid").exists()
