# 故障排查（troubleshooting）

目录
- [先跑自检](#先跑自检)
- [环境变量](#环境变量)
- [鉴权与端点白名单](#鉴权与端点白名单)
- [HTTP 状态码对照](#http-状态码对照)
- [积分与退款](#积分与退款)
- [超时与长任务](#超时与长任务)
- [签名 URL 过期](#签名-url-过期)
- [上传与路径](#上传与路径)
- [Windows / Git Bash 特有坑](#windows--git-bash-特有坑)
- [FILE_MODE 与共享挂载](#file_mode-与共享挂载)

## 先跑自检

```bash
python <skill>/scripts/ve.py env
```

输出 `endpoint`、`api_key_present`、`workdir`、`output_dir` 以及 `GET /api/v1/auth/me` 的结果
（`user_id` / `workspace_root` / `shared_root`）。**鉴权或端点有问题，先看这里。**

## 环境变量

| 变量 | 必需 | 默认 | 说明 |
|---|---|---|---|
| `VISION_ENGINE_API_ENDPOINT` | ✅ | 无 | 如 `https://api.visionengine-tech.com` |
| `VISION_ENGINE_API_KEY` | ✅ | 无 | Bearer 令牌 |
| `VISION_ENGINE_RENDER_ENDPOINT` | | `https://veconline-ai-api.visionengine-tech.com` | Remotion 渲染服务 |
| `VISION_ENGINE_WORKDIR` | | 当前目录 | 相对路径基准 |
| `VISION_ENGINE_OUTPUT_DIR` | | `./ve-output` | 产物落盘目录 |
| `VISION_ENGINE_FILE_MODE` | | `remote` | `remote` 自动上传 / `local` 共享挂载 |
| `VISION_ENGINE_REMOTION_WORK_DIR` | | `/vec` | `local` 模式的挂载根 |

缺失时 CLI 会直接报错并给出示例，退出码 1。所有命令也接受 `--endpoint` / `--api-key` / `--timeout` 临时覆盖。

**密钥只经环境变量注入，不要写进任何文件或提交到仓库。**

## 鉴权与端点权限

- 只有已开放的接口接受 API Key；管理类接口需要更高权限的令牌。
- 典型无权访问（会 401）：`/api/v1/image-edit/save`、studio 项目路由、部分管理端点。
- `api` 透传不等于全通——透传被 401 时，说明该接口未向 API Key 开放。
- 令牌无效/过期 → 401；令牌有效但无该资源权限 → 403。

## HTTP 状态码对照

| 状态码 | 含义 | 处理 |
|---|---|---|
| 400 | 参数错误（`detail` 里通常有中文说明） | 按提示改参数 |
| 401 | 缺少/无效 API Key | 检查 `VISION_ENGINE_API_KEY` |
| 402 | 积分不足（`INSUFFICIENT_CREDITS`） | 充值；注意渲染积分与媒体积分可能是不同池 |
| 403 | 资源不属于当前用户 | 检查 `--avatar-id` / `task_id` / 存储路径属主 |
| 404 | 路径或任务不存在 | 核对端点；`task_id` 拼写 |
| 413 | 体积超限 | 压缩输入；见下 |
| 422 | 上游校验失败（如视频理解输出不合规） | 换更常规的素材重试 |
| 500 | 服务端异常 | 重试；持续失败看 `error` 字段 |
| 503 | 上游模型不可用 | 稍后重试 |

## 积分与退款

- 异步任务（视频生成/克隆/对口型）**先预扣**、完成后按实际用量结算；失败自动回滚，
  `billing_status` 会显示 `settled` / `rolled_back`。
- 预扣额度：img2video 200、text2video 300、style-transfer 100、lipsync 500、video recognize 20、LLM 20。
- 每次 `query` 都返回 `billing_status`，可据此判断是否已退款。

## 超时与长任务

- 默认单次请求超时 60s；图片类放宽到 180s；视频理解/克隆/对口型放宽到 600s。
- `--wait` 的轮询上限默认 300s（`--timeout` 可调）。**超时不会丢任务**：
  用 `query --task-id <id>` 继续查即可。
- GPU 语音克隆首次调用含冷启动，约 175s 属正常。
- `video recognize submit` 是同步阻塞调用，不要用 `--wait` 概念套它。

## 签名 URL 过期

| 来源 | 有效期 |
|---|---|
| 私有产物链接（克隆参考音频、克隆产物） | 约 1h |
| 生成类产物链接（图片编辑、视频生成） | 约 24h |

链式流程请传递**存储路径**（`storage.path` / `video_path`，不过期），URL 只在下载时即时获取；
过期就重新 `query` 一次拿新 URL。

## 上传与路径

- 相对路径以 `VISION_ENGINE_WORKDIR` 为基准解析。
- 上传阈值 8MB：以下单次 multipart，以上 4MB 分片（CLI 自动复用 `upload_id`）。
- 同名冲突服务端自动改名 → 用返回的 `file.path`，不要假设文件名。
- 代码文件（`.tsx`/`.ts`）上传必须 `--target-path src`。

## Windows / Git Bash 特有坑

- **MSYS 路径改写**：Git Bash 会把 `/api/v1/...` 参数改写成 `C:/Program Files/Git/api/v1/...`。
  CLI 的 `api` 命令已自动还原；其它命令若发现路径被改写，可用 `MSYS_NO_PATHCONV=1` 前缀禁用：
  ```bash
  MSYS_NO_PATHCONV=1 python ve.py api GET /api/v1/files/list
  ```
- **HTTP 头不能承载中文**：`subtitle` 的 `X-Media-Filename` 会被 ASCII 化；中文文件名建议改用 URL 输入。
- **控制台编码**：CLI 启动时把 stdout/stderr 强制为 UTF-8，重定向到文件时中文不会乱码。
  若你另写 Python 片段或 shell 管道处理输出（如 `python -c ...`、`... | python -m json.tool`），
  Windows 下它们仍会用 GBK 解码而显示乱码——给这些命令加 `PYTHONUTF8=1` 前缀即可，与 CLI 本身无关。
- `FILE_MODE=local` 依赖 POSIX 挂载路径，**Windows 客户端不可用**（`relative_to` 会失败），请用默认 `remote`。

## FILE_MODE 与共享挂载

- `remote`（默认）：需要 URL 的媒体先 `POST /save` 上传，再拼 `/shared/<path>?download=true`。
- `local`：文件已在共享挂载（`VISION_ENGINE_REMOTION_WORK_DIR`，默认 `/vec`）之下，直接改写成 `/shared` URL，不重复上传。
  仅适用于服务端 / 已挂载环境。
