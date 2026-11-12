#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
_mcp_tools.py —— CLI 语义到 MCP 包/工具的映射层。

所有 camelCase 参数转换集中在这里；命令模块只描述业务意图。
本文件以下划线开头，是被 `ve.py` 导入的内部模块。
"""

from __future__ import annotations

from _mcp_client import ServerSpec, close_all, get_client
from _ve_context import child_env, require_api_key

SPECS = {
    "image-generate": ServerSpec(
        "image-generate", "@visionengine/image-generate", "ve-image-generate", "图片生成"
    ),
    "image-edit": ServerSpec(
        "image-edit", "@visionengine/image-edit", "ve-image-edit", "进阶图片编辑"
    ),
    "image-recognize": ServerSpec(
        "image-recognize", "@visionengine/image-recognize", "ve-image-recognize", "图片识别"
    ),
    "audio-tts": ServerSpec(
        "audio-tts", "@visionengine/audio-tts", "ve-audio-tts", "语音合成"
    ),
    "subtitle-generate": ServerSpec(
        "subtitle-generate", "@visionengine/subtitle-generate", "ve-subtitle-generate", "字幕"
    ),
    "video-style-transfer": ServerSpec(
        "video-style-transfer",
        "@visionengine/video-style-transfer",
        "ve-video-style-transfer",
        "视频风格重绘",
    ),
    "img2video": ServerSpec(
        "img2video", "@visionengine/img2video", "ve-img2video", "图生视频"
    ),
    "text2video": ServerSpec(
        "text2video", "@visionengine/text2video", "ve-text2video", "文生视频"
    ),
    "video-recognize": ServerSpec(
        "video-recognize", "@visionengine/video-recognize", "ve-video-recognize", "视频理解"
    ),
    "digital-human": ServerSpec(
        "digital-human", "@visionengine/digital-human", "ve-digital-human", "数字人"
    ),
    "render": ServerSpec(
        "render", "@visionengine/render", "ve-render", "Remotion 渲染"
    ),
    "remotion-file-bridge": ServerSpec(
        "remotion-file-bridge",
        "@visionengine/remotion-file-bridge",
        "ve-remotion-file-bridge",
        "Remotion 工作区文件",
    ),
}

TIMEOUTS = {
    "initialize": 120.0,
    "image": 180.0,
    "tts": 600.0,
    "subtitle": 700.0,
    "video-submit": 120.0,
    "video-query": 120.0,
    "dh-submit": 300.0,
    "dh-query": 120.0,
    "render-context": 60.0,
    "render-submit": 120.0,
    "render-query": 60.0,
    "render-wait": 1800.0,
    "bridge-read": 60.0,
    "bridge-save": 300.0,
    "bridge-upload": 1800.0,
    "bridge-install": 900.0,
    "bridge-download": 600.0,
}


def _client(key, ctx, api_key=None, require_key=True):
    spec = SPECS[key]
    if require_key:
        if not api_key:
            api_key, _ = require_api_key()
    env = child_env(ctx, api_key or "", key)
    return get_client(spec, env, ctx.project_dir)


def call(
    key,
    tool,
    arguments,
    ctx,
    api_key=None,
    *,
    require_key=True,
    timeout=600.0,
    raise_on_failure=True,
):
    client = _client(key, ctx, api_key, require_key=require_key)
    return client.call(
        tool,
        arguments or {},
        timeout=timeout,
        raise_on_failure=raise_on_failure,
    )


def call_text(key, tool, arguments, ctx, api_key=None, *, require_key=True, timeout=180.0):
    _, text = call(
        key,
        tool,
        arguments,
        ctx,
        api_key,
        require_key=require_key,
        timeout=timeout,
        raise_on_failure=True,
    )
    return text


def describe():
    return {
        key: {
            "npm": spec.npm,
            "bin": spec.bin,
            "title": spec.title,
        }
        for key, spec in SPECS.items()
    }


# ---------------------------------------------------------------- render


def _render_args(ctx):
    payload = {
        "usageType": ctx.usage_type,
        "system": ctx.system,
    }
    if ctx.workspace_id:
        payload["workspaceId"] = ctx.workspace_id
    if ctx.usage_type == "skills" and ctx.artifact_identifier:
        payload["artifactIdentifier"] = ctx.artifact_identifier
    return payload


def render_get_context(ctx, api_key=None):
    return call(
        "render",
        "get_context",
        {},
        ctx,
        api_key,
        require_key=False,
        timeout=TIMEOUTS["render-context"],
    )


def render_detect(ctx, api_key=None, workspace_path=None, extra=None):
    payload = _render_args(ctx)
    if workspace_path:
        payload["workspacePath"] = workspace_path
    payload.update(extra or {})
    return call(
        "render", "detect", payload, ctx, api_key, timeout=TIMEOUTS["render-query"]
    )


def render_submit(ctx, api_key, composition_id, options):
    payload = _render_args(ctx)
    payload["compositionId"] = composition_id
    payload.update({k: v for k, v in options.items() if v is not None})
    if ctx.usage_type == "skills":
        payload["artifactIdentifier"] = ctx.artifact_identifier
        payload["roundTimestamp"] = ctx.round_timestamp
    return call(
        "render", "submit", payload, ctx, api_key, timeout=TIMEOUTS["render-submit"]
    )


def render_query(ctx, api_key, task_id):
    return call(
        "render",
        "query",
        {"taskId": task_id},
        ctx,
        api_key,
        timeout=TIMEOUTS["render-query"],
        raise_on_failure=False,
    )


def render_wait(ctx, api_key, task_id, timeout_s=600, interval_s=5):
    return call(
        "render",
        "wait",
        {
            "taskId": task_id,
            "timeoutSeconds": max(5, int(timeout_s)),
            "intervalSeconds": max(2, int(interval_s)),
        },
        ctx,
        api_key,
        timeout=TIMEOUTS["render-wait"],
        raise_on_failure=False,
    )


def render_list(ctx, api_key, limit=20, all_workspaces=False):
    payload = {"limit": limit}
    if not all_workspaces:
        payload["system"] = ctx.system
        if ctx.workspace_id:
            payload["workspaceId"] = ctx.workspace_id
    return call("render", "list", payload, ctx, api_key, timeout=TIMEOUTS["render-query"])


def render_cancel(ctx, api_key, task_id):
    return call(
        "render", "cancel", {"taskId": task_id}, ctx, api_key, timeout=TIMEOUTS["render-query"]
    )


def render_retry(ctx, api_key, task_id):
    return call(
        "render", "retry", {"taskId": task_id}, ctx, api_key, timeout=TIMEOUTS["render-query"]
    )


# ---------------------------------------------------------------- file bridge


def bridge_list_workspaces(ctx, api_key):
    return call(
        "remotion-file-bridge",
        "list_workspaces",
        {},
        ctx,
        api_key,
        timeout=TIMEOUTS["bridge-read"],
    )


def bridge_quota(ctx, api_key):
    return call(
        "remotion-file-bridge",
        "get_workspace_quota",
        {},
        ctx,
        api_key,
        timeout=TIMEOUTS["bridge-read"],
    )


def bridge_create_workspace(ctx, api_key, name, description=None, template=None, local_dir=None):
    payload = {"name": name}
    if description:
        payload["description"] = description
    if template:
        payload["template"] = template
    if local_dir:
        payload["localDir"] = str(local_dir)
    return call(
        "remotion-file-bridge",
        "create_workspace",
        payload,
        ctx,
        api_key,
        timeout=TIMEOUTS["bridge-upload"],
        raise_on_failure=False,
    )


def bridge_get_workspace(ctx, api_key, workspace_id):
    return call(
        "remotion-file-bridge",
        "get_workspace",
        {"workspaceId": workspace_id},
        ctx,
        api_key,
        timeout=TIMEOUTS["bridge-read"],
    )


def bridge_rename_workspace(ctx, api_key, workspace_id, name):
    return call(
        "remotion-file-bridge",
        "rename_workspace",
        {"workspaceId": workspace_id, "name": name},
        ctx,
        api_key,
        timeout=TIMEOUTS["bridge-read"],
    )


def bridge_install_workspace(ctx, api_key, workspace_id):
    return call(
        "remotion-file-bridge",
        "install_workspace",
        {"workspaceId": workspace_id},
        ctx,
        api_key,
        timeout=TIMEOUTS["bridge-install"],
        raise_on_failure=False,
    )


def bridge_upload_project(ctx, api_key, local_dir, workspace_id=None, install=True):
    payload = {"localDir": str(local_dir), "install": install}
    if workspace_id:
        payload["workspaceId"] = workspace_id
    return call(
        "remotion-file-bridge",
        "upload_to_workspace",
        payload,
        ctx,
        api_key,
        timeout=TIMEOUTS["bridge-upload"],
        raise_on_failure=False,
    )


def bridge_list_files(ctx, api_key, path=".", **options):
    payload = {"path": path}
    payload.update({k: v for k, v in options.items() if v is not None})
    return call(
        "remotion-file-bridge",
        "list_files",
        payload,
        ctx,
        api_key,
        timeout=TIMEOUTS["bridge-read"],
    )


def bridge_read_file(ctx, api_key, path):
    return call(
        "remotion-file-bridge",
        "read_file",
        {"path": path, "asText": True},
        ctx,
        api_key,
        timeout=TIMEOUTS["bridge-read"],
    )


def bridge_save_file(ctx, api_key, source_type, file_name, local_path=None, content=None,
                     target_path=None, content_type=None, overwrite=None):
    payload = {
        "sourceType": source_type,
        "fileName": file_name,
    }
    if local_path:
        payload["localPath"] = str(local_path)
    if content is not None:
        payload["content"] = content
    if target_path:
        payload["targetPath"] = target_path
    if content_type:
        payload["contentType"] = content_type
    if overwrite is not None:
        payload["overwrite"] = overwrite
    return call(
        "remotion-file-bridge",
        "save_file",
        payload,
        ctx,
        api_key,
        timeout=TIMEOUTS["bridge-save"],
    )


def bridge_download_from_workspace(ctx, api_key, path, local_dir=None, workspace_id=None):
    payload = {"path": path}
    if local_dir:
        payload["localDir"] = str(local_dir)
    if workspace_id:
        payload["workspaceId"] = workspace_id
    return call(
        "remotion-file-bridge",
        "download_from_workspace",
        payload,
        ctx,
        api_key,
        timeout=TIMEOUTS["bridge-download"],
    )


def bridge_delete_file(ctx, api_key, path, workspace_id=None):
    payload = {"path": path}
    if workspace_id:
        payload["workspaceId"] = workspace_id
    return call(
        "remotion-file-bridge",
        "delete_file",
        payload,
        ctx,
        api_key,
        timeout=TIMEOUTS["bridge-read"],
    )
