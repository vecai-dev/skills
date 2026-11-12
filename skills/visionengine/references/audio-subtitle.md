# 语音与字幕（audio / subtitle）

目录
- [audio voices](#audio-voices)
- [audio tts](#audio-tts)
- [subtitle generate](#subtitle-generate)
- [subtitle align](#subtitle-align)
- [常见错误](#常见错误)

## audio voices

```bash
python <skill>/scripts/ve.py audio voices
python <skill>/scripts/ve.py audio voices --gender female --language zh-cn
python <skill>/scripts/ve.py audio voices --offline
```

- 默认调用 `audio-tts/list-voices` MCP；失败时自动回退随包 `assets/voices.json`。
- `--offline` 只读 `assets/voices.json`，不联网。
- `--gender`：`male | female`；`--language` 做包含匹配（如 `zh-cn`）。
- `voice_type` 即 `audio tts --speaker` 要传的值。

## audio tts

```bash
python <skill>/scripts/ve.py audio tts --text "你好，世界" --speaker zh_female_vv_uranus_bigtts
python <skill>/scripts/ve.py audio tts --text "..." --speaker zh_male_m191_uranus_bigtts \
  --format mp3 --speech-rate 10 --emotion happy
```

| 参数 | 取值 | 说明 |
|---|---|---|
| `--text` | 必填 | 待合成文本 |
| `--speaker` | 音色 ID | 默认 `zh_female_vv_uranus_bigtts` |
| `--format` | `mp3 \| ogg_opus \| pcm` | 默认 mp3 |
| `--sample-rate` | 8000–48000 | 默认 24000 |
| `--speech-rate` / `--loudness-rate` | -50–100 | 默认 0 |
| `--emotion` / `--emotion-scale` | happy/sad/...、1–5 | 可选 |
| `--pitch` | -12–12 | 可选 |
| `--explicit-language` | `zh-cn en ja es-mx id pt-br de fr crosslingual` | 可选 |
| `--context-text` | 可重复 | 上下文文本 |
| `--disable-markdown-filter` | 开关 | 关闭 Markdown 过滤 |

产物默认落 `./ve-output/tts-<时间戳>.<ext>`；`--out` 可覆盖。

## subtitle generate

```bash
python <skill>/scripts/ve.py subtitle generate --audio interview.mp4 --language zh-CN --words-per-line 15
python <skill>/scripts/ve.py subtitle generate --audio https://example.com/a.mp3 --caption-type speech --use-punc
```

- 常用参数：`--language zh-CN|en-US|ja-JP|ko-KR…`；`--words-per-line`（中文建议 15，英文 55，默认 46）；
  `--max-lines` 默认 1；`--caption-type auto|speech|singing`；`--use-punc` 仅 `speech` 生效；
  `--use-itn` 中文数字转阿拉伯数字；`--use-ddc` 静音标注；`--with-speaker-info` 说话人信息。
- CLI 会先把本地音频复制到工作区缓存，再把缓存副本交给 MCP，避免往只读 `materials/` 旁写 SRT；
  完成后把 `.srt` 复制到 `./ve-output`。
- 返回 `local_path`、`task_id`、`duration`、`utterance_count`、`utterances`。
- MCP 内部同步轮询；`--no-wait` 保留但会打 warning，无法提前返回。

## subtitle align

```bash
python <skill>/scripts/ve.py subtitle align --audio voice.mp3 --text "逐字稿内容" --caption-type speech
python <skill>/scripts/ve.py subtitle align --audio voice.mp3 --text-file transcript.txt \
  --caption-type speech --sta-punc-mode 3
```

- `--caption-type` 必填：`speech | singing`。
- `--sta-punc-mode`：`1` 去句尾标点 / `2` 替换为空格 / `3` 保留原标点。
- 长文本建议用 `--text-file`。
- 输出 `_aligned.srt`，`utterances[].words[]` 含逐词时间轴（CLI 只保留段落级）。

## 常见错误

| 现象 | 原因与处理 |
|---|---|
| `MISSING_API_KEY` | VECSKILL 走平台授权卡；本地 / VECONLINE 先向用户询问 Key，再以 `VEC_AI_API_KEY=...` 重试 |
| TTS 返回错误 | 文本含不支持字符（过长/纯符号），或音色 ID 拼错 |
| 字幕一直没有 `utterances` | 音频无人声（纯音乐/静音），或语言参数与音频不匹配 |
| `subtitle align` 参数错误 | 必须给 `--caption-type speech|singing` 与逐字稿 |
| 字幕文件没落盘 | MCP 未返回 `subtitleFile`；先看 stderr/`VE_DEBUG=1` |
