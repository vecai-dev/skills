#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
_ve_context.py —— 运行环境 / 工作区上下文解析。

不依赖 MCP 的自动探测：CLI 先从 cwd、env、参数解析出
usageType / system / workspaceId / artifactIdentifier / roundTimestamp，
再显式传给 MCP 子进程（env + tools/call 参数）。

本文件以下划线开头，是被 `ve.py` 导入的内部模块。
"""

from __future__ import annotations

import base64
import mimetypes
import os
import re
import shutil
from dataclasses import dataclass, field
from pathlib import Path

from _ve_util import VeError, sanitize_text as _sanitize_text

DEFAULT_API_BASE = "https://api.visionengine-tech.com"
DEFAULT_RENDER_BASE = "https://veconline-ai-api.visionengine-tech.com"
DEFAULT_REMOTION_WORK_DIR = "/vec"
DEFAULT_OUTPUT_DIR = "ve-output"

PATH_RE = re.compile(
    r"/(sys-veconline|sys-skills)/([^/]+)/(conv-[0-9a-fA-F-]{36})(?:/|$)"
)
WORKSPACE_RE = re.compile(r"^conv-[0-9a-fA-F-]{36}$")
ARTIFACT_RE = re.compile(r"^[a-z0-9][a-z0-9-]{0,63}$")
ROUND_TS_RE = re.compile(r"^\d{10}$")
URL_RE = re.compile(r"^https?://", re.IGNORECASE)
DATA_URL_RE = re.compile(r"^data:[^;]+;base64,", re.IGNORECASE)

MARKER_NAME = ".ve-workspace.json"


@dataclass
class VeContext:
    cwd: Path
    project_dir: Path
    marker_dir: Path | None
    usage_type: str
    system: str
    workspace_id: str | None
    artifact_identifier: str | None
    round_timestamp: int | None
    output_dir: Path
    cache_dir: Path
    package_name: str
    file_mode: str
    remotion_work_dir: str
    api_base: str
    render_base: str
    sources: dict = field(default_factory=dict)

    @property
    def is_cloud(self):
        return self.usage_type in ("veconline", "skills") and bool(self.workspace_id)

    @property
    def is_skills(self):
        return self.usage_type == "skills"


def _as_posix(value):
    return str(value).replace("\\", "/")


def _path_match(cwd):
    normalized = _as_posix(cwd)
    return PATH_RE.search(normalized), normalized


def _read_marker(start):
    directory = Path(start)
    for _ in range(8):
        candidate = directory / MARKER_NAME
        try:
            import json

            parsed = json.loads(candidate.read_text(encoding="utf-8"))
            if isinstance(parsed, dict):
                return parsed, directory
        except Exception:
            pass
        parent = directory.parent
        if parent == directory:
            break
        directory = parent
    return None, None


def _read_skills_candidates(project_dir):
    skills_dir = Path(project_dir) / ".claude" / "skills"
    try:
        return sorted(
            entry.name
            for entry in skills_dir.iterdir()
            if entry.is_dir() and entry.name != "skill-creator"
        )
    except OSError:
        return []


def _resolve_artifact_identifier(args, usage_type, project_dir, package_name):
    explicit = getattr(args, "artifact_identifier", None) or os.environ.get(
        "VE_SKILL_IDENTIFIER"
    )
    if explicit:
        value = str(explicit).strip()
        if not ARTIFACT_RE.match(value):
            raise VeError(
                f"artifactIdentifier 非法：{value!r}（需小写字母/数字/连字符，≤64）",
                code="ARTIFACT_IDENTIFIER_REQUIRED",
            )
        return value
    if usage_type != "skills":
        return None
    candidates = _read_skills_candidates(project_dir)
    if package_name in candidates:
        return package_name
    if len(candidates) == 1:
        return candidates[0]
    if candidates:
        raise VeError(
            "无法确定当前技能标识符。请在命令中显式传 --artifact-identifier，"
            f"候选：{', '.join(candidates)}",
            code="ARTIFACT_IDENTIFIER_REQUIRED",
            candidates=candidates,
        )
    return package_name


def resolve_context(args=None):
    args = args or object()
    cwd = Path(getattr(args, "workspace_root", None) or os.getcwd()).resolve()
    match, normalized = _path_match(cwd)
    marker, marker_dir = _read_marker(cwd)

    path_system = None
    path_workspace_id = None
    project_dir = cwd
    if match:
        path_system = "skills" if match.group(1) == "sys-skills" else "veconline"
        path_workspace_id = match.group(3)
        project_dir = Path(normalized[: match.end(3)]).resolve()

    explicit_usage = getattr(args, "usage_type", None)
    env_usage = (os.environ.get("VE_USAGE_TYPE") or "").strip()
    if explicit_usage and explicit_usage != "auto":
        usage_type = explicit_usage
    elif env_usage in ("veconline", "skills", "standalone"):
        usage_type = env_usage
    elif path_system:
        usage_type = path_system
    else:
        usage_type = "standalone"
    if usage_type not in ("veconline", "skills", "standalone"):
        raise VeError(
            f"usageType 非法：{usage_type!r}（veconline/skills/standalone）",
            code="INVALID_USAGE_TYPE",
        )

    explicit_system = getattr(args, "system", None)
    system = explicit_system or ("skills" if usage_type == "skills" else "veconline")

    workspace_id = (
        getattr(args, "workspace_id", None)
        or os.environ.get("VE_WORKSPACE_ID")
        or path_workspace_id
        or (marker or {}).get("workspaceId")
    )
    workspace_id = str(workspace_id).strip() if workspace_id else None
    if workspace_id and not WORKSPACE_RE.match(workspace_id):
        raise VeError(
            f"workspaceId 非法：{workspace_id!r}（需 conv-<uuid>）",
            code="WORKSPACE_REQUIRED",
        )

    package_name = Path(__file__).absolute().parent.parent.name
    artifact_identifier = _resolve_artifact_identifier(
        args, usage_type, project_dir, package_name
    )

    raw_round = getattr(args, "round_timestamp", None) or os.environ.get(
        "VE_ROUND_TIMESTAMP"
    )
    round_timestamp = None
    if raw_round not in (None, ""):
        value = str(raw_round).strip()
        if not ROUND_TS_RE.match(value):
            raise VeError(
                f"roundTimestamp 必须是 10 位 Unix 秒，当前为 {value!r}",
                code="INVALID_ROUND_TIMESTAMP",
            )
        round_timestamp = int(value)

    default_output = (
        project_dir / "workspace" / artifact_identifier
        if usage_type == "skills" and artifact_identifier
        else project_dir / DEFAULT_OUTPUT_DIR
    )
    output_setting = getattr(args, "out", None) or os.environ.get("VEC_AI_OUTPUT_DIR")
    output_path = Path(output_setting) if output_setting else default_output
    output_dir = (output_path if output_path.is_absolute() else project_dir / output_path).resolve()

    if usage_type == "skills" and artifact_identifier:
        cache_dir = project_dir / "workspace" / artifact_identifier / ".ve-cache"
    else:
        cache_dir = output_dir / ".ve-cache"

    file_mode = (os.environ.get("VEC_AI_FILE_MODE") or "").strip().lower()
    if file_mode not in ("remote", "local"):
        file_mode = "local" if usage_type in ("veconline", "skills") else "remote"

    sources = {
        "usage_type": (
            "explicit"
            if explicit_usage and explicit_usage != "auto"
            else "env:VE_USAGE_TYPE"
            if env_usage
            else "cwd-path"
            if path_system
            else "default:standalone"
        ),
        "workspace_id": (
            "explicit"
            if getattr(args, "workspace_id", None)
            else "env:VE_WORKSPACE_ID"
            if os.environ.get("VE_WORKSPACE_ID")
            else "cwd-path"
            if path_workspace_id
            else "marker" if marker_dir else "missing"
        ),
        "artifact_identifier": (
            "explicit"
            if getattr(args, "artifact_identifier", None)
            else "env:VE_SKILL_IDENTIFIER"
            if os.environ.get("VE_SKILL_IDENTIFIER")
            else "package" if usage_type == "skills" else "not-required"
        ),
        "marker_dir": str(marker_dir) if marker_dir else None,
    }

    return VeContext(
        cwd=cwd,
        project_dir=project_dir,
        marker_dir=marker_dir,
        usage_type=usage_type,
        system=system,
        workspace_id=workspace_id,
        artifact_identifier=artifact_identifier,
        round_timestamp=round_timestamp,
        output_dir=output_dir,
        cache_dir=cache_dir,
        package_name=package_name,
        file_mode=file_mode,
        remotion_work_dir=(os.environ.get("VEC_AI_REMOTION_WORK_DIR") or DEFAULT_REMOTION_WORK_DIR),
        api_base=(os.environ.get("VEC_AI_API_URL") or DEFAULT_API_BASE).rstrip("/"),
        render_base=(os.environ.get("VEC_AI_RENDER_URL") or DEFAULT_RENDER_BASE).rstrip("/"),
        sources=sources,
    )


def resolve_api_key():
    key = (os.environ.get("VEC_AI_API_KEY") or "").strip()
    if key:
        return key, "VEC_AI_API_KEY"
    return "", ""


def require_api_key():
    key, source = resolve_api_key()
    if key:
        return key, source
    raise VeError(
        "缺少 VisionEngine API Key。VECSKILL 云端工作区请先通过平台授权卡获取"
        "（VEC_AI_API_KEY 会写入当前项目 .env，本轮的 Bash 命令前先 "
        "set -a; . ./.env; set +a）；本地 / VECONLINE 请向用户询问 Key（获取地址："
        "https://www.visionengine-tech.com/keys），然后在该命令前设置环境变量后重试："
        "VEC_AI_API_KEY=<用户的 Key> python <skill>/scripts/ve.py <原命令>。"
        "不要把 Key 写入文件、日志或回复中。",
        code="MISSING_API_KEY",
    )


def require_workspace(ctx):
    if ctx.workspace_id:
        return ctx.workspace_id
    raise VeError(
        "未找到工作区。请先运行 `files workspaces` 查看，或用 "
        "`files create --name <名称> --local-dir <项目目录>` 创建并绑定；"
        "也可以在命令中显式传 --workspace-id。",
        code="WORKSPACE_REQUIRED",
    )


def require_skill_render(ctx):
    if ctx.usage_type != "skills":
        return
    if not ctx.artifact_identifier:
        raise VeError(
            "VECSKILL 渲染需要 artifactIdentifier。请传 --artifact-identifier。",
            code="ARTIFACT_IDENTIFIER_REQUIRED",
        )
    if not ctx.round_timestamp:
        raise VeError(
            "VECSKILL 渲染需要 roundTimestamp。请从用户本轮任务消息最后一行 "
            "`Timestamp:<10 位 Unix 秒>` 取值，并传 --round-timestamp。",
            code="INVALID_ROUND_TIMESTAMP",
        )


def child_env(ctx, api_key, package_key=""):
    env = dict(os.environ)
    if api_key:
        env["API_KEY"] = api_key
    else:
        env.pop("API_KEY", None)
    env["WORKDIR"] = str(ctx.project_dir)
    env["DEFAULT_OUTPUT_DIR"] = str(ctx.output_dir)
    env["FILE_MODE"] = ctx.file_mode
    env["REMOTION_WORK_DIR"] = ctx.remotion_work_dir
    env["VE_USAGE_TYPE"] = ctx.usage_type
    if ctx.workspace_id:
        env["VE_WORKSPACE_ID"] = ctx.workspace_id
    else:
        env.pop("VE_WORKSPACE_ID", None)
    if ctx.artifact_identifier:
        env["VE_SKILL_IDENTIFIER"] = ctx.artifact_identifier
    else:
        env.pop("VE_SKILL_IDENTIFIER", None)
    env["BASE_URL"] = ctx.api_base
    env["RENDER_BACKEND_URL"] = ctx.render_base
    env["WORKSPACE_API_URL"] = ctx.render_base
    env["npm_config_update_notifier"] = "false"
    env["npm_config_fund"] = "false"
    env["npm_config_audit"] = "false"
    if ctx.usage_type == "skills":
        env["npm_config_cache"] = str(ctx.cache_dir / "npm")
    return env


def stage_local_file(value, ctx):
    """把本地文件复制到 cache_dir，避免 MCP 往只读目录旁写产物。"""
    source = Path(value)
    if not source.is_absolute():
        source = (Path.cwd() / source).resolve()
    if not source.is_file():
        raise VeError(f"文件不存在：{value}", code="FILE_NOT_FOUND")
    ctx.cache_dir.mkdir(parents=True, exist_ok=True)
    target = ctx.cache_dir / source.name
    if source.resolve() != target.resolve():
        shutil.copy2(source, target)
    return target


def prepare_media_input(value, ctx, kind):
    """把本地媒体转成 MCP 可接受的输入。

    - image：本地文件转 base64 data URL；
    - audio/video：返回绝对本地路径，由 MCP 按 FILE_MODE 上传；
    - http(s) / data URL / 存储路径：原样透传。
    """
    if value is None:
        return None
    text = str(value)
    if not text.strip():
        return text
    if URL_RE.match(text) or DATA_URL_RE.match(text):
        return text
    path = Path(text)
    if not path.is_absolute():
        path = (Path.cwd() / path).resolve()
    if not path.is_file():
        # 不是本地文件：视为用户桶内存储路径，交给后端校验属主
        return text
    if kind == "image":
        mime = mimetypes.guess_type(path.name)[0] or "image/png"
        data = base64.b64encode(path.read_bytes()).decode("ascii")
        return f"data:{mime};base64,{data}"
    return str(path)


def local_render_path(ctx, output_path):
    if not output_path:
        return None
    path = Path(output_path)
    return path if path.is_absolute() else (ctx.project_dir / path)


def sanitize_text(text):
    return _sanitize_text(text, project_dir=None)
