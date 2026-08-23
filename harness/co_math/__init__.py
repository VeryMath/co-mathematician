"""Lightweight harness for a coding-agent-driven Co-Mathematician workspace."""

from .project import ProjectManifest, ResolvedProject, discover_project, resolve_project
from .schemas import GateResult
from .skill_handoff import read_skill_handoffs, record_skill_handoff
from .workspace import init_workspace, new_workstream

__all__ = [
    "GateResult",
    "ProjectManifest",
    "ResolvedProject",
    "discover_project",
    "init_workspace",
    "new_workstream",
    "read_skill_handoffs",
    "record_skill_handoff",
    "resolve_project",
]
