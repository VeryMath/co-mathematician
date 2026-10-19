# 本地项目可视化

Co-Math 网页是项目的阅读界面。你在 coding agent 中研究和保存文件，再来这里看论文、公式、笔记和进展。只在 coding agent 中工作也可以，不必一直打开网页。

网页不需要 API Key，不提供模型配置，也不加载 Pi 运行时。

## 让 coding agent 帮你启动

还没安装 Co-Math？先按 [README 的推荐安装方式](../README.zh-CN.md#quick-start)，把安装提示发给 coding agent。

已有项目时，在 coding agent 中打开项目文件夹，然后说：

```text
请帮我启动 Co-Math 阅读网页，告诉我访问地址和应打开的项目文件夹。
请使用项目说明中记录的工具位置和 Python 环境。
```

打开 agent 给出的链接即可。默认地址是 [http://127.0.0.1:4175](http://127.0.0.1:4175)，以实际启动时返回的地址为准。

<details>
<summary>备选：手动启动网页</summary>

在 Co-Math 工具的源码目录中操作，使用安装它的 Python 环境。需要 Python 3.10+ 和 Node.js 22.19+：

```bash
python -m pip install -e .
npm install --package-lock=false
npm run build
CO_MATH_PYTHON=python npm start
```

这里的 `python` 应是已安装 Co-Math 依赖的 Python 命令或完整路径。Windows PowerShell 先运行 `$env:CO_MATH_PYTHON="python"`，再运行 `npm start`。从下载到安装的完整步骤见 [README](../README.zh-CN.md#quick-start)。

保持启动进程运行。开发页面时使用 `npm run dev`；修改服务端代码后需要重启服务。源码更新后重新安装依赖并运行 `npm run build`。

</details>

## 打开已有项目

1. 在 coding agent 中创建或继续项目。新项目可以直接说：“请用 Co-Math 新建一个名为‘我的研究’的独立项目，告诉我文件夹位置。”
2. 在网页点击“打开项目”，选中 agent 给出的研究项目文件夹。选择整个项目目录，其中应有 `co-math.toml`；不要选工具安装目录或里面的 `workspace/` 子目录。
3. 从左侧打开研究目标、笔记、材料或报告。只有普通论文文件夹时，先让 agent 新建项目并把论文放进去。

<details>
<summary>用终端查找已有项目</summary>

在安装 Co-Math 的环境中运行：

```bash
co-math list
co-math resume --project /path/to/project
```

</details>

网页没有新建项目、上传、新建笔记或聊天输入。材料和笔记可由 coding agent 或本地编辑器保存到项目，再回到网页阅读。

## 继续已有研究

通过“项目说明”“研究目标”“进展记录”阅读现有项目文件。“项目位置”提供目录路径，便于在 coding agent 中打开同一项目。显示一条笔记或历史提问不表示目标已完成，也不表示数学结论已证明。

可在现有 `workspace/project/PROJECT_STATUS.md` 中填写 `## 最近进展`、
`## 未解决问题`、`## 下一步`；英文标题 `Recent Progress`、`Open Questions`、
`Next Action` 也支持。CLI 的 `co-math resume` 读取同一份项目状态。

下次回来，在 coding agent 中打开原来的项目文件夹，可以直接说：

```text
继续这个 Co-Math 项目，先看看上次的笔记和进展，再和我确认下一步。
把新的推导、结果和进展保存到项目文件，方便我在网页阅读。
```

## 阅读文件

左侧按目录浏览研究文件和项目级 Skills；文件名搜索覆盖可阅读的项目文件，结果可分批加载。搜索按文件名匹配，尚未加入正文全文检索。

“研究目标”将 `GOALS.yaml` 展示为可读的问题、语言和目标列表，也能查看原文。笔记、材料、研究分支报告和最终研究稿都来自项目文件。

PDF 可显示原始页面、翻页和跳转页码，也能查看提取文字。文件可通过下载入口保存原件。扫描页、部分字体编码、公式或表格的提取文字可能不完整，应对照 PDF 原页；当前没有 OCR 或图片公式识别。

网页读取和下载的单个文件目前最多 10 MB，文本预览最多 200,000 字符。PDF 文字默认提取前 40 页，也可选择其他页码范围，每次最多 40 页；正文材料可按段落选择阅读范围。40 页的限制只适用于文字提取，原页阅读器可翻阅文件的全部页面。

Markdown、TXT、Word 提取正文、LaTeX、研究目标及历史对话支持 `$…$`、`$$…$$`、`\(...\)` 和 `\[…\]`。文档可切换阅读和源文。LaTeX 支持常见数学环境及前导区中的简单命令定义，但这里只预览公式；完整论文排版请在 coding agent 中编译，再打开生成的 PDF。Word 支持常见原生公式，不支持的结构会提示对照原文件。Python、Lean 和配置文件保持源码显示。

页面与各栏底色为纯白，文字使用黑色或中性灰，仅品牌标志保留原色。分栏可拖动调整宽度，项目导航保持简短，让正文保留主要阅读空间。

## 文件更新与历史对话

coding agent 或编辑器保存项目文件后，网页会刷新项目状态、文件列表和正在阅读的内容。如果页面尚未更新，使用手动刷新入口；必要时重新打开项目。只有已保存到本机可访问项目目录的内容才能显示，远程或另一台机器上的文件需要先由你使用的工具保存到这里。

历史网页对话来自项目已有的 `.co-math/web/conversation.json`，可只读查看。没有历史文件的新项目不需要创建它，也不需要模型设置。打开旧记录不会重新发起模型请求。

**外部 coding agent 的私有聊天不会自动同步到网页。** Co-Math 不读取这些工具的私有会话存储。希望在网页查看的讨论、结论和待办，应让 agent 保存为 `workspace/project/notes/` 中的笔记，或更新 `PROJECT_STATUS.md`。文件刷新只更新这些保存的内容。

## 数据位置

| 内容 | 默认位置 |
| --- | --- |
| 项目名称与工作区位置 | 项目根目录的 `co-math.toml` |
| 项目说明、目标、进展 | `workspace/project/PROJECT.md`、`GOALS.yaml`、`PROJECT_STATUS.md` |
| 研究材料与笔记 | `workspace/project/materials/`、`workspace/project/notes/`，按需创建 |
| 研究分支、报告和审查 | `workspace/workstreams/` |
| 最终研究稿 | `workspace/final/working_paper.md` |
| 历史网页对话 | `.co-math/web/conversation.json`，如已有 |
| 已打开项目列表 | `~/.config/co-math/web-projects.json` |

可阅读格式包括 PDF、Word（`.docx`）、Markdown、TXT、LaTeX、CSV、JSON/YAML、Python、Lean 和 BibTeX。网页读取项目内文件并提供原文件下载，不向模型服务发送内容。

`co-math setup --projects-home /path/to/projects` 设置新项目的父目录，未设置时为 `~/CoMathProjects`，已有项目不会自动移动。`CO_MATH_CONFIG_HOME` 可指定配置目录；`CO_MATH_PROJECTS_HOME` 可为这次网页运行指定项目目录。CLI 的 `new` 和 `list` 可用 `--projects-home` 指向同一位置。

## 当前范围

2026-10-19 起，网页的用途是项目可视化：打开已有项目、浏览与搜索、阅读文档、下载原文件、查看简要详情和历史对话。模型配置、新网页聊天、新建笔记、上传和新建网页项目属于过去的功能，见 [README 历史更新](../README.zh-CN.md#版本更新)。

研究执行、领域 Skill、计算、证明和独立审查由 coding agent 负责，参见 [Skill 使用说明](skills-integration.md)。网页上的进展和结论来自保存的研究记录；文件能够显示，不等于其中的数学结论已被验证。
