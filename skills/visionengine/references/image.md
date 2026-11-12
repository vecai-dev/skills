# 图片能力（image）

目录
- [命令总览](#命令总览)
- [generate / edit / generate-from-images](#generate--edit--generate-from-images)
- [edit-advanced](#edit-advanced)
- [recognize](#recognize)
- [prompt-reverse](#prompt-reverse)
- [输入图片怎么传](#输入图片怎么传)
- [常见错误](#常见错误)

## 命令总览

| 命令 | MCP 包/工具 | 返回形态 |
|---|---|---|
| `image generate` | `image-generate/generate` | 落盘图片，返回 `local_paths` |
| `image edit` | `image-generate/edit` | 落盘图片，返回 `local_paths` |
| `image generate-from-images` | `image-generate/generateFromImages` | 落盘图片，返回 `local_paths` |
| `image edit-advanced` | `image-edit/edit` | 落盘图片，返回 `local_paths` |
| `image recognize` | `image-recognize/visual` 或 `text` | 文本 `content` |
| `image prompt-reverse` | `image-recognize/prompt_reverse` | 提示词文本 `prompt` |

产物默认落 `./ve-output`（`--out` 可覆盖）。不要解析原始 MCP 响应，使用 CLI 的
`local_paths` / `content` / `prompt` 字段。

## generate / edit / generate-from-images

```bash
python <skill>/scripts/ve.py image generate --prompt "一只橘猫在窗台晒太阳" --aspect-ratio 9:16
python <skill>/scripts/ve.py image edit --image cat.png --prompt "把背景换成雨天"
python <skill>/scripts/ve.py image generate-from-images --image ref.png --prompt "保持风格，换成夜景"
```

- `--aspect-ratio`：`1:1 2:3 3:2 3:4 4:3 4:5 5:4 9:16 16:9 21:9`（默认 `9:16`）。
- `--image-size`：`1K | 2K | 4K`（默认 `1K`）。
- `image edit` 只接受单张 `--image`；`generate-from-images` 可重复 `--image`；`generate` 不要给。
- 竖版偶尔被上游旋转 90°；提示词显式写“竖版竖向构图、地平线保持水平”可降低概率。

## edit-advanced

```bash
python <skill>/scripts/ve.py image edit-advanced \
  --image a.png --image b.png --prompt "把两张图合成一张海报" --n 2 --size 1024*1024
```

- `--image` 1–3 张；`--n` 1–6；`--size` 形如 `1024*1024`。
- `--negative-prompt` ≤500 字符；`--no-prompt-extend` 关闭提示词扩写；`--watermark` 加水印。
- 输出目录固定为 CLI 的 `--out`（默认 `./ve-output`）。

## recognize

```bash
python <skill>/scripts/ve.py image recognize --image photo.jpg --tool visual
python <skill>/scripts/ve.py image recognize --image chart.png --tool text
```

- `--tool` 必填：`visual`（设计元素/构图/配色）| `text`（OCR/结构化数据）。
- `--prompt` 可选；不传时用 MCP 内置默认提示词。
- 返回纯文本 `content`。

## prompt-reverse

```bash
python <skill>/scripts/ve.py image prompt-reverse --image photo.jpg --output-language zh
```

- `--output-language`：`zh | en`（默认 `en`）。
- `--user-prompt` 可选，追加自定义约束。
- 返回 `prompt` 文本。

## 输入图片怎么传

`--image` 接受：

1. `http(s)://` / `data:` URL → 原样透传；
2. 本地文件路径 → 图片生成/编辑 MCP 自行读取；CLI 对需要 URL 的图像输入会转 base64；
3. 其它字符串 → 视为用户桶内存储路径（服务端校验属主）。

图片类默认内联 base64 或直接由 MCP 读取本地文件，**不会**写入 Remotion 工作区。

## 常见错误

| 现象 | 原因与处理 |
|---|---|
| `MISSING_API_KEY` | 先向用户询问 Key，再以 `VEC_AI_API_KEY=...` 重试 |
| `image edit` 多图报错 | 只接受单图；多图改用 `edit-advanced` |
| 400 prompt 长度错误 | `edit-advanced` 的 prompt 限 1–800 字符 |
| 402 `INSUFFICIENT_CREDITS` | 账户积分不足，先充值 |
| 413 | 输入图片过大，压缩后再传 |
| 产物方向不对 | 上游偶发旋转；重生成一次，或用提示词强调竖向构图 |
