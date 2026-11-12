# 工作区文件与 Remotion 渲染

目录
- [先判定环境](#先判定环境)
- [render 命令](#render-命令)
- [云端渲染](#云端渲染)
- [本地 standalone 渲染](#本地-standalone-渲染)
- [files 命令](#files-命令)
- [常见错误](#常见错误)

## 先判定环境

```bash
python <skill>/scripts/ve.py render context
```

| usage_type | 场景 | 是否用 file bridge | 产物 |
|---|---|---|---|
| `standalone` | 用户本地 | 是，先上传工程/最后下载产物 | 远端 `out/` |
| `veconline` | VECONLINE 云端 | 否 | 工作区 `out/` |
| `skills` | VECSKILL 云端 | 否 | `artifact/{id}/` |

`render context` 不需要 API Key。它会同时输出 CLI 判定和渲染 MCP 的 `get_context` 结果，
两者不一致时以 CLI 判定为准（CLI 会把 `VE_*` 环境变量显式传给 MCP）。

## render 命令

| 命令 | MCP 工具 | 说明 |
|---|---|---|
| `render context` | `get_context` | 诊断运行环境，不调后端 |
| `render detect` | `detect` | 找 `package.json` + 入口文件，返回 candidates 与 outputDir |
| `render submit` | `submit` | 提交任务，返回 `task_id` |
| `render query` | `query` | 查询一次；`--wait` 时轮询到终态 |
| `render wait` | `wait` | 轮询到 `done/failed/canceled` |
| `render list` | `list` | 列出当前工作区渲染任务 |
| `render cancel` | `cancel` | 取消任务（best effort） |
| `render retry` | `retry` | 以相同参数重试终态任务 |
| `render download` | `query` + 下载 | standalone 从工作区下载；云端本地文件直接返回 |
| `render run` | `detect` + `submit` + `wait` + 落地 | 一把梭 |

`render submit` 常用参数：

| CLI | MCP 参数 |
|---|---|
| `--composition-id` | `compositionId`（必填） |
| `--input-props` | `inputProps`（JSON 字符串或 `@文件`） |
| `--export-type` | `exportType`：`video | still | audio | image-sequence` |
| `--codec` | `codec`：`h264 h265 vp8 vp9 prores gif` |
| `--audio-codec` | `audioCodec`：`mp3 aac wav` |
| `--image-format` | `imageFormat`：`png jpeg pdf webp` |
| `--out-name` | `outName`；skills 模式只取 basename |
| `--output-path` | `outputPath`；仅 veconline/standalone |
| `--entry-point` | `entryPoint`（默认 `src/index.ts`） |
| `--workspace-path` | `workspacePath`（源码根相对工作区） |
| `--start-frame` / `--end-frame` / `--every-nth-frame` / `--frame` | 同名 camelCase |
| `--image-sequence` | 未给 `--export-type` 时设为 `image-sequence` |
| `--studio-sid` | 已弃用，等价 `--workspace-id` |

skills 模式前置校验：`artifactIdentifier` 必须存在、`roundTimestamp` 必须是 10 位秒、
`exportType=image-sequence` 直接拒绝。

## 云端渲染

### VECONLINE

```bash
python <skill>/scripts/ve.py render submit --composition-id MyVideo
python <skill>/scripts/ve.py render wait --task-id <id>
```

- 输出在 `<workspace>/out/`；`wait` 后若文件在本机（同一 NAS 挂载）直接返回 `local_path`。
- 不调用 `files`，不上传下载。

### VECSKILL

```bash
python <skill>/scripts/ve.py render submit --composition-id MyVideo --round-timestamp 1792650600
python <skill>/scripts/ve.py render wait --task-id <id>
```

- `--artifact-identifier` 默认取技能包目录名（如 `visionengine`）；多技能时显式传。
- `--round-timestamp` 必须来自用户本轮任务消息最后一行 `Timestamp:<10 位 Unix 秒>`；
  追问轮沿用同一个值。
- 源码默认 `workspace/{id}/`；也可用 `--workspace-path` 指定。
- 产物自动落 `artifact/{id}/_<timestamp>_artifact_<文件名>`，CLI 不会重复加前缀。
- 不支持 `image-sequence`。

## 本地 standalone 渲染

首次：

```bash
python <skill>/scripts/ve.py files workspaces
python <skill>/scripts/ve.py files create --name "我的 Remotion 项目" --local-dir .
python <skill>/scripts/ve.py files upload-project --local-dir .
python <skill>/scripts/ve.py render detect
python <skill>/scripts/ve.py render submit --composition-id MyVideo
python <skill>/scripts/ve.py render wait --task-id <id>
python <skill>/scripts/ve.py render download --task-id <id> --out ./ve-output
```

或一条：

```bash
python <skill>/scripts/ve.py render run --composition-id MyVideo \
  --workspace-name "我的 Remotion 项目" --upload --out ./ve-output
```

`render run` 的行为：

- `standalone`：有工作区就直接用；没有则要求 `--workspace-name` 创建；`--upload` 时上传
  本地工程并默认跑 `pnpm install`；渲染完成后下载到 `--out` 或 `./ve-output`。
- `veconline` / `skills`：拒绝 `--upload`，不复制产物到 `ve-output`。

## files 命令

| 命令 | MCP 工具 | 说明 |
|---|---|---|
| `files workspaces` | `list_workspaces` | 工作区列表 + 配额 |
| `files quota` | `get_workspace_quota` | 免费 2 个、已购槽位、额外槽位价格 |
| `files create --name <名称> [--local-dir .]` | `create_workspace` | 创建工作区；`--local-dir` 写 `.ve-workspace.json` |
| `files get` / `rename` / `install` | `get_workspace` / `rename_workspace` / `install_workspace` | 工作区状态/改名/安装依赖 |
| `files upload-project --local-dir .` | `upload_to_workspace` | 整目录上传（排除 node_modules/.git/out 等）+ pnpm install |
| `files list --path .` | `list_files` | `--max-depth`、`--limit`、`--mode`、`--recursive`、`--include-content` |
| `files read --path src/index.ts` | `read_file` | 只读文本类文件 |
| `files upload ./a.tsx --target-path src` | `save_file` | 本地文件上传；`.tsx/.ts` 必须显式 `--target-path` |
| `files save --source-type text --file-name a.txt --content ...` | `save_file` | 文本/base64/local_path/remote_url |
| `files download --path out/demo.mp4 --out ./ve-output` | `download_from_workspace` | 目录产物由后端打 ZIP |
| `files delete --path out/demo.mp4` | `delete_file` | 不可恢复 |

workspaceId 解析顺序：`--workspace-id` → `VE_WORKSPACE_ID` → 向上 8 层 `.ve-workspace.json`。
缺失时先 `files workspaces` 查看，或 `files create` / `files upload-project` 创建绑定。

**VECSKILL 不使用文件桥**：`files` 命令会返回 `UNSUPPORTED_IN_SKILLS`，直接用本地文件系统。

## 常见错误

| 错误码 / 现象 | 原因与处理 |
|---|---|
| `MISSING_API_KEY` | VECSKILL 走平台授权卡；本地 / VECONLINE 先向用户询问 Key，再以 `VEC_AI_API_KEY=...` 重试 |
| `WORKSPACE_REQUIRED` | 本地渲染前先创建/绑定 VECONLINE 工作区 |
| `ARTIFACT_IDENTIFIER_REQUIRED` | VECSKILL 多技能时显式传 `--artifact-identifier` |
| `INVALID_ROUND_TIMESTAMP` | 从用户消息末尾取 10 位秒；不要传毫秒 |
| `IMAGE_SEQUENCE_UNSUPPORTED` | VECSKILL 改用 video/still/audio |
| `INSUFFICIENT_CREDITS` | 渲染积分不足；提示用户充值 |
| `WORKSPACE_QUOTA_EXCEEDED` | 免费 2 个工作区已满；提示用户购买或清空（清空前征得同意） |
| `NO_RENDERABLE_PROJECT` | 工作区没有 package.json + 入口文件；先上传工程 |
| `Entry point not found` | `.tsx/.ts` 上传到了错误目录；用 `--target-path src` |
| 下载拿不到产物 | 任务未 `done`，或 `outputPath` 为空；先 `render wait` / `query` |
