# Changelog

## 2026-11-27 — Remove GitHub Pages

- Remove GitHub Pages generator (`scripts/build_pages.py`), deployment workflow (`.github/workflows/deploy-pages.yml`), page tests (`tests/test_pages.py`), and `pages` configuration to keep traffic focused on the GitHub repository and `raphael.app`.

## 2026-11-26 — Initial 10 MAGI-2 video cases from CMS

- Import 10 curated MAGI-2 community cases from Directus CMS `magi2_materials` covering all 6 repository categories (dialogue lip-sync, multi-shot storytelling, omni-reference consistency, vertical UGC commercials, EDM/ambient SFX, and mixed-media/fantasy animation).
- Link playable audio-enabled 1080p/1440p MP4 videos hosted on Cloudflare R2 (`video_url`) while storing only lightweight (`< 500 KB`) extracted cover frames under `assets/examples/<id>/preview.jpg`.
- Generate `README.md`, `README.zh-CN.md`, and 20 bilingual standalone case pages (`cases/<id>/README*.md`), and pass `scripts/validate.py --release`.

## 2026-11-26 — Repository MVP scaffold

- Initialize `awesome-magi-2-prompts` structure with single-source `site.config.json` and `content/prompts.json`.
- Add video-native prompt schema (`short_prompt`, `structured_prompt`, `omni_references`, `task_type`, `duration_sec`, `fps`, `resolution`, `has_audio`, `video_url`) with `<= 500 KB` preview enforcement and `.mp4`/audio Git exclusions.
- Add `SKILL.md` and `examples/pe_template_helper.py` plus T2V/I2V structured PE templates aligned with `SandAI-org/MAGI-2-preview`.
- Add dependency-free README generator (`README.md`, `README.zh-CN.md`), GitHub Pages audio-video cheat sheet generator, validation workflow, CMS stats sync workflow (`magi2_materials`), and regression tests.
