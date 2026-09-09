#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
_ve_commands.py —— 各命令组的具体实现（被 `ve.py` 导入）。

约定：
- 每个 cmd_* 接收 argparse 命名空间，成功时用 emit() 输出 JSON，失败时抛 VeError。
- 服务端返回的字段别名较多，统一用 pick()/get_path() 取候选键。
- 本文件以下划线开头，不是入口。
"""

from __future__ import annotations

import base64
import json
import re
import sys
import time
import urllib.parse
from pathlib import Path

from _ve_client import (
    LONG_TIMEOUT,
    VeError,
    as_image_input,
    as_media_input,
    as_media_url,
    download_url,
    emit,
    get_path,
    load_config,
    poll,
    request_bytes,
    request_json,
    request_raw,
    upload_file,
)

ASSETS_DIR = Path(__file__).resolve().parent.parent / "assets"
DATA_URL_RE = re.compile(r"^data:(image/\w+);base64,(.+)$", re.S)

TERMINAL_FAILED = {"FAILED", "CANCELED", "CANCELLED", "UNKNOWN"}
RENDER_DONE = {"done"}
RENDER_FAILED = {"failed", "canceled"}

SUBTITLE_MEDIA_TYPES = {
    ".wav": "audio/wav", ".mp3": "audio/mpeg", ".mp4": "audio/mp4", ".m4a": "audio/mp4",
    ".aac": "audio/aac", ".ogg": "audio/ogg", ".flac": "audio/flac", ".webm": "audio/webm",
}


# ---------------------------------------------------------------- 小工具


def _cfg(args, require_network=True):
    return load_config(args, require_network=require_network)


def _wait_enabled(args, default=False):
    if getattr(args, "wait", False):
        return True
    if getattr(args, "no_wait", False):
        return False
    return default


def _json_arg(value, label="参数"):
    """接受 JSON 字符串或 @文件路径。"""
    if value is None:
        return None
    text = value
    if value.startswith("@"):
        text = Path(value[1:]).read_text(encoding="utf-8")
    try:
        return json.loads(text)
    except json.JSONDecodeError as exc:
        raise VeError(f"{label} 不是合法 JSON：{exc}") from exc


def _drop_empty(obj):
    return {k: v for k, v in obj.items() if v is not None}


def _json_from_raw(raw):
    try:
        return json.loads(raw.decode("utf-8"))
    except Exception as exc:
        raise VeError(f"响应不是合法 JSON：{exc}", payload=raw[:500].decode("utf-8", "replace")) from exc


def _format_srt_time(ms):
    ms = int(ms or 0)
    return f"{ms // 3600000:02d}:{ms % 3600000 // 60000:02d}:{ms % 60000 // 1000:02d},{ms % 1000:03d}"


def _to_srt(utterances):
    blocks = []
    for index, item in enumerate(utterances, 1):
        blocks.append(
            f"{index}\n{_format_srt_time(item.get('start_time'))} --> "
            f"{_format_srt_time(item.get('end_time'))}\n{(item.get('text') or '').strip()}\n"
        )
    return "\n".join(blocks)


def _save_data_url(data_url, cfg, prefix="image"):
    match = DATA_URL_RE.match(data_url or "")
    if not match:
        return None
    subtype, payload = match.group(1), match.group(2)
    ext = {"image/jpeg": "jpg", "image/png": "png", "image/webp": "webp", "image/gif": "gif"}.get(subtype, "png")
    dest = cfg.out_path(f"{prefix}-{time.strftime('%Y%m%d-%H%M%S')}.{ext}")
    dest.write_bytes(base64.b64decode(payload))
    return str(dest)


def _save_remote_images(urls, cfg, args, prefix="image"):
    saved = []
    for index, url in enumerate(urls, 1):
        name = f"{prefix}-{time.strftime('%Y%m%d-%H%M%S')}-{index}.png"
        dest = download_url(cfg, url, out_dir=getattr(args, "out", None), filename=name,
                            timeout=max(cfg.timeout, 120.0))
        saved.append(str(dest))
    return saved


def _timestamp():
    return time.strftime("%Y%m%d-%H%M%S")


def _async_error(payload):
    """异步任务失败时，上游错误常埋在 result.output.message 里，逐层兜底提取。"""
    for path in (("error",), ("result", "output", "message"), ("result", "message"),
                 ("result", "output", "error"), ("message",)):
        value = get_path(payload, *path)
        if isinstance(value, str) and value.strip():
            return value.strip()
        if isinstance(value, dict):
            nested = value.get("message") or value.get("error")
            if isinstance(nested, str) and nested.strip():
                return nested.strip()
    return None


def _pick_status(payload, *names):
    """异步任务状态键在各服务间不一致（task_status / status），按候选顺序取第一个非空值。"""
    for name in names or ("task_status", "status"):
        value = payload.get(name) if isinstance(payload, dict) else None
        if value:
            return str(value).upper()
    return ""


# ---------------------------------------------------------------- env / api


def cmd_env(args):
    cfg = _cfg(args, require_network=False)
    info = {
        "success": True,
        "endpoint": cfg.endpoint or None,
        "render_endpoint": cfg.render_endpoint,
        "api_key_present": bool(cfg.api_key),
        "api_key_preview": f"{cfg.api_key[:10]}…" if cfg.api_key else None,
        "workdir": str(cfg.workdir),
        "output_dir": str(cfg.output_dir),
        "file_mode": cfg.file_mode,
        "remotion_work_dir": cfg.remotion_work_dir,
        "python": sys.version.split()[0],
    }
    if not cfg.api_key:
        info["hint"] = "未设置 VISION_ENGINE_API_KEY，除 env / audio voices 外所有命令都需要它"
    if cfg.api_key:
        try:
            info["auth"] = request_json(cfg, "GET", "/api/v1/auth/me")
        except VeError as exc:
            info["auth"] = {"success": False, "error": exc.message, "http_status": exc.http_status}
    emit(info)


def _normalize_api_path(path):
    """Git Bash（MSYS2）会把 /api/v1/... 改写成 C:/Program Files/Git/api/v1/...，这里还原。"""
    match = re.match(r"^[A-Za-z]:[\\/].*?([\\/]api[\\/].*)$", path)
    if match:
        return "/" + match.group(1).replace("\\", "/").lstrip("/")
    return path


def cmd_api(args):
    cfg = _cfg(args)
    body = None
    if args.data_file:
        body = json.loads(Path(args.data_file).read_text(encoding="utf-8"))
    elif args.data:
        body = _json_arg(args.data, "--data")
    params = {}
    for item in args.query or []:
        if "=" not in item:
            raise VeError(f"--query 需要 K=V 形式：{item!r}")
        key, value = item.split("=", 1)
        params[key] = value

    method = args.method.upper()
    path = _normalize_api_path(args.path)
    if args.raw:
        raw = request_bytes(cfg, method, path, body=body, params=params)
        sys.stdout.write(raw.decode("utf-8", "replace"))
        return
    emit(request_json(cfg, method, path, body=body, params=params))


# ---------------------------------------------------------------- image


def cmd_image(args):
    cfg = _cfg(args)
    action = args.action

    if action in {"generate", "edit", "generate-from-images"}:
        body = {
            "prompt": args.prompt,
            "image_config": {"aspect_ratio": args.aspect_ratio, "image_size": args.image_size},
        }
        if args.model:
            body["model"] = args.model
        if action != "generate":
            body["images"] = [
                {"type": "base64_data_url", "data": as_image_input(cfg, item)}
                for item in args.image
            ]
        payload = request_json(cfg, "POST", f"/api/v1/image-generate/{action}", body=body,
                               timeout=max(cfg.timeout, 180.0))
        return _emit_generated_images(cfg, args, payload)

    if action == "edit-advanced":
        parameters = _drop_empty({
            "n": args.n, "negative_prompt": args.negative_prompt,
            "prompt_extend": False if args.prompt_extend is False else None,
            "watermark": True if args.watermark else None,
            "size": args.size, "seed": args.seed,
        })
        body = {
            "prompt": args.prompt,
            "images": [{"type": "base64_data_url", "data": as_image_input(cfg, item)} for item in args.image],
            "parameters": parameters,
        }
        if args.model:
            body["model"] = args.model
        payload = request_json(cfg, "POST", "/api/v1/image-edit/edit", body=body,
                               timeout=max(cfg.timeout, 180.0))
        urls = [item.get("url") for item in (payload.get("images") or []) if item.get("url")]
        emit({
            "success": True,
            "model_id": payload.get("model_id"),
            "image_urls": urls,
            "local_paths": _save_remote_images(urls, cfg, args, prefix="image-edit") if urls else [],
            "usage": payload.get("usage"),
        })
        return

    if action == "recognize":
        body = {
            "tool": args.tool,
            "prompt": args.prompt or _default_recognize_prompt(args.tool),
            "image": {"type": "base64_data_url", "data": as_image_input(cfg, args.image)},
        }
        if args.model:
            body["model"] = args.model
        payload = request_json(cfg, "POST", "/api/v1/image-recognize/analyze", body=body,
                               timeout=max(cfg.timeout, 180.0))
        content = ((payload.get("choices") or [{}])[0].get("message") or {}).get("content")
        emit({"success": True, "tool": args.tool, "content": content, "usage": payload.get("usage")})
        return

    if action == "prompt-reverse":
        body = {
            "image": {"type": "base64_data_url", "data": as_image_input(cfg, args.image)},
            "output_language": args.output_language,
        }
        if args.user_prompt:
            body["user_prompt"] = args.user_prompt
        if args.model:
            body["model"] = args.model
        payload = request_json(cfg, "POST", "/api/v1/image-prompt-reverse/reverse", body=body,
                               timeout=max(cfg.timeout, 180.0))
        emit({"success": True, "prompt": payload.get("prompt"), "usage": payload.get("usage")})
        return

    raise VeError(f"未知的 image 命令：{action}")


def _emit_generated_images(cfg, args, payload):
    choice = (payload.get("choices") or [{}])[0]
    images = ((choice.get("message") or {}).get("images")) or []
    local_paths, urls = [], []
    for item in images:
        url = ((item.get("image_url") or {}).get("url")) or ""
        urls.append(url)
        saved = _save_data_url(url, cfg)
        if saved:
            local_paths.append(saved)
    if not urls:
        raise VeError("服务端未返回图片（choices[0].message.images 为空）", payload=payload)
    emit({
        "success": True,
        "image_count": len(urls),
        "local_paths": local_paths,
        "usage": payload.get("usage"),
        "model": payload.get("model"),
    })


def _default_recognize_prompt(tool):
    if tool == "visual":
        return (
            "请分析这张图片的视觉设计元素，包括：\n"
            "1. 布局和构图\n2. 色彩搭配和配色方案，颜色可以带上具体色号\n"
            "3. 字体和排版\n4. 视觉层次\n5. 设计风格和特点\n6. 视觉焦点\n"
            "7. 设计原则的应用（如对比、平衡、对齐等）\n\n"
            "请提供详细的专业客观分析，不要输入任何评价信息。"
        )
    return (
        "请从这张图片中提取所有文字和数据信息，包括：\n"
        "1. 图片中的所有文字内容（OCR识别）\n2. 表格数据（如果有）\n3. 图表数据（如果有）\n"
        "4. 数字和统计信息\n5. 标签、标题、说明文字\n6. 任何其他结构化数据\n\n"
        "请按照清晰的格式组织提取的信息。"
    )


# ---------------------------------------------------------------- audio


def cmd_audio(args):
    if args.action == "voices":
        return _cmd_voices(args)
    if args.action == "tts":
        return _cmd_tts(args)
    raise VeError(f"未知的 audio 命令：{args.action}")


def _cmd_voices(args):
    path = ASSETS_DIR / "voices.json"
    if not path.is_file():
        raise VeError(f"音色目录缺失：{path}")
    data = json.loads(path.read_text(encoding="utf-8"))
    voices = data.get("voices", [])
    language = (args.language or "").lower()
    gender = (args.gender or "").lower()
    filtered = []
    for voice in voices:
        languages = [str(item.get("language") or "").lower() for item in voice.get("languages") or []]
        if language and not any(language in item or item in language for item in languages):
            continue
        if gender and str(voice.get("gender", "")).lower() != gender:
            continue
        filtered.append(voice)
    emit({"success": True, "total": len(filtered), "source_count": data.get("count"),
          "language": args.language or None, "gender": args.gender or None, "voices": filtered})


def _cmd_tts(args):
    cfg = _cfg(args)
    additions = {"cache_config": {"text_type": 1, "use_cache": True}}
    if args.explicit_language:
        additions["explicit_language"] = args.explicit_language
    if args.disable_markdown_filter:
        additions["disable_markdown_filter"] = True
    if args.context_text:
        additions["context_texts"] = args.context_text
    if args.pitch is not None:
        additions["post_process"] = {"pitch": args.pitch}

    audio_params = _drop_empty({
        "format": args.format,
        "sample_rate": args.sample_rate,
        "speech_rate": args.speech_rate,
        "loudness_rate": args.loudness_rate,
        "emotion": args.emotion,
        "emotion_scale": args.emotion_scale,
    })
    body = {
        "user": {"uid": "ve-cli"},
        "req_params": {
            "text": args.text,
            "speaker": args.speaker,
            "audio_params": audio_params,
            "additions": json.dumps(additions, ensure_ascii=False),
        },
        "model_id": args.model or "@preset/vec-1-0-audio-tts",
        "resource_id": args.model or "@preset/vec-1-0-audio-tts",
    }
    raw = request_bytes(cfg, "POST", "/api/v1/audio/tts", body=body,
                        timeout=max(cfg.timeout, LONG_TIMEOUT))

    chunks, usage, error = [], None, None
    for line in raw.splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            item = json.loads(line.decode("utf-8"))
        except Exception:
            continue
        code = item.get("code")
        if code == 0:
            data = item.get("data")
            if data:
                chunks.append(base64.b64decode(data))
        elif code == 20000000:
            usage = item.get("usage") or usage
            break
        else:
            error = f"code={code} {item.get('message', '')}".strip()
            break
    if error:
        raise VeError(f"TTS 合成失败：{error}")
    if not chunks:
        raise VeError("TTS 未返回音频数据")

    ext = "ogg" if args.format == "ogg_opus" else args.format
    dest = cfg.out_path(f"tts-{_timestamp()}.{ext}")
    dest.write_bytes(b"".join(chunks))
    emit({"success": True, "local_path": str(dest), "bytes": dest.stat().st_size,
          "format": args.format, "speaker": args.speaker, "usage": usage})


# ---------------------------------------------------------------- subtitle


def cmd_subtitle(args):
    cfg = _cfg(args)
    action = args.action
    params = {"model_id": args.model or f"@preset/vec-1-0-subtitle-{action}"}

    if action == "generate":
        for key, value in {
            "language": args.language,
            "words_per_line": args.words_per_line,
            "max_lines": args.max_lines,
            "caption_type": args.caption_type,
        }.items():
            if value is not None:
                params[key] = value
        for key, enabled in (("use_itn", args.use_itn), ("use_punc", args.use_punc),
                             ("use_ddc", args.use_ddc), ("with_speaker_info", args.with_speaker_info)):
            if enabled:
                params[key] = "true"
    else:
        text = args.text
        if args.text_file:
            text = Path(cfg.resolve_path(args.text_file)).read_text(encoding="utf-8")
        if not text:
            raise VeError("align 需要 --text 或 --text-file")
        params["caption_type"] = args.caption_type
        params["audio_text"] = text
        if args.sta_punc_mode:
            params["sta_punc_mode"] = args.sta_punc_mode
        if len(text) > 1500:
            print(f"⚠️  对齐文本 {len(text)} 字符，将通过 URL 查询串传输；过长可能触发网关长度限制。",
                  file=sys.stderr)

    headers, data = _subtitle_media(cfg, args.audio)
    submit = _json_from_raw(request_raw(cfg, "POST", f"/api/v1/subtitle/{action}/submit", data=data,
                                        params=params, headers=headers, timeout=max(cfg.timeout, 300.0)))
    if str(submit.get("code")) not in {"0", "None"}:
        raise VeError(f"字幕任务提交失败：{submit.get('message')}（code={submit.get('code')}）", payload=submit)
    task_id = submit.get("id")
    if not task_id:
        raise VeError("提交成功但未返回任务 id", payload=submit)

    if not _wait_enabled(args, default=True):
        emit({"success": True, "task_id": task_id, "message": "已提交，可用 api GET /api/v1/subtitle/%s/query?id=%s 查询" % (action, task_id)})
        return

    def _query():
        return request_json(cfg, "GET", f"/api/v1/subtitle/{action}/query",
                            params={"id": task_id, "blocking": "0"})

    payload = _query()
    if str(payload.get("code")) != "0":
        payload = poll(
            _query,
            is_done=lambda item: str(item.get("code")) == "0",
            is_failed=lambda item: str(item.get("code")) not in {"0", "2000"},
            interval=args.interval, timeout=args.timeout,
        )
    if str(payload.get("code")) != "0":
        raise VeError(f"字幕任务未完成：{payload.get('message')}（code={payload.get('code')}）", payload=payload)

    utterances = payload.get("utterances") or []
    if not utterances:
        raise VeError("识别/对齐结果为空（未检测到语音）", payload=payload)
    srt = _to_srt(utterances)
    dest = cfg.out_path(f"{Path(args.audio if not args.audio.startswith('http') else 'subtitle').stem}"
                        f"{'_aligned' if action == 'align' else ''}.srt")
    dest.write_text(srt, encoding="utf-8")
    emit({
        "success": True,
        "task_id": task_id,
        "duration": payload.get("duration"),
        "utterance_count": len(utterances),
        "local_path": str(dest),
        "utterances": [{"text": item.get("text"), "start_time": item.get("start_time"),
                        "end_time": item.get("end_time")} for item in utterances],
    })


def _subtitle_media(cfg, value):
    """字幕接口：本地文件走原始 body + X-Media-Filename；URL 走 X-Media-Url + 空 body。"""
    if value.startswith(("http://", "https://")):
        return {"X-Media-Url": value}, b""
    path = cfg.resolve_path(value)
    if not path.is_file():
        raise VeError(f"音频文件不存在：{path}")
    name = path.name
    ascii_name = name.encode("ascii", "replace").decode("ascii") or "media"
    content_type = SUBTITLE_MEDIA_TYPES.get(path.suffix.lower(), "audio/wav")
    return {"Content-Type": content_type, "X-Media-Filename": ascii_name}, path.read_bytes()


# ---------------------------------------------------------------- video

VIDEO_SUBMIT_PATHS = {
    "img2video": "/api/v1/img2video/submit",
    "text2video": "/api/v1/text2video/submit",
    "style-transfer": "/api/v1/video-style-transfer/submit",
}
VIDEO_QUERY_PATHS = {
    "img2video": "/api/v1/img2video/query",
    "text2video": "/api/v1/text2video/query",
    "style-transfer": "/api/v1/video-style-transfer/query",
}


def cmd_video(args):
    cfg = _cfg(args)
    action, op = args.action, getattr(args, "op", None)

    if action == "recognize":
        if op == "submit":
            return _video_recognize_submit(cfg, args)
        if op == "query":
            payload = request_json(cfg, "GET", f"/api/v1/video/task/{args.task_id}")
            emit(payload)
            return
        if op == "result":
            emit(request_json(cfg, "GET", f"/api/v1/video/task/{args.task_id}/result"))
            return
        if op == "cancel":
            emit(request_json(cfg, "POST", f"/api/v1/video/cancel/{args.task_id}"))
            return
        raise VeError(f"未知的 video recognize 操作：{op}")

    if action not in VIDEO_SUBMIT_PATHS:
        raise VeError(f"未知的 video 能力：{action}")

    if op == "submit":
        body = _video_submit_body(cfg, args)
        emit(request_json(cfg, "POST", VIDEO_SUBMIT_PATHS[action], body=body,
                          timeout=max(cfg.timeout, 120.0)))
        return

    if op == "query":
        payload = request_json(cfg, "GET", VIDEO_QUERY_PATHS[action], params={"task_id": args.task_id})
        if _wait_enabled(args) and _pick_status(payload) not in {"SUCCEEDED"} | TERMINAL_FAILED:
            payload = poll(
                lambda: request_json(cfg, "GET", VIDEO_QUERY_PATHS[action], params={"task_id": args.task_id}),
                is_done=lambda item: _pick_status(item) == "SUCCEEDED",
                is_failed=lambda item: _pick_status(item) in TERMINAL_FAILED,
                interval=args.interval, timeout=args.timeout,
            )
        status = _pick_status(payload)
        result = {"success": status == "SUCCEEDED", "task_id": payload.get("task_id") or args.task_id,
                  "task_status": status, "billing_status": payload.get("billing_status"),
                  "usage": payload.get("usage"),
                  "error": payload.get("error") or _async_error(payload)}
        url = payload.get("output_video_url")
        if url:
            result["output_video_url"] = url
            if getattr(args, "download", True):
                result["local_path"] = str(download_url(
                    cfg, url, out_dir=getattr(args, "out", None),
                    filename=f"{action}-{args.task_id[:8]}.mp4", timeout=max(cfg.timeout, 300.0)))
        emit(result)
        return

    raise VeError(f"未知的 video 操作：{op}")


def _video_submit_body(cfg, args):
    action = args.action
    if action == "img2video":
        body = {
            "model_id": args.model or "@preset/vec-1-0-img2video",
            "input": _drop_empty({
                "image": as_media_input(cfg, args.image, target_dir="public/images",
                                        force_upload=args.upload),
                "audio": as_media_input(cfg, args.audio_input, target_dir="public/audio") if args.audio_input else None,
                "prompt": args.prompt,
                "negative_prompt": args.negative_prompt,
            }),
            "parameters": _drop_empty({
                "duration": args.duration, "resolution": args.resolution,
                "prompt_extend": False if args.prompt_extend is False else None,
                "shot_type": args.shot_type, "audio": True if args.audio else None,
                "watermark": True if args.watermark else None, "seed": args.seed,
            }),
        }
        return body
    if action == "text2video":
        return {
            "model_id": args.model or "@preset/vec-1-0-text2video",
            "input": _drop_empty({
                "prompt": args.prompt, "negative_prompt": args.negative_prompt,
                "audio": as_media_input(cfg, args.audio_input, target_dir="public/audio") if args.audio_input else None,
            }),
            "parameters": _drop_empty({
                "size": args.size, "duration": args.duration,
                "prompt_extend": False if args.prompt_extend is False else None,
                "shot_type": args.shot_type, "watermark": True if args.watermark else None,
                "seed": args.seed,
            }),
        }
    # style-transfer
    return {
        "model_id": args.model or "@preset/vec-1-0-video-style-transfer",
        "input": as_media_input(cfg, args.video, target_dir="public/videos", force_upload=args.upload),
        "parameters": _drop_empty({
            "style": args.style, "video_fps": args.fps, "min_len": args.min_len,
            "animate_emotion": False if args.animate_emotion is False else None,
            "use_SR": True if args.use_sr else None,
        }),
    }


def _video_recognize_submit(cfg, args):
    video = args.video
    if not video.startswith(("http://", "https://", "data:")):
        path = cfg.resolve_path(video)
        if path.is_file():
            info = upload_file(cfg, path, target_dir="public/videos")
            video = f"{cfg.endpoint}/shared/{_quote(info['path'])}?download=true"
    if args.prompt_mode == "auto" and not args.prompt:
        raise VeError("--prompt-mode auto 需要同时提供 --prompt")
    body = _drop_empty({
        "video": video,
        "task_type": args.task_type,
        "prompt_mode": args.prompt_mode,
        "user_prompt": args.prompt,
        "stream": False,
        "response_format": {"type": "json_object"},
        "model_id": args.model,
    })
    if args.start_sec is not None or args.end_sec is not None:
        if args.start_sec is not None and args.end_sec is not None and args.end_sec <= args.start_sec:
            raise VeError("--end-sec 必须大于 --start-sec")
        body["analysis_range"] = _drop_empty({"type": "time", "start_sec": args.start_sec,
                                              "end_sec": args.end_sec})
    # 注意：该端点为同步阻塞调用，多分段视频可能耗时数分钟。
    payload = request_json(cfg, "POST", "/api/v1/video/analyze", body=body,
                           timeout=max(cfg.timeout, LONG_TIMEOUT))
    emit({
        "success": payload.get("status") in {"SUCCEEDED", "PARTIAL_SUCCESS"},
        "task_id": payload.get("task_id"),
        "status": payload.get("status"),
        "task_type": payload.get("task_type"),
        "warnings": payload.get("warnings"),
        "result": payload.get("result"),
        "usage": payload.get("usage"),
    })


def _quote(value):
    return "/".join(urllib.parse.quote(segment, safe="") for segment in value.split("/") if segment)


# ---------------------------------------------------------------- dh


def cmd_dh(args):
    cfg = _cfg(args)
    action, op = args.action, args.op
    if op == "submit":
        return _dh_submit(cfg, args)
    if op == "query":
        return _dh_query(cfg, args, action)
    raise VeError(f"未知的 dh 操作：{op}")


def _dh_submit(cfg, args):
    action = args.action
    if action == "clone":
        body = _drop_empty({
            "name": args.name,
            "source_video": as_media_input(cfg, args.video, target_dir="public/videos"),
        })
        # 注意：服务端顶层 success 表示"已就绪"而非"请求成功"，这里以请求是否被受理为准。
        payload = request_json(cfg, "POST", "/api/v1/dh/avatar-prep/submit", body=body,
                               timeout=max(cfg.timeout, 300.0))
        emit({"success": True, "avatar_id": payload.get("avatar_id"), "status": payload.get("status"),
              "avatar": payload.get("avatar"), "error": payload.get("error")})
        return

    if action == "voice":
        audio_url, prompt_text = args.prompt_audio_url, args.prompt_text
        if args.avatar_id:
            avatar = request_json(cfg, "GET", "/api/v1/dh/avatar-prep/query",
                                  params={"avatar_id": args.avatar_id})
            info = avatar.get("avatar") or {}
            if avatar.get("status") != "ready":
                raise VeError(f"克隆 {args.avatar_id} 尚未就绪（status={avatar.get('status')}）")
            audio_url = audio_url or info.get("audio_url")
            prompt_text = prompt_text or info.get("reference_audio_text")
        if not audio_url:
            raise VeError("需要 --prompt-audio-url 或 --avatar-id")
        if not prompt_text:
            raise VeError("需要 --prompt-text（参考音频逐字稿）或 --avatar-id")
        body = _drop_empty({
            "text": args.text,
            "prompt_audio_url": as_media_url(cfg, audio_url, target_dir="public/audio"),
            "prompt_text": prompt_text,
            "model_id": args.model,
            "seed": args.seed, "nfe": args.nfe,
            "guidance_strength": args.guidance_strength,
            "guidance_method": args.guidance_method,
            "max_chunk_chars": args.max_chunk_chars,
        })
        emit(request_json(cfg, "POST", "/api/v1/voice-clone/submit", body=body,
                          timeout=max(cfg.timeout, 120.0)))
        return

    # lipsync
    body = _drop_empty({
        "model_id": args.model,
        "input": {
            "video": as_media_input(cfg, args.video, target_dir="public/videos", force_upload=args.upload),
            "audio": as_media_input(cfg, args.audio, target_dir="public/audio", force_upload=args.upload),
        },
    })
    emit(request_json(cfg, "POST", "/api/v1/avatar-lipsync/submit", body=body,
                      timeout=max(cfg.timeout, 120.0)))


def _dh_query(cfg, args, action):
    if action == "clone":
        if not args.avatar_id:
            raise VeError("dh clone query 需要 --avatar-id")
        path, key, params = "/api/v1/dh/avatar-prep/query", "status", {"avatar_id": args.avatar_id}
        done, failed = "ready", "failed"
    else:
        if not args.task_id:
            raise VeError(f"dh {action} query 需要 --task-id")
        path = "/api/v1/voice-clone/query" if action == "voice" else "/api/v1/avatar-lipsync/query"
        key, params, done, failed = "task_status", {"task_id": args.task_id}, "SUCCEEDED", "FAILED"

    payload = request_json(cfg, "GET", path, params=params)
    if _wait_enabled(args) and str(payload.get(key, "")).lower() not in {done.lower(), failed.lower()}:
        payload = poll(
            lambda: request_json(cfg, "GET", path, params=params),
            is_done=lambda item: str(item.get(key, "")).lower() == done.lower(),
            is_failed=lambda item: str(item.get(key, "")).lower() == failed.lower(),
            interval=args.interval, timeout=args.timeout,
        )

    status = str(payload.get(key, ""))
    result = {"success": status.lower() == done.lower(), "status": status, "raw": payload}
    if action == "clone":
        avatar = payload.get("avatar") or {}
        result["avatar_id"] = payload.get("avatar_id")
        result["audio_url"] = avatar.get("audio_url")
        result["reference_audio_text"] = avatar.get("reference_audio_text")
        result["video_path"] = avatar.get("video_path")
        if avatar.get("audio_url") and getattr(args, "download", True) and status == "ready":
            result["local_path"] = str(download_url(
                cfg, avatar["audio_url"], out_dir=getattr(args, "out", None),
                filename=f"clone-{str(payload.get('avatar_id'))[:8]}-reference.wav"))
    else:
        result["task_id"] = payload.get("task_id") or args.task_id
        result["billing_status"] = payload.get("billing_status")
        result["result"] = payload.get("result")
        result["error"] = payload.get("error")
        url = payload.get("result_url")
        if url and getattr(args, "download", True) and status.upper() == done:
            suffix = "wav" if action == "voice" else "mp4"
            result["result_url"] = url
            result["local_path"] = str(download_url(
                cfg, url, out_dir=getattr(args, "out", None),
                filename=f"{action}-{str(args.task_id)[:8]}.{suffix}",
                timeout=max(cfg.timeout, 300.0)))
    emit(result)


# ---------------------------------------------------------------- files


def cmd_files(args):
    cfg = _cfg(args)
    action = args.action

    if action == "list":
        params = _drop_empty({
            "path": args.path, "max_depth": args.max_depth, "limit": args.limit,
            "mode": args.mode,
            "include_hidden": "true" if args.include_hidden else None,
            "include_content": "true" if args.include_content else None,
        })
        emit(request_json(cfg, "GET", "/api/v1/files/list", params=params))
        return

    if action == "read":
        payload = request_json(cfg, "GET", "/api/v1/files/list",
                               params={"path": args.path, "mode": "file", "include_content": "true"})
        entries = payload.get("entries") or []
        entry = entries[0] if entries else {}
        emit({"success": True, "path": entry.get("path", args.path),
              "content": entry.get("content"), "size": entry.get("size")})
        return

    if action == "upload":
        if args.source == "url":
            if not args.url:
                raise VeError("--source url 需要 --url")
            name = args.file_name or Path(urllib.parse.urlparse(args.url).path).name or "download"
            temp = cfg.out_path(name)
            download_url(cfg, args.url, out_dir=temp.parent, filename=temp.name)
            info = upload_file(cfg, temp, target_dir=args.target_path, file_name=args.file_name)
            temp.unlink(missing_ok=True)
        else:
            if not args.path:
                raise VeError("需要给出本地文件路径")
            info = upload_file(cfg, cfg.resolve_path(args.path),
                               target_dir=args.target_path, file_name=args.file_name)
        emit({"success": True, "file": info,
              "shared_url": f"{cfg.endpoint}/shared/{_quote(info['path'])}?download=true"})
        return

    if action == "download":
        me = request_json(cfg, "GET", "/api/v1/auth/me")
        user_id = me.get("user_id")
        if not user_id:
            raise VeError("无法解析 user_id（/api/v1/auth/me）", payload=me)
        relative = args.path.lstrip("/")
        prefix = f"{user_id}/"
        if relative.startswith(prefix):
            relative = relative[len(prefix):]
        url = f"{cfg.endpoint}/shared/{_quote(user_id)}/{_quote(relative)}?download=true"
        dest = download_url(cfg, url, out_dir=args.out, filename=Path(relative).name)
        emit({"success": True, "local_path": str(dest), "source_path": args.path})
        return

    if action == "delete":
        emit(request_json(cfg, "DELETE", "/api/v1/files/delete", params={"path": args.path}))
        return

    raise VeError(f"未知的 files 命令：{action}")


# ---------------------------------------------------------------- render


def cmd_render(args):
    cfg = _cfg(args)
    base = cfg.render_endpoint
    action = args.action

    if action == "submit":
        body = _drop_empty({
            "compositionId": args.composition_id,
            "inputProps": _json_arg(args.input_props, "--input-props"),
            "exportType": args.export_type,
            "codec": args.codec,
            "audioCodec": args.audio_codec,
            "imageFormat": args.image_format,
            "outName": args.out_name,
            "entryPoint": args.entry_point,
            "startFrame": args.start_frame,
            "endFrame": args.end_frame,
            "everyNthFrame": args.every_nth_frame,
            "frame": args.frame,
            "projectId": args.project_id,
            "studioOpaqueId": args.studio_sid,
        })
        if args.image_sequence:
            body["imageSequence"] = True
        payload = request_json(cfg, "POST", "/api/render-tasks", body=body, endpoint=base,
                               timeout=max(cfg.timeout, 120.0))
        task_id = (payload.get("data") or {}).get("taskId")
        emit({"success": bool(task_id), "task_id": task_id, "out_name": args.out_name, "raw": payload})
        return

    if action == "query":
        return _render_query(cfg, args, base)

    if action == "list":
        payload = request_json(cfg, "GET", "/api/render-tasks", endpoint=base,
                               params=_drop_empty({"studioOpaqueId": args.studio_opaque_id,
                                                   "limit": args.limit}))
        emit(payload)
        return

    if action in {"cancel", "retry"}:
        emit(request_json(cfg, "POST", f"/api/render-tasks/{args.task_id}/{action}", endpoint=base))
        return

    if action == "download":
        return _render_download(cfg, args, base)

    raise VeError(f"未知的 render 命令：{action}")


def _render_task(cfg, base, task_id):
    return (request_json(cfg, "GET", f"/api/render-tasks/{task_id}", endpoint=base).get("data") or {})


def _render_query(cfg, args, base):
    task = _render_task(cfg, base, args.task_id)
    status = str(task.get("status") or "")
    if _wait_enabled(args) and status not in RENDER_DONE | RENDER_FAILED:
        task = poll(
            lambda: _render_task(cfg, base, args.task_id),
            is_done=lambda item: str(item.get("status")) in RENDER_DONE,
            is_failed=lambda item: str(item.get("status")) in RENDER_FAILED,
            interval=args.interval, timeout=args.timeout,
        )
        status = str(task.get("status") or "")

    result = {
        "success": status in RENDER_DONE,
        "task_id": task.get("id") or args.task_id,
        "status": status,
        "progress": task.get("progress"),
        "composition_id": task.get("composition_id"),
        "out_name": task.get("out_name"),
        "error": task.get("error"),
        "message": task.get("message"),
        "duration_ms": task.get("duration_ms"),
        "result_payload": task.get("result_payload"),
    }
    if status in RENDER_DONE and getattr(args, "download", None):
        try:
            dest = _render_download(cfg, args, base, task=task, quiet=True)
            result["local_path"] = str(dest)
        except VeError as exc:
            result["download_error"] = exc.message
    emit(result)


def _render_download(cfg, args, base, task=None, quiet=False):
    task = task or _render_task(cfg, base, args.task_id)
    out_name = getattr(args, "filename", None) or task.get("out_name")
    if not out_name:
        raise VeError("任务记录缺少 out_name，无法定位产物")
    url = (f"{base.rstrip('/')}/api/render-tasks/{args.task_id}/file"
           f"?filename={urllib.parse.quote(Path(out_name).name)}")
    dest = download_url(cfg, url, out_dir=getattr(args, "out", None),
                        filename=Path(out_name).name, timeout=max(cfg.timeout, 600.0), auth=True)
    if not quiet:
        emit({"success": True, "local_path": str(dest), "out_name": out_name, "task_id": args.task_id})
    return dest


# ---------------------------------------------------------------- llm


def cmd_llm(args):
    cfg = _cfg(args)
    if args.action != "chat":
        raise VeError(f"未知的 llm 命令：{args.action}")

    messages = _json_arg(args.messages, "--messages")
    if not messages:
        if not args.prompt:
            raise VeError("需要 --prompt 或 --messages")
        messages = []
        if args.system:
            messages.append({"role": "system", "content": args.system})
        messages.append({"role": "user", "content": args.prompt})

    body = _drop_empty({
        "model": args.model or "@preset/vec-1-0",
        "messages": messages,
        "max_tokens": args.max_tokens,
        "temperature": args.temperature,
    })
    payload = request_json(cfg, "POST", "/api/v1/chat/completions", body=body,
                           timeout=max(cfg.timeout, 300.0))
    choice = (payload.get("choices") or [{}])[0]
    emit({"success": True, "content": (choice.get("message") or {}).get("content"),
          "model": payload.get("model"), "usage": payload.get("usage")})


COMMANDS = {
    "api": cmd_api,
    "audio": cmd_audio,
    "dh": cmd_dh,
    "env": cmd_env,
    "files": cmd_files,
    "image": cmd_image,
    "llm": cmd_llm,
    "render": cmd_render,
    "subtitle": cmd_subtitle,
    "video": cmd_video,
}
