#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
_ve_util.py —— VisionEngine CLI 的通用工具（仅标准库）。

职责：统一输出、错误信封、JSON 参数、下载、路径去重、错误脱敏。
本文件以下划线开头，是被 `ve.py` 导入的内部模块。
"""

from __future__ import annotations

import json
import os
import re
import sys
import time
import urllib.parse
import urllib.request
import uuid
from pathlib import Path

INTERNAL_PATH_RE = re.compile(
    r"(?:\/mnt\/nas_data)?\/vec\/(?:sys-(?:veconline|skills)\/[^/\s]+\/[^/\s]+|"
    r"renders-task\/[^\s]+|temp_tasks\/[^\s]+)"
)
SECRET_RE = re.compile(
    r"(?i)(bearer\s+)[^\s\"']+|(api[_-]?key\s*[=:]\s*)(?!<)[^\s\"'&]+"
)


class VeError(Exception):
    """携带错误码与上下文的业务/传输错误。"""

    def __init__(self, message, code=None, **extra):
        super().__init__(message)
        self.message = message
        self.code = code or "VE_ERROR"
        self.extra = extra


def setup_stdout():
    """强制 stdout/stderr 为 UTF-8，避免 Windows 控制台/重定向乱码。"""
    for stream in (sys.stdout, sys.stderr):
        try:
            stream.reconfigure(encoding="utf-8", errors="replace")
        except Exception:
            pass


def emit(payload):
    """统一的 JSON 输出：UTF-8、缩进 2、不排 ASCII。"""
    sys.stdout.write(json.dumps(payload, ensure_ascii=False, indent=2) + "\n")
    sys.stdout.flush()


def fail(message, code="VE_ERROR", **extra):
    """统一错误输出：stderr JSON，退出码 1。"""
    payload = {"success": False, "error": sanitize_text(message), "code": code}
    payload.update(extra)
    sys.stderr.write(json.dumps(payload, ensure_ascii=False, indent=2) + "\n")
    sys.stderr.flush()
    raise SystemExit(1)


def json_arg(value, label="参数"):
    """解析 JSON 字符串或 @文件。"""
    if value is None:
        return None
    text = str(value).strip()
    if not text:
        return None
    if text.startswith("@"):
        return load_json_file(text[1:], label)
    try:
        return json.loads(text)
    except json.JSONDecodeError as exc:
        raise VeError(f"{label} 不是合法 JSON：{exc}", code="INVALID_JSON") from exc


def load_json_file(path, label="参数"):
    try:
        return json.loads(Path(path).read_text(encoding="utf-8"))
    except OSError as exc:
        raise VeError(f"{label} 读取失败：{path}（{exc}）", code="INVALID_JSON") from exc
    except json.JSONDecodeError as exc:
        raise VeError(f"{label} 文件不是合法 JSON：{path}（{exc}）", code="INVALID_JSON") from exc


def unique_path(path):
    """同名时追加 -1/-2…，避免覆盖已有文件。"""
    path = Path(path)
    if not path.exists():
        return path
    stem, suffix, parent = path.stem, path.suffix, path.parent
    index = 1
    while True:
        candidate = parent / f"{stem}-{index}{suffix}"
        if not candidate.exists():
            return candidate
        index += 1


def timestamp_slug():
    return time.strftime("%Y%m%d-%H%M%S")


def download_url(url, out_dir, filename=None, timeout=600.0, headers=None):
    """下载 URL 到本地目录，返回最终路径。"""
    out = Path(out_dir)
    out.mkdir(parents=True, exist_ok=True)
    name = filename or _filename_from_url(url)
    target = unique_path(out / name)
    request = urllib.request.Request(url, headers=headers or {})
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            target.write_bytes(response.read())
    except Exception as exc:
        raise VeError(f"下载失败：{url}（{exc}）", code="DOWNLOAD_FAILED") from exc
    return target


def _filename_from_url(url):
    parsed = urllib.parse.urlparse(url)
    name = os.path.basename(urllib.parse.unquote(parsed.path))
    return name or f"download-{uuid.uuid4().hex[:8]}"


def sanitize_text(text, project_dir=None):
    """错误/日志脱敏：不暴露绝对 NAS 路径、密钥。"""
    if text is None:
        return None
    value = str(text)
    if project_dir:
        root = str(project_dir).rstrip("/\\")
        if root:
            value = value.replace(root, ".")
    value = INTERNAL_PATH_RE.sub("<workspace>", value)
    value = SECRET_RE.sub(lambda m: f"{m.group(1) or m.group(2)}***", value)
    if len(value) > 2000:
        value = value[:2000] + "…"
    return value


def pick(obj, *names, default=None):
    """从字典里按候选键名取第一个非空值。"""
    if not isinstance(obj, dict):
        return default
    for name in names:
        value = obj.get(name)
        if value not in (None, ""):
            return value
    return default


def get_path(obj, *keys, default=None):
    """按 a.b.c 取嵌套字段。"""
    current = obj
    for key in keys:
        if isinstance(current, dict) and key in current:
            current = current[key]
        else:
            return default
    return current
