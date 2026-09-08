# 语音与字幕（audio / subtitle）

目录
- [audio voices](#audio-voices)
- [audio tts](#audio-tts)
- [subtitle generate](#subtitle-generate)
- [subtitle align](#subtitle-align)
- [计费与耗时](#计费与耗时)
- [常见错误](#常见错误)

## audio voices

```bash
ve.py audio voices                       # 全部 10 个音色
ve.py audio voices --gender female --language zh-cn
```

- **纯本地**，不联网、不计费；数据来自随包分发的离线音色目录 `assets/voices.json`。
- `--gender` 只接受 `male | female`；`--language` 做包含匹配（如 `zh-cn`）。
- `voice_type` 即 `audio tts --speaker` 要传的值。

## audio tts

```bash
ve.py audio tts --text "你好，世界" --speaker zh_female_vv_uranus_bigtts
ve.py audio tts --text "..." --speaker zh_male_m191_uranus_bigtts --format mp3 --speech-rate 10 --emotion happy
```

请求体是带 `user` / `req_params` 信封的结构（CLI 已封装）：

```json
{
  "user": { "uid": "ve-cli" },
  "req_params": {
    "text": "待合成文本",
    "speaker": "zh_female_vv_uranus_bigtts",
    "audio_params": { "format": "mp3", "sample_rate": 24000, "speech_rate": 0, "loudness_rate": 0, "emotion": "happy", "emotion_scale": 4 },
    "additions": "{\"cache_config\":{\"text_type\":1,\"use_cache\":true}, ...}"
  },
  "model_id": "@preset/vec-1-0-audio-tts",
  "resource_id": "@preset/vec-1-0-audio-tts"
}
```

- **响应是 NDJSON 流**（逐行 JSON）：`code==0` 的行携带 base64 音频分片，`code==20000000` 表示结束，其它 code 是错误。
  CLI 已逐行拼接并落盘为 `local_path`（默认 mp3）。
- `--format`：`mp3 | ogg_opus | pcm`；`--sample-rate` 默认 24000。
- `--speech-rate` / `--loudness-rate` 区间 -50~100；`--emotion-scale` 1~5；`--pitch` -12~12。
- `--explicit-language`：`zh-cn en ja es-mx id pt-br de fr crosslingual`。
- `--context-text` 可重复；`--disable-markdown-filter` 关闭 Markdown 过滤。
- 落盘扩展名：`ogg_opus` → `.ogg`，`pcm` → `.pcm`。

## subtitle generate

```bash
ve.py subtitle generate --audio interview.mp4 --language zh-CN --words-per-line 15
ve.py subtitle generate --audio https://example.com/a.mp3 --caption-type speech --use-punc
```

**协议特殊**：参数走 **query string**，媒体字节走 **原始请求体**，文件名走请求头。

- `POST /api/v1/subtitle/generate/submit?model_id=...&language=...&words_per_line=...&max_lines=...&caption_type=...&use_itn=true&use_punc=true&use_ddc=true&with_speaker_info=true`
- 请求头 `X-Media-Filename: <ASCII 文件名>`（本地文件）或 `X-Media-Url: <url>`（URL 输入，body 为空）。
  **文件名含中文时会被 ASCII 化**（HTTP 头只能承载 latin-1）——用 URL 输入可避免。
- 本地文件直接读原始字节，**不经过 /save 上传**。
- 查询：`GET /api/v1/subtitle/generate/query?id=<task_id>&blocking=0`；`code==0` 完成、`code==2000` 处理中、其它为错误。
- CLI 默认轮询到完成并写出 `.srt`（`HH:MM:SS,mmm`，来自 `utterances[].{text,start_time,end_time}`），
  返回 `local_path` 与 `utterances`。`--no-wait` 只提交并打印 task_id。

常用参数：`--language zh-CN|en-US|ja-JP|ko-KR…`；`--words-per-line`（中文建议 15，英文 55，默认 46）；
`--max-lines` 默认 1；`--caption-type auto|speech|singing`；`--use-punc` 仅 `caption-type=speech` 生效；
`--use-itn` 中文数字转阿拉伯数字；`--use-ddc` 静音标注。

## subtitle align

```bash
ve.py subtitle align --audio voice.mp3 --text "逐字稿内容" --caption-type speech
ve.py subtitle align --audio voice.mp3 --text-file transcript.txt --caption-type speech --sta-punc-mode 3
```

- 与 generate 同协议，参数含 `caption_type`（**必填** `speech|singing`）与 `audio_text`（逐字稿）。
- **`audio_text` 放在 URL 查询串里**：长文本会撞网关 URL 长度限制，超过 ~1500 字符时 CLI 会打印警告；
  此时改用 `--text-file`（仍然走查询串）或先用 `subtitle generate`。
- 输出 `_aligned.srt`，`utterances[].words[]` 含逐词时间轴（CLI 只保留段落级）。

## 计费与耗时

- `audio tts` 按字符计费，极低；单次 1–3s。
- `subtitle generate` / `align` 使用语音识别，按音频时长计费；12s 音频约 10–30s 完成。
- 上传/识别失败会自动退款（`billing_status` 反映）。

## 常见错误

| 现象 | 原因与处理 |
|---|---|
| `code=2000` 一直不变 | 仍在处理中；`--no-wait` 后可再查 `api GET /api/v1/subtitle/generate/query --query id=...` |
| 中文文件名导致 400/500 | 请求头无法承载非 ASCII；改用 URL 输入或重命名文件 |
| align 提交后 414/400 | `audio_text` 过长触发 URL 长度限制，拆短或改用 generate |
| TTS 返回 `code != 0` | 文本含不支持字符（如过长/纯符号），或音色 ID 拼错 |
| 没有 `utterances` | 音频无人声（纯音乐/静音），或语言参数与音频不匹配 |
