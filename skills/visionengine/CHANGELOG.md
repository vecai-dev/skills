# 更新记录

本文件记录 visionengine 技能包的用户可见变更。版本号遵循语义化版本（`major.minor.patch`）。

## 2.0.0 — 2026-11-13

破坏性变更：

- 传输层从“CLI 直连 HTTP”改为 **CLI → 平台 MCP（stdio）**：
  - 优先使用 PATH 上的 `ve-*`（云端预装），本地回退
    `npx -y @visionengine/<pkg>@latest`；
  - 新增零依赖 Python MCP 客户端（initialize / tools/call / tools/list）。
- 配置变量从 `VISION_ENGINE_API_KEY` 改为 **`VEC_AI_API_KEY`**；Key 由 AI 向用户询问。
- 删除 `llm chat`（无对应 MCP 包）与 `api` 直连透传。
- `video recognize submit` 改为异步 MCP 调用；CLI 默认轮询到终态以保持旧用法，
  `--no-wait` 只返回 `task_id`。
- `image edit` 明确只接受单张图；多图改用 `edit-advanced`。
- `subtitle --no-wait` 保留参数，但 MCP 内部同步轮询，无法提前返回。

新增：

- `render context` / `detect` / `wait` / `run`；支持本地 standalone、VECONLINE、VECSKILL 三种环境。
- VECSKILL 渲染支持 `artifact/{identifier}/` 与 `_{timestamp}_artifact_` 前缀；
  `--round-timestamp` 来自用户消息末尾的 `Timestamp:10 位秒`。
- `files` 新增工作区生命周期命令：`workspaces` `quota` `create` `get` `rename`
  `install` `upload-project` `save`。
- `references/mcp-commands.md`：CLI→MCP 全量映射与子进程环境契约。
- 平台侧修复：媒体 MCP 的 `/save` 补 `workspace_id`、优先用 `root_path` 拼 `/shared`；
  渲染任务对外错误脱敏。

## 1.0.0 — 2026-09-09

首个版本。

- 覆盖平台已开放的媒体 AI 能力：图片生成 / 编辑 / 识别 / 提示词反推、语音合成与音色克隆、
  字幕生成与强制对齐、图生视频 / 文生视频 / 视频风格重绘 / 视频理解、数字人对口型、
  Remotion 工作区文件管理与远端渲染、LLM 文案生成。
- 纯标准库实现（Python 3.9+，零依赖），单入口 `scripts/ve.py`。
- 配置只需 `VISION_ENGINE_API_KEY`；服务地址、渲染服务地址均为内置默认值。
- 异步任务统一 `submit` / `query` 形态，`--wait` 轮询到终态，产物自动落盘。
- 随包分发离线音色目录 `assets/voices.json`，`audio voices` 不联网、不计费。
- 附带 `references/` 六篇分域文档：图片、语音与字幕、视频、数字人、工作区与渲染、故障排查。
- 采用 MIT 许可。
