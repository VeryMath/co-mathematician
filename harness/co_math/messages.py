from __future__ import annotations

import json
from pathlib import Path

from .schemas import VALID_MESSAGE_TYPES, MessageRecord, utc_timestamp


def append_message(
    workspace: str | Path,
    *,
    sender: str,
    recipient: str,
    message_type: str,
    content: str,
    provenance: list[str] | None = None,
    uncertainty: list[str] | None = None,
) -> MessageRecord:
    if message_type not in VALID_MESSAGE_TYPES:
        raise ValueError(f"Unsupported message type: {message_type}")

    record: MessageRecord = {
        "timestamp": utc_timestamp(),
        "sender": sender,
        "recipient": recipient,
        "type": message_type,
        "content": content,
        "provenance": provenance or [],
        "uncertainty": uncertainty or [],
    }
    path = Path(workspace) / "project" / "messages.jsonl"
    if path.is_symlink() or (path.exists() and not path.is_file()):
        raise ValueError(f"messages.jsonl is missing or unsafe: {path}")
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(record, ensure_ascii=False) + "\n")
    return record


def read_messages(workspace: str | Path) -> list[MessageRecord]:
    path = Path(workspace) / "project" / "messages.jsonl"
    if path.is_symlink() or (path.exists() and not path.is_file()):
        raise ValueError(f"messages.jsonl is missing or unsafe: {path}")
    if not path.exists():
        return []
    records: list[MessageRecord] = []
    for line_number, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
        if line.strip():
            try:
                record = json.loads(line)
            except json.JSONDecodeError as exc:
                raise ValueError(f"messages.jsonl line {line_number} is invalid JSON") from exc
            if not isinstance(record, dict):
                raise ValueError(f"messages.jsonl line {line_number} must be an object")
            required = {"timestamp", "sender", "recipient", "type", "content", "provenance", "uncertainty"}
            if set(record) != required or record["type"] not in VALID_MESSAGE_TYPES:
                raise ValueError(f"messages.jsonl line {line_number} has an invalid schema")
            if not all(isinstance(record[field], str) for field in ("timestamp", "sender", "recipient", "type", "content")):
                raise ValueError(f"messages.jsonl line {line_number} has invalid text fields")
            if not all(isinstance(record[field], list) and all(isinstance(item, str) for item in record[field]) for field in ("provenance", "uncertainty")):
                raise ValueError(f"messages.jsonl line {line_number} has invalid evidence fields")
            records.append(record)
    return records
