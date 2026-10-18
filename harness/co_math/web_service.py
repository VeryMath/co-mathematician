"""Small application interface for the local research workbench."""
from __future__ import annotations

import json
import base64
import os
import tempfile
from datetime import datetime, timezone
from pathlib import Path, PurePosixPath
from uuid import uuid4

from .context import project_summary
from .project import config_home, create_project, projects_home, read_project
from .workspace import load_goals, save_goals
from .materials import MATERIAL_SUFFIXES, MAX_FILE_BYTES, import_material, read_material
from .skill_access import SkillAccess
from .goal_view import goals_document


MAX_TEXT = 200_000


def now():
    return datetime.now(timezone.utc).isoformat()


def text(value, label, limit=MAX_TEXT):
    if not isinstance(value, str) or not value.strip() or len(value) > limit:
        raise ValueError(f"{label}不能为空，且不能超过 {limit} 个字符")
    return value


def checked_path(root: Path, relative: str, *, create_parents=False):
    if not isinstance(relative, str) or "\\" in relative or "\0" in relative:
        raise ValueError("文件路径无效")
    parts = PurePosixPath(relative).parts
    if not parts or PurePosixPath(relative).is_absolute() or any(p in {"..", "."} or ":" in p for p in parts):
        raise ValueError("文件路径必须在项目内")
    current = root
    for index, part in enumerate(parts):
        current = current / part
        if current.is_symlink():
            raise ValueError("不读取或写入符号链接")
        if index < len(parts) - 1:
            if create_parents:
                current.mkdir(exist_ok=True)
            if not current.is_dir():
                raise ValueError("文件目录不存在")
    if not current.resolve().is_relative_to(root.resolve()):
        raise ValueError("文件路径超出项目")
    return current


def read_json(path, default):
    if path.is_symlink():
        raise ValueError("配置不能是符号链接")
    if not path.exists():
        return default
    if path.stat().st_size > 8_000_000:
        raise ValueError("记录文件过大，请在外部编辑器查看")
    return json.loads(path.read_text(encoding="utf-8"))


def write_json(path, value):
    if path.is_symlink():
        raise ValueError("配置不能是符号链接")
    fd, temporary = tempfile.mkstemp(dir=path.parent, prefix=".writing-")
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as handle:
            json.dump(value, handle, ensure_ascii=False, indent=2)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary, path)
    finally:
        Path(temporary).unlink(missing_ok=True)


class WebService:
    def __init__(self):
        self.home = projects_home(os.environ.get("CO_MATH_PROJECTS_HOME"))
        self.config = config_home()
        if self.config.is_symlink():
            raise ValueError("配置目录不能是符号链接")
        self.config.mkdir(parents=True, exist_ok=True, mode=0o700)
        self.registry_file = self.config / "web-projects.json"
        self.registry = read_json(self.registry_file, {})
        if not isinstance(self.registry, dict):
            raise ValueError("网页项目列表格式错误")
        self.skills = SkillAccess(self.config, read_json, write_json)

    def discover(self):
        errors = []
        if self.home.is_symlink():
            raise ValueError("项目目录不能是符号链接")
        if self.home.exists():
            for path in sorted(self.home.iterdir()):
                if path.is_dir() and not path.is_symlink() and (path / "co-math.toml").exists():
                    try:
                        self.register(read_project(path))
                    except (ValueError, OSError) as exc:
                        errors.append({"name": path.name, "error": str(exc)})
        projects = []
        for pid, path in self.registry.items():
            try:
                project = read_project(path)
                projects.append({"id": pid, **project_summary(project)})
            except (ValueError, OSError) as exc:
                errors.append({"name": Path(path).name, "error": str(exc)})
        return {"projects": projects, "errors": errors, "home": str(self.home)}

    def register(self, project):
        path = str(project.root)
        for pid, existing in self.registry.items():
            if existing == path:
                return pid
        pid = uuid4().hex
        self.registry[pid] = path
        write_json(self.registry_file, self.registry)
        return pid

    def browse_projects(self, location):
        shortcuts = [{"name": name, "path": str(path)} for name, path in [
            ("项目位置", self.home), ("桌面", Path.home() / "Desktop"),
            ("文稿", Path.home() / "Documents"), ("个人文件夹", Path.home()),
        ] if path.is_dir() and not path.is_symlink()]
        if location is None or location == "":
            directory = Path(shortcuts[0]["path"])
        else:
            directory = Path(text(location, "文件夹路径", 4000).strip()).expanduser()
        if not directory.is_absolute() or directory.is_symlink() or not directory.is_dir():
            raise ValueError("找不到这个文件夹，请重新选择。")
        directory = directory.resolve(strict=True)
        folders = []
        truncated = False
        try:
            with os.scandir(directory) as entries:
                for index, entry in enumerate(entries):
                    if index >= 10_000:
                        truncated = True
                        break
                    if entry.name.startswith(".") or not entry.is_dir(follow_symlinks=False):
                        continue
                    if len(folders) >= 1000:
                        truncated = True
                        break
                    folders.append({"name": entry.name, "path": entry.path})
        except PermissionError as exc:
            raise ValueError("暂时无法读取这个文件夹，请选择你有访问权限的位置。") from exc
        project_name = ""
        project_error = ""
        if (directory / "co-math.toml").exists():
            try:
                project_name = read_project(directory).name
            except (ValueError, OSError):
                project_error = "检测到了研究项目，但项目文件不完整或无法读取。"
        return {"path": str(directory), "name": directory.name or str(directory),
                "parent": str(directory.parent) if directory.parent != directory else None,
                "folders": sorted(folders, key=lambda folder: folder["name"].casefold()),
                "shortcuts": shortcuts, "projectName": project_name, "projectError": project_error,
                "truncated": truncated}

    def project(self, pid):
        if not isinstance(pid, str) or pid not in self.registry:
            raise ValueError("项目未打开，请先选择项目目录")
        return read_project(self.registry[pid])

    def conversation_path(self, project):
        ignore = checked_path(project.root, ".gitignore")
        if ignore.exists() and (not ignore.is_file() or ignore.stat().st_size > 1_000_000):
            raise ValueError("无法更新项目的 Git 忽略规则，请检查 .gitignore 文件。")
        content = ignore.read_bytes() if ignore.exists() else b""
        rules = [line.strip() for line in content.splitlines() if line.strip() and not line.lstrip().startswith(b"#")]
        if not rules or rules[-1] not in {b".co-math/", b"/.co-math/"}:
            with ignore.open("ab") as handle:
                if content and not content.endswith(b"\n"):
                    handle.write(b"\n")
                handle.write(b"\n# Local web conversation history\n/.co-math/\n")
        return checked_path(project.root, ".co-math/web/conversation.json", create_parents=True)

    def conversation(self, project):
        value = read_json(self.conversation_path(project), {"messages": []})
        if not isinstance(value, dict) or not isinstance(value.get("messages"), list):
            raise ValueError("对话文件格式错误，原文件已保留")
        for index, message in enumerate(value["messages"]):
            message.setdefault("order", index)
        return value

    def allowed_file(self, project, relative):
        parts = PurePosixPath(relative).parts
        allowed = parts and (parts[0] == project.workspace.name or relative in {"AGENTS.md", "CLAUDE.md"} or parts[:2] == (".agents", "skills"))
        if not allowed or any(p.startswith(".") for p in parts[1:]) or Path(relative).suffix.lower() not in MATERIAL_SUFFIXES:
            raise ValueError("此文件不在可阅读的研究材料范围内")
        return checked_path(project.root, relative)

    def list_files(self, project, params):
        query = params.get("query") or ""
        if not isinstance(query, str) or len(query) > 200:
            raise ValueError("搜索名称不能超过 200 个字符")
        query = query.strip().casefold()
        relative = project.workspace.name if query else (params.get("directory") or f"{project.workspace.name}/project")
        directory = checked_path(project.root, relative)
        roots = [project.workspace, project.root / ".agents" / "skills"]
        if not any(directory == root or directory.is_relative_to(root) for root in roots):
            raise ValueError("请选择项目材料或项目方法目录")
        if not directory.is_dir():
            raise ValueError("材料目录不存在")
        values = []
        for key, default in (("offset", 0), ("limit", 100)):
            value = params.get(key)
            if value is None:
                value = default
            if isinstance(value, bool) or not str(value).isdecimal():
                raise ValueError("分页参数必须是非负整数")
            values.append(int(value))
        offset, limit = values
        if not 1 <= limit <= 200:
            raise ValueError("每页可显示 1 至 200 项")

        warnings = []

        def candidates():
            if not query:
                with os.scandir(directory) as entries:
                    items = [entry for entry in entries if not entry.name.startswith(".") and not entry.is_symlink()]
                items.sort(key=lambda entry: (not entry.is_dir(follow_symlinks=False), entry.name.casefold(), entry.name))
                for entry in items:
                    path = Path(entry.path)
                    if entry.is_dir(follow_symlinks=False):
                        yield ("directory", path)
                    elif entry.is_file(follow_symlinks=False) and path.suffix.lower() in MATERIAL_SUFFIXES:
                        yield ("file", path)
                return
            for root in roots:
                try:
                    checked_path(project.root, root.relative_to(project.root).as_posix())
                except ValueError:
                    continue
                for current, folders, files in os.walk(root, followlinks=False, onerror=lambda _: warnings.append("部分目录无法读取。")):
                    folders[:] = [name for name in sorted(folders) if not name.startswith(".") and not (Path(current) / name).is_symlink()]
                    for name in sorted(files):
                        path = Path(current) / name
                        if query in name.casefold() and not name.startswith(".") and not path.is_symlink() and path.suffix.lower() in MATERIAL_SUFFIXES:
                            yield ("file", path)

        page = []
        has_more = False
        for index, item in enumerate(candidates()):
            if index < offset:
                continue
            if len(page) == limit:
                has_more = True
                break
            page.append(item)
        files, directories = [], []
        for kind, path in page:
            relative_path = path.relative_to(project.root).as_posix()
            if kind == "directory":
                directories.append({"path": relative_path, "name": path.name})
                continue
            try:
                item = {"path": relative_path, "size": path.stat().st_size}
                if path.parent == project.workspace / "project":
                    if path.name in {"GOALS.yaml", "PROJECT.md"}:
                        item["title"] = "研究目标" if path.name == "GOALS.yaml" else "项目说明"
                    elif path.name in {"PROJECT_STATUS.md", "SKILL_HANDOFFS.md", "SKILL_REGISTRY.md", "skill_registry.json"}:
                        item["internal"] = True
                if relative_path.startswith(".agents/"):
                    item["internal"] = True
                if path.suffix.lower() == ".md" and path.parent.name in {"notes", "materials"}:
                    try:
                        with path.open(encoding="utf-8") as handle:
                            heading = handle.readline(300).strip()
                        if heading.startswith("# "):
                            item["title"] = heading[2:]
                    except UnicodeError:
                        pass
                files.append(item)
            except (OSError, UnicodeError):
                warnings.append(f"无法读取 {path.name}。")
        parent = directory.parent
        parent_path = parent.relative_to(project.root).as_posix() if any(parent == root or parent.is_relative_to(root) for root in roots) else None
        return {"files": files, "directories": directories, "directory": directory.relative_to(project.root).as_posix(),
                "parent": parent_path, "nextOffset": offset + limit if has_more else None,
                "hasMore": has_more, "truncated": False, "warnings": list(dict.fromkeys(warnings))[:5]}

    def dispatch(self, method, params):
        if not isinstance(params, dict):
            raise ValueError("请求参数必须是对象")
        if method == "startup":
            result = self.discover()
            for item in result["projects"]:
                project = self.project(item["id"])
                try:
                    conversation = self.conversation(project)
                    changed = False
                    for message in conversation["messages"]:
                        if message.get("status") in {"running", "cancelling"}:
                            message.update(status="interrupted", error="服务已重启，已有文字保留；可以继续提问。")
                            changed = True
                    if changed:
                        write_json(self.conversation_path(project), conversation)
                except (ValueError, OSError) as exc:
                    result["errors"].append({"name": project.name, "error": str(exc)})
            return result
        if method == "project.list":
            return self.discover()
        if method == "project.browse":
            return self.browse_projects(params.get("path"))
        if method == "skill.connect":
            return self.skills.connect(params.get("directory"))
        if method == "project.create":
            question = params.get("question", "")
            language = params.get("language", "中文")
            if not isinstance(question, str) or len(question) > 20000 or language not in {"中文", "English"}:
                raise ValueError("问题或语言无效")
            project, _ = create_project(text(params.get("name"), "项目名称", 120), projects_home_path=self.home)
            introduction = f"# {project.name}\n\n## 研究问题\n\n{question or '待补充。'}\n\n## 文档语言\n\n{language}\n\n## 当前进展\n\n正在讨论问题，尚未形成经过审阅的结论。\n"
            (project.workspace / "project" / "PROJECT.md").write_text(introduction, encoding="utf-8")
            goals = load_goals(project.workspace)
            goals["research_question"]["text"] = question
            goals["language_policy"].update(status="chosen", project_docs_language=language, notes_language=language, final_output_language=language)
            save_goals(project.workspace, goals)
            pid = self.register(project)
            self.conversation_path(project)
            return {"id": pid, **project_summary(project)}
        if method == "project.open":
            path = text(params.get("path"), "项目目录", 4000)
            try:
                project = read_project(path)
            except (ValueError, OSError) as exc:
                raise ValueError("这个文件夹无法作为研究项目打开。请选择之前保存的项目；论文和笔记可以在项目内通过“添加材料”导入。") from exc
            return {"id": self.register(project), **project_summary(project)}

        project = self.project(params.get("projectId"))
        if method == "project.read":
            return {"id": params["projectId"], **project_summary(project)}
        if method == "skill.list":
            return self.skills.list(project)
        if method == "skill.read":
            return self.skills.load(project, params.get("source"), params.get("path"), params.get("directory"))
        if method == "file.list":
            return self.list_files(project, params)
        if method == "file.read":
            relative = text(params.get("path"), "文件路径", 4000)
            path = self.allowed_file(project, relative)
            if path == project.workspace / "project" / "GOALS.yaml":
                if params.get("selection"):
                    raise ValueError("研究目标按完整配置展示，请对研究正文选择页码或段落")
                raw = read_material(path)
                if raw.get("truncated"):
                    return {"path": relative, "format": "goals", "title": "研究目标", "rawContent": raw["content"], "content": raw["content"], "readable": False, "note": "目标文件过长，无法完整展示。下方只保留原始内容节选，请在外部编辑器查看。"}
                return {"path": relative, **goals_document(raw["content"])}
            return {"path": relative, **read_material(path, selection=params.get("selection"))}
        if method == "material.import":
            directory = checked_path(project.root, f"{project.workspace.name}/project/materials", create_parents=True)
            directory.mkdir(exist_ok=True, mode=0o700)
            path = import_material(directory, params.get("name"), params.get("data"))
            return {"path": path.relative_to(project.root).as_posix(), "name": path.name, "size": path.stat().st_size}
        if method == "file.download":
            relative = text(params.get("path"), "材料路径", 4000)
            path = self.allowed_file(project, relative)
            if not path.is_file() or path.stat().st_size > MAX_FILE_BYTES:
                raise ValueError("文件不存在或超过 10 MB")
            return {"name": path.name, "data": base64.b64encode(path.read_bytes()).decode("ascii")}
        if method == "note.create":
            title = text(params.get("title"), "笔记标题", 200).replace("\n", " ")
            content = text(params.get("content"), "笔记内容")
            relative = f"{project.workspace.name}/project/notes/{datetime.now():%Y%m%d-%H%M%S}-{uuid4().hex[:8]}.md"
            path = checked_path(project.root, relative, create_parents=True)
            fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
            with os.fdopen(fd, "w", encoding="utf-8") as handle:
                handle.write(f"# {title}\n\n{content}\n")
            return {"path": relative, "content": path.read_text(encoding="utf-8")}
        if method == "chat.read":
            return self.conversation(project)
        if method == "chat.begin":
            content = text(params.get("content"), "问题", 20000)
            conversation = self.conversation(project)
            if len(conversation["messages"]) >= 500:
                raise ValueError("当前对话已达 500 条，请先在项目目录整理对话记录")
            position = len(conversation["messages"])
            run = {"id": uuid4().hex, "order": position + 1, "role": "assistant", "content": "", "status": "running", "createdAt": now(), "model": params["model"], "profileName": params.get("profileName", ""), "provider": params.get("provider", ""), "sources": params.get("sources", []), "sourceNotes": params.get("sourceNotes", [])}
            if params.get("skill"):
                run["skill"] = params["skill"]
            conversation["messages"].extend([
                {"id": uuid4().hex, "order": position, "role": "user", "content": content, "createdAt": now()}, run,
            ])
            if len(json.dumps(conversation, ensure_ascii=False, indent=2).encode("utf-8")) > 7_000_000:
                raise ValueError("对话记录接近容量，请先在项目目录整理历史记录；本次问题尚未发送")
            write_json(self.conversation_path(project), conversation)
            return run
        if method == "chat.update":
            conversation = self.conversation(project)
            for message in conversation["messages"]:
                if message.get("id") == params.get("runId") and message.get("role") == "assistant":
                    for field in ("content", "status", "error"):
                        if field in params:
                            message[field] = params[field]
                    write_json(self.conversation_path(project), conversation)
                    return message
            raise ValueError("找不到对应回答")
        raise ValueError("不支持的操作")
