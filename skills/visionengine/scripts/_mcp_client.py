#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
_mcp_client.py —— 零依赖 MCP stdio 客户端。

只做三件事：
1. 通过 PATH 上的 `ve-*` 或 `npx -y @visionengine/<pkg>@latest` 启动 MCP server；
2. newline-delimited JSON-RPC 2.0：initialize → notifications/initialized → tools/call；
3. 解析 MCP 返回的文本 JSON，统一抛 McpError。

本文件以下划线开头，是被 `ve.py` 导入的内部模块。
"""

from __future__ import annotations

import atexit
import json
import os
import queue
import shlex
import shutil
import subprocess
import sys
import threading
import time
from collections import deque
from dataclasses import dataclass

from _ve_util import VeError

PROTOCOL_VERSION = "2025-06-18"
CLIENT_NAME = "visionengine-cli"
CLIENT_VERSION = "2.0.0"


@dataclass(frozen=True)
class ServerSpec:
    key: str
    npm: str
    bin: str
    title: str


class McpError(VeError):
    def __init__(self, message, *, code="MCP_ERROR", server=None, tool=None,
                 payload=None, stderr_tail=None):
        super().__init__(message, code=code)
        self.server = server
        self.tool = tool
        self.payload = payload
        self.stderr_tail = stderr_tail


def resolve_command(spec: ServerSpec):
    """返回 (argv, source)。优先 PATH 上的预装 ve-*，其次 npx。"""
    override = os.environ.get("VE_MCP_BIN_" + spec.key.upper().replace("-", "_"))
    if override and override.strip():
        return shlex.split(override), "override"
    found = shutil.which(spec.bin)
    if found:
        return [found], "path"
    npx = shutil.which("npx")
    if not npx:
        raise McpError(
            "未找到 Node.js/npx。请安装 Node.js 18+，或在云端使用预装的 ve-* MCP 命令。",
            code="MCP_RUNTIME_MISSING",
            server=spec.key,
        )
    return [npx, "-y", f"{spec.npm}@latest"], "npx"


class McpClient:
    def __init__(self, spec: ServerSpec, env: dict, cwd, init_timeout: float = 120.0):
        self.spec = spec
        self.env = env
        self.cwd = str(cwd)
        self.init_timeout = init_timeout
        self.process = None
        self.command_source = None
        self.command = None
        self.server_info = {}
        self._responses = queue.Queue()
        self._stderr = deque(maxlen=200)
        self._noise = deque(maxlen=20)
        self._next_id = 1
        self._id_lock = threading.Lock()
        self._write_lock = threading.Lock()
        self._closed = False

    # ---- lifecycle -------------------------------------------------

    def start(self):
        argv, source = resolve_command(self.spec)
        self.command = argv
        self.command_source = source
        try:
            self.process = self._spawn(argv)
        except OSError:
            if os.name == "nt" and argv and argv[0].lower().endswith((".cmd", ".bat")):
                wrapped = [
                    os.environ.get("COMSPEC", "cmd.exe"),
                    "/d",
                    "/s",
                    "/c",
                    subprocess.list2cmdline(argv),
                ]
                self.command = wrapped
                self.process = self._spawn(wrapped)
            else:
                raise
        threading.Thread(target=self._read_stdout, daemon=True).start()
        threading.Thread(target=self._read_stderr, daemon=True).start()
        self.server_info = self._rpc(
            "initialize",
            {
                "protocolVersion": PROTOCOL_VERSION,
                "capabilities": {},
                "clientInfo": {"name": CLIENT_NAME, "version": CLIENT_VERSION},
            },
            timeout=self.init_timeout,
        )
        self._notify("notifications/initialized")
        return self

    def _spawn(self, argv):
        return subprocess.Popen(
            argv,
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            cwd=self.cwd,
            env=self.env,
            text=True,
            encoding="utf-8",
            errors="replace",
            bufsize=1,
            start_new_session=(os.name != "nt"),
        )

    def close(self):
        if self._closed:
            return
        self._closed = True
        process = self.process
        if process is None:
            return
        try:
            if process.stdin:
                process.stdin.close()
        except Exception:
            pass
        try:
            process.wait(timeout=2)
            return
        except Exception:
            pass
        try:
            process.terminate()
            process.wait(timeout=2)
            return
        except Exception:
            pass
        try:
            process.kill()
            process.wait(timeout=2)
        except Exception:
            pass
        if os.name == "nt":
            try:
                subprocess.run(
                    ["taskkill", "/F", "/T", "/PID", str(process.pid)],
                    stdout=subprocess.DEVNULL,
                    stderr=subprocess.DEVNULL,
                    check=False,
                )
            except Exception:
                pass
        elif process.pid:
            try:
                os.killpg(os.getpgid(process.pid), 9)
            except Exception:
                pass

    def __enter__(self):
        return self.start()

    def __exit__(self, *exc):
        self.close()

    # ---- protocol --------------------------------------------------

    def _read_stdout(self):
        process = self.process
        if process is None or process.stdout is None:
            return
        for line in process.stdout:
            text = line.strip()
            if not text:
                continue
            try:
                message = json.loads(text)
            except json.JSONDecodeError:
                self._noise.append(text[:300])
                continue
            if not isinstance(message, dict):
                continue
            if "id" in message and ("result" in message or "error" in message):
                self._responses.put(message)
            elif "id" in message and "method" in message:
                # 服务端反向请求：本 CLI 不提供任何方法。
                self._send(
                    {
                        "jsonrpc": "2.0",
                        "id": message.get("id"),
                        "error": {"code": -32601, "message": "Method not found"},
                    }
                )
            # notifications/* 直接忽略

    def _read_stderr(self):
        process = self.process
        if process is None or process.stderr is None:
            return
        for line in process.stderr:
            text = line.rstrip("\r\n")
            if not text:
                continue
            self._stderr.append(text)
            if os.environ.get("VE_DEBUG") == "1":
                sys.stderr.write(f"[mcp:{self.spec.key}] {text}\n")
                sys.stderr.flush()

    def _send(self, message):
        process = self.process
        if process is None or process.stdin is None:
            raise McpError("MCP 进程未启动", code="MCP_NOT_STARTED", server=self.spec.key)
        raw = json.dumps(message, ensure_ascii=False, separators=(",", ":"))
        with self._write_lock:
            try:
                process.stdin.write(raw + "\n")
                process.stdin.flush()
            except Exception as exc:
                raise McpError(
                    f"MCP 写入失败（{exc}）",
                    code="MCP_IO_ERROR",
                    server=self.spec.key,
                    stderr_tail=self.stderr_tail(),
                ) from exc

    def _notify(self, method, params=None):
        self._send({"jsonrpc": "2.0", "method": method, "params": params or {}})

    def _rpc(self, method, params=None, timeout=60.0):
        with self._id_lock:
            request_id = self._next_id
            self._next_id += 1
        self._send(
            {
                "jsonrpc": "2.0",
                "id": request_id,
                "method": method,
                "params": params or {},
            }
        )
        deadline = time.time() + float(timeout)
        while True:
            remaining = deadline - time.time()
            if remaining <= 0:
                raise McpError(
                    f"MCP 调用超时（{timeout:g}s）：{method}",
                    code="MCP_TIMEOUT",
                    server=self.spec.key,
                    tool=method,
                    stderr_tail=self.stderr_tail(),
                )
            try:
                message = self._responses.get(timeout=min(remaining, 0.5))
            except queue.Empty:
                if self.process is not None and self.process.poll() is not None:
                    raise McpError(
                        f"MCP 进程已退出（code={self.process.returncode}）：{method}",
                        code="MCP_EXITED",
                        server=self.spec.key,
                        tool=method,
                        stderr_tail=self.stderr_tail(),
                    )
                continue
            if message.get("id") != request_id:
                continue
            if "error" in message:
                error = message.get("error") or {}
                raise McpError(
                    str(error.get("message") or error),
                    code="MCP_RPC_ERROR",
                    server=self.spec.key,
                    tool=method,
                    payload=error,
                    stderr_tail=self.stderr_tail(),
                )
            return message.get("result") or {}

    # ---- tools -----------------------------------------------------

    def list_tools(self, timeout=60.0):
        result = self._rpc("tools/list", {}, timeout=timeout)
        tools = result.get("tools")
        return tools if isinstance(tools, list) else []

    def call(self, tool, arguments=None, timeout=600.0, raise_on_failure=True):
        result = self._rpc(
            "tools/call",
            {"name": tool, "arguments": arguments or {}},
            timeout=timeout,
        )
        content = result.get("content") or []
        text = "\n".join(
            item.get("text", "")
            for item in content
            if isinstance(item, dict) and item.get("type") == "text"
        ).strip()
        if result.get("isError"):
            raise McpError(
                _clean_tool_error(text) or f"MCP 工具执行失败：{tool}",
                code="MCP_TOOL_ERROR",
                server=self.spec.key,
                tool=tool,
                stderr_tail=self.stderr_tail(),
            )
        parsed = None
        if text.lstrip().startswith(("{", "[")):
            try:
                parsed = json.loads(text)
            except json.JSONDecodeError:
                parsed = None
        if (
            raise_on_failure
            and isinstance(parsed, dict)
            and parsed.get("success") is False
        ):
            message = (
                parsed.get("error")
                or parsed.get("message")
                or f"MCP 工具返回失败：{tool}"
            )
            raise McpError(
                str(message),
                code=_error_code(parsed, str(message)),
                server=self.spec.key,
                tool=tool,
                payload=parsed,
                stderr_tail=self.stderr_tail(),
            )
        return parsed, text

    def stderr_tail(self, limit=2000):
        text = "\n".join(self._stderr)
        if len(text) > limit:
            text = text[-limit:]
        return text


def _clean_tool_error(text):
    value = (text or "").strip()
    prefix = "Tool '"
    if value.startswith(prefix) and "execution failed:" in value:
        value = value.split("execution failed:", 1)[1].strip()
    return value


def _error_code(parsed, message):
    haystack = f"{message} {parsed.get('error') or ''}".upper()
    if "API_KEY" in haystack or "API KEY" in haystack:
        return "MISSING_API_KEY"
    if "WORKSPACE" in haystack and ("REQUIRED" in haystack or "CONV-" in haystack):
        return "WORKSPACE_REQUIRED"
    if "ARTIFACT_IDENTIFIER" in haystack:
        return "ARTIFACT_IDENTIFIER_REQUIRED"
    if "IMAGE-SEQUENCE" in haystack or "IMAGE_SEQUENCE" in haystack:
        return "IMAGE_SEQUENCE_UNSUPPORTED"
    if "INSUFFICIENT_CREDITS" in haystack or "积分不足" in haystack:
        return "INSUFFICIENT_CREDITS"
    if "UNKNOWN TOOL" in haystack or "TOOL NOT FOUND" in haystack:
        return "MCP_TOOL_MISSING"
    if "FETCH FAILED" in haystack or "ECONNREFUSED" in haystack or "ETIMEDOUT" in haystack:
        return "MCP_NETWORK_ERROR"
    return "MCP_TOOL_ERROR"


class McpRegistry:
    """一条 CLI 命令内按包复用 MCP 进程。"""

    def __init__(self):
        self._clients = {}
        self._lock = threading.Lock()

    def get(self, spec: ServerSpec, env, cwd):
        key = f"{spec.key}:{'key' if env.get('VEC_AI_API_KEY') else 'nokey'}"
        with self._lock:
            client = self._clients.get(key)
            if client is not None:
                return client
            client = McpClient(spec, env, cwd)
            client.start()
            self._clients[key] = client
            return client

    def close_all(self):
        with self._lock:
            clients = list(self._clients.values())
            self._clients.clear()
        for client in clients:
            try:
                client.close()
            except Exception:
                pass


_registry = McpRegistry()
atexit.register(_registry.close_all)


def get_client(spec: ServerSpec, env, cwd):
    return _registry.get(spec, env, cwd)


def close_all():
    _registry.close_all()
