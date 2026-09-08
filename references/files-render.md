# 工作区文件与 Remotion 渲染（files / render）

目录
- [files 命令](#files-命令)
- [上传规则](#上传规则)
- [路径映射](#路径映射)
- [render 命令](#render-命令)
- [渲染前置条件](#渲染前置条件)
- [常见错误](#常见错误)

## files 命令

| 命令 | 端点 | 说明 |
|---|---|---|
| `files list` | `GET /api/v1/files/list` | `--path`、`--max-depth`、`--limit`、`--mode`（`children\|tree\|file`）、`--include-hidden`、`--include-content` |
| `files read` | `GET /api/v1/files/list` + `mode=file&include_content=true` | **没有独立 read 端点**；CLI 已封装 |
| `files upload` | `POST /save`（≤8MB）或 `POST /save/chunk` | `--source local\|url`、`--target-path`、`--file-name` |
| `files download` | `GET /shared/{user_id}/{path}?download=true` | 需先 `GET /api/v1/auth/me` 拿 user_id |
| `files delete` | `DELETE /api/v1/files/delete?path=` | 不可恢复 |

`list` 返回的 `preview_url` / `download_url` 是**相对路径**（`/shared/...`），需要拼上 endpoint 才能访问。

## 上传规则

- **≤8MB** → 一次 multipart `POST /save`（字段：`file`、`file_name`、`path`=目标**目录**）。
- **>8MB** → `POST /save/chunk`，4MB 分片，**所有分片复用同一个 `upload_id`**（CLI 自动生成并复用），
  只有最后一片的响应带 `file` 对象。
- 同名冲突时后端**自动改名**（`a.png` → `a-1.png`）→ **一律使用返回的 `file.path`**。
- `--source url`：CLI 先下载到本地临时文件再走上面流程（替代已下线的 `/api/v1/save-remote`）。

## 路径映射

`--target-path` 省略时后端按 content-type 推断：

| 类型 | 落点 |
|---|---|
| `image/*` | `public/images` |
| `video/*` | `public/videos` |
| `audio/*` | `public/audio` |
| `font/*` | `public/fonts` |
| 其它 | `public/documents` |

**`.tsx` / `.ts` 等代码文件必须显式 `--target-path src`**，否则会落到 `public/documents`，渲染时找不到 composition。

## render 命令

| 命令 | 端点（render_endpoint） |
|---|---|
| `render submit` | `POST /api/render-tasks` |
| `render query` | `GET /api/render-tasks/{id}` |
| `render list` | `GET /api/render-tasks?studioOpaqueId=&limit=` |
| `render cancel` / `retry` | `POST /api/render-tasks/{id}/cancel|retry` |
| `render download` | `GET /api/render-tasks/{id}/file?filename=<out_name>` |

`render submit` 常用参数：

```bash
ve.py render submit --composition-id MyVideo --export-type video --codec h264 \
  --input-props '{"title":"你好"}' --out-name out/my-video.mp4
```

- `--composition-id` 必填；`--export-type`：`video | still | audio | image-sequence`。
- `--codec`：`h264 h265 vp8 vp9 prores gif`；`--audio-codec`：`mp3 aac wav`；`--image-format`：`png jpeg pdf webp`。
- `--input-props` 接受 JSON 字符串或 `@文件路径`。
- `--out-name` 省略时后端默认 `out/<compositionId>.<ext>`（image-sequence 为 `out/<compositionId>-frames`）。
- `--entry-point` 默认 `src/index.ts`；`--start-frame` / `--end-frame` / `--every-nth-frame` / `--frame`（still 用）。
- `--studio-sid` 写入 body 的 `studioOpaqueId`（默认 `api`）——**请求头方式无效**。
- 响应被包在 `{success, data:{taskId}}` / `{success, data: record}` / `{success, data:[...]}` 里，CLI 已解包。

`render query` 状态：`queued | bundling | rendering | encoding | done | failed | canceled`；
`--wait` 轮询到 `done`/`failed`/`canceled`，`--download` 完成后自动下载。
产物名取自任务记录的 `out_name`（任务记录里**没有** URL 字段）。

`render download` 对**目录产物**（image-sequence）会自动打包成 zip。

## 渲染前置条件

`render submit` 只提交任务，**composition 必须已存在于用户工作区**：

```bash
ve.py files upload ./MyVideo.tsx --target-path src        # 代码进 src
ve.py files upload ./bgm.mp3  --target-path public/audio  # 素材进 public/*
ve.py render submit --composition-id MyVideo
```

提交成功不代表渲染成功——`query --wait` 会透出 `error` / `message`。

## 常见错误

| 现象 | 原因与处理 |
|---|---|
| 402 `INSUFFICIENT_CREDITS` | 渲染积分不足（与媒体积分池不同），需充值 |
| submit 404 / composition not found | `.tsx` 上传到了 `public/documents`；重传并 `--target-path src` |
| 上传后文件名变了 | 同名冲突自动改名；用返回的 `file.path` |
| 大文件上传后文件缺失 | 分片未复用 `upload_id`；用本 CLI（已修复该问题） |
| download 拿不到产物 | 任务未 `done`，或 `out_name` 为空；先 `render query` |
| `files list` 的 URL 打不开 | 返回的是相对路径，需拼 `VISION_ENGINE_API_ENDPOINT` |
