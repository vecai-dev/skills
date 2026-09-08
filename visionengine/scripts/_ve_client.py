#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
_ve_client.py —— VisionEngine CLI 的传输层（仅标准库，无第三方依赖）。

职责：
- 读取环境变量 / 命令行覆盖 → Config
- HTTP 请求：JSON、原始字节、逐行 NDJSON 流
- 本地文件分流：图片内联 base64、媒体经 /save 上传、storage 路径透传
- /save 直传（≤8MB）与 /save/chunk 分块（4MB，稳定 upload_id）
- 产物下载、异步任务轮询
- 统一的 JSON 输出与错误信封

约定：本文件以下划线开头，是被 `ve.py` 导入的内部模块，不直接执行。
"""

from __future__ import annotations

import base64
import io
import json
import math
import mimetypes
import os
import shutil
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
import uuid
from pathlib import Path

# ---------------------------------------------------------------- 常量

DIRECT_UPLOAD_MAX_BYTES = 8 * 1024 * 1024
CHUNK_SIZE_BYTES = 4 * 1024 * 1024
DEFAULT_TIMEOUT = 60.0
LONG_TIMEOUT = 600.0
DEFAULT_RENDER_ENDPOINT = "https://veconline-ai-api.visionengine-tech.com"
DEFAULT_ENDPOINT_EXAMPLE = "https://api.visionengine-tech.com"

ENV_ENDPOINT = "VISION_ENGINE_API_ENDPOINT"
ENV_API_KEY = "VISION_ENGINE_API_KEY"
ENV_RENDER_ENDPOINT = "VISION_ENGINE_RENDER_ENDPOINT"
ENV_WORKDIR = "VISION_ENGINE_WORKDIR"
ENV_OUTPUT_DIR = "VISION_ENGINE_OUTPUT_DIR"
ENV_FILE_MODE = "VISION_ENGINE_FILE_MODE"
ENV_REMOTION_WORK_DIR = "VISION_ENGINE_REMOTION_WORK_DIR"


class VeError(Exception):
    """携带 HTTP 上下文的业务/传输错误。"""

    def __init__(self, message, http_status=None, endpoint=None, payload=None):
        super().__init__(message)
        self.message = message
        self.http_status = http_status
        self.endpoint = endpoint
        self.payload = payload


# ---------------------------------------------------------------- 配置


class Config:
    def __init__(self, endpoint="", api_key="", render_endpoint=DEFAULT_RENDER_ENDPOINT,
                 workdir=None, output_dir=None, file_mode="remote",
                 remotion_work_dir="/vec", timeout=DEFAULT_TIMEOUT):
        self.endpoint = (endpoint or "").rstrip("/")
        self.api_key = api_key or ""
        self.render_endpoint = (render_endpoint or DEFAULT_RENDER_ENDPOINT).rstrip("/")
        self.workdir = Path(workdir or os.getcwd()).resolve()
        out = output_dir or (self.workdir / "ve-output")
        out_path = Path(out)
        self.output_dir = (out_path if out_path.is_absolute() else self.workdir / out_path).resolve()
        self.file_mode = file_mode
        self.remotion_work_dir = remotion_work_dir
        self.timeout = float(timeout or DEFAULT_TIMEOUT)

    # -- 路径解析 --------------------------------------------------

    def resolve_path(self, value):
        """相对路径以 VISION_ENGINE_WORKDIR 为基准。"""
        path = Path(value)
        return (path if path.is_absolute() else self.workdir / path)

    def out_path(self, filename):
        self.output_dir.mkdir(parents=True, exist_ok=True)
        return _unique_path(self.output_dir / filename)

    # -- 校验 ------------------------------------------------------

    def require_endpoint(self):
        if not self.endpoint:
            raise VeError(
                f"缺少环境变量 {ENV_ENDPOINT}。示例：\n"
                f"  export {ENV_ENDPOINT}={DEFAULT_ENDPOINT_EXAMPLE}\n"
                f"  export {ENV_API_KEY}=<你的 API Key>"
            )
        return self.endpoint

    def require_key(self):
        if not self.api_key:
            raise VeError(
                f"缺少环境变量 {ENV_API_KEY}（Bearer 令牌）。"
                f"请在 VisionEngine 控制台创建 API Key 后注入环境变量。"
            )
        return self.api_key


def load_config(args, require_network=True):
    """从环境变量 + 命令行覆盖构造 Config。"""
    endpoint = (getattr(args, "endpoint", None) or os.environ.get(ENV_ENDPOINT) or "").strip()
    api_key = (getattr(args, "api_key", None) or os.environ.get(ENV_API_KEY) or "").strip()
    render_endpoint = (
        getattr(args, "render_endpoint", None)
        or os.environ.get(ENV_RENDER_ENDPOINT)
        or DEFAULT_RENDER_ENDPOINT
    ).strip()

    file_mode = (os.environ.get(ENV_FILE_MODE) or "remote").strip().lower()
    if file_mode not in {"remote", "local"}:
        raise VeError(f"{ENV_FILE_MODE} 只能是 remote 或 local，当前为 {file_mode!r}")

    cfg = Config(
        endpoint=endpoint,
        api_key=api_key,
        render_endpoint=render_endpoint,
        workdir=os.environ.get(ENV_WORKDIR) or os.getcwd(),
        # CLI 的 --out 优先于环境变量：显式传参最不容易被误解。
        output_dir=getattr(args, "out", None) or os.environ.get(ENV_OUTPUT_DIR) or None,
        file_mode=file_mode,
        remotion_work_dir=os.environ.get(ENV_REMOTION_WORK_DIR) or "/vec",
        timeout=getattr(args, "timeout", None) or DEFAULT_TIMEOUT,
    )

    if require_network:
        cfg.require_endpoint()
        cfg.require_key()
    return cfg


# ---------------------------------------------------------------- 输出


def emit(payload):
    """把结果以 UTF-8 JSON 打到 stdout。"""
    print(json.dumps(payload, ensure_ascii=False, indent=2))


def fail(message, **extra):
    """把错误信封打到 stderr 并以退出码 1 结束。"""
    payload = {"success": False, "error": str(message)}
    for key, value in extra.items():
        if value is not None:
            payload[key] = value
    print(json.dumps(payload, ensure_ascii=False, indent=2), file=sys.stderr)
    raise SystemExit(1)


def setup_stdout():
    """Windows 控制台默认 GBK，强制 UTF-8 避免中文乱码。"""
    for stream in (sys.stdout, sys.stderr):
        try:
            stream.reconfigure(encoding="utf-8")
        except Exception:
            pass


# ---------------------------------------------------------------- HTTP 基元


def build_url(base, path, params=None):
    if not path.startswith("/"):
        path = "/" + path
    url = base.rstrip("/") + path
    if params:
        clean = {k: v for k, v in params.items() if v is not None}
        if clean:
            url += "?" + urllib.parse.urlencode(clean, doseq=True)
    return url


def _open(method, url, data=None, headers=None, timeout=DEFAULT_TIMEOUT):
    request = urllib.request.Request(url, data=data, method=method)
    for key, value in (headers or {}).items():
        request.add_header(key, value)
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            return response.status, dict(response.headers), response.read()
    except urllib.error.HTTPError as exc:
        return exc.code, dict(exc.headers or {}), exc.read()
    except urllib.error.URLError as exc:
        raise VeError(f"网络请求失败：{exc.reason}", endpoint=f"{method} {url}") from exc
    except TimeoutError as exc:
        raise VeError(f"请求超时（{timeout:g}s）：{url}", endpoint=f"{method} {url}") from exc


def _parse_json(raw):
    if not raw:
        return None
    try:
        return json.loads(raw.decode("utf-8"))
    except Exception:
        return None


def _extract_error(payload, status):
    """FastAPI 用 detail，其余用 error/message；都取不到就回退到 HTTP 状态。"""
    if isinstance(payload, dict):
        for key in ("detail", "error", "message"):
            value = payload.get(key)
            if isinstance(value, str) and value.strip():
                return value.strip()
            if isinstance(value, (dict, list)) and value:
                return json.dumps(value, ensure_ascii=False)[:800]
    if isinstance(payload, str) and payload.strip():
        return payload.strip()[:800]
    return f"HTTP {status}"


def request_json(cfg, method, path, body=None, params=None, endpoint=None,
                 timeout=None, headers=None, auth=True):
    """发 JSON 请求并返回解析后的对象；非 2xx 抛 VeError。"""
    base = endpoint or cfg.endpoint
    url = build_url(base, path, params)
    hdrs = {"Accept": "application/json"}
    if auth:
        hdrs["Authorization"] = f"Bearer {cfg.api_key}"
    data = None
    if body is not None:
        data = json.dumps(body, ensure_ascii=False).encode("utf-8")
        hdrs["Content-Type"] = "application/json"
    hdrs.update(headers or {})

    status, _, raw = _open(method, url, data, hdrs, timeout or cfg.timeout)
    payload = _parse_json(raw)
    if not (200 <= status < 300):
        raise VeError(_extract_error(payload, status), http_status=status,
                      endpoint=f"{method} {url}", payload=payload)
    return payload


def request_bytes(cfg, method, path, body=None, params=None, endpoint=None,
                  timeout=None, headers=None, auth=True):
    """发请求并返回原始字节（TTS 流、文件下载等）。"""
    base = endpoint or cfg.endpoint
    url = build_url(base, path, params)
    hdrs = {}
    if auth:
        hdrs["Authorization"] = f"Bearer {cfg.api_key}"
    data = None
    if body is not None:
        data = json.dumps(body, ensure_ascii=False).encode("utf-8")
        hdrs["Content-Type"] = "application/json"
    hdrs.update(headers or {})

    status, _, raw = _open(method, url, data, hdrs, timeout or cfg.timeout)
    if not (200 <= status < 300):
        raise VeError(_extract_error(_parse_json(raw), status), http_status=status,
                      endpoint=f"{method} {url}")
    return raw


def request_raw(cfg, method, path, data=None, params=None, endpoint=None,
                timeout=None, headers=None, auth=True):
    """发送原始字节请求体（如字幕接口要求 body 直接是媒体字节），返回响应字节。"""
    base = endpoint or cfg.endpoint
    url = build_url(base, path, params)
    hdrs = {}
    if auth:
        hdrs["Authorization"] = f"Bearer {cfg.api_key}"
    hdrs.update(headers or {})

    status, _, raw = _open(method, url, data, hdrs, timeout or cfg.timeout)
    if not (200 <= status < 300):
        raise VeError(_extract_error(_parse_json(raw), status), http_status=status,
                      endpoint=f"{method} {url}")
    return raw


def download_url(cfg, url, out_dir=None, filename=None, timeout=None, auth=False):
    """下载产物到本地，返回落盘路径。签名 URL 通常不需要鉴权。"""
    target_dir = Path(out_dir) if out_dir else cfg.output_dir
    target_dir.mkdir(parents=True, exist_ok=True)
    name = filename or _filename_from_url(url)
    dest = _unique_path(target_dir / name)

    headers = {"Authorization": f"Bearer {cfg.api_key}"} if auth else {}
    request = urllib.request.Request(url, method="GET", headers=headers)
    try:
        with urllib.request.urlopen(request, timeout=timeout or cfg.timeout) as response:
            with dest.open("wb") as handle:
                shutil.copyfileobj(response, handle)
    except urllib.error.HTTPError as exc:
        raise VeError(f"下载失败 HTTP {exc.code}：{url}", http_status=exc.code) from exc
    except urllib.error.URLError as exc:
        raise VeError(f"下载失败：{exc.reason}（{url}）") from exc
    return dest


# ---------------------------------------------------------------- 上传


def _content_type_for(name):
    guessed = mimetypes.guess_type(name)[0]
    return guessed or "application/octet-stream"


def _ascii_header_value(value):
    """HTTP 头只能安全承载 latin-1；非 ASCII 一律降级，避免 UnicodeEncodeError。"""
    try:
        value.encode("latin-1")
        return value
    except UnicodeEncodeError:
        return value.encode("ascii", "replace").decode("ascii")


def _encode_multipart(fields, file_field, file_name, file_bytes, content_type):
    boundary = f"----ve{uuid.uuid4().hex}"
    crlf = b"\r\n"
    buffer = io.BytesIO()

    for key, value in fields.items():
        if value is None:
            continue
        buffer.write(f"--{boundary}".encode("utf-8"))
        buffer.write(crlf)
        buffer.write(f'Content-Disposition: form-data; name="{key}"'.encode("utf-8"))
        buffer.write(crlf)
        buffer.write(crlf)
        buffer.write(str(value).encode("utf-8"))
        buffer.write(crlf)

    buffer.write(f"--{boundary}".encode("utf-8"))
    buffer.write(crlf)
    disposition = f'Content-Disposition: form-data; name="{file_field}"; filename="{_ascii_header_value(file_name)}"'
    buffer.write(disposition.encode("utf-8"))
    buffer.write(crlf)
    buffer.write(f"Content-Type: {content_type}".encode("utf-8"))
    buffer.write(crlf)
    buffer.write(crlf)
    buffer.write(file_bytes)
    buffer.write(crlf)
    buffer.write(f"--{boundary}--".encode("utf-8"))
    buffer.write(crlf)
    return boundary, buffer.getvalue()


def upload_file(cfg, local_path, target_dir=None, file_name=None, timeout=None):
    """
    上传本地文件到用户 Remotion 工作区，返回后端给的 file 对象
    （字段 name / path / size / content_type）。

    ≤8MB 走 multipart /save；更大走 /save/chunk（4MB 分片 + 稳定 upload_id）。
    同名冲突后端会自动改名，因此调用方必须使用返回的 path。
    """
    path = Path(local_path)
    if not path.is_file():
        raise VeError(f"文件不存在：{path}")
    name = file_name or path.name
    size = path.stat().st_size

    if size <= DIRECT_UPLOAD_MAX_BYTES:
        return _upload_direct(cfg, path, name, target_dir, timeout)
    return _upload_chunked(cfg, path, name, target_dir, timeout)


def _upload_direct(cfg, path, name, target_dir, timeout):
    fields = {"file_name": name}
    if target_dir:
        fields["path"] = target_dir
    content_type = _content_type_for(name)
    boundary, body = _encode_multipart(fields, "file", name, path.read_bytes(), content_type)

    url = build_url(cfg.endpoint, "/save")
    headers = {
        "Authorization": f"Bearer {cfg.api_key}",
        "Content-Type": f"multipart/form-data; boundary={boundary}",
    }
    status, _, raw = _open("POST", url, body, headers, timeout or cfg.timeout)
    payload = _parse_json(raw)
    if not (200 <= status < 300):
        raise VeError(_extract_error(payload, status), http_status=status,
                      endpoint=f"POST {url}", payload=payload)
    file_info = (payload or {}).get("file")
    if not file_info or not file_info.get("path"):
        raise VeError("上传成功但响应缺少 file.path", endpoint=f"POST {url}", payload=payload)
    return file_info


def _upload_chunked(cfg, path, name, target_dir, timeout):
    total_chunks = math.ceil(path.stat().st_size / CHUNK_SIZE_BYTES)
    # 关键：分片必须共用同一个 upload_id，否则后端每个分片各建目录，永不合并。
    upload_id = f"upload_{uuid.uuid4().hex}"
    content_type = _content_type_for(name)
    last_payload = None

    with path.open("rb") as handle:
        for index in range(total_chunks):
            chunk = handle.read(CHUNK_SIZE_BYTES)
            body = {
                "upload_id": upload_id,
                "file_name": name,
                "chunk_index": index,
                "total_chunks": total_chunks,
                "content": base64.b64encode(chunk).decode("ascii"),
                "content_type": content_type,
            }
            if target_dir:
                body["path"] = target_dir
            last_payload = request_json(cfg, "POST", "/save/chunk", body=body,
                                        timeout=max(timeout or cfg.timeout, 120.0))

    file_info = (last_payload or {}).get("file")
    if not file_info or not file_info.get("path"):
        raise VeError("分块上传结束但响应缺少 file.path", payload=last_payload)
    return file_info


def upload_text(cfg, text, file_name, target_dir=None, timeout=None):
    """以 JSON 方式保存文本（代码/配置等），避免 multipart 与编码问题。"""
    body = {"file_name": file_name, "content": text, "encoding": "text"}
    if target_dir:
        body["path"] = target_dir
    payload = request_json(cfg, "POST", "/save", body=body, timeout=timeout)
    file_info = (payload or {}).get("file")
    if not file_info or not file_info.get("path"):
        raise VeError("保存文本失败：响应缺少 file.path", payload=payload)
    return file_info


# ---------------------------------------------------------------- 文件输入分流


def _data_url(path):
    content_type = _content_type_for(path.name)
    encoded = base64.b64encode(path.read_bytes()).decode("ascii")
    return f"data:{content_type};base64,{encoded}"


def _quote_path(value):
    return "/".join(urllib.parse.quote(segment, safe="") for segment in value.split("/") if segment)


def shared_url(cfg, path):
    """FILE_MODE=local：把共享挂载内的文件改写为 /shared URL。"""
    root = Path(cfg.remotion_work_dir)
    try:
        relative = Path(path).resolve().relative_to(root.resolve())
    except ValueError as exc:
        raise VeError(
            f"FILE_MODE=local 要求文件位于共享挂载根 {root} 之下，当前为 {path}；"
            f"请改用 FILE_MODE=remote 让 CLI 自动上传。"
        ) from exc
    return f"{cfg.endpoint}/shared/{_quote_path(relative.as_posix())}?download=true"


def as_image_input(cfg, value):
    """
    图片类输入：http(s)/data URL 原样透传；本地文件内联为 base64 data URL；
    其余当作后端可解析的 storage 路径。
    """
    if value.startswith(("http://", "https://", "data:")):
        return value
    path = cfg.resolve_path(value)
    if path.is_file():
        return _data_url(path)
    return value


def as_media_input(cfg, value, target_dir=None, force_upload=False):
    """
    媒体类输入（视频/音频）→ {"type":"url","data":...} 或 {"type":"storage","path":...}。
    本地文件在 remote 模式先上传；local 模式改写为 /shared URL。
    """
    if value.startswith(("http://", "https://")):
        return {"type": "url", "data": value}
    path = cfg.resolve_path(value)
    if path.is_file():
        if cfg.file_mode == "local" and not force_upload:
            return {"type": "url", "data": shared_url(cfg, path)}
        info = upload_file(cfg, path, target_dir=target_dir)
        url = f"{cfg.endpoint}/shared/{_quote_path(info['path'])}?download=true"
        return {"type": "url", "data": url}
    # 既不是 URL 也不是本地文件 → 视为用户桶内的存储路径，交由后端校验属主
    return {"type": "storage", "path": value}


def as_media_url(cfg, value, target_dir=None, force_upload=False):
    """需要纯 URL 字符串的场景（如 voice_submit.prompt_audio_url）。"""
    obj = as_media_input(cfg, value, target_dir=target_dir, force_upload=force_upload)
    if obj["type"] == "url":
        return obj["data"]
    raise VeError(
        f"该参数要求公网可访问的 URL（http/https），无法直接使用存储路径 {value!r}；"
        f"请传入本地文件或 https URL。"
    )


# ---------------------------------------------------------------- 轮询


def poll(fetch, is_done, is_failed=None, interval=15.0, timeout=300.0, on_tick=None):
    """
    通用轮询：fetch() 取一次状态，is_done/is_failed 判定终态。
    超时抛 VeError（可用 `query --task-id` 继续查）。
    """
    deadline = time.time() + float(timeout)
    last = None
    while True:
        last = fetch()
        if on_tick:
            on_tick(last)
        if is_done(last):
            return last
        if is_failed and is_failed(last):
            return last
        if time.time() >= deadline:
            raise VeError(
                f"轮询超时（{timeout:g}s）。任务仍在运行，可稍后用 `query --task-id` 继续查询。",
                payload=last,
            )
        time.sleep(interval)


# ---------------------------------------------------------------- 杂项


def _filename_from_url(url):
    parsed = urllib.parse.urlparse(url)
    name = os.path.basename(urllib.parse.unquote(parsed.path))
    return name or f"download-{uuid.uuid4().hex[:8]}"


def _unique_path(path):
    """同名时追加 -1/-2…，避免覆盖已有文件。"""
    if not path.exists():
        return path
    stem, suffix, parent = path.stem, path.suffix, path.parent
    index = 1
    while True:
        candidate = parent / f"{stem}-{index}{suffix}"
        if not candidate.exists():
            return candidate
        index += 1


def get_path(obj, *keys, default=None):
    """按 a.b.c 取嵌套字段，缺失返回 default。"""
    current = obj
    for key in keys:
        if isinstance(current, dict) and key in current:
            current = current[key]
        else:
            return default
    return current


def pick(obj, *names, default=None):
    """从字典里按候选键名取第一个非空值（后端字段别名较多）。"""
    if not isinstance(obj, dict):
        return default
    for name in names:
        value = obj.get(name)
        if value not in (None, ""):
            return value
    return default
