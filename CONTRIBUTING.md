# Contributing / 贡献指南

Thanks for helping build this MAGI-2 prompt collection. A useful entry includes the prompt (short and/or structured PE template), playable video source URL, known model variant (`MAGI-2` or `MAGI-2-preview`), audio/reference details, and clear creator credit.

欢迎补充 MAGI-2 提示词与视频案例。请尽量提供可直接复制的提示词（短提示词或结构化 PE 分镜模板）、可播放视频外链、已知的模型版本（`MAGI-2` 旗舰版或 `MAGI-2-preview` 开源版）、音画/多素材参考信息以及清晰的来源署名。

## Media and video storage rules / 音视频存储红线

- **Never commit large `.mp4`, `.mov`, `.webm`, `.wav`, or `.mp3` files into Git.** Keep 1080p audio-enabled MP4 clips on external storage (e.g. Cloudflare R2 or verified official/source video URLs) and record the HTTPS URL in `video_url`.
- **Keep local repository previews lightweight.** Only store still cover frames or compressed thumbnails (`<= 500 KB`) inside `assets/examples/<id>/` and reference inputs (`<= 500 KB`) inside `assets/references/<id>/`.

- **严禁将大体积音视频文件提交进 Git。** 1080p 有声 MP4 统一放对象存储（如 Cloudflare R2）或保留官方/原帖 HTTPS 视频地址，写入 `video_url`。
- **仓库内仅存轻量预览图。** 本地封面帧或压缩预览图保存在 `assets/examples/<id>/`，参考素材缩略图保存在 `assets/references/<id>/`，单个本地文件不得超过 `500 KB`。

## Add a prompt case / 添加提示词案例

1. Copy the template object in [`templates/prompt.json`](templates/prompt.json) into the array in [`content/prompts.json`](content/prompts.json).
2. Keep `status` as `draft` while collecting missing metadata. Drafts are omitted from generated README and Pages outputs.
3. Fill a unique lowercase slug `id`, bilingual `title` (`en`, `zh-CN`), `category` from [`site.config.json`](site.config.json), `origin` (`original`, `official`, `community`), and `prompt_status` (`public`, `not-public`, `unverified`).
4. Separate `short_prompt` (one-line prompt) and `structured_prompt` (MAGI-2 PE JSON or timeline format when available). Never fabricate a prompt when `prompt_status` is not `public`.
5. Record `parameters` (`task_type`, `duration_sec`, `fps`, `resolution`, `aspect_ratio`, `has_audio`, `audio_mode`) and any `omni_references` (image, video, audio).
6. Set `verification.status` to `source-only` unless you ran or reproduced the clip yourself.
7. Switch `status` to `published`, regenerate, and validate locally before opening a pull request:

```bash
python3 scripts/build_readme.py
python3 scripts/build_pages.py --out _site
python3 scripts/validate.py
python3 -m unittest discover -s tests -v
```

Do not edit generated `README.md`, `README.zh-CN.md`, or `assets/badges/*.svg` files directly.

请勿直接手动修改自动生成的 `README.md`、`README.zh-CN.md` 和 `assets/badges/*.svg`。

## Suggest via GitHub Issues / 通过 Issue 推荐

- Use the [Submit a MAGI-2 prompt](https://github.com/RaphaelAI-OpenLab/awesome-magi-2-prompts/issues/new?template=submit-prompt.yml) form for new examples.
- Use [Report a problem](https://github.com/RaphaelAI-OpenLab/awesome-magi-2-prompts/issues/new?template=report-problem.yml) for broken links, model attribution corrections, or takedown requests.

## Attribution & scope / 来源与范围

- Always link directly to the original post or official demo rather than a search-results URL.
- Attributing a creator does not grant a reuse license for third-party videos or prompts; record item-level terms under `rights`.
- This repository organizes prompt templates, metadata, and developer helper scripts. It does not bundle model weights or call remote generation APIs.
