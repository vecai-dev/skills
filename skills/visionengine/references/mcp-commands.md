# CLI → MCP 全量映射

本文是维护者参考：每个 CLI 命令对应哪个 MCP 包、哪个工具、关键参数是什么。
技能运行时只需要看 SKILL.md 和各能力参考文档。

## 包与启动命令

| key | npm 包 | PATH 命令 | 工具 |
|---|---|---|---|
| `image-generate` | `@visionengine/image-generate` | `ve-image-generate` | `generate` `edit` `generateFromImages` |
| `image-edit` | `@visionengine/image-edit` | `ve-image-edit` | `edit` |
| `image-recognize` | `@visionengine/image-recognize` | `ve-image-recognize` | `visual` `text` `prompt_reverse` |
| `audio-tts` | `@visionengine/audio-tts` | `ve-audio-tts` | `tts` `list-voices` |
| `subtitle-generate` | `@visionengine/subtitle-generate` | `ve-subtitle-generate` | `subtitle_generate` `subtitle_align` |
| `video-style-transfer` | `@visionengine/video-style-transfer` | `ve-video-style-transfer` | `submit` `query` |
| `img2video` | `@visionengine/img2video` | `ve-img2video` | `submit` `query` |
| `text2video` | `@visionengine/text2video` | `ve-text2video` | `submit` `query` |
| `video-recognize` | `@visionengine/video-recognize` | `ve-video-recognize` | `submit` `query` |
| `digital-human` | `@visionengine/digital-human` | `ve-digital-human` | `clone_submit` `clone_query` `voice_submit` `voice_query` `lipsync_submit` `lipsync_query` |
| `render` | `@visionengine/render` | `ve-render` | `get_context` `detect` `submit` `query` `wait` `list` `cancel` `retry` |
| `remotion-file-bridge` | `@visionengine/remotion-file-bridge` | `ve-remotion-file-bridge` | `list_workspaces` `get_workspace_quota` `create_workspace` `get_workspace` `rename_workspace` `upload_to_workspace` `install_workspace` `download_from_workspace` `list_files` `read_file` `download_file` `save_file` `delete_file` |

启动优先级：

1. `VE_MCP_BIN_<KEY>`（开发调试，如 `VE_MCP_BIN_RENDER="node .../dist/index.js"`）；
2. PATH 上的 `ve-*`（云端 entrypoint 预装，推荐）；
3. `npx -y @visionengine/<pkg>@latest`。

## CLI 命令映射

| CLI | MCP 包 | 工具 | 关键参数 |
|---|---|---|---|
| `image generate` | image-generate | `generate` | `prompt` `aspectRatio` `imageSize` `modelId` |
| `image edit` | image-generate | `edit` | `imagePath`（单图）`prompt` |
| `image edit-advanced` | image-edit | `edit` | `imagePaths` `prompt` `negativePrompt` `n` `size` `promptExtend` `watermark` `seed` `model` `outputDir` |
| `image generate-from-images` | image-generate | `generateFromImages` | `imagePaths` `prompt` `aspectRatio` `imageSize` |
| `image recognize` | image-recognize | `visual` / `text` | `imagePath` `prompt` `modelId` |
| `image prompt-reverse` | image-recognize | `prompt_reverse` | `imagePath` `outputLanguage` `userPrompt` |
| `audio tts` | audio-tts | `tts` | `text` `speaker` `format` `sampleRate` `speechRate` `loudnessRate` `emotion` `emotionScale` `pitch` `contextTexts` `explicitLanguage` `disableMarkdownFilter` `outputPath` |
| `audio voices` | audio-tts | `list-voices` | `language`；`--offline` 只读本地目录 |
| `subtitle generate` | subtitle-generate | `subtitle_generate` | `audioPath` `language` `wordsPerLine` `maxLines` `useItn` `captionType` `usePunc` `useDdc` `withSpeakerInfo` |
| `subtitle align` | subtitle-generate | `subtitle_align` | `audioPath` `subtitleText` `captionType` `staPuncMode` |
| `video img2video submit` | img2video | `submit` | `imagePath` `prompt` `negativePrompt` `audioPath` `duration` `resolution` `audio` `shotType` `promptExtend` `watermark` `seed` |
| `video img2video query` | img2video | `query` | `taskId` `downloadResult` `outputPath` |
| `video text2video submit` | text2video | `submit` | `prompt` `negativePrompt` `audioPath` `size` `duration` `shotType` `promptExtend` `watermark` `seed` |
| `video text2video query` | text2video | `query` | `taskId` `downloadResult` `outputPath` |
| `video style-transfer submit` | video-style-transfer | `submit` | `videoPath` `style` `videoFps` `minLen` `animateEmotion` `useSR` |
| `video style-transfer query` | video-style-transfer | `query` | `taskId` `downloadResult` `outputPath` |
| `video recognize submit` | video-recognize | `submit` | `video` `taskType` `promptMode` `userPrompt` `analysisRange` `responseFormat` `stream` |
| `video recognize query/result` | video-recognize | `query` | `taskId` |
| `dh clone submit` | digital-human | `clone_submit` | `videoPath` `name` |
| `dh clone query` | digital-human | `clone_query` | `avatarId` |
| `dh voice submit` | digital-human | `voice_submit` | `promptAudioUrl` `promptText` `text` `nfe` `guidanceStrength` `guidanceMethod` `maxChunkChars` `seed` |
| `dh voice query` | digital-human | `voice_query` | `taskId` `downloadResult` `outputPath` |
| `dh lipsync submit` | digital-human | `lipsync_submit` | `videoPath` `audioPath` |
| `dh lipsync query` | digital-human | `lipsync_query` | `taskId` `downloadResult` `outputPath` |
| `files workspaces` | remotion-file-bridge | `list_workspaces` | 无 |
| `files quota` | remotion-file-bridge | `get_workspace_quota` | 无 |
| `files create` | remotion-file-bridge | `create_workspace` | `name` `description` `template` `localDir` |
| `files get/rename/install` | remotion-file-bridge | `get_workspace` / `rename_workspace` / `install_workspace` | `workspaceId`（rename 另加 `name`） |
| `files upload-project` | remotion-file-bridge | `upload_to_workspace` | `localDir` `workspaceId` `install` |
| `files list` | remotion-file-bridge | `list_files` | `path` `maxDepth` `limit` `mode` `recursive` `includeContent` |
| `files read` | remotion-file-bridge | `read_file` | `path` |
| `files upload/save` | remotion-file-bridge | `save_file` | `sourceType` `fileName` `localPath`/`content` `targetPath` `contentType` `overwrite` |
| `files download` | remotion-file-bridge | `download_from_workspace` | `path` `localDir` `workspaceId` |
| `files delete` | remotion-file-bridge | `delete_file` | `path` `workspaceId` |
| `render context` | render | `get_context` | 无（不需要 Key） |
| `render detect` | render | `detect` | `system` `workspaceId` `workspacePath` `artifactIdentifier` `usageType` |
| `render submit` | render | `submit` | `compositionId` + 渲染参数 + 上下文参数 |
| `render query/wait` | render | `query` / `wait` | `taskId`、`timeoutSeconds`/`intervalSeconds` |
| `render list/cancel/retry` | render | `list` / `cancel` / `retry` | `limit`/`system`/`workspaceId`、`taskId` |

## 子进程环境契约

CLI 为每个 MCP 子进程构造完整 env（继承 `os.environ` 后覆盖）：

| 变量 | 值 |
|---|---|
| `VEC_AI_API_KEY` | 由 `VEC_AI_API_KEY` 注入（缺失时不设置） |
| `WORKDIR` | 工作区根目录（`ctx.project_dir`） |
| `DEFAULT_OUTPUT_DIR` | `ctx.output_dir` |
| `FILE_MODE` | `veconline`/`skills` → `local`；`standalone` → `remote` |
| `REMOTION_WORK_DIR` | 默认 `/vec`，可用 `VEC_AI_REMOTION_WORK_DIR` 覆盖 |
| `VE_USAGE_TYPE` | `veconline` / `skills` / `standalone` |
| `VE_WORKSPACE_ID` | 解析到的 `conv-<uuid>` |
| `VE_SKILL_IDENTIFIER` | VECSKILL 技能标识符 |
| `BASE_URL` | `VEC_AI_API_URL`，默认 `https://api.visionengine-tech.com` |
| `RENDER_BACKEND_URL` | `VEC_AI_RENDER_URL`，默认 `https://veconline-ai-api.visionengine-tech.com` |
| `WORKSPACE_API_URL` | 同 `RENDER_BACKEND_URL`（file bridge 工作区接口） |
| `npm_config_update_notifier` / `npm_config_fund` / `npm_config_audit` | `false` |
| `npm_config_cache` | skills 模式下 `workspace/{id}/.ve-cache/npm` |

媒体 MCP 在 `FILE_MODE=remote` 时上传本地文件需要 `VE_WORKSPACE_ID`；CLI 会自动注入。

## 版本与发布

- 技能包 2.0.0 依赖 `@visionengine/*@latest`。
- `video-style-transfer` 本地 1.0.7 需先发布到 npm（1.0.6 也可用，但 1.0.7 包含最新修复）。
- 媒体 MCP 的 `/save` 上传已补 `workspace_id` 并优先使用后端返回的 `root_path` 拼 `/shared`；
  发布前请确认 npm latest 包含该修复。
