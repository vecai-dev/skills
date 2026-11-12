# 故障排查（troubleshooting）

目录
- [先跑自检](#先跑自检)
- [环境变量](#环境变量)
- [MCP 启动](#mcp-启动)
- [密钥与鉴权](#密钥与鉴权)
- [常见错误码](#常见错误码)
- [超时与长任务](#超时与长任务)
- [Windows](#windows)
- [路径与目录纪律](#路径与目录纪律)

## 先跑自检

```bash
python <skill>/scripts/ve.py env
python <skill>/scripts/ve.py env --probe
```

第一条输出 Python/Node/npx、各 MCP 的启动命令与来源、Key 是否存在、当前上下文与输出目录。
第二条会启动 render 和 file bridge，列出 serverInfo 与工具名，用于确认 MCP 协议与 PATH 是否正常。

## 环境变量

| 变量 | 必需 | 默认 | 说明 |
|---|---|---|---|
| `VEC_AI_API_KEY` | ✅ | 无 | 唯一必须设置的变量；由 AI 向用户询问 |
| `VEC_AI_API_URL` | | `https://api.visionengine-tech.com` | 平台服务地址 |
| `VEC_AI_RENDER_URL` | | `https://veconline-ai-api.visionengine-tech.com` | Remotion 渲染服务 |
| `VEC_AI_OUTPUT_DIR` | | `./ve-output` | 产物落盘目录 |
| `VEC_AI_FILE_MODE` | | 自动 | `remote` / `local`；一般不需要手动设置 |
| `VEC_AI_REMOTION_WORK_DIR` | | `/vec` | 云端共享挂载根 |
| `VE_MCP_BIN_<KEY>` | | 无 | 覆盖某个 MCP 的启动命令（开发调试） |
| `VE_DEBUG` | | 无 | `1` 时把 MCP stderr 转发到 CLI stderr |

缺 Key 时 CLI 返回 `MISSING_API_KEY`，不会打印 Key。不要让 AI 把 Key 写进文件或最终回复。

## MCP 启动

启动优先级：

1. `VE_MCP_BIN_<KEY>`，例如 `VE_MCP_BIN_RENDER="node .../packages/render/dist/index.js"`；
2. PATH 上的 `ve-render` / `ve-remotion-file-bridge` / `ve-image-generate` 等（云端 entrypoint 预装）；
3. `npx -y @visionengine/<pkg>@latest`。

常见问题：

| 现象 | 处理 |
|---|---|
| `MCP_RUNTIME_MISSING` | 没有 Node.js/npx；安装 Node 18+，或使用云端预装命令 |
| 首次调用很慢 | npx 正在下载 MCP 包；后续会命中缓存 |
| `MCP_EXITED` | 看 `VE_DEBUG=1` 的 stderr；常见于 npx 网络失败或包版本不兼容 |
| `MCP_TOOL_MISSING` | npm 上的包版本过旧；使用 `@latest` 或升级预装包 |
| `MCP_TIMEOUT` | 单次调用超时；用 `--timeout` 放宽，或改用 `query --task-id` 续查 |

## 密钥与鉴权

- 只有 `VEC_AI_API_KEY`；CLI 映射为每个 MCP 子进程的 `API_KEY`。
- 同一把 Key 可调 ve-backend 和 veconline-ai-api 的所有平台 MCP；积分不足会返回 402。
- 不要提供 `--api-key` 参数；不要打印 Key 的前缀或完整值。
- Key 获取地址：`https://www.visionengine-tech.com/keys`。

## 常见错误码

| 错误码 | 含义与处理 |
|---|---|
| `MISSING_API_KEY` | 先向用户询问 Key，再以 `VEC_AI_API_KEY=...` 重试 |
| `WORKSPACE_REQUIRED` | 本地渲染/媒体上传前先创建或绑定 VECONLINE 工作区 |
| `ARTIFACT_IDENTIFIER_REQUIRED` | VECSKILL 多技能时显式传 `--artifact-identifier` |
| `INVALID_ROUND_TIMESTAMP` | 从用户消息末尾取 10 位秒，不要传毫秒 |
| `UNSUPPORTED_IN_SKILLS` | VECSKILL 不使用 file bridge；直接用本地文件系统 |
| `IMAGE_SEQUENCE_UNSUPPORTED` | VECSKILL 改用 video/still/audio |
| `INSUFFICIENT_CREDITS` | 积分不足；提示用户充值 |
| `WORKSPACE_QUOTA_EXCEEDED` | 免费 2 个工作区已满；提示购买或清空（清空前征得同意） |
| `NO_RENDERABLE_PROJECT` | 工作区没有 package.json + 入口文件；先上传工程 |
| `OUTPUT_NOT_FOUND` | 任务未 `done` 或 `outputPath` 为空；先 `render wait` |
| `MCP_NETWORK_ERROR` | 网络/后端不可达；稍后重试或看 `VE_DEBUG=1` |

## 超时与长任务

- 默认单次 MCP 调用超时因能力而异：图片 180s、TTS 600s、字幕 700s、渲染 submit 120s、
  渲染 wait 1800s、工作区上传 1800s、下载 600s。
- 异步任务轮询：`--wait` / `wait`；超时不会丢任务，用 `task_id` 继续查。
- 数字人 GPU 语音克隆首次含冷启动，约 175s 属正常。
- 渲染任务失败/超时后，CLI 会返回 `error` / `message`（已脱敏）；不要直接向用户展示内部路径。

## Windows

- `npx` 在 Windows 上是 `npx.CMD`；CLI 已处理 `.cmd` 启动与 `cmd.exe /c` 兜底。
- CLI 启动时强制 stdout/stderr 为 UTF-8；如果你另写 Python/管道处理输出，给这些命令加
  `PYTHONUTF8=1`。
- 本地相对路径以当前目录为基准；云端路径使用 `/vec/...`（POSIX）。
- `FILE_MODE=local` 只适用于服务端/已挂载环境；本地用户使用默认 `remote`。

## 路径与目录纪律

- VECONLINE：工作区在 `/vec/sys-veconline/{userId}/{conv-id}`；结果在 `out/`。
- VECSKILL：工作区在 `/vec/sys-skills/{userId}/{conv-id}`；交付物在 `artifact/{id}/`，
  中间文件/日志在 `workspace/{id}/`；不要写 `/tmp`。
- CLI 的缓存默认：
  - 本地/VECONLINE：`./ve-output/.ve-cache`；
  - VECSKILL：`workspace/{id}/.ve-cache`。
- 不要把绝对 NAS 路径、`/vec/sys-*`、Key 写进最终回复；CLI 已对错误做脱敏。
