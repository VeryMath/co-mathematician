"""Lightweight harness for a coding-agent-driven Co-Mathematician workspace."""

from .schemas import GateResult
from .workspace import init_workspace, new_workstream

__all__ = ["GateResult", "init_workspace", "new_workstream"]
