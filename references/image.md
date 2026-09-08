# 图片能力（image）

目录
- [命令总览](#命令总览)
- [generate / edit / generate-from-images](#generate--edit--generate-from-images)
- [edit-advanced](#edit-advanced)
- [recognize](#recognize)
- [prompt-reverse](#prompt-reverse)
- [输入图片怎么传](#输入图片怎么传)
- [计费与耗时](#计费与耗时)
- [常见错误](#常见错误)

## 命令总览

| 命令 | 端点 | 返回形态 |
|---|---|---|
| `image generate` | `POST /api/v1/image-generate/generate` | base64（自动落盘） |
| `image edit` | `POST /api/v1/image-generate/edit` | base64（自动落盘） |
| `image generate-from-images` | `POST /api/v1/image-generate/generate-from-images` | base64（自动落盘） |
| `image edit-advanced` | `POST /api/v1/image-edit/edit` | 公网 URL（自动下载落盘） |
| `image recognize` | `POST /api/v1/image-recognize/analyze` | 文本 |
| `image prompt-reverse` | `POST /api/v1/image-prompt-reverse/reverse` | 提示词文本 |

所有命令都返回 `local_paths` / `content` 等已处理好的字段，**不要**再去解析原始响应。

## generate / edit / generate-from-images

请求体：

```json
{
  "model": "@preset/vec-1-0-image-generate",
  "prompt": "描述文本",
  "image_config": { "aspect_ratio": "9:16", "image_size": "1K" },
  "images": [{ "type": "base64_data_url", "data": "data:image/png;base64,..." }]
}
```

- `--aspect-ratio` 取值：`1:1 2:3 3:2 3:4 4:3 4:5 5:4 9:16 16:9 21:9`（默认 `9:16`）。
- `--image-size`：`1K | 2K | 4K`（默认 `1K`）。
- `image edit` / `generate-from-images` 必须给 `--image`（可重复），`generate` 不要给。
- 返回：`choices[0].message.images[].image_url.url` 是 data URL；CLI 已解码落盘并返回 `local_paths`。
- 单张成本约 **$0.04**（14400 image tokens），耗时 15–30s。
- **竖版偶尔被旋转 90°**：上游模型对 `9:16` 请求偶发返回横置画面（尺寸仍是 1440×2560，但地平线竖直）。
  提示词里显式写"竖版竖向构图、地平线保持水平"可降低概率；若产物方向不对，重生成一次即可，
  不要把它当成 CLI 的 bug（CLI 只负责落盘与尺寸校验）。

## edit-advanced

请求体：

```json
{
  "prompt": "编辑指令（1-800 字符）",
  "images": [{ "type": "base64_data_url", "data": "..." }],
  "parameters": { "n": 1, "negative_prompt": "≤500 字符", "prompt_extend": true, "watermark": false, "size": "1024*1024", "seed": 0 }
}
```

- `--image` 1–3 张；`--n` 1–6；`--size` 形如 `1024*1024`（`WIDTH*HEIGHT`）。
- 与 `image generate` 不同：**返回的是公网 URL**（约 24h 有效），CLI 会自动下载到 `local_paths`。
- 成本很低（按张计费），单张约数秒。

## recognize

```bash
ve.py image recognize --image photo.jpg --tool visual     # 设计元素/构图/配色分析
ve.py image recognize --image chart.png --tool text       # OCR + 结构化数据提取
```

- `--tool` **必填**：`visual` | `text`。不传 `--prompt` 时使用内置默认提示词（视觉分析 / 文字提取两套）。
- 返回 `content`（`choices[0].message.content`）。
- 单次成本约 $0.002。

## prompt-reverse

```bash
ve.py image prompt-reverse --image photo.jpg --output-language zh
```

- `--output-language`：`zh | en`（默认 `en`）。
- `--user-prompt` 可选，追加自定义约束。
- 返回 `prompt`。成本约 $0.001。

## 输入图片怎么传

`--image` 接受三种值，按顺序判定：

1. `http(s)://` / `data:` URL → 原样透传；
2. 本地文件路径（相对 `VISION_ENGINE_WORKDIR`）→ CLI 读文件转 **base64 data URL** 内联；
3. 其它字符串 → 视为用户桶内存储路径（服务端强校验属主）。

图片类默认内联 base64，**不会**写入用户的 Remotion 工作区。

## 计费与耗时

- 生成/编辑类按张计费（`image generate` 约 $0.04/张），识别/反推按 token 计费（约 $0.001–0.002）。
- 生成类耗时 15–30s；CLI 对该类命令的 HTTP 超时已放宽到 180s。

## 常见错误

| 现象 | 原因与处理 |
|---|---|
| `image edit-advanced` 返回 URL 但下载失败 | 产物 URL 约 24h 过期；重新执行命令即可 |
| 400 `images is required` | `edit` / `generate-from-images` 忘了 `--image` |
| 400 `prompt` 长度错误 | `edit-advanced` 的 prompt 限 1–800 字符 |
| 402 INSUFFICIENT_CREDITS | 账户积分不足，先充值 |
| 413 | 输入图片过大，压缩后再传 |
