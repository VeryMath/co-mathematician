from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Literal, TypedDict

MessageType = Literal[
    "status",
    "instruction",
    "question",
    "proposal",
    "decision",
    "artifact",
    "review",
    "failure",
]
WorkstreamKind = Literal["proof", "computation", "literature", "review"]
SkillHandoffMode = Literal["skill_guided", "quick_skill"]

VALID_MESSAGE_TYPES: tuple[str, ...] = (
    "status",
    "instruction",
    "question",
    "proposal",
    "decision",
    "artifact",
    "review",
    "failure",
)
VALID_WORKSTREAM_KINDS: tuple[str, ...] = (
    "proof",
    "computation",
    "literature",
    "review",
)
VALID_SKILL_HANDOFF_MODES: tuple[str, ...] = ("skill_guided", "quick_skill")


class MessageRecord(TypedDict):
    timestamp: str
    sender: str
    recipient: str
    type: str
    content: str
    provenance: list[str]
    uncertainty: list[str]


class SkillHandoffRecord(TypedDict):
    timestamp: str
    skill: str
    mode: str
    status: str
    reason: str
    query: str
    skill_path: str


@dataclass(frozen=True)
class GateResult:
    gate: str
    passed: bool
    issues: list[str] = field(default_factory=list)
    details: dict[str, Any] = field(default_factory=dict)


def utc_timestamp() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")
