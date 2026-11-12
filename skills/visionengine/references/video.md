# 视频能力（video）

目录
- [异步任务通用模式](#异步任务通用模式)
- [img2video](#img2video)
- [text2video](#text2video)
- [style-transfer](#style-transfer)
- [recognize（视频理解）](#recognize视频理解)
- [已知限制](#已知限制)

## 异步任务通用模式

`img2video` / `text2video` / `style-transfer` / `recognize` 统一为：

```bash
python <skill>/scripts/ve.py video <能力> submit ...      # → task_id
python <skill>/scripts/ve.py video <能力> query --task-id <id> [--wait] [--no-download]
```

- `submit` 立即返回，预扣积分；`query` 默认只查一次，`--wait` 轮询到终态。
- 默认轮询 15s 一次、上限约 300s；超时不会丢任务，用 `query --task-id` 续查。
- 状态枚举：`PENDING | RUNNING | SUCCEEDED | FAILED | CANCELED`（CLI 统一大写）。
- `query` 默认下载产物到 `./ve-output` 并返回 `local_path`；`--no-download` 只回 URL。
- `video recognize` 的 MCP 没有 cancel 工具；`cancel` 会明确报错。

## img2video

```bash
python <skill>/scripts/ve.py video img2video submit --image first-frame.png --prompt "镜头缓慢推近" --duration 5 --resolution 720P
```

| 参数 | 取值 | 说明 |
|---|---|---|
| `--image` | 必填 | JPEG/PNG/BMP/WEBP，≤10MB，边长 240–8000px |
| `--prompt` | ≤1500 字符 | 动作/镜头描述 |
| `--negative-prompt` | ≤500 字符 | 负向提示词 |
| `--duration` | 2–15 秒 | 默认 5 |
| `--resolution` | `720P \| 1080P` | 默认 720P |
| `--audio` | 开关 | 让模型生成音频 |
| `--audio-input` | 文件/URL | 驱动音频（mp3/wav，3–30 秒，≤15MB） |
| `--shot-type` | `single \| multi` | `multi` 要求 prompt 扩写 |
| `--seed` | 整数 | 可选 |

本地图片会转 base64 data URL；本地音频在 `FILE_MODE=remote` 下由 MCP 上传，
需要 `VE_WORKSPACE_ID`（CLI 自动注入）。预扣 200 积分，按输出秒结算。

## text2video

```bash
python <skill>/scripts/ve.py video text2video submit --prompt "无人机掠过雪山日出，电影感" --duration 5 --size 1280*720
```

- `--prompt` 必填（≤1500 字符）；`--negative-prompt` ≤500 字符。
- `--size` 默认 `1280*720`，可选 `720*1280 960*960 1088*832 832*1088 1920*1080 1080*1920 1440*1440 1632*1248 1248*1632`。
- 其余参数同 img2video（无 `--audio` 开关，但有 `--audio-input`）。
- 预扣 300 积分。

## style-transfer

```bash
python <skill>/scripts/ve.py video style-transfer submit --video clip.mp4 --style 3 --fps 20
```

- `--video` 必填：≤30 秒、≤100MB、边长 256–4096px。
- `--style`：`0` 日式漫画 `1` 美式漫画 `2` 清新漫画 `3` 3D卡通 `4` 国风卡通 `5` 纸艺 `6` 简易插画 `7` 国风水墨。
- `--fps` 15–25（默认 15）；`--min-len` `540 | 720`；`--use-sr` 启用超分；`--no-animate-emotion` 关闭表情驱动。
- 预扣 100 积分，按输出秒结算。

## recognize（视频理解）

```bash
python <skill>/scripts/ve.py video recognize submit --video clip.mp4 --task-type understand
python <skill>/scripts/ve.py video recognize query --task-id <id>
python <skill>/scripts/ve.py video recognize result --task-id <id>
```

- `--task-type`：`understand`（默认）| `cut_effect_points` | `emotion_analysis` | `script_generate` | `style_analyze`。
- `--prompt-mode template|auto`：`auto` 必须同时给 `--prompt`。
- `--start-sec` / `--end-sec` 限定分析区间（秒）。
- MCP `submit` 是异步的，但 CLI 默认轮询到终态以保持旧语义；`--no-wait` 只返回 `task_id`。
- 返回 `status`（`SUCCEEDED` / `PARTIAL_SUCCESS` / `FAILED`）与 `result` / `usage`。
- 预扣 20 积分，按 token 结算。

## 已知限制

- **视频理解有体积上限**：服务端会把 >1.5MB 的视频切片到 ≤1.5MB 再送模型；
  若源视频码率过高导致切片仍超限，会返回 **413**。处理：先用 ffmpeg 压码率再提交。
- **style-transfer 上游会自己拉取视频 URL**：若上游拉不到（返回
  `the size of input video is out of valid range: (0,100MB]`），积分会回滚；
  换更常规的 mp4（H.264 + AAC、有真实画面）重试。
- **img2video / text2video 的驱动音频**要求公网可达 URL；本地文件由 MCP 上传，
  需要可用的 VECONLINE 工作区。
- **视频 MCP 没有 cancel 工具**；失败/超时后只能重新 submit 或等待。
