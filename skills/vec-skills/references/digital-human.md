# 数字人（dh）：音色克隆 / 语音合成 / 对口型

目录
- [三步链路](#三步链路)
- [dh clone](#dh-clone)
- [dh voice](#dh-voice)
- [dh lipsync](#dh-lipsync)
- [计费与耗时](#计费与耗时)
- [常见错误](#常见错误)

## 三步链路

```
dh clone submit --video 说话视频.mp4      # 免费，产出 avatar_id（音色参考音频 + 逐字稿）
dh clone query --avatar-id <id> --wait    # status: processing → ready
dh voice submit --text "要说的内容" --avatar-id <id>   # 用克隆音色合成（按字数计费）
dh voice query --task-id <id> --wait      # 产出 wav
dh lipsync submit --video 数字人视频.mp4 --audio 驱动音频.wav   # 对口型成片（预扣 500 积分）
dh lipsync query --task-id <id> --wait --download
```

`--avatar-id` 会自动补全参考音频 URL 与逐字稿，无需手工填 `--prompt-audio-url` / `--prompt-text`。

## dh clone

```bash
ve.py dh clone submit --video talk.mp4 --name "我的音色"
ve.py dh clone query --avatar-id <id> --wait --timeout 300
```

- `--video` 接受本地路径 / 公网 URL / 用户桶内存储路径；**时长必须 8–25 秒**（越界直接 failed），≤200MB。
- 本地文件在 `FILE_MODE=remote`（默认）下先上传到工作区 `public/videos`。
- 响应：`{success, avatar_id, status: processing|ready|failed, avatar{...}}`。
  **顶层 `success` 表示"是否已就绪"，不代表请求失败**——CLI 已改为按"是否受理"输出。
- `query` 的 `--avatar-id` 是必需参数（不是 `--task-id`）；`status == "ready"` 时返回：
  - `audio_url`：参考音频签名 URL（约 1h 有效），可直接作为 voice-clone 的 `prompt_audio_url`；
  - `reference_audio_text`：逐字稿；
  - `video_path`：源视频在工作区内的存储路径（**不过期**，链式流程优先用它）。
- 该环节**不计费**；重复提交会产生重复 avatar。
- 就绪耗时：数十秒（含 ffmpeg 提取 + ASR）。

## dh voice

```bash
ve.py dh voice submit --text "你好，这是克隆音色。" --avatar-id <id>
ve.py dh voice submit --text "..." --prompt-audio-url https://.../ref.wav --prompt-text "参考音频逐字稿"
```

| 参数 | 取值 | 说明 |
|---|---|---|
| `--text` | ≤3000 字符 | 必填 |
| `--avatar-id` | — | 从 `dh clone` 拿；与下面两个参数二选一 |
| `--prompt-audio-url` | http(s) URL | 参考音频，**只接受公网 URL**（本地文件 CLI 会先上传） |
| `--prompt-text` | — | 参考音频逐字稿（必须与音频逐字对应） |
| `--nfe` | 4–64 | 扩散步数 |
| `--guidance-strength` | 0–20 | 引导强度 |
| `--guidance-method` | `cfg \| apg` | |
| `--max-chunk-chars` | 40–120 | 分块字数 |
| `--seed` | — | |

- 响应：`{task_id, task_status, credits, ...}`；`query --task-id <id>` 完成后返回 `result_url` 与 `result.audio`（采样率 24000、时长等）。
- 单次合成上限约 30 秒（含参考音频占用的预算），长文本会自动分块，但参考音频过长会挤压生成空间——克隆源视频保持 8–25s 即可。
- 产物签名 URL 约 1h 过期；`result.storage.path` 不过期，可长期复用。

## dh lipsync

```bash
ve.py dh lipsync submit --video avatar.mp4 --audio speech.wav
ve.py dh lipsync query --task-id <id> --wait --download
```

- `--video` 数字人视频、`--audio` 驱动音频；都接受本地路径 / URL / 存储路径。
- 预扣 **500 积分**，按输出秒结算；失败自动回滚。
- 产物为 mp4，`query --download`（默认开）直接落盘。

## 计费与耗时

| 环节 | 费用 | 耗时 |
|---|---|---|
| `dh clone` | 免费 | 数十秒 |
| `dh voice` | 按字数（约 0.5–1 积分/百字级，实测 20 字 ≈ 0.57 积分） | 30–180s（首次含 GPU 冷启动约 175s） |
| `dh lipsync` | 预扣 500，按输出秒结算 | 数分钟 |

## 常见错误

| 现象 | 原因与处理 |
|---|---|
| clone 提交后 `failed` | 视频时长不在 8–25s、无音轨、或下载失败；`error` 字段有中文说明 |
| `dh voice` 报缺少参考音频 | 用了 `--avatar-id` 但 clone 尚未 ready；先 `dh clone query --wait` |
| `prompt_audio_url` 被拒 | 只接受 http(s)；本地文件让 CLI 上传，或改用 `--avatar-id` |
| 合成耗时很久 | GPU 冷启动约 175s，属正常；用 `--timeout 480` 轮询 |
| 音频 URL 打不开 | 签名 URL 约 1h 过期；用 `storage.path` 重新取，或重跑 query |
