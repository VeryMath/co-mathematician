"""Lightweight harness for a coding-agent-driven Co-Mathematician workspace."""

from .schemas import GateResult
from .skill_handoff import read_skill_handoffs, record_skill_handoff
from .workspace import init_workspace, new_workstream

__all__ = [
    "GateResult",
    "init_workspace",
    "new_workstream",
    "read_skill_handoffs",
    "record_skill_handoff",
]
