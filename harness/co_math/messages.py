from __future__ import annotations

import json
from pathlib import Path

from .schemas import VALID_MESSAGE_TYPES, MessageRecord, utc_timestamp
from .storage import append_jsonl, workspace_lock


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
    root = Path(workspace)
    with workspace_lock(root):
        append_jsonl(root / "project" / "messages.jsonl", record)
    return record


def read_messages(workspace: str | Path) -> list[MessageRecord]:
    path = Path(workspace) / "project" / "messages.jsonl"
    if not path.exists():
        return []
    records: list[MessageRecord] = []
    for line in path.read_text(encoding="utf-8").splitlines():
        if line.strip():
            records.append(json.loads(line))
    return records
