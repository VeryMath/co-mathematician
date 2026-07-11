from __future__ import annotations

import json
from functools import lru_cache
from importlib.resources import files
from typing import Any

from jsonschema import Draft202012Validator, FormatChecker  # type: ignore[import-untyped]


COMPLETION_MANIFEST_FILENAME = "completion-manifest.json"
COMPLETION_MANIFEST_PATH = f"reviewed/{COMPLETION_MANIFEST_FILENAME}"


@lru_cache(maxsize=1)
def _completion_manifest_validator() -> Draft202012Validator:
    schema_text = (
        files("harness.co_math.assets")
        .joinpath("completion_manifest_schema.json")
        .read_text(encoding="utf-8")
    )
    return Draft202012Validator(
        json.loads(schema_text),
        format_checker=FormatChecker(),
    )


def completion_manifest_schema_issues(payload: Any) -> list[str]:
    errors = sorted(
        _completion_manifest_validator().iter_errors(payload),
        key=lambda error: tuple(str(part) for part in error.absolute_path),
    )
    issues = []
    for error in errors:
        location = ".".join(str(part) for part in error.absolute_path) or "manifest"
        issues.append(f"{location}: {error.message}")
    return issues
