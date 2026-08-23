# Co-Math Project Core Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add durable, independent Co-Math projects that can be created, discovered, listed, adopted, inspected, and resumed without copying the harness repository.

**Architecture:** Add a project layer above the existing workspace lifecycle. `co-math.toml` is immutable project identity, the existing `workspace/` remains the mutable research source of truth, and a pointer-only user registry supports discovery without owning research state. Project creation uses packaged templates and an adjacent temporary directory before an atomic rename.

**Tech Stack:** Python 3.9+, argparse, pathlib, importlib.resources, tomllib/tomli, PyYAML, pytest, Git subprocesses

**Spec:** `docs/superpowers/specs/2026-08-23-opencode-gui-project-lifecycle-design.md`

## Global Constraints

- Preserve all existing `--workspace` command behavior and lifecycle gates.
- Do not mutate an existing project during `status`, `resume`, `list`, or `doctor`.
- Keep mutable research state out of `co-math.toml` and the user registry.
- Reject path traversal, symlinked managed paths, nested projects, and non-empty targets.
- Default new projects to independent Git repositories; `--no-git` is the only opt-out.
- Do not add project-level `completed` status in version 0.3.
- Use `/opt/anaconda3/bin/python3.13 -m pytest` for local verification.

---

### Task 1: Project Manifest And Resolver

**Files:**
- Create: `harness/co_math/project.py`
- Create: `harness/tests/test_project.py`
- Modify: `harness/co_math/__init__.py`
- Modify: `pyproject.toml`

**Interfaces:**
- Produces: `ProjectManifest`, `ResolvedProject`, `read_manifest()`, `write_manifest()`, `discover_project()`, `resolve_project()`, `validate_project_name()`, and `new_manifest()`.
- Consumes: `utc_timestamp()` and `atomic_write_text()` from existing modules.

- [ ] **Step 1: Write failing manifest validation tests**

```python
def test_manifest_round_trip_and_project_discovery(tmp_path):
    root = tmp_path / "Muon 研究"
    root.mkdir()
    manifest = new_manifest("Muon 研究", workspace="workspace")
    write_manifest(root, manifest)
    nested = root / "notes" / "drafts"
    nested.mkdir(parents=True)

    resolved = discover_project(nested)

    assert resolved.root == root.resolve()
    assert resolved.workspace == (root / "workspace").resolve()
    assert read_manifest(root).project_id == manifest.project_id


@pytest.mark.parametrize("workspace", ["../workspace", "a/b", ".", ""])
def test_manifest_rejects_unsafe_workspace(workspace, tmp_path):
    data = valid_manifest_data(workspace=workspace)
    write_raw_manifest(tmp_path, data)
    with pytest.raises(ValueError, match="workspace"):
        read_manifest(tmp_path)
```

- [ ] **Step 2: Run tests and verify RED**

Run: `/opt/anaconda3/bin/python3.13 -m pytest harness/tests/test_project.py -q`

Expected: collection fails because `harness.co_math.project` does not exist.

- [ ] **Step 3: Implement the immutable model and parser**

```python
@dataclass(frozen=True)
class ProjectManifest:
    schema_version: int
    project_id: str
    name: str
    workspace: str
    created_at: str
    created_with: str
    template_version: int


@dataclass(frozen=True)
class ResolvedProject:
    root: Path
    workspace: Path
    manifest: ProjectManifest
```

Use `tomllib` on Python 3.11+ and the conditional `tomli` dependency on Python 3.9-3.10. Serialize only the seven schema fields with escaped TOML strings. Require schema version `1`, template version `1`, a canonical UUID, a non-empty Unicode name, and one safe relative workspace directory name.

- [ ] **Step 4: Implement discovery and path precedence**

```python
def resolve_project(
    *,
    project: str | Path | None = None,
    workspace: str | Path | None = None,
    cwd: str | Path | None = None,
) -> ResolvedProject | None:
    """Resolve explicit project, nearest manifest, explicit legacy workspace, or cwd/workspace."""
```

An explicit `--project` must resolve a manifest. Upward discovery stops at the filesystem root. Legacy workspace resolution returns `None` at the project layer so callers can continue using the exact workspace path.

- [ ] **Step 5: Run focused and baseline tests**

Run: `/opt/anaconda3/bin/python3.13 -m pytest harness/tests/test_project.py harness/tests/test_workspace.py -q`

Expected: PASS.

- [ ] **Step 6: Commit**

```bash
git add harness/co_math/project.py harness/co_math/__init__.py harness/tests/test_project.py pyproject.toml
git commit -m "feat: add Co-Math project manifests"
```

### Task 2: User Configuration And Pointer Registry

**Files:**
- Create: `harness/co_math/registry.py`
- Create: `harness/tests/test_registry.py`
- Modify: `harness/co_math/storage.py`

**Interfaces:**
- Consumes: `ProjectManifest`, `read_manifest()`.
- Produces: `UserConfig`, `config_home()`, `load_user_config()`, `save_user_config()`, `register_project()`, `list_registered_projects()`, and a generic `file_lock()`.

- [ ] **Step 1: Write failing registry tests**

```python
def test_registry_is_pointer_only_and_reports_stale_projects(tmp_path, monkeypatch):
    monkeypatch.setenv("CO_MATH_CONFIG_HOME", str(tmp_path / "config"))
    project = make_manifest_project(tmp_path / "project")
    register_project(project)

    entry = list_registered_projects()[0]
    assert entry["manifest_path"] == str(project / "co-math.toml")
    assert "goals" not in entry
    project.rename(tmp_path / "moved")
    assert list_registered_projects()[0]["registry_status"] == "stale"


def test_registry_rejects_duplicate_id_at_a_different_path(tmp_path, monkeypatch):
    monkeypatch.setenv("CO_MATH_CONFIG_HOME", str(tmp_path / "config"))
    first, second = make_two_projects_with_same_id(tmp_path)
    register_project(first)
    with pytest.raises(ValueError, match="already registered"):
        register_project(second)
```

- [ ] **Step 2: Run tests and verify RED**

Run: `/opt/anaconda3/bin/python3.13 -m pytest harness/tests/test_registry.py -q`

Expected: collection fails because `harness.co_math.registry` does not exist.

- [ ] **Step 3: Generalize file locking without changing workspace locking**

```python
@contextmanager
def file_lock(lock_path: str | Path) -> Iterator[None]:
    target = Path(lock_path).resolve()
    target.parent.mkdir(parents=True, exist_ok=True)
    # Reuse the current thread/process lock implementation.
```

Refactor `workspace_lock()` to delegate to `file_lock(project / ".co-math.lock")`; preserve re-entrant and cross-process behavior.

- [ ] **Step 4: Implement config and registry schemas**

```python
@dataclass(frozen=True)
class UserConfig:
    projects_home: Path
    allowed_project_roots: tuple[Path, ...]


def register_project(project_root: str | Path) -> dict[str, object]:
    """Validate the manifest and atomically upsert its path under a registry lock."""
```

Use `CO_MATH_CONFIG_HOME` for deterministic tests, then `XDG_CONFIG_HOME`, `APPDATA`, or `~/.config/co-mathematician`. Store `config.json`, `projects.json`, and `.registry.lock` there. Revalidate every manifest during list and preserve stale records.

- [ ] **Step 5: Run registry, storage, and baseline tests**

Run: `/opt/anaconda3/bin/python3.13 -m pytest harness/tests/test_registry.py harness/tests/test_storage.py -q`

Expected: PASS.

- [ ] **Step 6: Commit**

```bash
git add harness/co_math/registry.py harness/co_math/storage.py harness/tests/test_registry.py
git commit -m "feat: add Co-Math project registry"
```

### Task 3: Packaged Project Template And Atomic Scaffold

**Files:**
- Create: `harness/co_math/project_template/__init__.py`
- Create: `harness/co_math/project_template/README.md`
- Create: `harness/co_math/project_template/AGENTS.md`
- Create: `harness/co_math/project_template/CLAUDE.md`
- Create: `harness/co_math/project_template/agents/roles/*.md`
- Create: `harness/co_math/project_template/.agents/skills/co-mathematician/**`
- Create: `harness/co_math/project_template/.codex/**`
- Create: `harness/co_math/project_template/.claude/**`
- Create: `harness/co_math/project_template/.cursor/**`
- Create: `harness/co_math/scaffold.py`
- Create: `harness/tests/test_scaffold.py`
- Modify: `harness/co_math/workspace.py`
- Modify: `pyproject.toml`

**Interfaces:**
- Consumes: `new_manifest()`, `write_manifest()`, `register_project()`, `init_workspace()`.
- Produces: `CreateProjectResult`, `create_project()`, `select_language_policy()`, `_resolve_target()`, `_copy_project_template()`, and `_initialize_git()`.

- [ ] **Step 1: Write failing scaffold behavior tests**

```python
def test_create_project_builds_self_contained_git_project(tmp_path, monkeypatch):
    configure_home(monkeypatch, tmp_path / "projects")
    result = create_project("ADMM 研究", language="user-readable")

    root = result.project.root
    assert (root / "co-math.toml").is_file()
    assert (root / "workspace/project/GOALS.yaml").is_file()
    assert (root / ".agents/skills/co-mathematician/SKILL.md").is_file()
    assert (root / "agents/roles/logic_reviewer.md").is_file()
    assert (root / ".git").is_dir()
    assert load_goals(root / "workspace")["language_policy"]["code"] == "user-readable"


def test_failed_scaffold_leaves_no_target_or_temp_directory(tmp_path, monkeypatch):
    target = tmp_path / "broken"
    monkeypatch.setattr(scaffold, "_initialize_git", raising_git_init)
    with pytest.raises(RuntimeError, match="git init"):
        create_project("broken", path=target)
    assert not target.exists()
    assert not list(tmp_path.glob(".broken.co-math-tmp-*"))
```

Also test Unicode normalization, Windows reserved names, path separators, existing non-empty directories, symlink parents, nested projects, two distinct IDs, `--no-git`, and registry-write warning behavior.

- [ ] **Step 2: Run tests and verify RED**

Run: `/opt/anaconda3/bin/python3.13 -m pytest harness/tests/test_scaffold.py -q`

Expected: collection fails because `harness.co_math.scaffold` does not exist.

- [ ] **Step 3: Package the protocol template**

Copy canonical role cards and existing platform adapters into the resource tree. Author project-specific entry documents that tell agents to resolve `co-math.toml`, run read-only `co-math resume`, refresh skills, and preserve goal/reviewer gates. Configure explicit package-data globs for every hidden adapter directory and verify resources through `importlib.resources.files()`.

- [ ] **Step 4: Add language-policy initialization**

```python
VALID_LANGUAGE_POLICIES = ("en", "user-notes", "user-readable", "match")


def select_language_policy(workspace: str | Path, policy: str) -> None:
    """Persist a stable policy code in GOALS.yaml and refresh project documents."""
```

Keep existing `init_workspace(workspace)` output unchanged when no policy is supplied.

- [ ] **Step 5: Implement atomic project creation**

```python
@dataclass(frozen=True)
class CreateProjectResult:
    project: ResolvedProject
    warnings: tuple[str, ...] = ()


def create_project(
    name: str,
    *,
    path: str | Path | None = None,
    language: str | None = None,
    initialize_git: bool = True,
) -> CreateProjectResult:
    target = _resolve_target(name, path)
    temporary = _create_adjacent_temporary(target)
    try:
        _copy_project_template(temporary)
        init_workspace(temporary / "workspace")
        if language is not None:
            select_language_policy(temporary / "workspace", language)
        write_manifest(temporary, new_manifest(name))
        if initialize_git:
            _initialize_git(temporary)
        _publish_temporary_project(temporary, target)
    except Exception:
        shutil.rmtree(temporary, ignore_errors=True)
        raise
    return _register_created_project(target)
```

Validate first, copy resources into an adjacent temporary directory, initialize `workspace/`, write the manifest, optionally run `git init` with an argument array, and atomically rename. If registry update alone fails, return the created project with a repair warning instead of deleting it.

- [ ] **Step 6: Run scaffold and existing lifecycle tests**

Run: `/opt/anaconda3/bin/python3.13 -m pytest harness/tests/test_scaffold.py harness/tests/test_lifecycle.py harness/tests/test_workspace.py -q`

Expected: PASS.

- [ ] **Step 7: Commit**

```bash
git add harness/co_math/project_template harness/co_math/scaffold.py harness/co_math/workspace.py harness/tests/test_scaffold.py pyproject.toml
git commit -m "feat: scaffold independent Co-Math projects"
```

### Task 4: Read-Only Project Context

**Files:**
- Create: `harness/co_math/context.py`
- Create: `harness/tests/test_context.py`

**Interfaces:**
- Consumes: `ResolvedProject`, `load_goals()`, `read_messages()`, `read_skill_handoffs()`, and existing gates.
- Produces: `project_snapshot()` and `render_resume_text()`.

- [ ] **Step 1: Write failing snapshot tests**

```python
def test_resume_aggregates_state_without_writing(tmp_path):
    project = make_project_with_goal_and_workstream(tmp_path)
    before = tree_hashes(project.root)

    snapshot = project_snapshot(project)

    assert snapshot["status"] == "active"
    assert snapshot["goals"]["approved"][0]["id"] == "G1"
    assert snapshot["workstreams"]["active"][0]["goal_id"] == "G1"
    assert snapshot["next_gate"] == "workstream_review"
    assert tree_hashes(project.root) == before
```

Test `onboarding`, `active`, `final_ready`, invalid state, recent-message limits, and active Skill handoffs.

- [ ] **Step 2: Run tests and verify RED**

Run: `/opt/anaconda3/bin/python3.13 -m pytest harness/tests/test_context.py -q`

Expected: collection fails because `harness.co_math.context` does not exist.

- [ ] **Step 3: Implement status projection and deterministic output**

```python
def project_snapshot(project: ResolvedProject, *, recent_limit: int = 10) -> dict[str, object]:
    """Return a JSON-safe projection without refreshing or rewriting any file."""


def render_resume_text(snapshot: Mapping[str, object]) -> str:
    """Render project identity, current gates, and the next safe action."""
```

Return only `onboarding`, `active`, `final_ready`, or `invalid`. Treat missing registry paths as `stale` only in registry list output, never as an internal project status.

- [ ] **Step 4: Run context and gate tests**

Run: `/opt/anaconda3/bin/python3.13 -m pytest harness/tests/test_context.py harness/tests/test_gating.py -q`

Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add harness/co_math/context.py harness/tests/test_context.py
git commit -m "feat: add read-only project resume context"
```

### Task 5: Project Lifecycle CLI And Legacy Compatibility

**Files:**
- Modify: `harness/co_math/cli.py`
- Create: `harness/tests/test_project_cli.py`
- Modify: `harness/tests/test_cli_lifecycle.py`
- Modify: `harness/co_math/__init__.py`

**Interfaces:**
- Consumes: all project, registry, scaffold, and context interfaces from Tasks 1-4.
- Produces: `new`, `list`, `status`, `resume`, `adopt`, and `doctor` commands plus automatic project resolution for existing lifecycle commands.

- [ ] **Step 1: Write failing CLI tests**

```python
def test_cli_new_list_and_resume_json(tmp_path, monkeypatch, capsys):
    configure_home(monkeypatch, tmp_path / "projects")
    assert main(["new", "Muon", "--language", "match", "--no-git", "--json"]) == 0
    created = json.loads(capsys.readouterr().out)
    assert created["status"] == "onboarding"

    assert main(["list", "--json"]) == 0
    listed = json.loads(capsys.readouterr().out)
    assert listed[0]["project_id"] == created["project_id"]

    assert main(["resume", "--project", created["path"], "--json"]) == 0
    resumed = json.loads(capsys.readouterr().out)
    assert resumed["project"]["project_id"] == created["project_id"]
```

Add tests for `adopt` preserving every pre-existing workspace file, `doctor` diagnostics, nearest-manifest discovery from a child directory, explicit `--workspace` precedence, and the unchanged old lifecycle test.

- [ ] **Step 2: Run tests and verify RED**

Run: `/opt/anaconda3/bin/python3.13 -m pytest harness/tests/test_project_cli.py -q`

Expected: argparse rejects `new` as an unknown command.

- [ ] **Step 3: Add parsers and structured command results**

```text
co-math new <name> [--path PATH] [--language POLICY] [--no-git] [--json]
co-math list [--json]
co-math status [--project PATH] [--json]
co-math resume [--project PATH] [--json]
co-math adopt <path> [--json]
co-math doctor [--project PATH] [--json]
```

JSON commands write one JSON document to stdout; failures continue through the existing `ERROR:` stderr boundary and return code `1`.

- [ ] **Step 4: Add unified existing-command resolution**

Give existing commands optional `--project` and change parser-level workspace defaults to `None`. Resolve explicit workspace first when supplied, then explicit project, nearest manifest, and finally legacy `./workspace`. Keep `co-math init` creation semantics unchanged.

- [ ] **Step 5: Run CLI and full tests**

Run: `/opt/anaconda3/bin/python3.13 -m pytest harness/tests/test_project_cli.py harness/tests/test_cli_lifecycle.py -q`

Run: `/opt/anaconda3/bin/python3.13 -m pytest -q`

Expected: all tests PASS.

- [ ] **Step 6: Commit**

```bash
git add harness/co_math/cli.py harness/co_math/__init__.py harness/tests/test_project_cli.py harness/tests/test_cli_lifecycle.py
git commit -m "feat: add Co-Math project lifecycle commands"
```

### Task 6: Version, Packaging, And User Documentation

**Files:**
- Modify: `pyproject.toml`
- Modify: `README.md`
- Modify: `README.zh-CN.md`
- Create: `harness/tests/test_packaging.py`

**Interfaces:**
- Consumes: the complete Project Core CLI.
- Produces: installable version `0.3.0` with discoverable package resources and a first-project/next-project guide.

- [ ] **Step 1: Write failing package-resource test**

```python
def test_packaged_project_template_has_required_hidden_resources():
    root = resources.files("harness.co_math.project_template")
    required = [
        "AGENTS.md",
        ".agents/skills/co-mathematician/SKILL.md",
        ".codex/config.toml",
        ".claude/agents/logic_reviewer.md",
        ".cursor/rules/co-mathematician.mdc",
    ]
    for relative in required:
        assert root.joinpath(*relative.split("/")).is_file()
```

- [ ] **Step 2: Run the resource test and verify RED if package globs are incomplete**

Run: `/opt/anaconda3/bin/python3.13 -m pytest harness/tests/test_packaging.py -q`

Expected: FAIL until every required package-data pattern is declared.

- [ ] **Step 3: Update packaging and bilingual lifecycle documentation**

Document one-time Core installation, `co-math new`, opening the returned directory in a GUI coding agent, `co-math resume`, `co-math list`, and starting a second independent project. Keep legacy in-repository workspace instructions in a compatibility section.

- [ ] **Step 4: Build and inspect a wheel**

Run: `/opt/anaconda3/bin/python3.13 -m pip wheel . --no-deps -w /tmp/co-math-wheel`

Run: `/opt/anaconda3/bin/python3.13 -m zipfile -l /tmp/co-math-wheel/co_mathematician_workspace-0.3.0-py3-none-any.whl`

Expected: the wheel lists manifest code and all project-template hidden resources.

- [ ] **Step 5: Run the full suite**

Run: `/opt/anaconda3/bin/python3.13 -m pytest -q`

Expected: all tests PASS.

- [ ] **Step 6: Commit**

```bash
git add pyproject.toml README.md README.zh-CN.md harness/tests/test_packaging.py
git commit -m "docs: document independent Co-Math projects"
```
