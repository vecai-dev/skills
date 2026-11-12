---
name: visionengine
description: "VisionEngine（视擎科技）平台能力命令行：通过 npx/PATH 上的平台 MCP 调用图片生成/编辑/识别/提示词反推、语音合成与音色克隆、字幕生成与打轴、图生视频/文生视频/视频风格重绘/视频理解、数字人对口型、Remotion 工作区文件管理与云端渲染。当用户要求生成图片或视频、给视频配音、克隆音色、做数字人、生成字幕或转写、做视频风格迁移、把素材上传到 Remotion 工作区、渲染 Remotion 成片、反推图片提示词，或提到 VisionEngine / 视擎 / ve 的媒体任务时使用本技能——即使用户没有点名 VisionEngine，只要任务落在上述媒体 AI 能力范围内也应使用。不适用于与 VisionEngine 平台无关的纯本地 ffmpeg 处理或通用编码任务。"
license: "MIT"
compatibility: "Python 3.9+（仅标准库）；需要 Node.js 18+ 与 npx，或云端预装的 ve-* MCP 命令；需要 VisionEngine API Key（环境变量 VEC_AI_API_KEY）"
metadata:
  author: "VisionEngine 视擎科技"
  version: "2.0.0"
  homepage: "https://www.visionengine-tech.com"
---

# VisionEngine CLI

零依赖 Python CLI，把 VisionEngine 平台的 MCP 能力包装成命令。每条命令内部启动
`ve-*` 或 `npx -y @visionengine/<pkg>@latest` 的 stdio MCP server，通过 JSON-RPC 调用工具。

## 运行环境与自检

先跑：

```bash
python <skill>/scripts/ve.py env
```

确认 `python`、`node`、`npx`、各 MCP 的启动命令与 API Key 是否存在（只显示是否存在，不显示值）。
需要验证 MCP 协议与工具列表时：

```bash
python <skill>/scripts/ve.py env --probe
```

## API Key（先问用户）

只使用一个环境变量 `VEC_AI_API_KEY`。缺 Key 时 CLI 会返回 `MISSING_API_KEY`，
此时**先向用户询问 API Key**，并告诉用户可在 `https://www.visionengine-tech.com/keys` 获取；
拿到后在该命令前设置环境变量重试：

```bash
VEC_AI_API_KEY=<用户的 Key> python <skill>/scripts/ve.py <原命令>
```

不要把 Key 写入文件、日志、命令输出或最终回复。CLI 会把它映射为各 MCP 的 `API_KEY`，
不会打印、不会落盘。

## 先判定运行环境

React Remotion 渲染前必须先判断当前是本地、VECONLINE 还是 VECSKILL：

```bash
python <skill>/scripts/ve.py render context
```

| `usage_type` | 场景 | 渲染方式 | 产物位置 |
|---|---|---|---|
| `standalone` | 用户本地电脑 | 渲染 MCP + 文件桥接 | 远端 `out/`，下载到本地 |
| `veconline` | VECONLINE 云端 | 只用渲染 MCP | 工作区 `out/`，不下载 |
| `skills` | VECSKILL 云端 | 只用渲染 MCP | `artifact/{技能标识符}/`，不下载 |

判定依据：显式参数 > `VE_USAGE_TYPE` > 当前目录的 `sys-veconline` / `sys-skills` 路径 >
`.ve-workspace.json` > 默认 `standalone`。云端 VECSKILL 禁用会话 MCP，CLI 会自己拉起 MCP。

## 命令地图

| 组 | 命令 | 说明 | 参考 |
|---|---|---|---|
| `env` | `env` / `env --probe` | 诊断运行环境、MCP、Key | ¹ |
| `image` | `generate` `edit` `edit-advanced` `generate-from-images` `recognize` `prompt-reverse` | 图片生成/编辑/识别/反推 | ² |
| `audio` | `tts` `voices` | 语音合成 / 音色目录 | ³ |
| `subtitle` | `generate` `align` | 字幕生成 / 强制对齐 | ³ |
| `video` | `img2video\|text2video\|style-transfer\|recognize` × `submit\|query` | 视频生成与理解 | ⁴ |
| `dh` | `clone\|voice\|lipsync` × `submit\|query` | 音色克隆 / 克隆音色合成 / 对口型 | ⁵ |
| `files` | `workspaces` `quota` `create` `get` `rename` `install` `upload-project` `list` `read` `upload` `save` `download` `delete` | Remotion 工作区文件（VECONLINE/本地） | ⁶ |
| `render` | `context` `detect` `submit` `query` `wait` `list` `cancel` `retry` `download` `run` | Remotion 云端渲染 | ⁶ |

每个命令都支持 `--help`。通用开关：`--timeout`（单次 MCP 调用超时）、`--out`（产物目录）。
上下文开关：`--usage-type`、`--system`、`--workspace-id`、`--artifact-identifier`、
`--round-timestamp`、`--workspace-root`。完整的 CLI→MCP 映射与子进程环境契约见 ⁷。

## 核心工作流

### 1. 图片

```bash
python <skill>/scripts/ve.py image generate --prompt "一只橘猫在窗台晒太阳" --aspect-ratio 9:16
python <skill>/scripts/ve.py image edit-advanced --image a.png --prompt "把背景换成雨天"
python <skill>/scripts/ve.py image recognize --image a.png --tool visual
python <skill>/scripts/ve.py image prompt-reverse --image a.png --output-language zh
```

图片生成/编辑产物默认落 `./ve-output`；`image edit` 只接受单张图，多图用 `edit-advanced`。

### 2. 配音与字幕

```bash
python <skill>/scripts/ve.py audio voices --gender female
python <skill>/scripts/ve.py audio tts --text "你好，欢迎使用视擎" --speaker zh_female_vv_uranus_bigtts
python <skill>/scripts/ve.py subtitle generate --audio talk.mp4 --language zh-CN
```

字幕 MCP 内部同步轮询；`--no-wait` 无法提前返回。字幕文件会落到 `./ve-output`。

### 3. 视频与数字人

```bash
python <skill>/scripts/ve.py video img2video submit --image first.png --prompt "镜头推进"
python <skill>/scripts/ve.py video img2video query --task-id <id> --wait --download
python <skill>/scripts/ve.py video text2video submit --prompt "海边日落，电影感"
python <skill>/scripts/ve.py video recognize submit --video talk.mp4 --task-type understand
python <skill>/scripts/ve.py dh clone submit --video talk.mp4 --name "我的音色"
python <skill>/scripts/ve.py dh voice submit --text "大家好" --avatar-id <avatar_id>
python <skill>/scripts/ve.py dh lipsync submit --video human.mp4 --audio speech.wav
```

异步任务 `submit` 立即返回 `task_id`；`query` 默认只查一次，加 `--wait` 轮询到终态。
超时不丢任务，用同一个 `task_id` 继续查。数字人 `voice submit --avatar-id` 会自动补全
参考音频与逐字稿。

### 4. 文件桥（本地 / VECONLINE）

```bash
python <skill>/scripts/ve.py files workspaces          # 列工作区 + 配额
python <skill>/scripts/ve.py files quota
python <skill>/scripts/ve.py files create --name "我的 Remotion 项目" --local-dir .
python <skill>/scripts/ve.py files upload-project --local-dir .
python <skill>/scripts/ve.py files upload ./MyVideo.tsx --target-path src
python <skill>/scripts/ve.py files upload ./bgm.mp3 --target-path public/audio
python <skill>/scripts/ve.py files download --path out/demo.mp4 --out ./ve-output
```

工作区免费 2 个（含主工作区），超额需在 `https://www.visionengine-tech.com/projects` 购买。
没有可用工作区时先提示用户解锁或清空；**清空前必须征得用户同意**。VECSKILL 不使用文件桥，
`files` 命令会直接拒绝。

### 5. 云端渲染（VECONLINE / VECSKILL）

VECONLINE：

```bash
python <skill>/scripts/ve.py render context
python <skill>/scripts/ve.py render detect
python <skill>/scripts/ve.py render submit --composition-id MyVideo
python <skill>/scripts/ve.py render wait --task-id <id>
```

VECSKILL：必须把本轮用户消息最后一行 `Timestamp:<10 位 Unix 秒>` 传给 `--round-timestamp`；
源码默认放 `workspace/{技能标识符}/`，产物自动落 `artifact/{技能标识符}/`，文件名由后端加
`_{timestamp}_artifact_` 前缀：

```bash
python <skill>/scripts/ve.py render submit --composition-id MyVideo --round-timestamp 1792650600
python <skill>/scripts/ve.py render wait --task-id <id>
```

云端不调用文件桥、不上传下载；`wait` 后产物已在 NAS 工作区。VECSKILL 不支持
`image-sequence`。

### 6. 本地 standalone 渲染

```bash
python <skill>/scripts/ve.py render run --composition-id MyVideo \
  --workspace-name "我的 Remotion 项目" --upload --out ./ve-output
```

`render run` 依次做 detect → submit → wait；standalone 会创建/绑定工作区、上传工程
（默认跑 `pnpm install`）并下载产物。也可以拆开：

```bash
python <skill>/scripts/ve.py files upload-project --local-dir .
python <skill>/scripts/ve.py render detect
python <skill>/scripts/ve.py render submit --composition-id MyVideo
python <skill>/scripts/ve.py render wait --task-id <id>
python <skill>/scripts/ve.py render download --task-id <id> --out ./ve-output
```

## 通用约定

- **异步任务**：`submit` 返回 `task_id`；`query --wait` 或 `wait` 轮询到 `done/failed/canceled`。
  轮询超时不会丢任务，用 `task_id` 继续查。
- **产物目录**：本地/VECONLINE 默认落 `./ve-output`，VECSKILL 默认落 `workspace/{id}/`；
  `--out` 可覆盖。云端渲染不复制产物到 `ve-output`：VECONLINE 在 `out/`，VECSKILL 在
  `artifact/{id}/`。
- **密钥**：只有 `VEC_AI_API_KEY`；不要打印、不要写文件、不要放进最终回复。
- **路径**：不要把绝对 NAS 路径、`/vec/sys-*`、工作区内部路径写进最终回复；CLI 已做错误脱敏。
- **VECSKILL 目录**：交付物放 `artifact/{id}/`；中间文件/日志放 `workspace/{id}/`，不要写 `/tmp`。
- **VECONLINE 工作区**：默认 2 个；超额先提示用户购买或清空，清空必须征得同意。
- **MCP 启动**：优先 PATH 上的 `ve-*`（云端预装），本地回退 `npx -y @visionengine/<pkg>@latest`；
  首次运行可能下载包，属正常。

## 参考文件

1. [故障排查、环境变量与 MCP 启动](references/troubleshooting.md)
2. [图片能力参数](references/image.md)
3. [语音与字幕参数](references/audio-subtitle.md)
4. [视频能力参数](references/video.md)
5. [数字人能力参数](references/digital-human.md)
6. [工作区文件与 Remotion 渲染](references/files-render.md)
7. [CLI→MCP 全量映射](references/mcp-commands.md)

```non-md
- [CLI 入口](scripts/ve.py)
- [MCP 客户端](scripts/_mcp_client.py)
- [MCP 工具映射](scripts/_mcp_tools.py)
- [上下文解析](scripts/_ve_context.py)
- [命令实现](scripts/_ve_commands.py)
- [files 命令](scripts/_ve_cmd_files.py)
- [render 命令](scripts/_ve_cmd_render.py)
- [离线音色目录](assets/voices.json)
```

## 已知限制

- 图片抠图（image-matting）与 `video-generate` 暂无对应 MCP 包，不提供命令。
- `video recognize` 的 MCP 没有 cancel 工具；`video recognize cancel` 会明确报错。
- VECSKILL 渲染不支持 `image-sequence`。
- VECONLINE 的技能动态装载 API 在当前版本可能不稳定；本技能只依赖启动时已发现的
  `.claude/skills`，不依赖动态装载。
- 包根 `README.md` / `CHANGELOG.md` / `icon.png` 为 GitHub 分发保留；上传技能工坊时
  可能收到“包根多余文件”警告，不影响使用。
