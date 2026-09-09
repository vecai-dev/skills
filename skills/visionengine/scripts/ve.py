#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
ve.py —— VisionEngine CLI 入口。

用法：
    python ve.py <组> <命令> [参数]

环境变量：
    VISION_ENGINE_API_KEY        Bearer API Key（唯一必须设置的变量）
    VISION_ENGINE_API_ENDPOINT   平台服务地址（默认官方地址）
    VISION_ENGINE_RENDER_ENDPOINT Remotion 渲染服务（默认官方地址）
    VISION_ENGINE_WORKDIR        相对路径基准目录（默认当前目录）
    VISION_ENGINE_OUTPUT_DIR     产物落盘目录（默认 ./ve-output）
    VISION_ENGINE_FILE_MODE      remote（默认，自动上传）或 local（共享挂载）
    VISION_ENGINE_REMOTION_WORK_DIR  local 模式的共享挂载根（默认 /vec）

本目录下只有 ve.py 是入口，其余模块以下划线开头，供导入使用。
"""

from __future__ import annotations

import argparse
import sys

sys.path.insert(0, str(__import__("pathlib").Path(__file__).resolve().parent))

import _ve_commands as C  # noqa: E402
from _ve_client import DEFAULT_TIMEOUT, VeError, fail, setup_stdout  # noqa: E402


def _common():
    # SUPPRESS 让子命令未显式给出时不覆盖顶层同名参数（argparse 子解析器默认值会覆盖父命名空间）
    parser = argparse.ArgumentParser(add_help=False)
    parser.add_argument("--timeout", type=float, default=argparse.SUPPRESS, help="单次请求超时秒数（默认 60）")
    return parser


def _add_output(parser):
    parser.add_argument("--out", "-o", help="产物落盘目录（默认 VISION_ENGINE_OUTPUT_DIR）")


def _add_wait(parser, default_off=True):
    if default_off:
        parser.add_argument("--wait", action="store_true", help="轮询到终态（默认只查一次）")
    else:
        parser.add_argument("--no-wait", dest="no_wait", action="store_true", help="提交后立即返回，不等待结果")
    parser.add_argument("--interval", type=float, default=15.0, help="轮询间隔秒数（默认 15）")


def build_parser():
    common = _common()
    parser = argparse.ArgumentParser(
        prog="ve",
        description="VisionEngine CLI —— 图片/语音/字幕/视频/数字人/文件/Remotion 渲染能力",
        parents=[common],
    )
    groups = parser.add_subparsers(dest="group", required=True, metavar="<组>")

    # ---- env ----------------------------------------------------
    groups.add_parser("env", parents=[common], help="诊断环境变量与鉴权（GET /api/v1/auth/me）")

    # ---- api ----------------------------------------------------
    api = groups.add_parser("api", parents=[common], help="任意白名单端点透传")
    api.add_argument("method", help="HTTP 方法，如 GET/POST/DELETE")
    api.add_argument("path", help="以 / 开头的路径，如 /api/v1/files/list")
    api.add_argument("--data", help="JSON 请求体字符串")
    api.add_argument("--data-file", dest="data_file", help="从文件读取 JSON 请求体")
    api.add_argument("--query", action="append", metavar="K=V", help="查询参数，可重复")
    api.add_argument("--raw", action="store_true", help="原样输出响应文本")

    # ---- image --------------------------------------------------
    image = groups.add_parser("image", parents=[common], help="图片生成/编辑/识别/反推提示词")
    image_sub = image.add_subparsers(dest="action", required=True, metavar="<命令>")

    p = image_sub.add_parser("generate", parents=[common], help="文生图")
    p.add_argument("--prompt", required=True)
    p.add_argument("--aspect-ratio", dest="aspect_ratio", default="9:16",
                   choices=["1:1", "2:3", "3:2", "3:4", "4:3", "4:5", "5:4", "9:16", "16:9", "21:9"])
    p.add_argument("--image-size", dest="image_size", default="1K", choices=["1K", "2K", "4K"])
    p.add_argument("--model")
    _add_output(p)

    p = image_sub.add_parser("edit", parents=[common], help="图生图（image-generate 的 edit）")
    p.add_argument("--prompt", required=True)
    p.add_argument("--image", action="append", required=True, help="输入图片（本地路径/URL），可重复")
    p.add_argument("--aspect-ratio", dest="aspect_ratio", default="9:16",
                   choices=["1:1", "2:3", "3:2", "3:4", "4:3", "4:5", "5:4", "9:16", "16:9", "21:9"])
    p.add_argument("--image-size", dest="image_size", default="1K", choices=["1K", "2K", "4K"])
    p.add_argument("--model")
    _add_output(p)

    p = image_sub.add_parser("edit-advanced", parents=[common], help="进阶图片编辑（image-edit/edit）")
    p.add_argument("--prompt", required=True, help="编辑指令，1-800 字符")
    p.add_argument("--image", action="append", required=True, help="输入图片，1-3 张")
    p.add_argument("--n", type=int, default=1, help="生成张数 1-6（默认 1）")
    p.add_argument("--negative-prompt", dest="negative_prompt", help="负向提示词，≤500 字符")
    p.add_argument("--size", help="输出尺寸 WIDTH*HEIGHT，如 1024*1024")
    p.add_argument("--seed", type=int)
    p.add_argument("--no-prompt-extend", dest="prompt_extend", action="store_false", help="关闭提示词自动扩写")
    p.add_argument("--watermark", action="store_true", help="添加水印")
    p.add_argument("--model")
    _add_output(p)

    p = image_sub.add_parser("generate-from-images", parents=[common], help="以参考图生成新图")
    p.add_argument("--prompt", required=True)
    p.add_argument("--image", action="append", required=True, help="参考图片，可重复")
    p.add_argument("--aspect-ratio", dest="aspect_ratio", default="9:16",
                   choices=["1:1", "2:3", "3:2", "3:4", "4:3", "4:5", "5:4", "9:16", "16:9", "21:9"])
    p.add_argument("--image-size", dest="image_size", default="1K", choices=["1K", "2K", "4K"])
    p.add_argument("--model")
    _add_output(p)

    p = image_sub.add_parser("recognize", parents=[common], help="图片识别（视觉分析 / 文字提取）")
    p.add_argument("--image", required=True)
    p.add_argument("--tool", required=True, choices=["visual", "text"], help="visual=设计元素分析，text=OCR/数据提取")
    p.add_argument("--prompt", help="自定义提示词（缺省用内置默认提示词）")
    p.add_argument("--model")

    p = image_sub.add_parser("prompt-reverse", parents=[common], help="反推图片的生成提示词")
    p.add_argument("--image", required=True)
    p.add_argument("--output-language", dest="output_language", default="en", choices=["zh", "en"])
    p.add_argument("--user-prompt", dest="user_prompt", help="可选的自定义指令")
    p.add_argument("--model")

    # ---- audio --------------------------------------------------
    audio = groups.add_parser("audio", parents=[common], help="语音合成与音色查询")
    audio_sub = audio.add_subparsers(dest="action", required=True, metavar="<命令>")

    p = audio_sub.add_parser("tts", parents=[common], help="文本转语音")
    p.add_argument("--text", required=True, help="待合成文本")
    p.add_argument("--speaker", default="zh_female_vv_uranus_bigtts", help="音色 ID，见 audio voices")
    p.add_argument("--format", default="mp3", choices=["mp3", "ogg_opus", "pcm"])
    p.add_argument("--sample-rate", dest="sample_rate", type=int, default=24000,
                   choices=[8000, 16000, 22050, 24000, 32000, 44100, 48000])
    p.add_argument("--speech-rate", dest="speech_rate", type=int, help="语速 -50~100（默认 0）")
    p.add_argument("--loudness-rate", dest="loudness_rate", type=int, help="音量 -50~100（默认 0）")
    p.add_argument("--emotion", help="情感，如 happy/sad/angry")
    p.add_argument("--emotion-scale", dest="emotion_scale", type=int, help="情感强度 1~5（默认 4）")
    p.add_argument("--pitch", type=int, help="音调 -12~12（默认 0）")
    p.add_argument("--explicit-language", dest="explicit_language",
                   choices=["zh-cn", "en", "ja", "es-mx", "id", "pt-br", "de", "fr", "crosslingual"])
    p.add_argument("--context-text", dest="context_text", action="append", help="上下文文本，可重复")
    p.add_argument("--disable-markdown-filter", dest="disable_markdown_filter", action="store_true")
    p.add_argument("--model")
    _add_output(p)

    p = audio_sub.add_parser("voices", parents=[common], help="列出可用音色（本地目录，不联网）")
    p.add_argument("--language", help="按语言过滤，如 zh-cn")
    p.add_argument("--gender", choices=["male", "female"], help="按性别过滤")

    # ---- subtitle -----------------------------------------------
    subtitle = groups.add_parser("subtitle", parents=[common], help="字幕生成与强制对齐")
    subtitle_sub = subtitle.add_subparsers(dest="action", required=True, metavar="<命令>")

    p = subtitle_sub.add_parser("generate", parents=[common], help="语音识别生成字幕")
    p.add_argument("--audio", required=True, help="本地音视频文件或公网 URL")
    p.add_argument("--language", help="如 zh-CN / en-US / ja-JP / ko-KR")
    p.add_argument("--words-per-line", dest="words_per_line", type=int, help="每行字数（默认 46；中文建议 15，英文 55）")
    p.add_argument("--max-lines", dest="max_lines", type=int, help="最大行数（默认 1）")
    p.add_argument("--use-itn", dest="use_itn", action="store_true", help="中文数字转阿拉伯数字")
    p.add_argument("--caption-type", dest="caption_type", default="auto", choices=["auto", "speech", "singing"])
    p.add_argument("--use-punc", dest="use_punc", action="store_true", help="加标点（仅 caption-type=speech 生效）")
    p.add_argument("--use-ddc", dest="use_ddc", action="store_true", help="静音标注")
    p.add_argument("--with-speaker-info", dest="with_speaker_info", action="store_true")
    p.add_argument("--model")
    _add_output(p)
    _add_wait(p, default_off=False)

    p = subtitle_sub.add_parser("align", parents=[common], help="把已知文本与音频强制对齐")
    p.add_argument("--audio", required=True, help="本地音视频文件或公网 URL")
    p.add_argument("--text", help="要对齐的文本（长文本请用 --text-file）")
    p.add_argument("--text-file", dest="text_file", help="从文件读取对齐文本")
    p.add_argument("--caption-type", dest="caption_type", required=True, choices=["speech", "singing"])
    p.add_argument("--sta-punc-mode", dest="sta_punc_mode", choices=["1", "2", "3"],
                   help="1=去句尾标点 2=替换为空格 3=保留原标点")
    p.add_argument("--model")
    _add_output(p)
    _add_wait(p, default_off=False)

    # ---- video --------------------------------------------------
    video = groups.add_parser("video", parents=[common], help="图生视频/文生视频/风格重绘/视频理解")
    video_sub = video.add_subparsers(dest="action", required=True, metavar="<能力>")

    p = video_sub.add_parser("img2video", parents=[common], help="图片生成视频")
    _video_ops(p, recognize=False)
    p_submit = p._ve_submit
    p_submit.add_argument("--image", required=True, help="输入图片（本地路径/URL）；JPEG/PNG/BMP/WEBP，≤10MB，边长 240-8000px")
    p_submit.add_argument("--prompt", help="动作/镜头提示词")
    p_submit.add_argument("--negative-prompt", dest="negative_prompt")
    p_submit.add_argument("--duration", type=int, help="时长秒 2-15（默认 5）")
    p_submit.add_argument("--resolution", choices=["720P", "1080P"], help="默认 720P")
    p_submit.add_argument("--audio", action="store_true", help="让模型生成音频")
    p_submit.add_argument("--audio-input", dest="audio_input", help="驱动音频文件/URL（mp3/wav，3-30 秒，≤15MB）")
    p_submit.add_argument("--shot-type", dest="shot_type", choices=["single", "multi"])
    p_submit.add_argument("--no-prompt-extend", dest="prompt_extend", action="store_false")
    p_submit.add_argument("--watermark", action="store_true")
    p_submit.add_argument("--seed", type=int)
    p_submit.add_argument("--model")
    p_submit.add_argument("--upload", action="store_true", help="强制上传本地文件（FILE_MODE=local 时）")

    p = video_sub.add_parser("text2video", parents=[common], help="文本生成视频")
    _video_ops(p, recognize=False)
    p_submit = p._ve_submit
    p_submit.add_argument("--prompt", required=True, help="提示词，≤1500 字符")
    p_submit.add_argument("--negative-prompt", dest="negative_prompt", help="≤500 字符")
    p_submit.add_argument("--size", help="默认 1280*720，可选 720*1280 / 960*960 / 1088*832 / 832*1088 / 1920*1080 / 1080*1920 / 1440*1440 / 1632*1248 / 1248*1632")
    p_submit.add_argument("--duration", type=int, help="时长秒 2-15（默认 5）")
    p_submit.add_argument("--audio-input", dest="audio_input", help="驱动音频文件/URL（mp3/wav，3-30 秒，≤15MB）")
    p_submit.add_argument("--shot-type", dest="shot_type", choices=["single", "multi"])
    p_submit.add_argument("--no-prompt-extend", dest="prompt_extend", action="store_false")
    p_submit.add_argument("--watermark", action="store_true")
    p_submit.add_argument("--seed", type=int)
    p_submit.add_argument("--model")

    p = video_sub.add_parser("style-transfer", parents=[common], help="视频风格重绘")
    _video_ops(p, recognize=False)
    p_submit = p._ve_submit
    p_submit.add_argument("--video", required=True, help="输入视频（本地路径/URL）；≤30 秒、≤100MB、边长 256-4096px")
    p_submit.add_argument("--style", type=int, choices=range(0, 8), metavar="{0-7}",
                          help="0 日式漫画 1 美式漫画 2 清新漫画 3 3D卡通 4 国风卡通 5 纸艺 6 简易插画 7 国风水墨")
    p_submit.add_argument("--fps", type=int, help="帧率 15-25（默认 15）")
    p_submit.add_argument("--min-len", dest="min_len", type=int, choices=[540, 720], help="最短边（默认 720）")
    p_submit.add_argument("--no-animate-emotion", dest="animate_emotion", action="store_false")
    p_submit.add_argument("--use-sr", dest="use_sr", action="store_true", help="启用超分")
    p_submit.add_argument("--model")
    p_submit.add_argument("--upload", action="store_true", help="强制上传本地文件")

    p = video_sub.add_parser("recognize", parents=[common], help="视频理解（submit 为同步阻塞调用，可能耗时数分钟）")
    _video_ops(p, recognize=True)
    p_submit = p._ve_submit
    p_submit.add_argument("--video", required=True, help="输入视频（本地路径/公网 URL）")
    p_submit.add_argument("--task-type", dest="task_type", default="understand",
                          choices=["understand", "cut_effect_points", "emotion_analysis", "script_generate", "style_analyze"],
                          help="分析类型（默认 understand）")
    p_submit.add_argument("--prompt-mode", dest="prompt_mode", default="template", choices=["template", "auto"],
                          help="auto 时必须提供 --prompt")
    p_submit.add_argument("--prompt", help="自定义分析指令（prompt-mode=auto 时必填）")
    p_submit.add_argument("--start-sec", dest="start_sec", type=float, help="分析区间起点（秒）")
    p_submit.add_argument("--end-sec", dest="end_sec", type=float, help="分析区间终点（秒）")
    p_submit.add_argument("--model")
    p_submit.add_argument("--upload", action="store_true", help="强制上传本地文件")

    # ---- dh（数字人）---------------------------------------------
    dh = groups.add_parser("dh", parents=[common], help="音色克隆 / 语音合成 / 对口型")
    dh_sub = dh.add_subparsers(dest="action", required=True, metavar="<能力>")

    p = dh_sub.add_parser("clone", parents=[common], help="克隆音色（免费，仅需 8-25 秒说话视频）")
    _dh_ops(p)
    p_submit = p._ve_submit
    p_submit.add_argument("--video", required=True, help="说话视频（本地路径/URL/存储路径），8-25 秒、≤200MB")
    p_submit.add_argument("--name", help="克隆名称，≤50 字符")

    p = dh_sub.add_parser("voice", parents=[common], help="用克隆音色合成语音（按字数计费）")
    _dh_ops(p)
    p_submit = p._ve_submit
    p_submit.add_argument("--text", required=True, help="待合成文本，≤3000 字符")
    p_submit.add_argument("--avatar-id", dest="avatar_id",
                          help="克隆 ID：自动补全参考音频与逐字稿（来自 dh clone）")
    p_submit.add_argument("--prompt-audio-url", dest="prompt_audio_url",
                          help="参考音频（本地路径或 https URL）；给了 --avatar-id 可省略")
    p_submit.add_argument("--prompt-text", dest="prompt_text",
                          help="参考音频逐字稿；给了 --avatar-id 可省略")
    p_submit.add_argument("--nfe", type=int, help="扩散步数 4-64")
    p_submit.add_argument("--guidance-strength", dest="guidance_strength", type=float, help="引导强度 0-20")
    p_submit.add_argument("--guidance-method", dest="guidance_method", choices=["cfg", "apg"])
    p_submit.add_argument("--max-chunk-chars", dest="max_chunk_chars", type=int, help="分块字数 40-120")
    p_submit.add_argument("--seed", type=int)
    p_submit.add_argument("--model")

    p = dh_sub.add_parser("lipsync", parents=[common], help="数字人对口型（预扣 500 积分，按输出秒结算）")
    _dh_ops(p)
    p_submit = p._ve_submit
    p_submit.add_argument("--video", required=True, help="数字人视频（本地路径/URL/存储路径）")
    p_submit.add_argument("--audio", required=True, help="驱动音频（本地路径/URL/存储路径）")
    p_submit.add_argument("--model")
    p_submit.add_argument("--upload", action="store_true", help="强制上传本地文件")

    # ---- files --------------------------------------------------
    files = groups.add_parser("files", parents=[common], help="Remotion 工作区文件操作")
    files_sub = files.add_subparsers(dest="action", required=True, metavar="<命令>")

    p = files_sub.add_parser("list", parents=[common], help="列出工作区文件")
    p.add_argument("--path", default=".", help="相对工作区根的路径（默认 .）")
    p.add_argument("--max-depth", dest="max_depth", type=int, help="递归深度")
    p.add_argument("--limit", type=int, help="返回条数上限")
    p.add_argument("--include-hidden", dest="include_hidden", action="store_true", help="包含隐藏文件")
    p.add_argument("--include-content", dest="include_content", action="store_true", help="附带文件内容")
    p.add_argument("--mode", help="过滤模式，如 file")

    p = files_sub.add_parser("read", parents=[common], help="读取工作区文本文件")
    p.add_argument("--path", required=True)

    p = files_sub.add_parser("upload", parents=[common], help="上传本地文件，或把 URL 抓取进工作区")
    p.add_argument("path", nargs="?", help="本地文件路径")
    p.add_argument("--source", choices=["local", "url"], default="local")
    p.add_argument("--url", help="--source url 时待抓取的 http(s) 地址")
    p.add_argument("--target-path", dest="target_path",
                   help="工作区目标目录，如 public/images、src（.tsx/.ts 必须显式指定 src）")
    p.add_argument("--file-name", dest="file_name", help="重命名（仅文件名，不含目录）")

    p = files_sub.add_parser("download", parents=[common], help="下载工作区文件")
    p.add_argument("--path", required=True)
    _add_output(p)

    p = files_sub.add_parser("delete", parents=[common], help="删除工作区文件")
    p.add_argument("--path", required=True)

    # ---- render -------------------------------------------------
    render = groups.add_parser("render", parents=[common], help="Remotion 远端渲染")
    render_sub = render.add_subparsers(dest="action", required=True, metavar="<命令>")

    p = render_sub.add_parser("submit", parents=[common], help="提交渲染任务")
    p.add_argument("--composition-id", dest="composition_id", required=True)
    p.add_argument("--input-props", dest="input_props", help="JSON 字符串或 @文件路径")
    p.add_argument("--export-type", dest="export_type", help="video|still|audio|image-sequence")
    p.add_argument("--codec", help="h264|h265|vp8|vp9|prores|gif")
    p.add_argument("--audio-codec", dest="audio_codec", help="mp3|aac|wav")
    p.add_argument("--image-format", dest="image_format", help="png|jpeg|pdf|webp")
    p.add_argument("--out-name", dest="out_name", help="产物名（默认 out/<compositionId>.<ext>）")
    p.add_argument("--entry-point", dest="entry_point", help="入口文件（默认 src/index.ts）")
    p.add_argument("--start-frame", dest="start_frame", type=int)
    p.add_argument("--end-frame", dest="end_frame", type=int)
    p.add_argument("--every-nth-frame", dest="every_nth_frame", type=int)
    p.add_argument("--frame", type=int, help="still 导出的帧号")
    p.add_argument("--project-id", dest="project_id")
    p.add_argument("--image-sequence", dest="image_sequence", action="store_true")
    p.add_argument("--studio-sid", dest="studio_sid", help="写入 body.studioOpaqueId（默认 api）")

    p = render_sub.add_parser("query", parents=[common], help="查询渲染任务")
    p.add_argument("--task-id", dest="task_id", required=True)
    _add_wait(p)
    p.add_argument("--download", dest="download", action="store_true", default=None, help="完成后下载产物")
    p.add_argument("--no-download", dest="download", action="store_false", help="只回任务信息")
    _add_output(p)

    p = render_sub.add_parser("list", parents=[common], help="列出渲染任务")
    p.add_argument("--studio-opaque-id", dest="studio_opaque_id")
    p.add_argument("--limit", type=int)

    p = render_sub.add_parser("cancel", parents=[common], help="取消渲染任务")
    p.add_argument("--task-id", dest="task_id", required=True)

    p = render_sub.add_parser("retry", parents=[common], help="重试渲染任务")
    p.add_argument("--task-id", dest="task_id", required=True)

    p = render_sub.add_parser("download", parents=[common], help="下载渲染产物（目录自动打包为 zip）")
    p.add_argument("--task-id", dest="task_id", required=True)
    p.add_argument("--filename", help="覆盖 out_name（一般无需指定）")
    _add_output(p)

    # ---- llm ----------------------------------------------------
    llm = groups.add_parser("llm", parents=[common], help="LLM 对话（文案/脚本生成）")
    llm_sub = llm.add_subparsers(dest="action", required=True, metavar="<命令>")

    p = llm_sub.add_parser("chat", parents=[common], help="发起一次对话补全")
    p.add_argument("--prompt", help="用户消息")
    p.add_argument("--messages", help="完整 messages 数组的 JSON 字符串或 @文件")
    p.add_argument("--system", help="系统提示词")
    p.add_argument("--model", help="平台 preset id")
    p.add_argument("--max-tokens", dest="max_tokens", type=int)
    p.add_argument("--temperature", type=float)
    _add_output(p)

    return parser


def _video_ops(parser, recognize=False):
    """给 video 的每个能力挂 submit/query（recognize 额外挂 result/cancel）。"""
    ops = parser.add_subparsers(dest="op", required=True, metavar="<操作>")
    submit = ops.add_parser("submit", parents=[_common()], help="提交任务")
    parser._ve_submit = submit
    query = ops.add_parser("query", parents=[_common()], help="查询任务")
    query.add_argument("--task-id", dest="task_id", required=True)
    _add_wait(query)
    query.add_argument("--download", dest="download", action="store_true", default=True, help="下载产物（默认开）")
    query.add_argument("--no-download", dest="download", action="store_false")
    _add_output(query)
    if recognize:
        result = ops.add_parser("result", parents=[_common()], help="取回任务结果")
        result.add_argument("--task-id", dest="task_id", required=True)
        cancel = ops.add_parser("cancel", parents=[_common()], help="取消任务")
        cancel.add_argument("--task-id", dest="task_id", required=True)


def _dh_ops(parser):
    ops = parser.add_subparsers(dest="op", required=True, metavar="<操作>")
    submit = ops.add_parser("submit", parents=[_common()], help="提交任务")
    parser._ve_submit = submit
    query = ops.add_parser("query", parents=[_common()], help="查询任务")
    query.add_argument("--task-id", dest="task_id", help="任务 ID（voice/lipsync）")
    query.add_argument("--avatar-id", dest="avatar_id", help="克隆 ID（clone）")
    _add_wait(query)
    query.add_argument("--download", dest="download", action="store_true", default=True, help="下载产物（默认开）")
    query.add_argument("--no-download", dest="download", action="store_false")
    _add_output(query)


def main(argv=None):
    setup_stdout()
    parser = build_parser()
    args = parser.parse_args(argv)
    handler = C.COMMANDS.get(args.group)
    if handler is None:  # pragma: no cover - argparse 已限制取值
        fail(f"未知命令组：{args.group}")
    try:
        handler(args)
    except VeError as exc:
        fail(exc.message, http_status=exc.http_status, endpoint=exc.endpoint)
    except KeyboardInterrupt:
        fail("已中断")
    return 0


if __name__ == "__main__":
    sys.exit(main())
