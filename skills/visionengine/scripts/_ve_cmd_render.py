#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
_ve_cmd_render.py —— Remotion 云渲染命令。

三种运行环境：
- veconline：输出 out/，不下载；
- skills：输出 artifact/{id}/，必须带 roundTimestamp；
- standalone：先上传到 VECONLINE 工作区，渲染后下载产物。
"""

from __future__ import annotations

from _mcp_tools import (
    bridge_create_workspace,
    bridge_download_from_workspace,
    bridge_upload_project,
    render_cancel,
    render_detect,
    render_get_context,
    render_list,
    render_query,
    render_retry,
    render_submit,
    render_wait,
)
from _ve_context import (
    local_render_path,
    require_api_key,
    require_skill_render,
    require_workspace,
    resolve_context,
)
from _ve_util import VeError, emit, get_path, pick, sanitize_text

DONE = {"done", "failed", "canceled"}


def _ctx(args):
    return resolve_context(args)


def _task_from(parsed):
    if not isinstance(parsed, dict):
        return {}
    task = parsed.get("task")
    if isinstance(task, dict):
        return task
    data = parsed.get("data")
    if isinstance(data, dict):
        return data
    return parsed


def _task_status(task):
    return str(task.get("status") or task.get("task_status") or "").lower()


def _task_output(task):
    return task.get("outputPath") or task.get("output_path") or task.get("outName") or task.get("out_name")


def _emit_task(task, **extra):
    payload = {
        "success": _task_status(task) == "done",
        "task_id": task.get("id") or task.get("taskId") or task.get("task_id"),
        "status": _task_status(task) or task.get("status"),
        "progress": task.get("progress"),
        "output_path": _task_output(task),
        "workspace_id": task.get("workspaceId") or task.get("workspace_id"),
        "usage_type": task.get("usageType") or task.get("usage_type"),
        "artifact_identifier": task.get("artifactIdentifier") or task.get("artifact_identifier"),
        "error": sanitize_text(task.get("error")),
        "message": sanitize_text(task.get("message")),
    }
    payload.update(extra)
    emit(payload)


def _submit_options(args):
    options = {
        "inputProps": None,
        "exportType": getattr(args, "export_type", None),
        "codec": getattr(args, "codec", None),
        "audioCodec": getattr(args, "audio_codec", None),
        "imageFormat": getattr(args, "image_format", None),
        "outName": getattr(args, "out_name", None),
        "outputPath": getattr(args, "output_path", None),
        "startFrame": getattr(args, "start_frame", None),
        "endFrame": getattr(args, "end_frame", None),
        "everyNthFrame": getattr(args, "every_nth_frame", None),
        "frame": getattr(args, "frame", None),
        "workspacePath": getattr(args, "workspace_path", None),
        "entryPoint": getattr(args, "entry_point", None),
    }
    raw_props = getattr(args, "input_props", None)
    if raw_props:
        from _ve_util import json_arg

        props = json_arg(raw_props, "--input-props")
        if props is not None and not isinstance(props, dict):
            raise VeError("--input-props 必须是 JSON 对象", code="INVALID_INPUT_PROPS")
        options["inputProps"] = props
    if getattr(args, "image_sequence", False) and not options["exportType"]:
        options["exportType"] = "image-sequence"
    return {key: value for key, value in options.items() if value is not None}


def _materialize(ctx, task, api_key, out_dir=None):
    usage = task.get("usageType") or task.get("usage_type") or ctx.usage_type
    output_path = _task_output(task)
    if not output_path:
        return None
    local = local_render_path(ctx, output_path)
    if usage in ("skills", "veconline") and local and local.exists():
        return str(local)
    if ctx.workspace_id:
        parsed, _ = bridge_download_from_workspace(
            ctx,
            api_key,
            output_path,
            local_dir=out_dir or ctx.output_dir,
            workspace_id=ctx.workspace_id,
        )
        if isinstance(parsed, dict):
            return parsed.get("localPath") or parsed.get("local_path")
        return None
    raise VeError(
        f"无法定位产物：{output_path}；请检查 outputPath 或稍后重试。",
        code="OUTPUT_NOT_FOUND",
    )


def _wait(ctx, api_key, task_id, timeout_s=600, interval_s=5):
    parsed, _ = render_wait(ctx, api_key, task_id, timeout_s, interval_s)
    return _task_from(parsed)


def _do_submit(ctx, args, api_key, composition_id):
    require_skill_render(ctx)
    if getattr(args, "image_sequence", False) or getattr(args, "export_type", None) == "image-sequence":
        if ctx.usage_type == "skills":
            raise VeError(
                "VECSKILL 渲染不支持 image-sequence；请改用 video/still/audio。",
                code="IMAGE_SEQUENCE_UNSUPPORTED",
            )
    if ctx.usage_type != "skills":
        require_workspace(ctx)
    parsed, _ = render_submit(ctx, api_key, composition_id, _submit_options(args))
    data = parsed.get("data") if isinstance(parsed, dict) else None
    task_id = pick(data or {}, "taskId", "task_id")
    if not task_id:
        raise VeError("提交成功但响应缺少 taskId", code="INVALID_RESPONSE", payload=parsed)
    return {
        "task_id": task_id,
        "workspace_id": pick(data or {}, "workspaceId", "workspace_id") or ctx.workspace_id,
        "system": pick(data or {}, "system") or ctx.system,
        "usage_type": pick(data or {}, "usageType", "usage_type") or ctx.usage_type,
        "output_path": pick(data or {}, "outputPath", "output_path"),
        "artifact_identifier": pick(data or {}, "artifactIdentifier", "artifact_identifier")
        or ctx.artifact_identifier,
        "round_timestamp": ctx.round_timestamp,
    }


def _extract_workspace_id(parsed):
    if not isinstance(parsed, dict):
        return None
    return (
        get_path(parsed, "data", "workspace", "id")
        or get_path(parsed, "data", "workspaceId")
        or parsed.get("workspaceId")
        or get_path(parsed, "workspace", "id")
    )


def _maybe_prepare_standalone(ctx, args, api_key):
    if ctx.usage_type != "standalone":
        if getattr(args, "upload", False):
            raise VeError(
                "VECONLINE/VECSKILL 的项目已在云端工作区，不需要 --upload。",
                code="UNSUPPORTED_IN_CLOUD",
            )
        return
    if getattr(args, "upload", False):
        local_dir = getattr(args, "local_dir", None) or ctx.marker_dir or ctx.cwd
        if not ctx.workspace_id:
            name = getattr(args, "workspace_name", None)
            if not name:
                raise VeError(
                    "没有可用的 VECONLINE 工作区。请传 --workspace-name 创建，或先运行 "
                    "files workspaces / files upload-project。",
                    code="WORKSPACE_REQUIRED",
                )
            created, _ = bridge_create_workspace(
                ctx, api_key, name=name, local_dir=local_dir
            )
            workspace_id = _extract_workspace_id(created)
            if not workspace_id:
                emit(
                    {
                        "success": False,
                        "step": "create_workspace",
                        "error": sanitize_text(
                            (created or {}).get("error") if isinstance(created, dict) else None
                        )
                        or "创建工作区失败",
                        "data": created,
                    }
                )
                raise SystemExit(1)
            ctx.workspace_id = workspace_id
        uploaded, _ = bridge_upload_project(
            ctx,
            api_key,
            local_dir=local_dir,
            workspace_id=ctx.workspace_id,
            install=not getattr(args, "no_install", False),
        )
        if isinstance(uploaded, dict) and uploaded.get("success") is False:
            emit({"success": False, "step": "upload", "data": uploaded})
            raise SystemExit(1)
        ctx.sources["workspace_id"] = "created/uploaded"
    require_workspace(ctx)


def cmd_render(args):
    action = args.action
    ctx = _ctx(args)

    if action == "context":
        mcp = None
        mcp_error = None
        try:
            parsed, _ = render_get_context(ctx)
            mcp = parsed
        except VeError as exc:
            mcp_error = sanitize_text(exc.message)
        paths = {
            "project_dir": str(ctx.project_dir),
            "output_dir": str(ctx.output_dir),
            "artifact_dir": str(ctx.project_dir / "artifact" / ctx.artifact_identifier)
            if ctx.artifact_identifier
            else None,
            "workspace_dir": str(ctx.project_dir / "workspace" / ctx.artifact_identifier)
            if ctx.artifact_identifier
            else None,
        }
        emit(
            {
                "success": True,
                "cli": {
                    "cwd": str(ctx.cwd),
                    "usage_type": ctx.usage_type,
                    "system": ctx.system,
                    "workspace_id": ctx.workspace_id,
                    "artifact_identifier": ctx.artifact_identifier,
                    "round_timestamp": ctx.round_timestamp,
                    "sources": ctx.sources,
                },
                "mcp": mcp,
                **({"mcp_error": mcp_error} if mcp_error else {}),
                "paths": paths,
                "recommended_out_dir": "artifact/{0}/".format(ctx.artifact_identifier)
                if ctx.usage_type == "skills"
                else "out/",
            }
        )
        return

    api_key, _ = require_api_key()

    if action == "detect":
        parsed, _ = render_detect(
            ctx,
            api_key,
            workspace_path=getattr(args, "workspace_path", None),
        )
        emit(parsed if isinstance(parsed, dict) else {"success": True, "data": parsed})
        return

    if action == "submit":
        composition_id = getattr(args, "composition_id", None)
        if not composition_id:
            raise VeError("--composition-id 必填", code="COMPOSITION_REQUIRED")
        result = _do_submit(ctx, args, api_key, composition_id)
        emit({"success": True, **result})
        return

    if action in ("query", "wait"):
        task_id = getattr(args, "task_id", None)
        if not task_id:
            raise VeError("--task-id 必填", code="TASK_ID_REQUIRED")
        if action == "wait" or getattr(args, "wait", False):
            task = _wait(
                ctx,
                api_key,
                task_id,
                timeout_s=getattr(args, "wait_timeout", None) or 600,
                interval_s=getattr(args, "interval", None) or 5,
            )
        else:
            parsed, _ = render_query(ctx, api_key, task_id)
            task = _task_from(parsed)
        if _task_status(task) in DONE:
            local = _materialize(ctx, task, api_key, getattr(args, "out", None))
            _emit_task(task, local_path=local)
        else:
            _emit_task(task)
        return

    if action == "list":
        parsed, _ = render_list(
            ctx,
            api_key,
            limit=getattr(args, "limit", None) or 20,
        )
        emit(parsed if isinstance(parsed, dict) else {"success": True, "data": parsed})
        return

    if action == "cancel":
        parsed, _ = render_cancel(ctx, api_key, args.task_id)
        emit(parsed if isinstance(parsed, dict) else {"success": True, "data": parsed})
        return

    if action == "retry":
        parsed, _ = render_retry(ctx, api_key, args.task_id)
        emit(parsed if isinstance(parsed, dict) else {"success": True, "data": parsed})
        return

    if action == "download":
        task_id = getattr(args, "task_id", None)
        if not task_id:
            raise VeError("--task-id 必填", code="TASK_ID_REQUIRED")
        parsed, _ = render_query(ctx, api_key, task_id)
        task = _task_from(parsed)
        if _task_status(task) != "done":
            _emit_task(task)
            return
        local = _materialize(ctx, task, api_key, getattr(args, "out", None))
        _emit_task(task, local_path=local)
        return

    if action == "run":
        _maybe_prepare_standalone(ctx, args, api_key)
        detect_result = None
        detect_error = None
        composition_id = getattr(args, "composition_id", None)
        if not composition_id:
            try:
                detect_result, _ = render_detect(
                    ctx,
                    api_key,
                    workspace_path=getattr(args, "workspace_path", None),
                )
                data = (detect_result or {}).get("data") or {}
                candidates = data.get("candidates") or []
                if candidates:
                    composition_id = candidates[0].get("compositionId")
            except VeError as exc:
                detect_error = sanitize_text(exc.message)
        if not composition_id:
            raise VeError(
                "无法确定 compositionId；请传 --composition-id。"
                + (f"（detect 失败：{detect_error}）" if detect_error else ""),
                code="COMPOSITION_REQUIRED",
            )
        submit = _do_submit(ctx, args, api_key, composition_id)
        task = _wait(
            ctx,
            api_key,
            submit["task_id"],
            timeout_s=getattr(args, "wait_timeout", None) or 900,
            interval_s=getattr(args, "interval", None) or 5,
        )
        local = None
        if _task_status(task) in DONE:
            local = _materialize(ctx, task, api_key, getattr(args, "out", None))
        emit(
            {
                "success": _task_status(task) == "done",
                "detect": detect_result,
                **({"detect_error": detect_error} if detect_error else {}),
                "submit": submit,
                "task": task,
                "local_path": local,
            }
        )
        return

    raise VeError(f"未知的 render 命令：{action}", code="UNKNOWN_ACTION")
