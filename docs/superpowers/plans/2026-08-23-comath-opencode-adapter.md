# Co-Math OpenCode Adapter Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Let OpenCode Desktop users create, list, inspect, resume, and adopt independent Co-Math projects through natural-language-triggered global typed tools.

**Architecture:** A Python installer writes five thin TypeScript tool definitions and one shared runner into the user's OpenCode config directory. The runner invokes an absolute `co-math` executable with a subprocess argument array, applies allowed-root checks before writes, and delegates all lifecycle behavior to Project Core. New projects contain project-local OpenCode subagent adapters generated from canonical role cards.

**Tech Stack:** Python 3.9+, pathlib, JSON, TypeScript, `@opencode-ai/plugin`, Bun subprocess API, pytest

**Spec:** `docs/superpowers/specs/2026-08-23-opencode-gui-project-lifecycle-design.md`

## Global Constraints

- Global adapter files live under `~/.config/opencode/tools/` and `~/.config/opencode/co-math/` by default.
- Installation stores an absolute Core executable path; it must not depend on Desktop shell `PATH`.
- Every subprocess invocation uses an argument array and never shell interpolation.
- Write tools reject targets outside configured allowed project roots before invoking Core.
- Read-only tools use the OpenCode `context.directory` unless the user supplies a project path.
- Project-local agents preserve canonical role IDs and reviewer independence boundaries.
- Actual OpenCode Desktop verification remains a separate smoke gate; static/CLI tests cannot claim it passed.

---

### Task 1: Project-Local OpenCode Agent Adapters

**Files:**
- Create: `harness/co_math/project_template/.opencode/agents/workstream_coordinator.md`
- Create: `harness/co_math/project_template/.opencode/agents/proof_explorer.md`
- Create: `harness/co_math/project_template/.opencode/agents/computational_experimenter.md`
- Create: `harness/co_math/project_template/.opencode/agents/literature_researcher.md`
- Create: `harness/co_math/project_template/.opencode/agents/logic_reviewer.md`
- Create: `harness/co_math/project_template/.opencode/agents/adversarial_reviewer.md`
- Create: `harness/co_math/project_template/.opencode/agents/citation_checker.md`
- Create: `harness/co_math/project_template/.opencode/agents/synthesis_agent.md`
- Modify: `harness/tests/test_agent_adapters.py`
- Modify: `harness/tests/test_scaffold.py`

**Interfaces:**
- Consumes: canonical `agents/roles/<role_id>.md` files.
- Produces: eight OpenCode Markdown subagent definitions with matching file stems.

- [ ] **Step 1: Write failing adapter parity tests**

```python
def test_opencode_project_template_covers_canonical_role_ids():
    adapters = {
        path.stem
        for path in (TEMPLATE / ".opencode" / "agents").glob("*.md")
    }
    assert adapters == ROLE_IDS

    for role_id in ROLE_IDS:
        text = (TEMPLATE / ".opencode" / "agents" / f"{role_id}.md").read_text()
        assert "mode: subagent" in text
        assert f"agents/roles/{role_id}.md" in text
        assert "Do not mark any workstream complete." in text
```

Reviewer adapter tests also require `permission.edit: deny` and explicit prohibition on author self-approval. The synthesis adapter may edit only `workspace/final/working_paper.md` by instruction.

- [ ] **Step 2: Run tests and verify RED**

Run: `/opt/anaconda3/bin/python3.13 -m pytest harness/tests/test_agent_adapters.py -q`

Expected: FAIL because `.opencode/agents` is absent.

- [ ] **Step 3: Add all OpenCode subagent files**

Use current OpenCode Markdown frontmatter:

```yaml
---
description: Review one Co-Math workstream for logical correctness.
mode: subagent
permission:
  edit: deny
---
```

Each body points back to its canonical role card and preserves the existing platform-neutral boundaries.

- [ ] **Step 4: Run adapter and scaffold tests**

Run: `/opt/anaconda3/bin/python3.13 -m pytest harness/tests/test_agent_adapters.py harness/tests/test_scaffold.py -q`

Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add harness/co_math/project_template/.opencode harness/tests/test_agent_adapters.py harness/tests/test_scaffold.py
git commit -m "feat: add OpenCode project agents"
```

### Task 2: Global Typed-Tool Bundle And Installer

**Files:**
- Create: `harness/co_math/opencode.py`
- Create: `harness/co_math/opencode_adapter/runner.ts`
- Create: `harness/co_math/opencode_adapter/comath_project_new.ts`
- Create: `harness/co_math/opencode_adapter/comath_project_list.ts`
- Create: `harness/co_math/opencode_adapter/comath_project_status.ts`
- Create: `harness/co_math/opencode_adapter/comath_project_resume.ts`
- Create: `harness/co_math/opencode_adapter/comath_project_adopt.ts`
- Create: `harness/tests/test_opencode_adapter.py`
- Modify: `pyproject.toml`

**Interfaces:**
- Consumes: absolute `co-math` executable, Core user config, allowed project roots.
- Produces: `install_opencode_adapter()`, `remove_opencode_adapter()`, `inspect_opencode_adapter()`, `_resolve_executable()`, `_resolve_allowed_roots()`, and five global tool files.

- [ ] **Step 1: Write failing installer tests**

```python
def test_installer_writes_exact_global_tool_names_and_absolute_cli(tmp_path):
    cli = tmp_path / "bin" / "co-math"
    cli.parent.mkdir()
    cli.write_text("#!/bin/sh\n")
    result = install_opencode_adapter(
        config_dir=tmp_path / "opencode",
        cli_path=cli,
        projects_home=tmp_path / "projects",
        allowed_roots=[tmp_path / "projects"],
    )

    assert {path.name for path in result.tool_files} == {
        "comath_project_new.ts",
        "comath_project_list.ts",
        "comath_project_status.ts",
        "comath_project_resume.ts",
        "comath_project_adopt.ts",
    }
    config = json.loads((tmp_path / "opencode/co-math/config.json").read_text())
    assert config["cli_path"] == str(cli.resolve())
```

Also test refusal of relative/nonexistent executables, resolved allowed roots, atomic overwrite of only managed files, idempotent reinstall, and removal that preserves unrelated OpenCode files.

- [ ] **Step 2: Run tests and verify RED**

Run: `/opt/anaconda3/bin/python3.13 -m pytest harness/tests/test_opencode_adapter.py -q`

Expected: collection fails because `harness.co_math.opencode` does not exist.

- [ ] **Step 3: Implement the adapter resource files**

Each tool uses the current OpenCode helper:

```typescript
import { tool } from "@opencode-ai/plugin"
import { runCore, requireAllowedTarget } from "../co-math/runner"

export default tool({
  description: "Create an independent Co-Math research project.",
  args: {
    name: tool.schema.string().min(1),
    language: tool.schema.enum(["en", "user-notes", "user-readable", "match"]),
    path: tool.schema.string().optional(),
    initializeGit: tool.schema.boolean().optional(),
  },
  async execute(args) {
    if (args.path) await requireAllowedTarget(args.path)
    return runCore(["new", args.name, "--language", args.language, "--json"])
  },
})
```

The actual implementation appends optional arguments without string concatenation and calls `Bun.spawn([config.cliPath, ...args], ...)`. Status and resume pass `context.directory` as `--project` by default.

- [ ] **Step 4: Implement safe installation and removal**

```python
@dataclass(frozen=True)
class OpenCodeInstallResult:
    config_dir: Path
    tool_files: tuple[Path, ...]
    runner_file: Path
    config_file: Path


def install_opencode_adapter(
    *,
    config_dir: str | Path | None = None,
    cli_path: str | Path,
    projects_home: str | Path,
    allowed_roots: Sequence[str | Path],
) -> OpenCodeInstallResult:
    root = resolve_opencode_config_dir(config_dir)
    executable = _resolve_executable(cli_path)
    resolved_home, resolved_roots = _resolve_allowed_roots(
        projects_home,
        allowed_roots,
    )
    written = _write_managed_adapter_files(
        root,
        executable,
        resolved_home,
        resolved_roots,
    )
    _write_install_manifest(root, written)
    return _build_install_result(root, written)
```

Resolve the executable and roots before writing. Use atomic writes, a managed-file manifest, and no recursive deletion. `remove_opencode_adapter()` deletes only files whose current digest matches the install manifest; changed files are reported and preserved.

- [ ] **Step 5: Add static no-shell and tool-schema tests**

```python
def test_runner_uses_argument_array_without_shell_interpolation():
    text = adapter_resource("runner.ts")
    assert "Bun.spawn([config.cliPath, ...args]" in text
    assert "Bun.$" not in text
    assert "shell:" not in text
```

Assert each tool imports `tool`, exposes typed args, emits `--json`, and delegates rather than parsing workspace files.

- [ ] **Step 6: Run adapter tests**

Run: `/opt/anaconda3/bin/python3.13 -m pytest harness/tests/test_opencode_adapter.py -q`

Expected: PASS.

- [ ] **Step 7: Commit**

```bash
git add harness/co_math/opencode.py harness/co_math/opencode_adapter harness/tests/test_opencode_adapter.py pyproject.toml
git commit -m "feat: add OpenCode global project tools"
```

### Task 3: Adapter CLI, Doctor, And Documentation

**Files:**
- Modify: `harness/co_math/cli.py`
- Modify: `harness/co_math/context.py`
- Modify: `harness/tests/test_project_cli.py`
- Modify: `README.md`
- Modify: `README.zh-CN.md`

**Interfaces:**
- Consumes: `install_opencode_adapter()`, `remove_opencode_adapter()`, and `inspect_opencode_adapter()`.
- Produces: `install-opencode`, `uninstall-opencode`, and adapter-aware `doctor` behavior.

- [ ] **Step 1: Write failing CLI tests**

```python
def test_cli_installs_and_diagnoses_opencode_adapter(tmp_path, capsys):
    cli = make_fake_cli(tmp_path)
    config_dir = tmp_path / "opencode"
    assert main([
        "install-opencode",
        "--config-dir", str(config_dir),
        "--cli-path", str(cli),
        "--projects-home", str(tmp_path / "projects"),
        "--json",
    ]) == 0
    installed = json.loads(capsys.readouterr().out)
    assert installed["installed"] is True

    assert main(["doctor", "--opencode-config-dir", str(config_dir), "--json"]) == 0
    diagnosis = json.loads(capsys.readouterr().out)
    assert diagnosis["opencode"]["cli_path_matches"] is True
```

- [ ] **Step 2: Run tests and verify RED**

Run: `/opt/anaconda3/bin/python3.13 -m pytest harness/tests/test_project_cli.py -q`

Expected: argparse rejects `install-opencode`.

- [ ] **Step 3: Add install/uninstall parsers and adapter diagnosis**

```text
co-math install-opencode [--config-dir PATH] [--cli-path PATH]
                         [--projects-home PATH] [--allow-root PATH] [--json]
co-math uninstall-opencode [--config-dir PATH] [--json]
co-math doctor [--project PATH] [--opencode-config-dir PATH] [--json]
```

Default `--cli-path` comes from `shutil.which("co-math")`, but the installer must fail with a direct remediation message if it cannot resolve an executable.

- [ ] **Step 4: Update the OpenCode GUI guide**

Document the one-time install command, the natural-language prompts for create/list/resume, manual GUI opening of the returned absolute directory, allowed-root configuration, and the explicit statement that Desktop smoke testing has not happened merely because CLI tests pass.

- [ ] **Step 5: Run focused and full verification**

Run: `/opt/anaconda3/bin/python3.13 -m pytest harness/tests/test_project_cli.py harness/tests/test_opencode_adapter.py harness/tests/test_agent_adapters.py -q`

Run: `/opt/anaconda3/bin/python3.13 -m pytest -q`

Expected: all tests PASS.

- [ ] **Step 6: Commit**

```bash
git add harness/co_math/cli.py harness/co_math/context.py harness/tests/test_project_cli.py README.md README.zh-CN.md
git commit -m "docs: add OpenCode GUI project workflow"
```

### Task 4: Release Verification Without Overclaiming Desktop Support

**Files:**
- Create: `docs/opencode-desktop-smoke-test.md`
- Modify: `README.md`
- Modify: `README.zh-CN.md`

**Interfaces:**
- Consumes: the built wheel, temporary adapter installation, and all automated tests.
- Produces: reproducible automated evidence and a separate manual Desktop release checklist.

- [ ] **Step 1: Test the installed wheel in an isolated virtual environment**

Run: `/opt/anaconda3/bin/python3.13 -m venv /tmp/co-math-0.3-venv`

Run: `/tmp/co-math-0.3-venv/bin/pip install /tmp/co-math-wheel/co_mathematician_workspace-0.3.0-py3-none-any.whl`

Run: `CO_MATH_CONFIG_HOME=/tmp/co-math-0.3-config /tmp/co-math-0.3-venv/bin/co-math new "Smoke Project" --path /tmp/co-math-smoke-project --language match --no-git --json`

Expected: JSON reports `onboarding`, and the new directory has a manifest, workspace, protocol Skill, canonical roles, and OpenCode agents.

- [ ] **Step 2: Test adapter installation against temporary OpenCode config**

Run: `CO_MATH_CONFIG_HOME=/tmp/co-math-0.3-config /tmp/co-math-0.3-venv/bin/co-math install-opencode --config-dir /tmp/opencode-config --cli-path /tmp/co-math-0.3-venv/bin/co-math --projects-home /tmp --json`

Run: `CO_MATH_CONFIG_HOME=/tmp/co-math-0.3-config /tmp/co-math-0.3-venv/bin/co-math doctor --project /tmp/co-math-smoke-project --opencode-config-dir /tmp/opencode-config --json`

Expected: Core project and adapter checks pass.

- [ ] **Step 3: Write the manual Desktop checklist**

The checklist records OpenCode Desktop version, OS, model/provider, tool discovery, natural-language create, external-directory prompt, project opening, project rules/Skill discovery, session deletion, and resume. Leave each result explicitly `not_run` until performed in the actual GUI.

- [ ] **Step 4: Run final automated verification**

Run: `/opt/anaconda3/bin/python3.13 -m pytest -q`

Run: `git diff --check`

Expected: all automated tests PASS and no whitespace errors. Report Desktop GUI as unverified unless the manual checklist is actually executed.

- [ ] **Step 5: Commit**

```bash
git add docs/opencode-desktop-smoke-test.md README.md README.zh-CN.md
git commit -m "test: add OpenCode Desktop release gate"
```
