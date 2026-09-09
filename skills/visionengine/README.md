# VisionEngine 技能包（visionengine）

VisionEngine（视擎科技）媒体 AI 能力的命令行技能包：一个零依赖的 Python CLI，覆盖平台的图片、语音、字幕、视频、数字人、Remotion 工作区与渲染能力，供 Claude Code / 任意 agent 直接调用。

![icon](icon.png)

## 安装

把本目录整体放到技能目录下即可（无需安装依赖，Python 3.9+ 标准库）：

```bash
# 用户级：所有项目可用
cp -r . ~/.claude/skills/visionengine

# 项目级：仅该项目可用
cp -r . <项目根>/.claude/skills/visionengine
```

## 配置

只需要一个环境变量：

```bash
export VISION_ENGINE_API_KEY=<在 https://www.visionengine-tech.com/keys 获取的密钥>
```

服务地址、渲染服务地址等都有内置默认值，无需配置；缺密钥时 CLI 会直接报错并给出上面的示例。

## 快速开始

```bash
python <skill>/scripts/ve.py env                       # 自检：确认凭据可用
python <skill>/scripts/ve.py image generate --prompt "一只橘猫在窗台晒太阳" --aspect-ratio 9:16
python <skill>/scripts/ve.py audio voices --gender female
python <skill>/scripts/ve.py files list --path . --max-depth 1
```

所有命令输出统一 JSON（UTF-8、缩进 2）；失败时向 stderr 输出 `{"success": false, "error": ..., "http_status": ...}` 并返回退出码 1。

## 能力一览

| 组 | 命令 | 说明 |
|---|---|---|
| `env` | `env` | 诊断端点 / 密钥 / 鉴权 |
| `api` | `api <METHOD> <PATH>` | 任意已开放接口透传 |
| `image` | `generate` `edit` `edit-advanced` `generate-from-images` `recognize` `prompt-reverse` | 图片生成 / 编辑 / 识别 / 提示词反推 |
| `audio` | `tts` `voices` | 语音合成 / 音色目录（本地） |
| `subtitle` | `generate` `align` | 字幕生成 / 强制对齐（自动落 `.srt`） |
| `video` | `img2video` `text2video` `style-transfer` `recognize` × `submit` / `query` | 视频生成与理解 |
| `dh` | `clone` / `voice` / `lipsync` × `submit` / `query` | 音色克隆 / 克隆音色合成 / 对口型 |
| `files` | `list` `read` `upload` `download` `delete` | Remotion 工作区文件 |
| `render` | `submit` `query` `list` `cancel` `retry` `download` | Remotion 远端渲染 |
| `llm` | `chat` | 文案 / 脚本生成 |

每个命令都支持 `--help`。

## 目录结构

```
visionengine/
├── SKILL.md            # 技能说明（触发条件、命令地图、工作流）
├── README.md           # 本文件
├── CHANGELOG.md        # 更新记录
├── icon.png            # 图标（取自官网 favicon）
├── scripts/
│   ├── ve.py           # 入口（唯一不带下划线前缀的脚本）
│   ├── _ve_client.py   # 传输层：请求 / 上传 / 下载 / 轮询 / 错误
│   └── _ve_commands.py # 各命令实现
├── references/         # 按域拆分的详细文档
└── assets/voices.json  # 随包分发的离线音色目录
```

## 文档

- `SKILL.md` —— 触发说明、命令地图、四条核心工作流、通用约定
- `references/image.md`、`audio-subtitle.md`、`video.md`、`digital-human.md`、`files-render.md`、`troubleshooting.md`

## 许可

[MIT](../LICENSE) © VisionEngine 视擎科技

## 更新记录

见 [CHANGELOG.md](CHANGELOG.md)。
