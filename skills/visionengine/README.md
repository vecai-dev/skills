# VisionEngine 技能包（visionengine）

VisionEngine（视擎科技）平台能力的命令行技能包：零依赖 Python CLI + 平台 MCP（stdio）。
覆盖图片、语音、字幕、视频、数字人、Remotion 工作区与云端渲染，供 Claude Code / 任意 agent 调用。

## 安装

需要 Python 3.9+ 与 Node.js 18+（用于 `npx` 拉起 MCP）。把本目录整体放到技能目录：

```bash
# 用户级
cp -r . ~/.claude/skills/visionengine

# 项目级
cp -r . <项目根>/.claude/skills/visionengine
```

云端 VECONLINE/VECSKILL 已预装 `ve-*` MCP 命令，CLI 会优先使用 PATH，不需要 npx 下载。

## 配置

只需要一个环境变量：

```bash
export VEC_AI_API_KEY=<在 https://www.visionengine-tech.com/keys 获取的密钥>
```

CLI 会把它映射为各 MCP 子进程的 `API_KEY`；不要把 Key 写入文件、日志或最终回复。
缺 Key 时：**VECSKILL 云端工作区走平台授权卡**（AskUser header `VEC_API_KEY_AUTH`，平台写入项目 `.env`，不向用户索要密钥原文）；本地 / VECONLINE 才向用户询问，再以 `VEC_AI_API_KEY=...` 重试。

## 快速开始

```bash
python <skill>/scripts/ve.py env                       # 诊断 Python/Node/npx/MCP/Key
python <skill>/scripts/ve.py env --probe               # 启动 MCP 并列出工具
python <skill>/scripts/ve.py render context            # 判断 本地/VECONLINE/VECSKILL
python <skill>/scripts/ve.py image generate --prompt "一只橘猫在窗台晒太阳"
python <skill>/scripts/ve.py audio voices --gender female
python <skill>/scripts/ve.py audio tts --text "你好，欢迎使用视擎"
python <skill>/scripts/ve.py files workspaces
```

所有命令输出统一 JSON（UTF-8、缩进 2）；失败时向 stderr 输出
`{"success": false, "error": ..., "code": ...}` 并返回退出码 1。

## 能力一览

| 组 | 命令 | 说明 |
|---|---|---|
| `env` | `env` / `env --probe` | 诊断运行环境、MCP、Key |
| `image` | `generate` `edit` `edit-advanced` `generate-from-images` `recognize` `prompt-reverse` | 图片生成/编辑/识别/反推 |
| `audio` | `tts` `voices` | 语音合成 / 音色目录 |
| `subtitle` | `generate` `align` | 字幕生成 / 强制对齐 |
| `video` | `img2video` `text2video` `style-transfer` `recognize` × `submit`/`query` | 视频生成与理解 |
| `dh` | `clone` / `voice` / `lipsync` × `submit`/`query` | 音色克隆 / 克隆音色合成 / 对口型 |
| `files` | `workspaces` `quota` `create` `get` `rename` `install` `upload-project` `list` `read` `upload` `save` `download` `delete` | Remotion 工作区文件（VECONLINE/本地） |
| `render` | `context` `detect` `submit` `query` `wait` `list` `cancel` `retry` `download` `run` | Remotion 云端渲染 |

每个命令都支持 `--help`。

## 渲染环境

| `usage_type` | 场景 | 渲染 | 产物 |
|---|---|---|---|
| `standalone` | 用户本地 | 渲染 MCP + 文件桥接 | 工作区 `out/`，下载到本地 |
| `veconline` | VECONLINE 云端 | 只用渲染 MCP | 工作区 `out/`，不下载 |
| `skills` | VECSKILL 云端 | 只用渲染 MCP | `artifact/{id}/`，不下载 |

`render context` 会自动判断；VECSKILL 渲染需要来自用户消息末尾的 10 位 `Timestamp`。

## 目录结构

```
visionengine/
├── SKILL.md            # 技能说明（触发条件、命令地图、工作流）
├── README.md           # 本文件
├── CHANGELOG.md        # 更新记录
├── icon.png            # 图标
├── scripts/
│   ├── ve.py           # CLI 入口
│   ├── _mcp_client.py  # stdio JSON-RPC 客户端
│   ├── _mcp_tools.py   # CLI→MCP 映射
│   ├── _ve_context.py  # 环境/上下文解析
│   ├── _ve_util.py     # 输出/错误/下载/脱敏
│   ├── _ve_commands.py # image/audio/subtitle/video/dh/env
│   ├── _ve_cmd_files.py
│   └── _ve_cmd_render.py
├── references/         # 分域详细文档
└── assets/voices.json  # 离线音色目录
```

## 文档

- `SKILL.md` —— 触发说明、命令地图、核心工作流
- `references/image.md`、`audio-subtitle.md`、`video.md`、`digital-human.md`、
  `files-render.md`、`troubleshooting.md`、`mcp-commands.md`

## 许可

[MIT](../LICENSE) © VisionEngine 视擎科技

## 更新记录

见 [CHANGELOG.md](CHANGELOG.md)。
