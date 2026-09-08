# VisionEngine Skills

VisionEngine（视擎科技）工作区的**技能包仓库**——把 workspace 各子项目的核心能力封装成 agent 可直接调用的技能。
每个技能自包含（`SKILL.md` + `scripts/` + `references/` + `assets/`），可单独复制到 `~/.claude/skills/` 使用。

## 技能清单

| 技能 | 定位 | 形态 |
|---|---|---|
| [`visionengine/`](visionengine/) | 媒体 AI 全能力 CLI：图片生成/编辑/识别、TTS 与音色克隆、字幕、图生/文生视频、视频理解、数字人对口型、Remotion 工作区文件与远端渲染、LLM 文案 | 纯标准库 Python CLI（`scripts/ve.py`），零依赖 |

## 安装

技能默认**不自动安装**。两种用法：

```bash
# 1) 直接按绝对路径引用（推荐先用这个验证）
python F:/visionengine/skills/visionengine/scripts/ve.py --help

# 2) 让 Claude Code 自动触发：复制或软链到用户技能目录
cp -r F:/visionengine/skills/visionengine ~/.claude/skills/
```

## 环境变量

所有技能共用同一套凭据约定——**只经环境变量注入，绝不写入文件或提交到仓库**：

```bash
export VISION_ENGINE_API_ENDPOINT=https://api.visionengine-tech.com
export VISION_ENGINE_API_KEY=<你的 API Key>
```

可选变量与逐条说明见 [visionengine/references/troubleshooting.md](visionengine/references/troubleshooting.md)。

## 目录约定

```
skills/
├── README.md                  # 本文件
├── .gitignore
└── <skill-name>/              # 每个技能一个目录，目录名 = SKILL.md 的 name
    ├── SKILL.md               # 触发说明 + 命令地图 + 工作流（<500 行）
    ├── scripts/               # 可执行脚本（Python 入口不带 _ 前缀，内部模块带 _ 前缀）
    ├── references/            # 按需加载的详细文档
    ├── assets/                # 静态资源（如音色目录）
    └── evals/evals.json       # skill-creator 评测用例
```

评测产物写入 `visionengine-workspace/`（已 gitignore）。

## 开发约定

- 技能用 **skill-creator** 流程开发与评测：`evals/evals.json` → with-skill / without_skill 对比 → `grading.json` → benchmark → 评测视图。
- 脚本零依赖（Python 标准库），中文文档 + 英文标识符，与 workspace 其余项目一致。
- 新增能力优先扩展既有技能的 CLI 命令，而不是新建技能；跨项目能力接入见各技能 `SKILL.md` 的 Roadmap。
