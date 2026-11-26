---
name: awesome-magi-2-prompts
description: Query and apply MAGI-2 & MAGI-2-preview video prompts, synced audio patterns, Omni-Reference inputs, and structured PE (Prompt Enhancement) JSON templates from this repository.
---

# Awesome MAGI-2 Prompts Skill

Use this repository as a structured source of **MAGI-2** (480B flagship, 4–30s 1080p/25fps, Omni-Reference up to 20 media items) and **MAGI-2-preview** (114B/6B Apache 2.0, 10s 1080p) video prompts.

## Where data lives

- `site.config.json`: Canonical repository slug, category IDs, model IDs (`magi-2`, `magi-2-preview`), and brand configuration.
- `content/prompts.json`: Single source of truth for all published cases (`status == "published"`), each carrying:
  - `short_prompt`: One-line prompt for fast iteration.
  - `structured_prompt`: Official MAGI-2 PE JSON (`global_layer` + `dynamic_layer` for T2V; `global_caption` + `reference_bank` + `shot_timeline` + `audio_event_timeline` for I2V) or shot timeline notes.
  - `omni_references`: Ordered `image`, `video`, and `audio` reference inputs.
  - `parameters`: `task_type` (`t2v`, `i2v`, `omni-ref`), `duration_sec`, `fps`, `resolution`, `aspect_ratio`, `has_audio`, `audio_mode`.
  - `video_url`: External playable MP4 URL (never stored inside Git).
- `examples/t2v_pe_template.json` & `examples/i2v_pe_template.json`: Empty structured PE templates aligned with `SandAI-org/MAGI-2-preview`.

## Common workflows

1. **Scaffold a structured PE JSON prompt** before invoking MAGI-2:
   ```bash
   python3 examples/pe_template_helper.py scaffold --mode t2v --prompt "Rainy cafe dialogue" --out prompt.json
   ```
2. **Export repository prompts into `MAGI-2-preview` batch format (`samples.json`)**:
   ```bash
   python3 examples/pe_template_helper.py export --out my_samples.json
   ```
3. **Add a new curated case**: copy `templates/prompt.json` into `content/prompts.json`, keep videos external (`video_url`), keep local thumbnails `<= 500 KB` in `assets/examples/<id>/`, then run:
   ```bash
   python3 scripts/build_readme.py
   python3 scripts/validate.py
   ```
