# Co-Mathematician

> [English](README.md) | 中文

一个轻量级、由 coding agent 驱动的 Co-Mathematician 数学研究工作区模式。它的目标是：
Codex、Claude Code、Cursor 或其他能读写仓库的 coding agent clone 之后，
都能知道如何启动和使用。

本项目受 Google DeepMind
[AI Co-Mathematician 论文](https://arxiv.org/abs/2605.06651)中公开设计原则启发，
但**不是**对其系统的复现。本项目将这些思想改写为一个 coding-agent-native、基于文件系统的
轻量工作流。

本仓库**不是**新的多 agent 平台。coding agent 本身就是 driver；仓库文件系统
就是 shared artifact store；原生 subagents、task agents 或独立 reviewer pass
扮演 workstream coordinator、specialist 和 reviewer；harness 只负责 schema、
状态、gating、报告骨架和验证脚本。

## 包含什么

- `AGENTS.md`：Codex 和其他 coding agent 的硬规则。
- `CLAUDE.md`：Claude Code 入口说明。
- `.cursor/rules/`：Cursor Agent 规则。
- `.agents/skills/co-mathematician/`：Skill 和可复用模板。
- `.codex/`：窄角色 custom agents，包括 proof、computation、review、citation checking 和 synthesis。
- `harness/co_math/`：用于 workspace 状态和 gates 的小型 Python harness。
- `workspace/`：新项目的空 scaffold。

## 不包含什么

- 不包含已解决的研究项目。
- 不包含下载的论文库。
- 不包含外部仓库快照。
- 不包含 Web app 或 agent runtime。
- 不包含 proprietary prompts 或私有系统内容。

## 安装

支持 Python 3.9+。

```bash
python3 -m pip install -e .
co-math --help
```

不安装也可以运行：

```bash
PYTHONPATH=. python3 -m harness.co_math.cli --help
```

## 在 Coding Agent 里使用

clone 仓库后，在你的 coding agent 里打开项目，并让 agent 先读取对应入口文件：

| Agent | 入口文件 |
| --- | --- |
| Codex | `AGENTS.md`、`.agents/skills/co-mathematician/SKILL.md`、`.codex/config.toml` |
| Claude Code | `CLAUDE.md`、`AGENTS.md`、`.agents/skills/co-mathematician/SKILL.md` |
| Cursor | `.cursor/rules/co-mathematician.mdc`、`AGENTS.md`、`.agents/skills/co-mathematician/SKILL.md` |

推荐第一条 prompt：

```text
Use this repository as a coding-agent-driven AI Co-Mathematician workspace.
Read the repository instructions first. You are the Project Coordinator.

Initialize the workspace, then start onboarding. First ask me to choose the
workspace document language policy. Do not solve the math problem, do not create
a workstream, and do not mark anything complete until the required goal approval
and reviewer gates pass.
```

随后 agent 应运行：

```bash
python3 -m pip install -e ".[dev]"
co-math init --workspace workspace
```

## 使用 Skill

让 coding agent 使用 `co-mathematician` Skill，或直接遵循本仓库里的
`.agents/skills/co-mathematician/SKILL.md`。流程是：

```text
onboarding -> research question formalization -> goal approval -> workstreams -> reviewer loop -> final working paper
```

核心规则很简单：用户明确 approve goal 之前，不得启动 workstream；workstream report
未通过独立 reviewer 审查之前，不得标记 complete。如果当前 agent 环境没有原生
subagent 功能，就用一个 fresh prompt 做独立 reviewer pass，并把 review 保存到
workstream 的 `reviews/` 目录。

## 开始一个新项目

初始化 workspace：

```bash
co-math init --workspace workspace
```

onboarding 阶段，Project Coordinator 应更新：

```text
workspace/project/PROJECT.md
workspace/project/GOALS.yaml
workspace/project/PROJECT_STATUS.md
workspace/project/messages.jsonl
```

onboarding 的第一个偏好问题应该是文档语言策略。推荐选项：

1. 所有 workspace documents 都用英文。
2. research notes 用用户语言，schemas、gates、reviews 用英文。
3. 所有人类可读 research documents 都用用户语言。
4. 跟随每个 project 或 conversation 的语言。

把用户选择写入 `PROJECT.md`、`PROJECT_STATUS.md` 和 `GOALS.yaml` 的
`language_policy` 区块。schema keys、gate names、statuses 和 harness commands
保持英文。

draft goal 不可执行。只有当 goal 状态恰好是下面这样，才能启动 workstream：

```yaml
status: approved
```

检查 goal approval：

```bash
co-math check-gate --workspace workspace --gate goal_approval --goal-id G1
```

为 approved goal 创建 workstream：

```bash
co-math new-workstream \
  --workspace workspace \
  --goal-id G1 \
  --title "Literature baseline review" \
  --kind literature
```

允许的 workstream kind 是 `proof`、`computation`、`literature` 和 `review`。

## Agent 角色

Project Coordinator 可以把窄任务委派给 subagents、task agents 或独立 reviewer pass：

- `proof_explorer`：证明路线、归约、例子和 proof gaps。
- `computational_experimenter`：有边界的计算实验和可复现性检查。
- `logic_reviewer`：逻辑正确性和依赖结构审查。
- `adversarial_reviewer`：反例、隐藏假设和过度 claim 检查。
- `citation_checker`：provenance 与 source-to-claim 对齐检查。
- `synthesis_agent`：只从 reviewer-approved workstream reports 综合 working paper。

这些角色都必须保持窄边界。它们不能 approve goals，不能启动未批准的 workstreams，
也不能把自己的 report 标记为 complete。

## Harness 命令

```bash
co-math init --workspace workspace
co-math append-message --workspace workspace --sender project_coordinator --recipient user --type status --content "..."
co-math new-workstream --workspace workspace --goal-id G1 --title "..." --kind proof
co-math check-gate --workspace workspace --gate goal_approval --goal-id G1
co-math check-gate --workspace workspace --gate workstream_completion --workstream-id WS-G1-001-example
co-math render-final --workspace workspace
```

## 测试

```bash
python3 -m pip install -e ".[dev]"
python3 -m pytest harness/tests -q
```

## 许可证

MIT。见 `LICENSE`。
