# VisionEngine Skills

[![English](https://img.shields.io/badge/English-Click-yellow)](README.md)
[![中文文档](https://img.shields.io/badge/中文文档-点击查看-orange)](README-zh.md)

VisionEngine（视擎科技）的 Agent Skills 集合：把平台的媒体 AI 能力打包成 Claude Code / 任意 agent 可直接调用的技能。

![icon](skills/visionengine/icon.png)

## 安装

```bash
# 方式一：一键安装（skills CLI）
npx skills add vecai-dev/skills
npx skills add vecai-dev/skills --skill visionengine --agent claude-code --copy -y  # 非交互

# 方式二：手动复制到技能目录
cp -r skills/visionengine ~/.claude/skills/visionengine          # 用户级
cp -r skills/visionengine <项目根>/.claude/skills/visionengine   # 项目级
```

交互式安装会询问装到哪些 agent、装哪些技能；加 `-y` 跳过询问，加 `--copy` 以复制代替符号链接
（Windows 上符号链接需要开发者模式或管理员权限，推荐用 `--copy`）。

## 配置

所有技能共用一个密钥（服务地址有内置默认值，无需配置）：

```bash
export VISION_ENGINE_API_KEY=<在 https://www.visionengine-tech.com/keys 获取的密钥>
```

## 可用技能

### /visionengine

零依赖 Python CLI（仅标准库），覆盖图片生成/编辑/识别/反推、语音合成与音色克隆、字幕生成与打轴、图生视频/文生视频/风格重绘/视频理解、数字人对口型、Remotion 工作区文件管理与远端渲染、LLM 文案生成。

示例提示词：

- 生成一张 9:16 的竖版封面图，主题是赛博朋克城市夜景
- 用这段说话视频克隆我的音色，再用这个音色念一段欢迎语
- 把 ./bgm.mp3 上传到我的 Remotion 工作区，然后渲染 MyVideo 成片
- 给这段视频生成中文字幕，并输出 .srt 文件

详见 [skills/visionengine/SKILL.md](skills/visionengine/SKILL.md)。

## 目录结构

```
skills/                       # 仓库根（GitHub: vecai-dev/skills）
├── README.md                 # 英文文档
├── README-zh.md              # 本文件
├── LICENSE                   # MIT
└── skills/visionengine/      # 技能本体
    ├── SKILL.md              # 触发说明、命令地图、核心工作流
    ├── README.md             # 技能级说明（安装、配置、能力一览）
    ├── CHANGELOG.md          # 更新记录
    ├── icon.png              # 图标
    ├── scripts/              # ve.py（入口）+ _ve_client.py / _ve_commands.py
    ├── references/           # 按域拆分的详细文档
    └── assets/               # 随包分发的离线音色目录
```

## 许可

[MIT](LICENSE)
