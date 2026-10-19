# 在 Coding Agent 中使用 Skill

Skill 可以理解为给 coding agent 的使用说明。Co-Math 自带一份，用来帮助 agent 创建、继续和整理研究项目；其他数学领域的 Skill 可以按需添加。

首次使用不必先学这些配置。推荐按 [README 的安装提示](../README.zh-CN.md#quick-start)，让 coding agent 完成安装和项目创建。

## 开始或继续项目

安装后，在 coding agent 中说：

```text
请用 Co-Math 为“我的研究题目”新建一个独立项目，文档使用中文。
告诉我项目文件夹的位置，先不要开始研究。
```

用 coding agent 打开返回的**研究项目文件夹**，然后说“继续这个 Co-Math 项目”。项目中已包含 `AGENTS.md` 和 `.agents/skills/co-mathematician/SKILL.md`，通常不需要再单独安装 Co-Math Skill。

支持 Agent Skills 的工具可直接发现项目说明；其他能够读取文件和执行命令的 agent，也可以按 `AGENTS.md` 使用。网页只展示保存的文件，无需选择模型或填写 API Key。

<details>
<summary>对应的命令</summary>

下面这些步骤可以交给 agent 执行。创建项目：

```bash
co-math new "Muon Convergence"
```

在返回的项目目录中继续：

```bash
co-math resume --project .
```

</details>

## 添加领域方法

在研究项目根目录把需要的完整 Skill 包放进 `.agents/skills/`，包括其引用的参考资料和工具说明。支持以下目录形式：

```text
.agents/skills/<skill>/SKILL.md
.agents/skills/<category>/<skill>/SKILL.md
```

例如，复制本机 VeryMath Skill 库并刷新项目中的方法列表：

```bash
mkdir -p .agents/skills
rsync -a /path/to/AI4Math-Skill-Library/skills/ .agents/skills/
co-math refresh-skills --workspace workspace
co-math suggest-skills --workspace workspace --query "Stiefel manifold optimization"
```

将示例路径换成实际的本机库目录，也可以只复制本次需要的完整 Skill 包。`refresh-skills` 更新 `workspace/project/skill_registry.json` 和 `workspace/project/SKILL_REGISTRY.md`；`suggest-skills` 默认先刷新，再推荐相关方法。请让 agent 阅读选中的 `SKILL.md`，并按实际工具环境处理依赖和执行步骤。

## 让领域 Skill 指导任务

用户明确选择某个领域 Skill 后，按它自己的提问、建模和研究步骤继续。下面用 `optimization-skill` 作为示例名称，应替换为实际选择的方法：

```bash
co-math skill-handoff \
  --workspace workspace \
  --skill optimization-skill \
  --mode skill_guided \
  --reason "The task is an optimization modeling problem." \
  --query "Stiefel manifold optimization" \
  --skill-path ".agents/skills/optimization-skill/SKILL.md"
```

这条命令记录采用的方法。具体研究由 coding agent 按 Skill 执行；命令本身不安装依赖，也不运行数学工具。简短任务可按 Skill 完成；需要长期研究、独立审查或最终研究稿时，继续使用 Co-Math 现有的目标、研究分支和审查流程。详细角色与命令见 [README](../README.zh-CN.md#研究架构)。

## 在网页中阅读结果

把进展写入 `workspace/project/PROJECT_STATUS.md`，笔记保存到 `workspace/project/notes/`，材料放到 `workspace/project/materials/`。研究分支文件继续放在 `workspace/workstreams/`，最终研究稿为 `workspace/final/working_paper.md`。网页可浏览项目级 Skill 说明以及这些研究文件，并在文件保存后刷新；也可手动刷新。

coding agent 的私有会话不会自动进入网页。需要保留的讨论应由 agent 保存为项目笔记或进展说明。旧版网页保存的 `.co-math/web/conversation.json` 仍可只读查看，但不能在网页发起新对话或执行 Skill。

2026-10-19 起，网页中的 Skill 选择、模型上下文预算和模型请求接口不再是使用入口。此前的网页 Skill 演示属于历史功能，不代表当前页面能够执行 Lean、求解器或独立审稿。现在这些工作由 coding agent 使用其实际可用的工具完成，结果与未解决问题保存到项目文件。
