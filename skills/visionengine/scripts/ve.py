#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
ve.py —— VisionEngine CLI 入口。

用法：
    python ve.py <组> <命令> [参数]

所有平台能力通过平台 MCP（stdio）调用；CLI 自带零依赖 JSON-RPC 客户端。

环境变量：
    VEC_AI_API_KEY        VisionEngine API Key（唯一必须设置的变量）
    VEC_AI_API_URL        平台服务地址（默认 https://api.visionengine-tech.com）
    VEC_AI_RENDER_URL     Remotion 渲染服务（默认 https://veconline-ai-api.visionengine-tech.com）
    VEC_AI_OUTPUT_DIR     产物落盘目录（默认 ./ve-output）
    VEC_AI_FILE_MODE      remote / local（一般由 CLI 按环境自动选择）
"""

from __future__ import annotations

import argparse
import sys

from _mcp_client import close_all
from _ve_commands import COMMANDS
from _ve_util import VeError, fail, setup_stdout


def _common():
    parser = argparse.ArgumentParser(add_help=False)
    parser.add_argument(
        "--timeout", type=float, default=argparse.SUPPRESS, help="单次 MCP 调用超时秒数"
    )
    return parser


def _context_options():
    parser = argparse.ArgumentParser(add_help=False)
    parser.add_argument(
        "--usage-type",
        dest="usage_type",
        choices=["auto", "veconline", "skills", "standalone"],
        default="auto",
        help="运行环境；默认自动识别",
    )
    parser.add_argument("--system", choices=["veconline", "skills"], help="覆盖 system")
    parser.add_argument("--workspace-id", dest="workspace_id", help="VECONLINE 工作区 ID（conv-<uuid>）")
    parser.add_argument(
        "--artifact-identifier",
        dest="artifact_identifier",
        help="VECSKILL 当前技能标识符（默认取技能包目录名）",
    )
    parser.add_argument(
        "--round-timestamp",
        dest="round_timestamp",
        type=int,
        help="VECSKILL 本轮 10 位 Unix 秒（用户消息末尾 Timestamp: 后的数字）",
    )
    parser.add_argument("--workspace-root", dest="workspace_root", help="覆盖工作区根目录")
    return parser


def _add_output(parser):
    parser.add_argument("--out", "-o", help="产物落盘目录（默认 VEC_AI_OUTPUT_DIR 或 ./ve-output）")


def _add_wait(parser, default_off=True):
    if default_off:
        parser.add_argument("--wait", action="store_true", help="轮询到终态（默认只查一次）")
    else:
        parser.add_argument("--no-wait", dest="no_wait", action="store_true", help="不等待，立即返回")
    parser.add_argument("--interval", type=float, default=15.0, help="轮询间隔秒数（默认 15）")
    parser.add_argument(
        "--wait-timeout",
        dest="wait_timeout",
        type=float,
        default=None,
        help="轮询总预算秒数（默认由命令决定）",
    )


def _leaf(subparsers, name, *, help_text=None, parents=None):
    return subparsers.add_parser(
        name,
        parents=parents or [_common(), _context_options()],
        help=help_text or name,
    )


def build_parser():
    common = _common()
    ctx = _context_options()
    parser = argparse.ArgumentParser(
        prog="ve",
        description="VisionEngine CLI —— 图片/语音/字幕/视频/数字人/Remotion 渲染（MCP）",
        parents=[common],
    )
    groups = parser.add_subparsers(dest="group", required=True, metavar="<组>")

    # ---- env ----------------------------------------------------
    env = groups.add_parser("env", parents=[common, ctx], help="诊断运行环境、MCP 命令与凭据")
    env.add_argument("--probe", action="store_true", help="启动 render / file bridge 并列出工具")

    # ---- image --------------------------------------------------
    image = groups.add_parser("image", parents=[common], help="图片生成/编辑/识别/反推提示词")
    image_sub = image.add_subparsers(dest="action", required=True, metavar="<命令>")

    p = _leaf(image_sub, "generate", help_text="文生图")
    p.add_argument("--prompt", required=True)
    p.add_argument("--aspect-ratio", dest="aspect_ratio", default="9:16",
                   choices=["1:1", "2:3", "3:2", "3:4", "4:3", "4:5", "5:4", "9:16", "16:9", "21:9"])
    p.add_argument("--image-size", dest="image_size", default="1K", choices=["1K", "2K", "4K"])
    p.add_argument("--model")
    _add_output(p)

    p = _leaf(image_sub, "edit", help_text="图生图（单图）")
    p.add_argument("--prompt", required=True)
    p.add_argument("--image", action="append", required=True, help="输入图片（单张）")
    p.add_argument("--aspect-ratio", dest="aspect_ratio", default="9:16",
                   choices=["1:1", "2:3", "3:2", "3:4", "4:3", "4:5", "5:4", "9:16", "16:9", "21:9"])
    p.add_argument("--image-size", dest="image_size", default="1K", choices=["1K", "2K", "4K"])
    p.add_argument("--model")
    _add_output(p)

    p = _leaf(image_sub, "edit-advanced", help_text="进阶图片编辑（1-3 张）")
    p.add_argument("--prompt", required=True, help="编辑指令，1-800 字符")
    p.add_argument("--image", action="append", required=True, help="输入图片，1-3 张")
    p.add_argument("--n", type=int, default=1, help="生成张数 1-6（默认 1）")
    p.add_argument("--negative-prompt", dest="negative_prompt")
    p.add_argument("--size", help="输出尺寸 WIDTH*HEIGHT，如 1024*1024")
    p.add_argument("--seed", type=int)
    p.add_argument("--no-prompt-extend", dest="prompt_extend", action="store_false")
    p.add_argument("--watermark", action="store_true")
    p.add_argument("--model")
    _add_output(p)

    p = _leaf(image_sub, "generate-from-images", help_text="以参考图生成新图")
    p.add_argument("--prompt", required=True)
    p.add_argument("--image", action="append", required=True, help="参考图片，可重复")
    p.add_argument("--aspect-ratio", dest="aspect_ratio", default="9:16",
                   choices=["1:1", "2:3", "3:2", "3:4", "4:3", "4:5", "5:4", "9:16", "16:9", "21:9"])
    p.add_argument("--image-size", dest="image_size", default="1K", choices=["1K", "2K", "4K"])
    p.add_argument("--model")
    _add_output(p)

    p = _leaf(image_sub, "recognize", help_text="图片识别（视觉分析 / 文字提取）")
    p.add_argument("--image", required=True)
    p.add_argument("--tool", required=True, choices=["visual", "text"])
    p.add_argument("--prompt")
    p.add_argument("--model")

    p = _leaf(image_sub, "prompt-reverse", help_text="反推图片生成提示词")
    p.add_argument("--image", required=True)
    p.add_argument("--output-language", dest="output_language", default="en", choices=["zh", "en"])
    p.add_argument("--user-prompt", dest="user_prompt")
    p.add_argument("--model")

    # ---- audio --------------------------------------------------
    audio = groups.add_parser("audio", parents=[common], help="语音合成与音色查询")
    audio_sub = audio.add_subparsers(dest="action", required=True, metavar="<命令>")

    p = _leaf(audio_sub, "tts", help_text="文本转语音")
    p.add_argument("--text", required=True)
    p.add_argument("--speaker", default="zh_female_vv_uranus_bigtts")
    p.add_argument("--format", default="mp3", choices=["mp3", "ogg_opus", "pcm"])
    p.add_argument("--sample-rate", dest="sample_rate", type=int, default=24000,
                   choices=[8000, 16000, 22050, 24000, 32000, 44100, 48000])
    p.add_argument("--speech-rate", dest="speech_rate", type=int)
    p.add_argument("--loudness-rate", dest="loudness_rate", type=int)
    p.add_argument("--emotion")
    p.add_argument("--emotion-scale", dest="emotion_scale", type=int)
    p.add_argument("--pitch", type=int)
    p.add_argument("--explicit-language", dest="explicit_language",
                   choices=["zh-cn", "en", "ja", "es-mx", "id", "pt-br", "de", "fr", "crosslingual"])
    p.add_argument("--context-text", dest="context_text", action="append")
    p.add_argument("--disable-markdown-filter", dest="disable_markdown_filter", action="store_true")
    p.add_argument("--model")
    _add_output(p)

    p = _leaf(audio_sub, "voices", help_text="列出可用音色")
    p.add_argument("--language")
    p.add_argument("--gender", choices=["male", "female"])
    p.add_argument("--offline", action="store_true", help="只读随包音色目录")

    # ---- subtitle -----------------------------------------------
    subtitle = groups.add_parser("subtitle", parents=[common], help="字幕生成与强制对齐")
    subtitle_sub = subtitle.add_subparsers(dest="action", required=True, metavar="<命令>")

    p = _leaf(subtitle_sub, "generate", help_text="语音识别生成字幕")
    p.add_argument("--audio", required=True)
    p.add_argument("--language")
    p.add_argument("--words-per-line", dest="words_per_line", type=int)
    p.add_argument("--max-lines", dest="max_lines", type=int)
    p.add_argument("--use-itn", dest="use_itn", action="store_true")
    p.add_argument("--caption-type", dest="caption_type", default="auto", choices=["auto", "speech", "singing"])
    p.add_argument("--use-punc", dest="use_punc", action="store_true")
    p.add_argument("--use-ddc", dest="use_ddc", action="store_true")
    p.add_argument("--with-speaker-info", dest="with_speaker_info", action="store_true")
    p.add_argument("--model")
    _add_output(p)
    _add_wait(p, default_off=False)

    p = _leaf(subtitle_sub, "align", help_text="把已知文本与音频强制对齐")
    p.add_argument("--audio", required=True)
    p.add_argument("--text")
    p.add_argument("--text-file", dest="text_file")
    p.add_argument("--caption-type", dest="caption_type", required=True, choices=["speech", "singing"])
    p.add_argument("--sta-punc-mode", dest="sta_punc_mode", choices=["1", "2", "3"])
    p.add_argument("--model")
    _add_output(p)
    _add_wait(p, default_off=False)

    # ---- video --------------------------------------------------
    video = groups.add_parser("video", parents=[common], help="图生视频/文生视频/风格重绘/视频理解")
    video_sub = video.add_subparsers(dest="action", required=True, metavar="<能力>")

    p = _video_ops(video_sub, "img2video", "图片生成视频")
    submit = p._ve_submit
    submit.add_argument("--image", required=True)
    submit.add_argument("--prompt")
    submit.add_argument("--negative-prompt", dest="negative_prompt")
    submit.add_argument("--audio-input", dest="audio_input")
    submit.add_argument("--duration", type=int)
    submit.add_argument("--resolution", choices=["720P", "1080P"])
    submit.add_argument("--audio", action="store_true")
    submit.add_argument("--shot-type", dest="shot_type", choices=["single", "multi"])
    submit.add_argument("--no-prompt-extend", dest="prompt_extend", action="store_false")
    submit.add_argument("--watermark", action="store_true")
    submit.add_argument("--seed", type=int)
    submit.add_argument("--model")

    p = _video_ops(video_sub, "text2video", "文本生成视频")
    submit = p._ve_submit
    submit.add_argument("--prompt", required=True)
    submit.add_argument("--negative-prompt", dest="negative_prompt")
    submit.add_argument("--audio-input", dest="audio_input")
    submit.add_argument("--size")
    submit.add_argument("--duration", type=int)
    submit.add_argument("--shot-type", dest="shot_type", choices=["single", "multi"])
    submit.add_argument("--no-prompt-extend", dest="prompt_extend", action="store_false")
    submit.add_argument("--watermark", action="store_true")
    submit.add_argument("--seed", type=int)
    submit.add_argument("--model")

    p = _video_ops(video_sub, "style-transfer", "视频风格重绘")
    submit = p._ve_submit
    submit.add_argument("--video", required=True)
    submit.add_argument("--style", type=int, choices=range(0, 8), metavar="{0-7}")
    submit.add_argument("--fps", type=int)
    submit.add_argument("--min-len", dest="min_len", type=int, choices=[540, 720])
    submit.add_argument("--no-animate-emotion", dest="animate_emotion", action="store_false")
    submit.add_argument("--use-sr", dest="use_sr", action="store_true")
    submit.add_argument("--model")

    p = _video_ops(video_sub, "recognize", "视频理解", recognize=True)
    submit = p._ve_submit
    submit.add_argument("--video", required=True)
    submit.add_argument("--task-type", dest="task_type", default="understand",
                        choices=["understand", "cut_effect_points", "emotion_analysis", "script_generate", "style_analyze"])
    submit.add_argument("--prompt-mode", dest="prompt_mode", default="template", choices=["template", "auto"])
    submit.add_argument("--prompt")
    submit.add_argument("--start-sec", dest="start_sec", type=float)
    submit.add_argument("--end-sec", dest="end_sec", type=float)
    submit.add_argument("--model")
    submit.add_argument("--no-wait", dest="no_wait", action="store_true", help="只提交，不等待结果")

    # ---- dh -----------------------------------------------------
    dh = groups.add_parser("dh", parents=[common], help="音色克隆 / 语音合成 / 对口型")
    dh_sub = dh.add_subparsers(dest="action", required=True, metavar="<能力>")

    p = _dh_ops(dh_sub, "clone", "克隆音色")
    submit = p._ve_submit
    submit.add_argument("--video", required=True)
    submit.add_argument("--name")

    p = _dh_ops(dh_sub, "voice", "用克隆音色合成语音")
    submit = p._ve_submit
    submit.add_argument("--text", required=True)
    submit.add_argument("--avatar-id", dest="avatar_id")
    submit.add_argument("--prompt-audio-url", dest="prompt_audio_url")
    submit.add_argument("--prompt-text", dest="prompt_text")
    submit.add_argument("--nfe", type=int)
    submit.add_argument("--guidance-strength", dest="guidance_strength", type=float)
    submit.add_argument("--guidance-method", dest="guidance_method", choices=["cfg", "apg"])
    submit.add_argument("--max-chunk-chars", dest="max_chunk_chars", type=int)
    submit.add_argument("--seed", type=int)
    submit.add_argument("--model")

    p = _dh_ops(dh_sub, "lipsync", "数字人对口型")
    submit = p._ve_submit
    submit.add_argument("--video", required=True)
    submit.add_argument("--audio", required=True)
    submit.add_argument("--model")

    # ---- files --------------------------------------------------
    files = groups.add_parser("files", parents=[common], help="Remotion 工作区文件（VECONLINE 本地）")
    files_sub = files.add_subparsers(dest="action", required=True, metavar="<命令>")

    _leaf(files_sub, "workspaces", help_text="列出工作区与配额")
    _leaf(files_sub, "quota", help_text="查看工作区配额")

    p = _leaf(files_sub, "create", help_text="创建工作区")
    p.add_argument("--name", required=True)
    p.add_argument("--description")
    p.add_argument("--template", help="empty 或 copy:<workspaceId>")
    p.add_argument("--local-dir", dest="local_dir")

    p = _leaf(files_sub, "get", help_text="查看工作区状态")

    p = _leaf(files_sub, "rename", help_text="重命名工作区")
    p.add_argument("--name", required=True)

    p = _leaf(files_sub, "install", help_text="安装工作区依赖")

    p = _leaf(files_sub, "upload-project", help_text="上传整个本地工程并安装依赖")
    p.add_argument("--local-dir", dest="local_dir")
    p.add_argument("--no-install", dest="no_install", action="store_true")

    p = _leaf(files_sub, "list", help_text="列出工作区文件")
    p.add_argument("--path", default=".")
    p.add_argument("--max-depth", dest="max_depth", type=int)
    p.add_argument("--limit", type=int)
    p.add_argument("--include-hidden", dest="include_hidden", action="store_true")
    p.add_argument("--include-content", dest="include_content", action="store_true")
    p.add_argument("--mode")
    p.add_argument("--recursive", action="store_true")

    p = _leaf(files_sub, "read", help_text="读取工作区文本文件")
    p.add_argument("--path", required=True)

    p = _leaf(files_sub, "upload", help_text="上传本地文件或抓取 URL")
    p.add_argument("path", nargs="?")
    p.add_argument("--source", choices=["local", "url"], default="local")
    p.add_argument("--url")
    p.add_argument("--target-path", dest="target_path")
    p.add_argument("--file-name", dest="file_name")

    p = _leaf(files_sub, "save", help_text="写入文本/base64/local_path/remote_url")
    p.add_argument("--source-type", dest="source_type", required=True,
                   choices=["text", "base64", "local_path", "remote_url"])
    p.add_argument("--content")
    p.add_argument("--content-file", dest="content_file")
    p.add_argument("--local-path", dest="local_path")
    p.add_argument("--file-name", dest="file_name", required=True)
    p.add_argument("--target-path", dest="target_path")
    p.add_argument("--content-type", dest="content_type")
    p.add_argument("--overwrite", action="store_true")

    p = _leaf(files_sub, "download", help_text="下载工作区文件")
    p.add_argument("--path", required=True)
    _add_output(p)

    p = _leaf(files_sub, "delete", help_text="删除工作区文件")
    p.add_argument("--path", required=True)

    # ---- render -------------------------------------------------
    render = groups.add_parser("render", parents=[common], help="Remotion 云端渲染")
    render_sub = render.add_subparsers(dest="action", required=True, metavar="<命令>")

    _leaf(render_sub, "context", help_text="诊断本地/VECONLINE/VECSKILL 运行环境")

    p = _leaf(render_sub, "detect", help_text="检测可渲染的 Remotion 工程")
    p.add_argument("--workspace-path", dest="workspace_path")

    p = _leaf(render_sub, "submit", help_text="提交渲染任务")
    p.add_argument("--composition-id", dest="composition_id")
    p.add_argument("--input-props", dest="input_props")
    p.add_argument("--export-type", dest="export_type")
    p.add_argument("--codec")
    p.add_argument("--audio-codec", dest="audio_codec")
    p.add_argument("--image-format", dest="image_format")
    p.add_argument("--out-name", dest="out_name")
    p.add_argument("--output-path", dest="output_path")
    p.add_argument("--entry-point", dest="entry_point")
    p.add_argument("--start-frame", dest="start_frame", type=int)
    p.add_argument("--end-frame", dest="end_frame", type=int)
    p.add_argument("--every-nth-frame", dest="every_nth_frame", type=int)
    p.add_argument("--frame", type=int)
    p.add_argument("--workspace-path", dest="workspace_path")
    p.add_argument("--image-sequence", dest="image_sequence", action="store_true")
    p.add_argument("--studio-sid", dest="studio_sid", help="(已弃用) 等价 --workspace-id")

    p = _leaf(render_sub, "query", help_text="查询渲染任务")
    p.add_argument("--task-id", dest="task_id", required=True)
    _add_wait(p)
    _add_output(p)

    p = _leaf(render_sub, "wait", help_text="等待渲染任务完成")
    p.add_argument("--task-id", dest="task_id", required=True)
    p.add_argument("--wait-timeout", dest="wait_timeout", type=float, default=600)
    p.add_argument("--interval", type=float, default=5)

    p = _leaf(render_sub, "list", help_text="列出渲染任务")
    p.add_argument("--limit", type=int, default=20)

    p = _leaf(render_sub, "cancel", help_text="取消渲染任务")
    p.add_argument("--task-id", dest="task_id", required=True)

    p = _leaf(render_sub, "retry", help_text="重试渲染任务")
    p.add_argument("--task-id", dest="task_id", required=True)

    p = _leaf(render_sub, "download", help_text="下载渲染产物")
    p.add_argument("--task-id", dest="task_id", required=True)
    _add_output(p)

    p = _leaf(render_sub, "run", help_text="一把梭：detect → submit → wait → 落地")
    p.add_argument("--composition-id", dest="composition_id")
    p.add_argument("--workspace-name", dest="workspace_name")
    p.add_argument("--upload", action="store_true", help="standalone：创建/上传本地工程")
    p.add_argument("--local-dir", dest="local_dir")
    p.add_argument("--no-install", dest="no_install", action="store_true")
    p.add_argument("--workspace-path", dest="workspace_path")
    p.add_argument("--input-props", dest="input_props")
    p.add_argument("--export-type", dest="export_type")
    p.add_argument("--codec")
    p.add_argument("--audio-codec", dest="audio_codec")
    p.add_argument("--image-format", dest="image_format")
    p.add_argument("--out-name", dest="out_name")
    p.add_argument("--output-path", dest="output_path")
    p.add_argument("--entry-point", dest="entry_point")
    p.add_argument("--start-frame", dest="start_frame", type=int)
    p.add_argument("--end-frame", dest="end_frame", type=int)
    p.add_argument("--every-nth-frame", dest="every_nth_frame", type=int)
    p.add_argument("--frame", type=int)
    p.add_argument("--image-sequence", dest="image_sequence", action="store_true")
    p.add_argument("--wait-timeout", dest="wait_timeout", type=float, default=900)
    p.add_argument("--interval", type=float, default=5)
    _add_output(p)

    return parser


def _video_ops(subparsers, name, help_text, recognize=False):
    parser = _leaf(subparsers, name, help_text=help_text)
    ops = parser.add_subparsers(dest="op", required=True, metavar="<操作>")
    submit = _leaf(ops, "submit", help_text="提交任务")
    parser._ve_submit = submit
    query = _leaf(ops, "query", help_text="查询任务")
    query.add_argument("--task-id", dest="task_id", required=True)
    _add_wait(query)
    query.add_argument("--download", dest="download", action="store_true", default=True)
    query.add_argument("--no-download", dest="download", action="store_false")
    _add_output(query)
    if recognize:
        result = _leaf(ops, "result", help_text="取回任务结果")
        result.add_argument("--task-id", dest="task_id", required=True)
        cancel = _leaf(ops, "cancel", help_text="取消任务")
        cancel.add_argument("--task-id", dest="task_id", required=True)
    return parser


def _dh_ops(subparsers, name, help_text):
    parser = _leaf(subparsers, name, help_text=help_text)
    ops = parser.add_subparsers(dest="op", required=True, metavar="<操作>")
    submit = _leaf(ops, "submit", help_text="提交任务")
    parser._ve_submit = submit
    query = _leaf(ops, "query", help_text="查询任务")
    query.add_argument("--task-id", dest="task_id")
    query.add_argument("--avatar-id", dest="avatar_id")
    _add_wait(query)
    query.add_argument("--download", dest="download", action="store_true", default=True)
    query.add_argument("--no-download", dest="download", action="store_false")
    _add_output(query)
    return parser


def main(argv=None):
    setup_stdout()
    parser = build_parser()
    args = parser.parse_args(argv)
    if getattr(args, "studio_sid", None) and not getattr(args, "workspace_id", None):
        args.workspace_id = args.studio_sid
    handler = COMMANDS.get(args.group)
    if handler is None:
        fail(f"未知命令组：{args.group}", code="UNKNOWN_GROUP")
    try:
        handler(args)
    except VeError as exc:
        fail(exc.message, code=exc.code, **exc.extra)
    except KeyboardInterrupt:
        fail("已中断", code="INTERRUPTED")
    finally:
        close_all()
    return 0


if __name__ == "__main__":
    sys.exit(main())
