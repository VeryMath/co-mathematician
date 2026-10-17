# 复用已有研究文件

[English](artifact-reuse.md) | 中文

同一份计算结果保留在原位置，需要用它的新工作分支（workstream）记录文件路径、
直接读取，避免为每个分支再复制一份大文件。

## 使用方法

创建工作分支时，用 `--input` 指定已有文件。多个文件就重复添加该参数：

```bash
co-math new-workstream \
  --workspace workspace \
  --goal-id G1 \
  --title "Analyze existing results" \
  --kind computation \
  --input workstreams/WS-G1-001-search/artifacts/results.csv \
  --input workstreams/WS-G1-001-search/report.md
```

运行前，目标 `G1` 需要得到用户批准，示例中的输入文件也需要已经存在。
`--input` 的路径相对于 `--workspace` 指定的工作区，而不是当前终端目录。
路径支持 `/` 和 Windows 的 `\` 分隔符；无效路径会在创建工作分支前被拒绝。
同一路径重复传入时只记录一次。

## 文件放在哪里

```text
workspace/workstreams/
  WS-G1-001-search/
    artifacts/results.csv
    report.md
  WS-G1-002-analyze-existing-results/
    inputs.md
    artifacts/
```

新分支的 `inputs.md` 保存指向原文件的相对链接。即使有很多分支引用，原文件仍只
保留在原位置；新产生的结果放在当前分支自己的 `artifacts/` 下。
大文件和二进制文件也可以这样引用，记录路径时不会读取或复制文件内容。

整体移动工作区时，只要内部目录结构不变，相对链接就仍然可用。
该方式不依赖硬链接或符号链接，适用于 Windows、macOS 和 Linux 的目录布局；
本次尚未在 Windows、Linux 实机验收。

## 读取和修改约定

共享输入应保持不变。这是使用约定，不会改变文件系统权限：修改原文件后，所有
引用它的分支都会读到新内容；重命名或删除原文件会使链接失效。
请保持上游路径稳定，并在报告中注明所用文件路径。

如果某个实验需要单独修改输入，就明确复制一份到该分支，并在笔记中说明原因。
路径引用不会为实验保存一份独立副本。

## 已有项目怎么办

现有输入目录、报告和研究记录保持原样。只有使用 `--input` 的新分支才采用这种
引用方式，原有命令仍可继续使用。

后续任务优先引用已有上游文件，减少新的 `artifacts/input/` 副本。
这次不会自动扫描、去重、删除或迁移旧副本。以后如需清理，应先确认哪些原文件和
历史引用需要保留，再决定处理范围。

本次改进回应了 [issue #7](https://github.com/VeryMath/co-mathematician/issues/7)
提出的重复存储问题。对方报告的空间统计来自其研究工作区，本仓库尚未复现这些
数字；issue 保持开放，继续确认复制脚本的位置和所用版本。
