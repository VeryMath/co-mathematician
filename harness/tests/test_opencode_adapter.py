from __future__ import annotations

import json
from pathlib import Path

import pytest

from harness.co_math.opencode import (
    TOOL_FILENAMES,
    adapter_resource_text,
    inspect_opencode_adapter,
    install_opencode_adapter,
    remove_opencode_adapter,
)
from harness.co_math.registry import load_user_config


def _fake_cli(tmp_path: Path) -> Path:
    cli = tmp_path / "bin" / "co-math"
    cli.parent.mkdir(parents=True)
    cli.write_text("#!/bin/sh\nexit 0\n", encoding="utf-8")
    cli.chmod(0o755)
    return cli


def _install(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
):
    monkeypatch.setenv("CO_MATH_CONFIG_HOME", str(tmp_path / "core-config"))
    cli = _fake_cli(tmp_path)
    projects = tmp_path / "projects"
    archive = tmp_path / "archive"
    return install_opencode_adapter(
        config_dir=tmp_path / "opencode",
        cli_path=cli,
        projects_home=projects,
        allowed_roots=[projects, archive],
    )


def test_installer_writes_exact_global_tools_and_absolute_cli(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    result = _install(tmp_path, monkeypatch)

    assert {path.name for path in result.tool_files} == set(TOOL_FILENAMES)
    assert all(path.parent == tmp_path / "opencode" / "tools" for path in result.tool_files)
    assert result.runner_file == tmp_path / "opencode" / "co-math" / "runner.ts"
    assert result.config_file == tmp_path / "opencode" / "co-math" / "config.json"
    assert result.manifest_file.is_file()
    config = json.loads(result.config_file.read_text(encoding="utf-8"))
    assert config == {
        "schema_version": 1,
        "core_version": "0.3.0",
        "cli_path": str((tmp_path / "bin" / "co-math").resolve()),
        "projects_home": str((tmp_path / "projects").resolve()),
        "allowed_project_roots": [
            str((tmp_path / "projects").resolve()),
            str((tmp_path / "archive").resolve()),
        ],
    }
    core_config = load_user_config()
    assert core_config.projects_home == (tmp_path / "projects").resolve()
    assert core_config.allowed_project_roots == (
        (tmp_path / "projects").resolve(),
        (tmp_path / "archive").resolve(),
    )


def test_installer_is_idempotent_and_preserves_unrelated_files(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    first = _install(tmp_path, monkeypatch)
    unrelated = first.config_dir / "tools" / "my_tool.ts"
    unrelated.write_text("export default {}\n", encoding="utf-8")
    before_manifest = first.manifest_file.read_text(encoding="utf-8")

    second = install_opencode_adapter(
        config_dir=first.config_dir,
        cli_path=tmp_path / "bin" / "co-math",
        projects_home=tmp_path / "projects",
        allowed_roots=[tmp_path / "projects", tmp_path / "archive"],
    )

    assert second == first
    assert second.manifest_file.read_text(encoding="utf-8") == before_manifest
    assert unrelated.read_text(encoding="utf-8") == "export default {}\n"


def test_installer_refuses_relative_missing_or_nonexecutable_cli(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("CO_MATH_CONFIG_HOME", str(tmp_path / "core-config"))
    projects = tmp_path / "projects"
    relative = Path("bin/co-math")
    missing = tmp_path / "missing"
    nonexecutable = tmp_path / "co-math"
    nonexecutable.write_text("#!/bin/sh\n", encoding="utf-8")

    for cli, message in (
        (relative, "absolute"),
        (missing, "does not exist"),
        (nonexecutable, "not executable"),
    ):
        with pytest.raises(ValueError, match=message):
            install_opencode_adapter(
                config_dir=tmp_path / "opencode",
                cli_path=cli,
                projects_home=projects,
                allowed_roots=[projects],
            )


def test_reinstall_refuses_to_overwrite_modified_managed_file(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    installed = _install(tmp_path, monkeypatch)
    modified = installed.tool_files[0]
    modified.write_text("// user modification\n", encoding="utf-8")

    with pytest.raises(ValueError, match="modified"):
        install_opencode_adapter(
            config_dir=installed.config_dir,
            cli_path=tmp_path / "bin" / "co-math",
            projects_home=tmp_path / "projects",
            allowed_roots=[tmp_path / "projects", tmp_path / "archive"],
        )

    assert modified.read_text(encoding="utf-8") == "// user modification\n"


def test_failed_reinstall_does_not_change_core_project_roots(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    installed = _install(tmp_path, monkeypatch)
    before = load_user_config()
    installed.tool_files[0].write_text("// user modification\n", encoding="utf-8")

    with pytest.raises(ValueError, match="modified"):
        install_opencode_adapter(
            config_dir=installed.config_dir,
            cli_path=tmp_path / "bin" / "co-math",
            projects_home=tmp_path / "different-projects",
            allowed_roots=[tmp_path / "different-projects"],
        )

    assert load_user_config() == before


def test_installer_rejects_symlinked_opencode_config_directory(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("CO_MATH_CONFIG_HOME", str(tmp_path / "core-config"))
    actual = tmp_path / "actual-opencode"
    actual.mkdir()
    linked = tmp_path / "linked-opencode"
    linked.symlink_to(actual, target_is_directory=True)

    with pytest.raises(ValueError, match="symlink"):
        install_opencode_adapter(
            config_dir=linked,
            cli_path=_fake_cli(tmp_path),
            projects_home=tmp_path / "projects",
            allowed_roots=[tmp_path / "projects"],
        )


def test_uninstall_removes_only_digest_matching_managed_files(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    installed = _install(tmp_path, monkeypatch)
    modified = installed.runner_file
    modified.write_text("// keep modified runner\n", encoding="utf-8")
    unrelated = installed.config_dir / "tools" / "unrelated.ts"
    unrelated.write_text("// unrelated\n", encoding="utf-8")

    removal = remove_opencode_adapter(config_dir=installed.config_dir)

    assert modified in removal.preserved_files
    assert modified.read_text(encoding="utf-8") == "// keep modified runner\n"
    assert unrelated.is_file()
    assert not installed.config_file.exists()
    assert not installed.manifest_file.exists()
    assert all(not path.exists() for path in installed.tool_files)
    assert any("modified" in warning for warning in removal.warnings)


def test_inspection_detects_healthy_and_drifted_installation(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    installed = _install(tmp_path, monkeypatch)

    healthy = inspect_opencode_adapter(config_dir=installed.config_dir)

    assert healthy["installed"] is True
    assert healthy["healthy"] is True
    assert healthy["cli_path"] == str((tmp_path / "bin" / "co-math").resolve())
    assert healthy["cli_path_matches"] is True
    assert healthy["issues"] == []

    installed.config_file.write_text("{}\n", encoding="utf-8")
    drifted = inspect_opencode_adapter(config_dir=installed.config_dir)

    assert drifted["installed"] is True
    assert drifted["healthy"] is False
    assert any("digest" in issue for issue in drifted["issues"])


def test_inspection_detects_adapter_core_version_drift(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    installed = _install(tmp_path, monkeypatch)
    manifest = json.loads(installed.manifest_file.read_text(encoding="utf-8"))
    manifest["core_version"] = "0.2.0"
    installed.manifest_file.write_text(
        json.dumps(manifest, indent=2) + "\n",
        encoding="utf-8",
    )

    diagnosis = inspect_opencode_adapter(config_dir=installed.config_dir)

    assert diagnosis["healthy"] is False
    assert any("version" in issue for issue in diagnosis["issues"])


def test_runner_uses_argument_array_without_shell_interpolation() -> None:
    text = adapter_resource_text("runner.ts")

    assert "Bun.spawn([config.cli_path, ...args]" in text
    assert "Bun.$" not in text
    assert "shell:" not in text
    assert "allowed_project_roots" in text
    assert "requireAllowedTarget" in text


@pytest.mark.parametrize(
    ("filename", "command"),
    [
        ("comath_project_new.ts", "new"),
        ("comath_project_list.ts", "list"),
        ("comath_project_status.ts", "status"),
        ("comath_project_resume.ts", "resume"),
        ("comath_project_adopt.ts", "adopt"),
    ],
)
def test_tools_are_typed_json_delegates(filename: str, command: str) -> None:
    text = adapter_resource_text(filename)

    assert 'from "@opencode-ai/plugin"' in text
    assert "export default tool({" in text
    assert f'"{command}"' in text
    assert '"--json"' in text
    assert "Bun.spawn" not in text
    assert "workspace/project" not in text


def test_write_tools_enforce_allowed_roots() -> None:
    new_tool = adapter_resource_text("comath_project_new.ts")
    adopt_tool = adapter_resource_text("comath_project_adopt.ts")

    assert "requireAllowedTarget" in new_tool
    assert "requireAllowedTarget" in adopt_tool
