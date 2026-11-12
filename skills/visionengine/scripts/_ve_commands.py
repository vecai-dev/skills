#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
_ve_commands.py —— 图片 / 语音 / 字幕 / 视频 / 数字人 / 环境诊断命令。

所有平台能力都通过 `_mcp_tools.call()` 走 MCP；CLI 只做参数转换、
轮询、落盘与错误整形。
"""

from __future__ import annotations

import json
import os
import shutil
import sys
import time
import urllib.parse
from pathlib import Path

from _mcp_client import resolve_command
from _mcp_tools import (
    SPECS,
    TIMEOUTS,
    bridge_quota,
    call,
    call_text,
    describe,
    render_get_context,
)
from _ve_cmd_files import cmd_files
from _ve_cmd_render import cmd_render
from _ve_context import (
    prepare_media_input,
    require_api_key,
    resolve_api_key,
    resolve_context,
    stage_local_file,
)
from _ve_util import (
    VeError,
    download_url,
    emit,
    get_path,
    pick,
    sanitize_text,
    timestamp_slug,
)

ASSETS_DIR = Path(__file__).absolute().parent.parent / "assets"
DEFAULT_VOICES = ASSETS_DIR / "voices.json"

VIDEO_DONE = {"SUCCEEDED", "PARTIAL_SUCCESS"}
VIDEO_FAILED = {"FAILED", "CANCELED", "CANCELLED"}


def _ctx(args, ensure_out=True):
    ctx = resolve_context(args)
    if ensure_out:
        ctx.output_dir.mkdir(parents=True, exist_ok=True)
    return ctx


def _key():
    return require_api_key()[0]


def _status(value):
    return str(value or "").upper()


def _local_media(value):
    """图片输入：URL/data/存储路径原样透传；本地相对路径转绝对路径。"""
    if value is None:
        return value
    text = str(value)
    lowered = text.lower()
    if lowered.startswith(("http://", "https://", "data:")):
        return text
    path = Path(text)
    if not path.is_absolute():
        path = (Path.cwd() / path).resolve()
    return str(path) if path.is_file() else text


def _task_id(parsed):
    return pick(parsed or {}, "task_id", "taskId", "id")


def _image_paths(parsed):
    images = pick(parsed or {}, "images", "local_paths", "files", default=[])
    result = []
    if isinstance(images, list):
        for item in images:
            if isinstance(item, dict):
                value = pick(item, "filePath", "path", "local_path", "file_path")
            else:
                value = item
            if value:
                result.append(str(value))
    if not result:
        single = pick(parsed or {}, "filePath", "local_path", "file_path")
        if single:
            result.append(str(single))
    return result


# ---------------------------------------------------------------- env


def cmd_env(args):
    ctx = _ctx(args, ensure_out=False)
    key, key_source = resolve_api_key()
    packages = {}
    for package_key, spec in SPECS.items():
        entry = {
            "npm": spec.npm,
            "bin": spec.bin,
            "title": spec.title,
        }
        try:
            argv, source = resolve_command(spec)
            entry["command"] = argv
            entry["command_source"] = source
        except VeError as exc:
            entry["command_error"] = sanitize_text(exc.message)
        packages[package_key] = entry

    payload = {
        "success": True,
        "python": sys.version.split()[0],
        "node": shutil.which("node"),
        "npx": shutil.which("npx"),
        "api_key_present": bool(key),
        "api_key_source": key_source,
        "context": {
            "cwd": str(ctx.cwd),
            "project_dir": str(ctx.project_dir),
            "usage_type": ctx.usage_type,
            "system": ctx.system,
            "workspace_id": ctx.workspace_id,
            "artifact_identifier": ctx.artifact_identifier,
            "round_timestamp": ctx.round_timestamp,
            "output_dir": str(ctx.output_dir),
            "cache_dir": str(ctx.cache_dir),
            "file_mode": ctx.file_mode,
            "sources": ctx.sources,
        },
        "packages": packages,
    }
    if getattr(args, "probe", False):
        probe = {}
        try:
            client = _mcp_client_for("render", ctx, key)
            probe["render"] = {
                "server_info": client.server_info,
                "tools": [tool.get("name") for tool in client.list_tools()],
            }
        except VeError as exc:
            probe["render"] = {"error": sanitize_text(exc.message)}
        try:
            client = _mcp_client_for("remotion-file-bridge", ctx, key)
            probe["remotion-file-bridge"] = {
                "server_info": client.server_info,
                "tools": [tool.get("name") for tool in client.list_tools()],
            }
        except VeError as exc:
            probe["remotion-file-bridge"] = {"error": sanitize_text(exc.message)}
        payload["probe"] = probe
    emit(payload)


def _mcp_client_for(package_key, ctx, api_key):
    from _mcp_tools import _client

    return _client(package_key, ctx, api_key, require_key=False)


# ---------------------------------------------------------------- image


def cmd_image(args):
    ctx = _ctx(args)
    api_key = _key()
    action = args.action

    if action == "generate":
        parsed, _ = call(
            "image-generate",
            "generate",
            {
                "prompt": args.prompt,
                "aspectRatio": args.aspect_ratio,
                "imageSize": args.image_size,
                **({"modelId": args.model} if getattr(args, "model", None) else {}),
            },
            ctx,
            api_key,
            timeout=TIMEOUTS["image"],
        )
        emit({"success": True, "local_paths": _image_paths(parsed), "raw": parsed})
        return

    if action == "edit":
        images = getattr(args, "image", None) or []
        if len(images) != 1:
            raise VeError(
                "image edit 只接受单张 --image；多图请用 image edit-advanced。",
                code="INVALID_ARGUMENT",
            )
        parsed, _ = call(
            "image-generate",
            "edit",
            {
                "imagePath": _local_media(images[0]),
                "prompt": args.prompt,
                "aspectRatio": args.aspect_ratio,
                "imageSize": args.image_size,
                **({"modelId": args.model} if getattr(args, "model", None) else {}),
            },
            ctx,
            api_key,
            timeout=TIMEOUTS["image"],
        )
        emit({"success": True, "local_paths": _image_paths(parsed), "raw": parsed})
        return

    if action == "edit-advanced":
        parsed, _ = call(
            "image-edit",
            "edit",
            {
                "imagePaths": [_local_media(item) for item in args.image],
                "prompt": args.prompt,
                "n": args.n,
                **({"negativePrompt": args.negative_prompt} if args.negative_prompt else {}),
                **({"size": args.size} if args.size else {}),
                **({"seed": args.seed} if args.seed is not None else {}),
                "promptExtend": args.prompt_extend,
                "watermark": args.watermark,
                "outputDir": str(ctx.output_dir),
                **({"model": args.model} if getattr(args, "model", None) else {}),
            },
            ctx,
            api_key,
            timeout=TIMEOUTS["image"],
        )
        emit({"success": True, "local_paths": _image_paths(parsed), "raw": parsed})
        return

    if action == "generate-from-images":
        parsed, _ = call(
            "image-generate",
            "generateFromImages",
            {
                "imagePaths": [_local_media(item) for item in args.image],
                "prompt": args.prompt,
                "aspectRatio": args.aspect_ratio,
                "imageSize": args.image_size,
                **({"modelId": args.model} if getattr(args, "model", None) else {}),
            },
            ctx,
            api_key,
            timeout=TIMEOUTS["image"],
        )
        emit({"success": True, "local_paths": _image_paths(parsed), "raw": parsed})
        return

    if action == "recognize":
        tool = "text" if args.tool == "text" else "visual"
        text = call_text(
            "image-recognize",
            tool,
            {
                "imagePath": _local_media(args.image),
                **({"prompt": args.prompt} if args.prompt else {}),
                **({"modelId": args.model} if getattr(args, "model", None) else {}),
            },
            ctx,
            api_key,
            timeout=TIMEOUTS["image"],
        )
        emit({"success": True, "tool": tool, "content": text})
        return

    if action == "prompt-reverse":
        text = call_text(
            "image-recognize",
            "prompt_reverse",
            {
                "imagePath": _local_media(args.image),
                "outputLanguage": args.output_language,
                **({"userPrompt": args.user_prompt} if args.user_prompt else {}),
                **({"modelId": args.model} if getattr(args, "model", None) else {}),
            },
            ctx,
            api_key,
            timeout=TIMEOUTS["image"],
        )
        emit({"success": True, "prompt": text})
        return

    raise VeError(f"未知的 image 命令：{action}", code="UNKNOWN_ACTION")


# ---------------------------------------------------------------- audio / subtitle


def cmd_audio(args):
    ctx = _ctx(args)
    action = args.action

    if action == "voices":
        _emit_voices(args)
        return

    if action == "tts":
        api_key = _key()
        ext = {"mp3": "mp3", "ogg_opus": "ogg", "pcm": "pcm"}.get(args.format, "mp3")
        output_path = ctx.output_dir / f"tts-{timestamp_slug()}.{ext}"
        parsed, _ = call(
            "audio-tts",
            "tts",
            {
                "text": args.text,
                "speaker": args.speaker,
                "format": args.format,
                "sampleRate": str(args.sample_rate),
                **({"speechRate": args.speech_rate} if args.speech_rate is not None else {}),
                **({"loudnessRate": args.loudness_rate} if args.loudness_rate is not None else {}),
                **({"emotion": args.emotion} if args.emotion else {}),
                **({"emotionScale": args.emotion_scale} if args.emotion_scale is not None else {}),
                **({"pitch": args.pitch} if args.pitch is not None else {}),
                **({"contextTexts": args.context_text} if args.context_text else {}),
                **({"explicitLanguage": args.explicit_language} if args.explicit_language else {}),
                "disableMarkdownFilter": args.disable_markdown_filter,
                **({"modelId": args.model} if getattr(args, "model", None) else {}),
                "outputPath": str(output_path),
            },
            ctx,
            api_key,
            timeout=TIMEOUTS["tts"],
        )
        local = pick(parsed or {}, "filePath", "file_path", "local_path") or str(output_path)
        emit({"success": True, "local_path": local, "raw": parsed})
        return

    raise VeError(f"未知的 audio 命令：{action}", code="UNKNOWN_ACTION")


def _emit_voices(args):
    if getattr(args, "offline", False):
        voices = _load_local_voices()
    else:
        try:
            parsed, _ = call(
                "audio-tts",
                "list-voices",
                {},
                resolve_context(args),
                None,
                require_key=False,
                timeout=TIMEOUTS["image"],
            )
            voices = pick(parsed or {}, "voices", default=[]) or _load_local_voices()
        except VeError as exc:
            sys.stderr.write(f"warning: list-voices MCP 失败，回退本地目录（{exc.message}）\n")
            voices = _load_local_voices()
    language = getattr(args, "language", None)
    gender = getattr(args, "gender", None)
    if language:
        wanted = str(language).lower()
        voices = [
            voice for voice in voices
            if any(lang.startswith(wanted) for lang in _voice_languages(voice))
        ]
    if gender:
        voices = [
            voice for voice in voices
            if str(voice.get("gender") or voice.get("gender_label") or "").lower()
            in _gender_values(gender)
        ]
    for voice in voices:
        if not voice.get("voice_type"):
            voice["voice_type"] = (
                voice.get("voiceType") or voice.get("voice_id") or voice.get("id")
            )
    emit({"success": True, "total": len(voices), "voices": voices})


def _voice_languages(voice):
    value = voice.get("languages")
    if isinstance(value, list):
        result = []
        for item in value:
            if isinstance(item, dict):
                lang = item.get("language") or item.get("lang")
            else:
                lang = item
            if lang:
                result.append(str(lang).lower())
        return result
    single = voice.get("language") or voice.get("lang")
    return [str(single).lower()] if single else []


def _load_local_voices():
    try:
        parsed = json.loads(DEFAULT_VOICES.read_text(encoding="utf-8"))
    except Exception as exc:
        raise VeError(f"读取本地音色目录失败：{exc}", code="VOICES_UNAVAILABLE") from exc
    if isinstance(parsed, list):
        return parsed
    if isinstance(parsed, dict):
        for key in ("voices", "data", "items"):
            value = parsed.get(key)
            if isinstance(value, list):
                return value
    return []


def _gender_values(gender):
    value = str(gender).lower()
    if value in ("male", "男", "男性"):
        return {"male", "男", "男性", "m"}
    if value in ("female", "女", "女性"):
        return {"female", "女", "女性", "f"}
    return {value}


def cmd_subtitle(args):
    ctx = _ctx(args)
    api_key = _key()
    action = args.action
    if getattr(args, "no_wait", False):
        sys.stderr.write("warning: subtitle MCP 内部同步轮询，--no-wait 无法提前返回\n")
        sys.stderr.flush()
    staged_audio = _stage_audio(args.audio, ctx)
    common = {
        "audioPath": str(staged_audio),
        "captionType": args.caption_type,
        **({"modelId": args.model} if getattr(args, "model", None) else {}),
    }

    if action == "generate":
        parsed, _ = call(
            "subtitle-generate",
            "subtitle_generate",
            {
                **common,
                **({"language": args.language} if args.language else {}),
                **({"wordsPerLine": args.words_per_line} if args.words_per_line is not None else {}),
                **({"maxLines": args.max_lines} if args.max_lines is not None else {}),
                "useItn": args.use_itn,
                "usePunc": args.use_punc,
                "useDdc": args.use_ddc,
                "withSpeakerInfo": args.with_speaker_info,
            },
            ctx,
            api_key,
            timeout=TIMEOUTS["subtitle"],
        )
    elif action == "align":
        text = getattr(args, "text", None)
        text_file = getattr(args, "text_file", None)
        if text_file and not text:
            text = Path(text_file).read_text(encoding="utf-8")
        if not text:
            raise VeError("subtitle align 需要 --text 或 --text-file", code="INVALID_ARGUMENT")
        parsed, _ = call(
            "subtitle-generate",
            "subtitle_align",
            {
                **common,
                "subtitleText": text,
                **({"staPuncMode": args.sta_punc_mode} if args.sta_punc_mode else {}),
            },
            ctx,
            api_key,
            timeout=TIMEOUTS["subtitle"],
        )
    else:
        raise VeError(f"未知的 subtitle 命令：{action}", code="UNKNOWN_ACTION")

    subtitle_file = pick(parsed or {}, "subtitleFile", "subtitle_file", "local_path")
    local_path = _move_subtitle(subtitle_file, staged_audio, ctx)
    emit(
        {
            "success": True,
            "local_path": str(local_path) if local_path else None,
            "task_id": _task_id(parsed),
            "duration": pick(parsed or {}, "duration"),
            "utterance_count": pick(parsed or {}, "utteranceCount", "utterance_count"),
            "utterances": pick(parsed or {}, "utterances", default=[]),
        }
    )


def _stage_audio(value, ctx):
    if not value:
        raise VeError("--audio 必填", code="INVALID_ARGUMENT")
    if str(value).lower().startswith(("http://", "https://")):
        return str(value)
    return stage_local_file(value, ctx)


def _move_subtitle(subtitle_file, staged_audio, ctx):
    if not subtitle_file:
        return None
    if isinstance(staged_audio, str):
        stem = Path(urllib.parse.urlparse(staged_audio).path).stem or "subtitle"
        source_dir = ctx.cwd
    else:
        stem = staged_audio.stem
        source_dir = staged_audio.parent
    candidates = [Path(subtitle_file)]
    if not Path(subtitle_file).is_absolute():
        candidates.extend(
            [
                source_dir / subtitle_file,
                ctx.project_dir / subtitle_file,
                ctx.cwd / subtitle_file,
            ]
        )
    source = next((path for path in candidates if path.is_file()), None)
    if not source:
        return None
    target = ctx.output_dir / f"{stem}.srt"
    ctx.output_dir.mkdir(parents=True, exist_ok=True)
    if source.resolve() != target.resolve():
        shutil.copy2(source, target)
    return target


# ---------------------------------------------------------------- video


def cmd_video(args):
    ctx = _ctx(args)
    api_key = _key()
    kind = args.action
    op = args.op
    key = {
        "img2video": "img2video",
        "text2video": "text2video",
        "style-transfer": "video-style-transfer",
        "recognize": "video-recognize",
    }[kind]

    if op == "cancel":
        raise VeError("视频 MCP 暂未提供取消工具。", code="MCP_TOOL_MISSING")

    if op == "submit":
        if kind == "img2video":
            payload = {
                "imagePath": prepare_media_input(args.image, ctx, "image"),
                **({"prompt": args.prompt} if args.prompt else {}),
                **({"negativePrompt": args.negative_prompt} if args.negative_prompt else {}),
                **({"audioPath": prepare_media_input(args.audio_input, ctx, "audio")} if args.audio_input else {}),
                **({"duration": args.duration} if args.duration is not None else {}),
                **({"resolution": args.resolution} if args.resolution else {}),
                "audio": args.audio,
                **({"shotType": args.shot_type} if args.shot_type else {}),
                "promptExtend": args.prompt_extend,
                "watermark": args.watermark,
                **({"seed": args.seed} if args.seed is not None else {}),
                **({"modelId": args.model} if getattr(args, "model", None) else {}),
            }
        elif kind == "text2video":
            payload = {
                "prompt": args.prompt,
                **({"negativePrompt": args.negative_prompt} if args.negative_prompt else {}),
                **({"audioPath": prepare_media_input(args.audio_input, ctx, "audio")} if args.audio_input else {}),
                **({"size": args.size} if args.size else {}),
                **({"duration": args.duration} if args.duration is not None else {}),
                **({"shotType": args.shot_type} if args.shot_type else {}),
                "promptExtend": args.prompt_extend,
                "watermark": args.watermark,
                **({"seed": args.seed} if args.seed is not None else {}),
                **({"modelId": args.model} if getattr(args, "model", None) else {}),
            }
        elif kind == "style-transfer":
            payload = {
                "videoPath": prepare_media_input(args.video, ctx, "video"),
                **({"style": args.style} if args.style is not None else {}),
                **({"videoFps": args.fps} if args.fps is not None else {}),
                **({"minLen": args.min_len} if args.min_len is not None else {}),
                "animateEmotion": args.animate_emotion,
                "useSR": args.use_sr,
                **({"modelId": args.model} if getattr(args, "model", None) else {}),
            }
        else:  # recognize
            analysis_range = None
            if args.start_sec is not None or args.end_sec is not None:
                analysis_range = {"type": "time"}
                if args.start_sec is not None:
                    analysis_range["startSec"] = args.start_sec
                if args.end_sec is not None:
                    analysis_range["endSec"] = args.end_sec
            payload = {
                "video": prepare_media_input(args.video, ctx, "video"),
                "taskType": args.task_type,
                **({"promptMode": args.prompt_mode} if args.prompt_mode else {}),
                **({"userPrompt": args.prompt} if args.prompt else {}),
                **({"analysisRange": analysis_range} if analysis_range else {}),
                "responseFormat": "json_object",
                "stream": False,
                **({"modelId": args.model} if getattr(args, "model", None) else {}),
            }

        parsed, _ = call(key, "submit", payload, ctx, api_key, timeout=TIMEOUTS["video-submit"])
        task_id = _task_id(parsed)
        if kind == "recognize" and not getattr(args, "no_wait", False):
            parsed = _poll_video(key, task_id, ctx, api_key, args)
        emit(_video_result(parsed, task_id, kind))
        return

    task_id = getattr(args, "task_id", None)
    if not task_id:
        raise VeError("--task-id 必填", code="TASK_ID_REQUIRED")
    if op in ("query", "result"):
        if op == "query" and getattr(args, "wait", False):
            parsed = _poll_video(key, task_id, ctx, api_key, args)
        elif kind == "recognize":
            parsed, _ = call(
                key,
                "query",
                {"taskId": task_id},
                ctx,
                api_key,
                timeout=TIMEOUTS["video-query"],
                raise_on_failure=False,
            )
        else:
            download = getattr(args, "download", True)
            output_path = ctx.output_dir / f"{kind}-{task_id[:8]}.mp4"
            parsed, _ = call(
                key,
                "query",
                {
                    "taskId": task_id,
                    **({"downloadResult": download, "outputPath": str(output_path)} if download else {}),
                },
                ctx,
                api_key,
                timeout=TIMEOUTS["video-query"],
                raise_on_failure=False,
            )
        emit(_video_result(parsed, task_id, kind))
        return

    raise VeError(f"未知的 video 操作：{op}", code="UNKNOWN_ACTION")


def _poll_video(key, task_id, ctx, api_key, args):
    deadline = time.time() + float(getattr(args, "timeout", None) or getattr(args, "wait_timeout", None) or 600)
    interval = float(getattr(args, "interval", None) or 15)
    last = {}
    while True:
        parsed, _ = call(
            key,
            "query",
            {"taskId": task_id},
            ctx,
            api_key,
            timeout=TIMEOUTS["video-query"],
            raise_on_failure=False,
        )
        last = parsed or {}
        status = _status(pick(last, "taskStatus", "task_status", "status"))
        if status in VIDEO_DONE or status in VIDEO_FAILED:
            return last
        if time.time() >= deadline:
            raise VeError(
                f"轮询超时（{getattr(args, 'timeout', None) or 600}s）。任务仍在运行，"
                f"可稍后用 `video {args.action} query --task-id {task_id}` 继续查询。",
                code="POLL_TIMEOUT",
                payload=last,
            )
        time.sleep(interval)


def _video_result(parsed, task_id, kind):
    parsed = parsed or {}
    status = pick(parsed, "taskStatus", "task_status", "status")
    local = pick(
        parsed,
        "outputVideoPath",
        "output_video_path",
        "local_path",
        "outputFilePath",
        "output_file_path",
    )
    return {
        "success": _status(status) in VIDEO_DONE or _status(status) == "DONE",
        "task_id": pick(parsed, "task_id", "taskId", "id") or task_id,
        "status": status,
        "local_path": local,
        "result_url": pick(parsed, "outputVideoUrl", "output_video_url", "resultUrl", "result_url"),
        "result": pick(parsed, "result"),
        "usage": pick(parsed, "usage"),
        "error": sanitize_text(pick(parsed, "error", "message")),
        "raw": parsed if kind == "recognize" and not local else None,
    }


# ---------------------------------------------------------------- digital human


def cmd_dh(args):
    ctx = _ctx(args)
    api_key = _key()
    kind = args.action
    op = args.op

    if kind == "clone":
        if op == "submit":
            parsed, _ = call(
                "digital-human",
                "clone_submit",
                {
                    "videoPath": prepare_media_input(args.video, ctx, "video"),
                    **({"name": args.name} if args.name else {}),
                },
                ctx,
                api_key,
                timeout=TIMEOUTS["dh-submit"],
            )
            emit(_dh_result(parsed))
            return
        if op == "query":
            avatar_id = args.avatar_id
            if not avatar_id:
                raise VeError("--avatar-id 必填", code="INVALID_ARGUMENT")
            if getattr(args, "wait", False):
                parsed = _poll_clone(avatar_id, ctx, api_key, args)
            else:
                parsed, _ = call(
                    "digital-human",
                    "clone_query",
                    {"avatarId": avatar_id},
                    ctx,
                    api_key,
                    timeout=TIMEOUTS["dh-query"],
                    raise_on_failure=False,
                )
            local = None
            audio_url = get_path(parsed or {}, "avatar", "audioUrl") or pick(
                parsed or {}, "audioUrl", "audio_url"
            )
            if getattr(args, "download", False) and audio_url:
                local = str(download_url(audio_url, ctx.output_dir, timeout=TIMEOUTS["dh-query"]))
            emit(_dh_result(parsed, local_path=local))
            return

    if kind == "voice":
        if op == "submit":
            prompt_audio = args.prompt_audio_url
            prompt_text = args.prompt_text
            if args.avatar_id:
                clone = _poll_clone(args.avatar_id, ctx, api_key, args)
                prompt_audio = get_path(clone or {}, "avatar", "audioUrl") or pick(
                    clone or {}, "audioUrl", "audio_url"
                )
                prompt_text = get_path(clone or {}, "avatar", "referenceAudioText") or pick(
                    clone or {}, "referenceAudioText", "reference_audio_text"
                )
                if not prompt_audio or not prompt_text:
                    raise VeError(
                        f"无法从 avatar {args.avatar_id} 获取参考音频/逐字稿。",
                        code="AVATAR_NOT_READY",
                        payload=clone,
                    )
            if not prompt_audio or not prompt_text:
                raise VeError(
                    "voice submit 需要 --avatar-id，或同时提供 --prompt-audio-url 与 --prompt-text。",
                    code="INVALID_ARGUMENT",
                )
            parsed, _ = call(
                "digital-human",
                "voice_submit",
                {
                    "promptAudioUrl": prepare_media_input(prompt_audio, ctx, "audio"),
                    "promptText": prompt_text,
                    "text": args.text,
                    **({"nfe": args.nfe} if args.nfe is not None else {}),
                    **({"guidanceStrength": args.guidance_strength} if args.guidance_strength is not None else {}),
                    **({"guidanceMethod": args.guidance_method} if args.guidance_method else {}),
                    **({"maxChunkChars": args.max_chunk_chars} if args.max_chunk_chars is not None else {}),
                    **({"seed": args.seed} if args.seed is not None else {}),
                    **({"modelId": args.model} if getattr(args, "model", None) else {}),
                },
                ctx,
                api_key,
                timeout=TIMEOUTS["dh-submit"],
            )
            emit(_dh_result(parsed))
            return
        if op == "query":
            task_id = args.task_id
            if not task_id:
                raise VeError("--task-id 必填", code="TASK_ID_REQUIRED")
            output_path = ctx.output_dir / f"voice-{task_id[:8]}.wav"
            payload = {
                "taskId": task_id,
                **(
                    {"downloadResult": True, "outputPath": str(output_path)}
                    if getattr(args, "download", True)
                    else {"downloadResult": False}
                ),
            }
            if getattr(args, "wait", False):
                parsed = _poll_dh("voice_query", payload, ctx, api_key, args)
            else:
                parsed, _ = call(
                    "digital-human",
                    "voice_query",
                    payload,
                    ctx,
                    api_key,
                    timeout=TIMEOUTS["dh-query"],
                    raise_on_failure=False,
                )
            emit(_dh_result(parsed))
            return

    if kind == "lipsync":
        if op == "submit":
            parsed, _ = call(
                "digital-human",
                "lipsync_submit",
                {
                    "videoPath": prepare_media_input(args.video, ctx, "video"),
                    "audioPath": prepare_media_input(args.audio, ctx, "audio"),
                    **({"modelId": args.model} if getattr(args, "model", None) else {}),
                },
                ctx,
                api_key,
                timeout=TIMEOUTS["dh-submit"],
            )
            emit(_dh_result(parsed))
            return
        if op == "query":
            task_id = args.task_id
            if not task_id:
                raise VeError("--task-id 必填", code="TASK_ID_REQUIRED")
            output_path = ctx.output_dir / f"lipsync-{task_id[:8]}.mp4"
            payload = {
                "taskId": task_id,
                **(
                    {"downloadResult": True, "outputPath": str(output_path)}
                    if getattr(args, "download", True)
                    else {"downloadResult": False}
                ),
            }
            if getattr(args, "wait", False):
                parsed = _poll_dh("lipsync_query", payload, ctx, api_key, args)
            else:
                parsed, _ = call(
                    "digital-human",
                    "lipsync_query",
                    payload,
                    ctx,
                    api_key,
                    timeout=TIMEOUTS["dh-query"],
                    raise_on_failure=False,
                )
            emit(_dh_result(parsed))
            return

    raise VeError(f"未知的 dh 命令：{kind} {op}", code="UNKNOWN_ACTION")


def _poll_clone(avatar_id, ctx, api_key, args):
    deadline = time.time() + float(
        getattr(args, "wait_timeout", None) or getattr(args, "timeout", None) or 600
    )
    interval = float(getattr(args, "interval", None) or 10)
    last = {}
    while True:
        parsed, _ = call(
            "digital-human",
            "clone_query",
            {"avatarId": avatar_id},
            ctx,
            api_key,
            timeout=TIMEOUTS["dh-query"],
            raise_on_failure=False,
        )
        last = parsed or {}
        status = _status(
            pick(last, "status", "taskStatus", "task_status")
            or get_path(last, "avatar", "status")
        )
        if status in ("READY", "SUCCEEDED", "DONE", "FAILED", "ERROR"):
            return last
        if time.time() >= deadline:
            return last
        time.sleep(interval)


def _poll_dh(tool, payload, ctx, api_key, args):
    deadline = time.time() + float(
        getattr(args, "wait_timeout", None) or getattr(args, "timeout", None) or 600
    )
    interval = float(getattr(args, "interval", None) or 10)
    last = {}
    while True:
        parsed, _ = call(
            "digital-human",
            tool,
            payload,
            ctx,
            api_key,
            timeout=TIMEOUTS["dh-query"],
            raise_on_failure=False,
        )
        last = parsed or {}
        status = _status(pick(last, "status", "taskStatus", "task_status"))
        if status in ("SUCCEEDED", "DONE", "FAILED", "CANCELED", "CANCELLED", "ERROR"):
            return last
        if time.time() >= deadline:
            return last
        time.sleep(interval)


def _dh_result(parsed, local_path=None):
    parsed = parsed or {}
    return {
        "success": bool(pick(parsed, "success", default=True)),
        "task_id": pick(parsed, "task_id", "taskId", "id"),
        "avatar_id": pick(parsed, "avatarId", "avatar_id")
        or get_path(parsed, "avatar", "id"),
        "status": pick(parsed, "status", "taskStatus", "task_status"),
        "local_path": local_path
        or pick(parsed, "outputFilePath", "output_file_path", "local_path"),
        "result_url": pick(parsed, "resultUrl", "result_url"),
        "result_storage_path": pick(
            parsed, "resultStoragePath", "result_storage_path"
        )
        or get_path(parsed, "result", "path"),
        "avatar": parsed.get("avatar"),
        "error": sanitize_text(pick(parsed, "error", "message")),
        "raw": parsed,
    }


COMMANDS = {
    "env": cmd_env,
    "image": cmd_image,
    "audio": cmd_audio,
    "subtitle": cmd_subtitle,
    "video": cmd_video,
    "dh": cmd_dh,
    "files": cmd_files,
    "render": cmd_render,
}
