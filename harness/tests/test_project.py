from __future__ import annotations

import uuid
from pathlib import Path

import pytest

from harness.co_math.project import (
    MANIFEST_FILENAME,
    discover_project,
    new_manifest,
    read_manifest,
    resolve_project,
    validate_project_name,
    write_manifest,
)


def _manifest_text(**overrides: object) -> str:
    values: dict[str, object] = {
        "schema_version": 1,
        "project_id": "67f2956d-0196-4f49-9fae-0c44b5173ec5",
        "name": "ADMM Research",
        "workspace": "workspace",
        "created_at": "2026-08-23T00:00:00Z",
        "created_with": "0.3.0",
        "template_version": 1,
    }
    values.update(overrides)
    return "\n".join(
        [
            f"schema_version = {values['schema_version']}",
            f'project_id = "{values["project_id"]}"',
            f'name = "{values["name"]}"',
            f'workspace = "{values["workspace"]}"',
            f'created_at = "{values["created_at"]}"',
            f'created_with = "{values["created_with"]}"',
            f"template_version = {values['template_version']}",
            "",
        ]
    )


def test_manifest_round_trip_and_project_discovery(tmp_path: Path) -> None:
    root = tmp_path / "Muon 研究"
    root.mkdir()
    (root / "workspace").mkdir()
    manifest = new_manifest("Muon 研究", workspace="workspace")
    write_manifest(root, manifest)
    nested = root / "notes" / "drafts"
    nested.mkdir(parents=True)

    resolved = discover_project(nested)

    assert resolved.root == root.resolve()
    assert resolved.workspace == (root / "workspace").resolve()
    assert read_manifest(root) == manifest
    assert uuid.UUID(manifest.project_id).version == 4


@pytest.mark.parametrize("workspace", ["../workspace", "a/b", "a\\b", ".", "", "/tmp/ws"])
def test_manifest_rejects_unsafe_workspace(workspace: str, tmp_path: Path) -> None:
    (tmp_path / MANIFEST_FILENAME).write_text(
        _manifest_text(workspace=workspace), encoding="utf-8"
    )

    with pytest.raises(ValueError, match="workspace"):
        read_manifest(tmp_path)


@pytest.mark.parametrize(
    ("field", "value", "message"),
    [
        ("schema_version", 2, "schema_version"),
        ("template_version", 0, "template_version"),
        ("project_id", "not-a-uuid", "project_id"),
        ("name", "", "name"),
        ("created_at", "yesterday", "created_at"),
        ("created_with", "", "created_with"),
    ],
)
def test_manifest_rejects_invalid_fields(
    field: str,
    value: object,
    message: str,
    tmp_path: Path,
) -> None:
    (tmp_path / MANIFEST_FILENAME).write_text(
        _manifest_text(**{field: value}), encoding="utf-8"
    )

    with pytest.raises(ValueError, match=message):
        read_manifest(tmp_path)


def test_manifest_rejects_unknown_or_missing_keys(tmp_path: Path) -> None:
    path = tmp_path / MANIFEST_FILENAME
    path.write_text(_manifest_text() + 'mutable_status = "active"\n', encoding="utf-8")
    with pytest.raises(ValueError, match="Unknown manifest fields"):
        read_manifest(tmp_path)

    path.write_text(
        _manifest_text().replace('created_with = "0.3.0"\n', ""),
        encoding="utf-8",
    )
    with pytest.raises(ValueError, match="Missing manifest fields"):
        read_manifest(tmp_path)


def test_manifest_rejects_noncanonical_project_name(tmp_path: Path) -> None:
    (tmp_path / MANIFEST_FILENAME).write_text(
        _manifest_text(name="  ＡＤＭＭ 研究  "), encoding="utf-8"
    )

    with pytest.raises(ValueError, match="canonical project name"):
        read_manifest(tmp_path)


def test_discovery_uses_nearest_manifest_and_explicit_project_wins(tmp_path: Path) -> None:
    outer = tmp_path / "outer"
    inner = outer / "inner"
    child = inner / "child"
    for root, name in ((outer, "Outer"), (inner, "Inner")):
        root.mkdir(parents=True, exist_ok=True)
        (root / "workspace").mkdir()
        write_manifest(root, new_manifest(name))
    child.mkdir()

    assert discover_project(child).root == inner.resolve()
    assert resolve_project(project=outer, cwd=child).root == outer.resolve()


def test_resolve_project_accepts_manifest_path(tmp_path: Path) -> None:
    (tmp_path / "workspace").mkdir()
    write_manifest(tmp_path, new_manifest("Manifest path"))

    resolved = resolve_project(project=tmp_path / MANIFEST_FILENAME)

    assert resolved.root == tmp_path.resolve()


def test_discovery_rejects_symlinked_workspace(tmp_path: Path) -> None:
    root = tmp_path / "project"
    external = tmp_path / "external"
    root.mkdir()
    external.mkdir()
    (root / "workspace").symlink_to(external, target_is_directory=True)
    write_manifest(root, new_manifest("Unsafe"))

    with pytest.raises(ValueError, match="symlink"):
        discover_project(root)


@pytest.mark.parametrize(
    "name",
    ["", "   ", ".", "..", "a/b", "a\\b", "CON", "nul", "bad\x00name", "line\nbreak"],
)
def test_validate_project_name_rejects_unsafe_names(name: str) -> None:
    with pytest.raises(ValueError, match="project name"):
        validate_project_name(name)


def test_validate_project_name_normalizes_unicode_and_trims() -> None:
    assert validate_project_name("  ＡＤＭＭ 研究  ") == "ADMM 研究"
