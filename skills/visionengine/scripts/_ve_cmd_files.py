#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
_ve_cmd_files.py —— Remotion 工作区文件桥命令。

VECONLINE / 本地 standalone 使用；VECSKILL 不使用文件桥。
"""

from __future__ import annotations

import sys
import urllib.parse
from pathlib import Path

from _mcp_tools import (
    bridge_create_workspace,
    bridge_delete_file,
    bridge_download_from_workspace,
    bridge_get_workspace,
    bridge_install_workspace,
    bridge_list_files,
    bridge_list_workspaces,
    bridge_quota,
    bridge_read_file,
    bridge_rename_workspace,
    bridge_save_file,
    bridge_upload_project,
)
from _ve_context import require_api_key, require_workspace, resolve_context
from _ve_util import VeError, emit, get_path, sanitize_text

CODE_EXTS = {".ts", ".tsx", ".js", ".jsx"}


def _ctx(args):
    return resolve_context(args)


def _ensure_bridge_supported(ctx):
    if ctx.usage_type == "skills":
        raise VeError(
            "VECSKILL 项目文件就在本地工作区，不使用文件桥接。"
            "请直接用本地文件系统操作；渲染产物会自动落在 artifact/{id}/。",
            code="UNSUPPORTED_IN_SKILLS",
        )


def _workspace(ctx, args):
    workspace_id = getattr(args, "workspace_id", None) or ctx.workspace_id
    if workspace_id:
        return workspace_id
    return require_workspace(ctx)


def _create_workspace_id(parsed):
    return (
        get_path(parsed, "data", "workspace", "id")
        or get_path(parsed, "data", "workspaceId")
        or get_path(parsed, "workspace", "id")
        or (parsed or {}).get("workspaceId")
    )


def _warn(message):
    sys.stderr.write(f"warning: {message}\n")
    sys.stderr.flush()


def cmd_files(args):
    action = args.action
    ctx = _ctx(args)
    _ensure_bridge_supported(ctx)

    if action == "workspaces":
        api_key, _ = require_api_key()
        parsed, _ = bridge_list_workspaces(ctx, api_key)
        emit(parsed if isinstance(parsed, dict) else {"success": True, "data": parsed})
        return

    if action == "quota":
        api_key, _ = require_api_key()
        parsed, _ = bridge_quota(ctx, api_key)
        emit(parsed if isinstance(parsed, dict) else {"success": True, "data": parsed})
        return

    api_key, _ = require_api_key()

    if action == "create":
        name = getattr(args, "name", None)
        if not name:
            raise VeError("--name 必填", code="INVALID_ARGUMENT")
        parsed, _ = bridge_create_workspace(
            ctx,
            api_key,
            name=name,
            description=getattr(args, "description", None),
            template=getattr(args, "template", None),
            local_dir=getattr(args, "local_dir", None),
        )
        workspace_id = _create_workspace_id(parsed)
        if not workspace_id:
            emit(parsed if isinstance(parsed, dict) else {"success": False, "data": parsed})
            return
        emit(
            {
                "success": True,
                "workspace_id": workspace_id,
                "workspace": get_path(parsed, "data", "workspace"),
                "quota": get_path(parsed, "data", "quota"),
            }
        )
        return

    if action == "get":
        parsed, _ = bridge_get_workspace(ctx, api_key, _workspace(ctx, args))
        emit(parsed if isinstance(parsed, dict) else {"success": True, "data": parsed})
        return

    if action == "rename":
        name = getattr(args, "name", None)
        if not name:
            raise VeError("--name 必填", code="INVALID_ARGUMENT")
        parsed, _ = bridge_rename_workspace(
            ctx, api_key, _workspace(ctx, args), name
        )
        emit(parsed if isinstance(parsed, dict) else {"success": True, "data": parsed})
        return

    if action == "install":
        parsed, _ = bridge_install_workspace(ctx, api_key, _workspace(ctx, args))
        emit(parsed if isinstance(parsed, dict) else {"success": True, "data": parsed})
        return

    if action == "upload-project":
        local_dir = getattr(args, "local_dir", None) or ctx.marker_dir or ctx.cwd
        parsed, _ = bridge_upload_project(
            ctx,
            api_key,
            local_dir=local_dir,
            workspace_id=_workspace(ctx, args),
            install=not getattr(args, "no_install", False),
        )
        emit(parsed if isinstance(parsed, dict) else {"success": True, "data": parsed})
        return

    if action == "list":
        if getattr(args, "include_hidden", False):
            _warn("MCP list_files 暂不支持 include_hidden，已忽略")
        parsed, _ = bridge_list_files(
            ctx,
            api_key,
            path=getattr(args, "path", ".") or ".",
            maxDepth=getattr(args, "max_depth", None),
            limit=getattr(args, "limit", None),
            mode=getattr(args, "mode", None),
            recursive=True if getattr(args, "recursive", False) else None,
            includeContent=True if getattr(args, "include_content", False) else None,
        )
        emit(parsed if isinstance(parsed, dict) else {"success": True, "data": parsed})
        return

    if action == "read":
        path = getattr(args, "path", None)
        if not path:
            raise VeError("--path 必填", code="INVALID_ARGUMENT")
        parsed, _ = bridge_read_file(ctx, api_key, path)
        emit(parsed if isinstance(parsed, dict) else {"success": True, "data": parsed})
        return

    if action in ("upload", "save"):
        _handle_save(args, ctx, api_key)
        return

    if action == "download":
        path = getattr(args, "path", None)
        if not path:
            raise VeError("--path 必填", code="INVALID_ARGUMENT")
        local_dir = getattr(args, "out", None) or ctx.output_dir
        parsed, _ = bridge_download_from_workspace(
            ctx,
            api_key,
            path=path,
            local_dir=local_dir,
            workspace_id=_workspace(ctx, args),
        )
        emit(parsed if isinstance(parsed, dict) else {"success": True, "data": parsed})
        return

    if action == "delete":
        path = getattr(args, "path", None)
        if not path:
            raise VeError("--path 必填", code="INVALID_ARGUMENT")
        parsed, _ = bridge_delete_file(
            ctx, api_key, path, workspace_id=_workspace(ctx, args)
        )
        emit(parsed if isinstance(parsed, dict) else {"success": True, "data": parsed})
        return

    raise VeError(f"未知的 files 命令：{action}", code="UNKNOWN_ACTION")


def _handle_save(args, ctx, api_key):
    source = getattr(args, "source", None)
    if args.action == "save":
        source_type = getattr(args, "source_type", None) or "text"
        file_name = getattr(args, "file_name", None)
        if not file_name:
            raise VeError("--file-name 必填", code="INVALID_ARGUMENT")
        content = getattr(args, "content", None)
        content_file = getattr(args, "content_file", None)
        local_path = getattr(args, "local_path", None)
        if content_file:
            content = Path(content_file).read_text(encoding="utf-8")
        if source_type in ("text", "base64", "remote_url") and content is None:
            raise VeError(f"--content 是 sourceType={source_type} 的必填项", code="INVALID_ARGUMENT")
        if source_type == "local_path" and not local_path:
            raise VeError("--local-path 是 sourceType=local_path 的必填项", code="INVALID_ARGUMENT")
        parsed, _ = bridge_save_file(
            ctx,
            api_key,
            source_type=source_type,
            file_name=file_name,
            local_path=local_path,
            content=content,
            target_path=getattr(args, "target_path", None),
            content_type=getattr(args, "content_type", None),
            overwrite=True if getattr(args, "overwrite", False) else None,
        )
        emit(parsed if isinstance(parsed, dict) else {"success": True, "data": parsed})
        return

    if source == "url":
        url = getattr(args, "url", None)
        if not url:
            raise VeError("--source url 需要 --url", code="INVALID_ARGUMENT")
        file_name = getattr(args, "file_name", None) or Path(
            urllib.parse.urlparse(url).path
        ).name
        if not file_name:
            raise VeError("无法从 URL 推断文件名，请传 --file-name", code="INVALID_ARGUMENT")
        parsed, _ = bridge_save_file(
            ctx,
            api_key,
            source_type="remote_url",
            file_name=file_name,
            content=url,
            target_path=getattr(args, "target_path", None),
        )
        emit(parsed if isinstance(parsed, dict) else {"success": True, "data": parsed})
        return

    path_value = getattr(args, "path", None)
    if not path_value:
        raise VeError("files upload 需要本地文件路径", code="INVALID_ARGUMENT")
    source_path = Path(path_value).expanduser()
    if not source_path.is_absolute():
        source_path = (Path.cwd() / source_path).resolve()
    if not source_path.is_file():
        raise VeError(f"文件不存在：{path_value}", code="FILE_NOT_FOUND")
    target_path = getattr(args, "target_path", None)
    if source_path.suffix.lower() in CODE_EXTS and not target_path:
        raise VeError(
            "代码文件（.tsx/.ts/.js/.jsx）必须显式指定 --target-path src，"
            "否则无法参与 Remotion 渲染。",
            code="INVALID_ARGUMENT",
        )
    file_name = getattr(args, "file_name", None) or source_path.name
    parsed, _ = bridge_save_file(
        ctx,
        api_key,
        source_type="local_path",
        file_name=file_name,
        local_path=source_path,
        target_path=target_path,
    )
    emit(parsed if isinstance(parsed, dict) else {"success": True, "data": parsed})
