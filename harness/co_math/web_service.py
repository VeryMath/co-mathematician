"""Read-only project access and the local opened-project list."""
from __future__ import annotations

import json
import base64
import os
import tempfile
from pathlib import Path, PurePosixPath
from uuid import uuid4

from .context import project_summary
from .project import config_home, projects_home, read_project
from .materials import MATERIAL_SUFFIXES, MAX_FILE_BYTES, read_material
from .goal_view import goals_document


MAX_TEXT = 200_000


def text(value, label, limit=MAX_TEXT):
    if not isinstance(value, str) or not value.strip() or len(value) > limit:
        raise ValueError(f"{label}不能为空，且不能超过 {limit} 个字符")
    return value


def checked_path(root: Path, relative: str):
    if not isinstance(relative, str) or "\\" in relative or "\0" in relative:
        raise ValueError("文件路径无效")
    parts = PurePosixPath(relative).parts
    if not parts or PurePosixPath(relative).is_absolute() or any(p in {"..", "."} or ":" in p for p in parts):
        raise ValueError("文件路径必须在项目内")
    current = root
    for part in parts:
        current = current / part
        if current.is_symlink():
            raise ValueError("不读取符号链接")
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
        self.registry_file = self.config / "web-projects.json"
        self.registry = read_json(self.registry_file, {})
        if not isinstance(self.registry, dict):
            raise ValueError("网页项目列表格式错误")

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

    def register(self, project, *, remember=False):
        path = str(project.root)
        pid = next((pid for pid, existing in self.registry.items() if existing == path), None) or uuid4().hex
        if remember:
            saved = read_json(self.registry_file, {})
            if not isinstance(saved, dict):
                raise ValueError("网页项目列表格式错误")
            saved[pid] = path
            self.config.mkdir(parents=True, exist_ok=True, mode=0o700)
            write_json(self.registry_file, saved)
        self.registry[pid] = path
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
        return checked_path(project.root, ".co-math/web/conversation.json")

    def conversation(self, project):
        value = read_json(self.conversation_path(project), {"messages": []})
        if not isinstance(value, dict) or not isinstance(value.get("messages"), list):
            raise ValueError("对话文件格式错误，原文件已保留")
        for index, message in enumerate(value["messages"]):
            if (
                not isinstance(message, dict)
                or any(not isinstance(message.get(key), str) for key in ("id", "role", "content", "createdAt"))
                or message["role"] not in {"user", "assistant"}
                or not isinstance(message.get("sources", []), list)
                or any(not isinstance(source, str) for source in message.get("sources", []))
            ):
                raise ValueError("对话消息格式错误，原文件已保留")
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
        if method in {"startup", "project.list"}:
            return self.discover()
        if method == "project.browse":
            return self.browse_projects(params.get("path"))
        if method == "project.open":
            path = text(params.get("path"), "项目目录", 4000)
            try:
                project = read_project(path)
            except (ValueError, OSError) as exc:
                raise ValueError("这个文件夹无法作为研究项目打开。请选择已有 co-math.toml 和 workspace 的项目目录。") from exc
            return {"id": self.register(project, remember=True), **project_summary(project)}

        if method not in {"project.read", "file.list", "file.read", "file.download", "chat.read"}:
            raise ValueError("不支持的操作")

        project = self.project(params.get("projectId"))
        if method == "project.read":
            return {"id": params["projectId"], **project_summary(project)}
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
        if method == "file.download":
            relative = text(params.get("path"), "材料路径", 4000)
            path = self.allowed_file(project, relative)
            if not path.is_file() or path.stat().st_size > MAX_FILE_BYTES:
                raise ValueError("文件不存在或超过 10 MB")
            return {"name": path.name, "data": base64.b64encode(path.read_bytes()).decode("ascii")}
        if method == "chat.read":
            return self.conversation(project)
