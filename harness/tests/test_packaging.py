from __future__ import annotations

from pathlib import Path

from setuptools import find_namespace_packages

try:
    import tomllib
except ModuleNotFoundError:  # pragma: no cover - Python 3.9 and 3.10
    import tomli as tomllib


ROOT = Path(__file__).resolve().parents[2]


def test_distribution_excludes_test_packages() -> None:
    config = tomllib.loads((ROOT / "pyproject.toml").read_text(encoding="utf-8"))
    discovery = config["tool"]["setuptools"]["packages"]["find"]
    packages = find_namespace_packages(
        where=str(ROOT),
        include=discovery["include"],
        exclude=discovery.get("exclude", ()),
    )

    assert "harness.co_math" in packages
    assert all(not package.startswith("harness.tests") for package in packages)
