"""Store research references and read their text without executing file content."""
from __future__ import annotations

import base64
import binascii
import os
import multiprocessing
import unicodedata
import zipfile
from pathlib import Path
from xml.etree import ElementTree
from .word_math import read_word_paragraph

MAX_FILE_BYTES = 10 * 1024 * 1024
MAX_PREVIEW_CHARACTERS = 200_000
TEXT_SUFFIXES = {".md", ".txt", ".tex", ".csv", ".json", ".yaml", ".yml", ".py", ".lean", ".bib"}
MATERIAL_SUFFIXES = TEXT_SUFFIXES | {".pdf", ".docx"}


def decode_text(data: bytes) -> str:
    encodings = ["utf-16"] if data.startswith((b"\xff\xfe", b"\xfe\xff")) else ["utf-8-sig", "gb18030"]
    for encoding in encodings:
        try:
            content = data.decode(encoding)
            if "\0" in content:
                raise ValueError("文件包含二进制内容，请选择文本材料")
            return content
        except UnicodeDecodeError:
            continue
    raise ValueError("无法读取文件编码，请另存为 UTF-8 文本后再添加")


def import_material(directory: Path, name: str, encoded: str) -> Path:
    if not isinstance(name, str) or not name.strip() or len(name) > 180:
        raise ValueError("文件名不能为空，且不能超过 180 个字符")
    name = unicodedata.normalize("NFC", name)
    reserved = {"CON", "PRN", "AUX", "NUL", *(f"COM{i}" for i in range(1, 10)), *(f"LPT{i}" for i in range(1, 10))}
    if name.startswith(".") or name.endswith((".", " ")) or any(c in name for c in '<>:"/\\|?*') or any(unicodedata.category(c) == "Cc" for c in name) or name.split(".")[0].upper() in reserved:
        raise ValueError("文件名包含不支持的字符，请重命名后添加")
    suffix = Path(name).suffix.lower()
    if suffix not in MATERIAL_SUFFIXES:
        raise ValueError("支持 PDF、Word（.docx）、Markdown、文本、LaTeX、CSV 和代码材料")
    if not isinstance(encoded, str) or len(encoded) > (MAX_FILE_BYTES + 2) // 3 * 4:
        raise ValueError("单个材料不能超过 10 MB")
    try:
        data = base64.b64decode(encoded, validate=True)
    except (ValueError, binascii.Error) as exc:
        raise ValueError("上传内容不完整，请重新选择文件") from exc
    if not data or len(data) > MAX_FILE_BYTES:
        raise ValueError("请选择非空文件，单个文件不超过 10 MB")
    if suffix in TEXT_SUFFIXES:
        decode_text(data)
    elif suffix == ".pdf" and b"%PDF-" not in data[:1024]:
        raise ValueError("这个文件不是可识别的 PDF，请检查原文件")
    elif suffix == ".docx" and not data.startswith(b"PK"):
        raise ValueError("这个文件不是可识别的 Word 文档，请使用 .docx 文件")
    stem = Path(name).stem
    for number in range(1, 1001):
        destination = directory / (name if number == 1 else f"{stem} ({number}){Path(name).suffix}")
        try:
            descriptor = os.open(destination, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
            with os.fdopen(descriptor, "wb") as handle:
                try:
                    handle.write(data)
                    handle.flush()
                    os.fsync(handle.fileno())
                except BaseException:
                    destination.unlink(missing_ok=True)
                    raise
            return destination
        except FileExistsError:
            continue
    raise ValueError("同名材料太多，请修改文件名后添加")


def _extract_material(path: Path) -> dict:
    if not path.is_file() or path.stat().st_size > MAX_FILE_BYTES:
        raise ValueError("材料不存在或超过 10 MB，请下载原文件阅读")
    suffix = path.suffix.lower()
    if suffix in TEXT_SUFFIXES:
        content = decode_text(path.read_bytes())
        truncated = len(content) > MAX_PREVIEW_CHARACTERS
        return {"content": content[:MAX_PREVIEW_CHARACTERS], "format": "markdown" if suffix == ".md" else "text", "readable": bool(content.strip()), "truncated": truncated, "note": "文件较长，显示开头部分。" if truncated else ""}
    if suffix == ".pdf":
        try:
            from pypdf import PdfReader
            reader = PdfReader(path)
            if reader.is_encrypted and not reader.decrypt(""):
                return {"content": "", "format": "text", "readable": False, "note": "PDF 需要密码。原文件已保留，请解密后重新添加。"}
            count = len(reader.pages)
            chunks = []
            remaining = MAX_PREVIEW_CHARACTERS
            readable = False
            pages_read = 0
            truncated = False
            for number, page in enumerate(reader.pages):
                if number >= 40 or remaining <= 0:
                    truncated = True
                    break
                page_text = page.extract_text() or ""
                readable = readable or bool(page_text.strip())
                block = f"[PDF 第 {number + 1} 页]\n{page_text}\n\n"
                if len(block) > remaining:
                    truncated = True
                chunks.append(block[:remaining])
                remaining -= len(block)
                pages_read += 1
            note = "PDF 文字提取结果；若有乱码、公式或表格缺失，请查看原文。"
            if truncated:
                note += f" 原文共 {count} 页，目前显示开头 {pages_read} 页的文字节选。"
            if not readable:
                note = "没有提取到文字，可能是扫描版 PDF。原文件已保留；加入对话前请先转成可复制的文字。"
            return {"content": "".join(chunks) if readable else "", "format": "text", "readable": readable, "truncated": truncated, "pageCount": count, "note": note}
        except ImportError:
            return {"content": "", "format": "text", "readable": False, "note": "PDF 原文件已保存；当前 Python 缺少 pypdf，请安装项目依赖后重新打开。"}
        except Exception:
            return {"content": "", "format": "text", "readable": False, "note": "PDF 原文件已保存，但无法自动提取文字，请下载原文件查看。"}
    if suffix == ".docx":
        try:
            with zipfile.ZipFile(path) as document:
                entry = document.getinfo("word/document.xml")
                if entry.file_size > 4_000_000:
                    raise ValueError("正文过大")
                root = ElementTree.fromstring(document.read(entry))
            ns = "{http://schemas.openxmlformats.org/wordprocessingml/2006/main}"
            paragraphs = []
            warnings = set()
            # Remove deleted revisions before paragraph lookup or equation fallback.
            for parent in root.iter():
                for child in list(parent):
                    if child.tag in {ns + "del", ns + "moveFrom"}:
                        parent.remove(child)
                        warnings.add("修订中的删除内容已略过，新增内容已保留，请对照原文件。")
                    elif child.tag in {ns + "ins", ns + "moveTo"}:
                        warnings.add("修订中的删除内容已略过，新增内容已保留，请对照原文件。")
            for paragraph in root.iter(ns + "p"):
                text = read_word_paragraph(paragraph, warnings)
                if text:
                    paragraphs.append(text)
            content = "\n\n".join(paragraphs)
            truncated = len(content) > MAX_PREVIEW_CHARACTERS
            return {"content": content[:MAX_PREVIEW_CHARACTERS], "format": "text", "readable": bool(content.strip()), "truncated": truncated,
                    "note": "Word 正文与常见公式预览；完整排版请查看原文件。" + " ".join(sorted(warnings)) + (" 文档较长，仅显示开头部分。" if truncated else "") if content.strip() else "Word 原文件已保存，但未提取到正文文字。"}
        except (OSError, ValueError, KeyError, RuntimeError, NotImplementedError, zipfile.BadZipFile, ElementTree.ParseError):
            return {"content": "", "format": "text", "readable": False, "note": "Word 原文件已保存，但无法自动提取文字，请下载原文件查看。"}
    raise ValueError("不支持读取这种材料")


def _extract_worker(path: str, connection):
    try:
        connection.send(_extract_material(Path(path)))
    except Exception:
        connection.send({"content": "", "format": "text", "readable": False, "note": "原文件已保留，但暂时无法提取正文，请查看原文件。"})
    finally:
        connection.close()


def read_material(path: Path) -> dict:
    if path.suffix.lower() not in {".pdf", ".docx"}:
        return _extract_material(path)
    # Parsing is confined to a short-lived worker so one document cannot stop Core.
    context = multiprocessing.get_context("spawn")
    receiver, sender = context.Pipe(duplex=False)
    worker = context.Process(target=_extract_worker, args=(str(path), sender), daemon=True)
    worker.start()
    sender.close()
    try:
        if receiver.poll(8):
            return receiver.recv()
        return {"content": "", "format": "text", "readable": False, "note": "正文提取用时过长，已停止提取。原文件已保留，可直接查看或下载。"}
    except (EOFError, OSError):
        return {"content": "", "format": "text", "readable": False, "note": "正文提取未完成，原文件已保留。"}
    finally:
        receiver.close()
        if worker.is_alive():
            worker.terminate()
        worker.join(timeout=1)
        if worker.is_alive():
            worker.kill()
            worker.join(timeout=1)
