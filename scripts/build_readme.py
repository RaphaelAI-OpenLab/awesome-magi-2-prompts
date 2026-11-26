#!/usr/bin/env python3
"""Render README.md, README.zh-CN.md, bilingual case pages, and SVG pills."""

from __future__ import annotations

import argparse
import datetime as dt
import sys
from pathlib import Path

from common import (
    GENERATED_MARKER, ROOT, asset_path, code_block, format_structured_prompt,
    has_copyable_prompt, html_attr, load_data, localized, md_link, md_text,
    md_url, published, repo_url, tracked_url,
)
from i18n import DETAIL_LANGUAGES, LANGUAGES, filename, ui
from presentation import asset_outputs, language_nav, repo_badges
from sync_cms_stats import CmsStats, cms_rows, read_cms_stats, stats_marker

LOCAL_QUICKSTART_SNIPPET = """```bash
# 1) Clone SandAI-org/MAGI-2-preview and download Apache 2.0 weights (~307 GB)
git clone https://github.com/SandAI-org/MAGI-2-preview.git && cd MAGI-2-preview
hf download sand-ai/MAGI-2-preview --local-dir ckpt

# 2) Run a single 10s 1080p audio-video clip (8x NVIDIA Hopper GPUs)
torchrun --nproc_per_node=8 inference/pipeline/entry.py \\
  --prompt "A red fox trotting through fresh snow, crunching footsteps and winter wind" \\
  --output output/

# 3) Export prompts from this repo into MAGI-2-preview samples.json
python3 examples/pe_template_helper.py export --out my_samples.json
SAMPLES=my_samples.json bash scripts/run_demo.sh
```"""

PE_SKELETON_SNIPPET = """```json
{
  "global_layer": {
    "context": "Single continuous take inside a rainy corner cafe.",
    "audio_baseline": {
      "ambience": "Steady rain against glass, low espresso machine hum",
      "dialogue": { "language": "English", "speaker_tags": ["<subject 1>"] }
    },
    "video_metadata": { "duration": 10.0, "aspect_ratio": "16:9" }
  },
  "dynamic_layer": {
    "timeline_segments": [
      {
        "segment_basic_info": { "timestamp_range": "00:00.0-00:10.0" },
        "audio": {
          "dialogue_lines": [{ "timestamp": "00:03.0-00:06.5", "speaker": "<subject 1>", "text": "Hot latte for window two.", "delivery": "calm, conversational" }],
          "special_audio_events": [{ "timestamp": "00:01.8", "sound_description": "ceramic cup clink on saucer", "visual_sync": "cup touches saucer" }]
        }
      }
    ]
  }
}
```"""


def case_page_path(item: dict, language: str) -> str:
    """Return repository-relative path for a standalone bilingual case page."""
    return f"cases/{item['id']}/{filename(language)}"


def render_category_nav(config: dict, items: list[dict], language: str) -> str:
    """Render in-page category anchor navigation with live published counts."""
    counts = {cat["id"]: 0 for cat in config["categories"]}
    for item in items:
        cid = item["category"]
        if cid in counts:
            counts[cid] += 1
    parts = [md_link(f"{ui('All', '全部', language)} ({len(items)})", "#all-cases")]
    for cat in config["categories"]:
        label = localized(cat["label"], language)
        parts.append(md_link(f"{label} ({counts[cat['id']]})", f"#category-{cat['id']}"))
    return " · ".join(parts)


def render_case_card(
    item: dict,
    config: dict,
    language: str,
    *,
    number: int | None = None,
    standalone: bool = False,
    featured: bool = False,
) -> str:
    """Render one MAGI-2 prompt entry for README or standalone case page."""
    c = lambda en, cn: ui(en, cn, language)
    prefix = "../../" if standalone else ""
    title = localized(item["title"], language)
    heading_title = f"{number}. {title}" if number is not None and not standalone else title
    anchor_id = f"featured-{item['id']}" if featured else f"case-{item['id']}"
    lines = [f'<a id="{anchor_id}"></a>', "", f"{'#' if standalone else '####'} {md_text(heading_title)}", ""]
    if standalone:
        lines.extend([md_link(c("← Back to collection", "← 返回合集"), prefix + filename(language)), ""])

    meta_badges = [
        f"**{c('Origin', '来源类型')}**: `{item['origin']}`",
        f"**{c('Task', '任务')}**: `{item['parameters']['task_type'].upper()}`",
        f"**{c('Audio', '音画')}**: `{'Yes' if item['parameters']['has_audio'] else 'Silent'}`",
        f"**{c('Status', '状态')}**: `{c('Tested', '已实测') if item['verification']['status'] == 'tested' else c('Source-linked', '来源收录')}`",
    ]
    lines.extend([" · ".join(meta_badges), ""])

    summary = localized(item.get("summary", {}), language)
    if summary:
        lines.extend([summary, ""])

    preview_path = item["preview"].get("path", "")
    video_url = item.get("video_url")
    if preview_path:
        alt = html_attr(localized(item["preview"]["alt"], language) or title)
        src = html_attr(asset_path(preview_path, prefix))
        img_width = "300" if item["parameters"].get("aspect_ratio") == "9:16" else "640"
        img_tag = f'<img src="{src}" alt="{alt}" width="{img_width}" />'
        if video_url:
            lines.extend([f'<a href="{html_attr(video_url)}">{img_tag}</a>', ""])
        else:
            lines.extend([img_tag, ""])
    if video_url:
        lines.extend([f"▶ **{md_link(c('Watch audio-enabled MP4', '播放有声视频原片'), video_url)}**", ""])

    if has_copyable_prompt(item):
        short_text = item.get("short_prompt", "").strip()
        if short_text:
            lines.extend([f"**{c('Prompt', '提示词')}**", "", code_block(short_text, "text"), ""])
        structured = format_structured_prompt(item.get("structured_prompt"))
        if structured:
            is_json = isinstance(item.get("structured_prompt"), (dict, list))
            lang = "json" if is_json else "text"
            summary_label = (
                c("Structured PE / Shot Timeline", "展开结构化 PE / 分镜时间轴")
                if is_json
                else c(f"Full Structured Prompt ({len(structured)} chars)", f"展开完整原始提示词（{len(structured)} 字）")
            )
            if standalone:
                lines.extend([f"**{c('Full Prompt', '完整原始提示词')}**", "", code_block(structured, lang), ""])
            else:
                lines.extend([
                    f"<details><summary><strong>{summary_label}</strong></summary>\n",
                    code_block(structured, lang),
                    "\n</details>",
                    "",
                ])
    else:
        lines.extend([f"> *{c('Prompt status', '提示词状态')}: `{item['prompt_status']}` — {c('original prompt not published by source.', '原作者未公开原始提示词，不作臆造补充。')}*", ""])

    params = item["parameters"]
    param_rows = [
        (c("Model", "模型"), f"{item['model']['family'] or 'MAGI-2'} ({item['model']['variant']})"),
        (c("Task type", "任务类型"), params["task_type"]),
        (c("Duration / FPS", "时长 / 帧率"), f"{params['duration_sec'] or '—'}s · {params['fps'] or '—'} fps"),
        (c("Resolution / Ratio", "分辨率 / 比例"), f"{params['resolution'] or '—'} · {params['aspect_ratio'] or '—'}"),
        (c("Audio mode", "音频模式"), f"{params['audio_mode']} (audio={params['has_audio']})"),
    ]
    lines.extend([f"| {c('Parameter', '参数')} | {c('Value', '配置')} |", "| --- | --- |"])
    lines.extend(f"| {md_text(k)} | {md_text(v)} |" for k, v in param_rows)
    lines.append("")

    if item.get("omni_references"):
        lines.extend([f"**{c('Omni-References', '多素材参考输入')}**", ""])
        for idx, ref in enumerate(item["omni_references"], 1):
            desc = localized(ref.get("description", {}), language) or f"Reference {idx}"
            target = asset_path(ref["path"], prefix) if ref.get("path") else (ref.get("url") or "")
            entry = md_link(desc, target) if target else md_text(desc)
            lines.append(f"{idx}. `{ref['kind']}` · {entry}")
        lines.append("")

    source = item["source"]
    src_bits = []
    if source.get("url"):
        src_bits.append(md_link(c("Original source", "原始来源"), source["url"]))
    if source.get("author"):
        author = md_link(source["author"], source["author_url"]) if source.get("author_url") else md_text(source["author"])
        src_bits.append(f"{c('Creator', '作者')}: {author}")
    if source.get("published_at"):
        src_bits.append(source["published_at"])
    if src_bits:
        lines.extend([" · ".join(src_bits), ""])

    note_text = localized(item.get("notes", {}), language)
    if note_text:
        lines.extend([f"> {note_text}", ""])

    cta_url = item["links"].get("generate_url") or config["brand"]["gallery_url"]
    cta_label = c("Generate similar on Raphael →", "在 Raphael 上生成同类视频 →")
    action_bits = []
    if not standalone and config["presentation"]["generate_case_pages"]:
        action_bits.append(md_link(c("Case page", "案例详情页"), case_page_path(item, language)))
    action_bits.append("**" + md_link(cta_label, tracked_url(cta_url, f"case_{item['id']}", language, config)) + "**")
    lines.extend([" · ".join(action_bits), ""])
    return "\n".join(lines).rstrip() + "\n"


def render_home(config: dict, prompts: list[dict], language: str, cms_stats: CmsStats | None) -> str:
    """Render root README.md or README.zh-CN.md from config and prompts dataset."""
    c = lambda en, cn: ui(en, cn, language)
    items = published(prompts)
    featured_ids = config["presentation"]["featured_case_ids"]
    by_id = {item["id"]: item for item in items}
    if featured_ids:
        featured_items = [by_id[cid] for cid in featured_ids if cid in by_id]
    else:
        featured_items = [item for item in items if item.get("featured")]
    featured_items = featured_items[: config["presentation"]["featured_limit"]]

    brand = config["brand"]
    project = config["project"]
    repo = repo_url(config)
    gallery_url = brand.get("gallery_url") or brand["home_url"]
    title = c("Awesome MAGI-2 Prompts", "MAGI-2 提示词大全")
    updated = dt.datetime.fromisoformat(config["presentation"]["updated_at"])

    def heading(anchor: str, en: str, cn: str) -> list[str]:
        return [f'<a id="{anchor}"></a>', "", "## " + c(en, cn), ""]

    lines = [
        GENERATED_MARKER,
        "",
        '<a id="top"></a>',
        "",
        f"[![{title}](assets/header.svg)]({tracked_url(brand['home_url'], 'hero', language, config)})",
        "",
        f"# 🎬 {title}",
        "",
        repo_badges(config, language),
        "",
        "> 🎥 "
        + c(
            "Curated MAGI-2 & MAGI-2-preview prompts, native audio-video templates, Omni-Reference workflows, and structured PE (Prompt Enhancement) schemas.",
            "Sand.ai **MAGI-2** 与开源 **MAGI-2-preview** 提示词及工程模板合集——聚焦原生音画同步（对白/音效/配乐）、Omni-Reference 多素材参考与结构化 PE 分镜时间轴。",
        ),
        "",
        "> ⚠️ **"
        + c("Media & Copyright Notice", "音视频存储与版权声明")
        + c("**: ", "**：")
        + c(
            "This collection indexes public prompts, original reproductions, and developer PE templates for educational use. Playable MP4 videos stay on external storage or official links rather than inside Git. To report an issue or request removal, ",
            "本仓库收录公开来源的提示词、原创复现与开发者 PE 模板，仅供学习参考；可播放 MP4 视频统一保存在外部存储或官方原链，不塞入 Git。如需更正署名或申请移除，请",
        )
        + md_link(c("open an issue", "提交 Issue"), f"{repo}/issues/new?template=report-problem.yml")
        + ".",
        "",
        "---",
        "",
        language_nav(language),
        "",
        "---",
        "",
    ]

    lines += heading("gallery", "🌐 Generate & Compare Online", "🌐 在线生成与对比")
    lines += [
        "**"
        + md_link(
            "👉 " + c("Try AI Video Generation on {brand}", "前往 {brand} 在线体验 AI 视频生成").format(brand=brand["name"]),
            tracked_url(gallery_url, "top_cta", language, config),
        )
        + "**",
        "",
        "| " + c("Feature", "能力对比") + " | GitHub README | " + c("{brand} Website", "{brand} 网页端").format(brand=brand["name"]) + " |",
        "| --- | --- | --- |",
        "| 🎬 " + c("Video + Audio Workflows", "音画视频创作") + " | " + c("Copy short prompts & PE JSON templates", "复制短提示词与结构化 PE JSON 模板") + " | " + c("Generate in browser without local GPU setup", "免部署本地 GPU 集群，浏览器直接生成") + " |",
        "| 🧩 " + c("Multi-Model Switching", "多模型对比") + " | " + c("Compare MAGI-2 vs MAGI-2-preview formats", "查看 MAGI-2 与 MAGI-2-preview 提示词规范") + " | " + c("Switch across leading AI video models", "一站式切换体验多款主流视频生成模型") + " |",
        "| 📱 " + c("Access Anywhere", "随时访问") + " | " + c("Lightweight Markdown & JSON index", "轻量 Markdown 与 JSON 检索") + " | " + c("Direct web generation on desktop & mobile", "桌面端与移动端即开即用") + " |",
        "",
    ]

    lines += heading("categories", "🏷️ Browse by category", "🏷️ 按分类浏览")
    lines += [render_category_nav(config, items, language), ""]

    lines += heading("contents", "📖 Contents", "📖 目录")
    for target, en, cn in [
        ("#about", "What is MAGI-2 (Flagship vs MAGI-2-preview)?", "什么是 MAGI-2（旗舰版 vs 开源 Preview）？"),
        ("#quickstart", "Developer Quickstart & Structured PE Templates", "开发者 Quickstart 与结构化 PE 模板"),
        ("#statistics", "Statistics", "统计数据"),
        ("#featured", "Featured cases", "精选案例"),
        ("#all-cases", "All cases", "全部案例"),
        ("#using", "How to use", "如何使用"),
        ("#contribute", "Contribute", "如何贡献"),
        ("#license", "License & Attribution", "许可证与署名"),
    ]:
        lines.append("- " + md_link(c(en, cn), target))
    lines.append("")

    lines += heading("about", "🤔 What is MAGI-2 (Flagship vs MAGI-2-preview)?", "🤔 什么是 MAGI-2（旗舰版 vs 开源 Preview）？")
    lines += [
        c(
            "Sand.ai introduced **MAGI-2** (a 480B-parameter flagship Multi-Head Latent MoE audio-video model) alongside the open-weights **MAGI-2-preview** (114B total / 6B active parameters under Apache 2.0). Both share a dense, timeline-driven captioning style where synchronized dialogue, sound effects, camera motion, and reference identities are described explicitly.",
            "Sand.ai 推出了旗舰级音画同步视频模型 **MAGI-2**（480B 总参数 Multi-Head Latent MoE 架构）与开源权重版本 **MAGI-2-preview**（114B 总参数 / 6B 激活参数，Apache 2.0 协议）。两者均依赖高密度的分镜时间轴与音画事件描述来充分发挥模型控制力。",
        ),
        "",
        md_link(c("MAGI-2 Preview Blog", "官方技术博客"), project["official_url"])
        + " · "
        + md_link(c("SandAI-org/MAGI-2-preview", "官方开源代码仓"), project["model_docs_url"])
        + " · "
        + md_link(c("Hugging Face Weights", "Hugging Face 权重"), project["huggingface_url"]),
        "",
        "| " + c("Capability", "核心规格") + " | `MAGI-2` (Flagship) | `MAGI-2-preview` (Open-Weights) |",
        "| --- | --- | --- |",
        "| " + c("Parameter scale", "参数规模") + " | 480B total (~28B active) | 114B total (6B active, MagiMoE) |",
        "| " + c("Duration & output", "时长与规格") + " | 4–30s · 1080p · 25 fps | 10s · 1080p (`512×896` → `1088×1920` refiner) |",
        "| " + c("Audio generation", "原生音画同步") + " | " + c("Synced dialogue, SFX & music in one pass", "单次生成同步对白、音效与配乐") + " | " + c("Unified audio-video generation (`ffmpeg` muxed)", "原生音画联合生成（`ffmpeg` 混流输出）") + " |",
        "| " + c("Input modes", "输入控制方式") + " | T2V, I2V, **Omni-Reference** (up to 20 images/videos/audio) | T2V, I2V + optional JSON **Prompt Enhancement (PE)** |",
        "| " + c("License / Hardware", "协议 / 运行环境") + " | " + c("Commercial / hosted API & product", "商用平台 / 云端算力") + " | Apache 2.0 · 8× NVIDIA Hopper GPUs (~307 GB ckpt) |",
        "",
    ]

    lines += heading("quickstart", "⚡ Developer Quickstart & Structured PE Templates", "⚡ 开发者 Quickstart 与结构化 PE 模板")
    lines += [
        c(
            "Short handwritten prompts underuse MAGI-2. Sand.ai's inference pipeline ships `t2v.md` and `i2v.md` Prompt Enhancement (PE) schemas so an LLM expands a short idea into `global_layer` + `dynamic_layer` (T2V) or `shot_timeline` + `audio_event_timeline` (I2V). This repository includes ready-to-use templates and a CLI helper:",
            "手写短句往往无法激活 MAGI-2 的多镜头与对白控制力。官方推理代码内置 `t2v.md` 与 `i2v.md` 结构化增强（PE）模板，将短提示词改写为 `global_layer` + `dynamic_layer`（文生视频）或 `shot_timeline` + `audio_event_timeline`（图生视频）。本仓库直接附带模板与导出工具：",
        ),
        "",
        "- " + md_link("SKILL.md", "SKILL.md") + " — " + c("Agent-readable index to query `content/prompts.json` and build PE prompts", "供 AI 编程助手直接检索提示词库与生成 PE 模板的 Skill 说明"),
        "- " + md_link("examples/pe_template_helper.py", "examples/pe_template_helper.py") + " — " + c("Export repo cases to `MAGI-2-preview` `samples.json` or scaffold T2V/I2V PE JSON", "一键导出 `MAGI-2-preview` 批量推理 `samples.json`，或生成 T2V/I2V PE JSON 骨架"),
        "- " + md_link("examples/t2v_pe_template.json", "examples/t2v_pe_template.json") + " · " + md_link("examples/i2v_pe_template.json", "examples/i2v_pe_template.json") + " · " + md_link("examples/demo_samples.example.json", "examples/demo_samples.example.json"),
        "",
        LOCAL_QUICKSTART_SNIPPET,
        "",
        "<details><summary><strong>"
        + c("Preview: MAGI-2 T2V Structured PE JSON shape", "展开示例：MAGI-2 文生视频结构化 PE JSON 结构")
        + "</strong></summary>\n",
        PE_SKELETON_SNIPPET,
        "\n</details>",
        "",
    ]

    lines += heading("statistics", "📊 Statistics", "📊 统计数据")
    lines += [
        "| **" + c("Metric", "指标") + "** | **" + c("Count", "数量") + "** |",
        "| --- | --- |",
        "| 🎬 " + c("Total cases", "素材总数") + f" | **{len(items)}** |",
        "| ⭐ " + c("Featured cases", "精选案例") + f" | **{len(featured_items)}** |",
        *cms_rows(language, cms_stats, updated),
        "",
        stats_marker(cms_stats),
        "",
    ]

    lines += heading("featured", "🔥 Featured cases", "🔥 精选案例")
    if featured_items:
        for idx, item in enumerate(featured_items, 1):
            lines += [render_case_card(item, config, language, number=idx, featured=True), "---", ""]
    else:
        lines += [
            f"![{c('Reserved video preview slots; placeholders only, not generated outputs', '预留视频展示槽位；当前仅作占位示意，非模型生成输出')}](assets/gallery-placeholder.svg)",
            "",
            c(
                "Repository scaffold, PE templates, validation CI, and developer helpers are live. Curated MAGI-2 video cases and playable audio-enabled clips are being ingested into `content/prompts.json`.",
                "仓库骨架、结构化 PE 模板、自动化校验与导出工具已全部就绪；首批经过来源核对的 MAGI-2 有声视频案例正在陆续整理并合入 `content/prompts.json`。",
            ),
            "",
        ]

    lines += heading("all-cases", "📋 All cases", "📋 全部案例")
    number = 0
    for cat in config["categories"]:
        lines += [f'<a id="category-{cat["id"]}"></a>', "", f"### {localized(cat['label'], language)}", ""]
        group = [item for item in items if item["category"] == cat["id"]]
        if group:
            for item in group:
                number += 1
                lines += [render_case_card(item, config, language, number=number), "---", ""]
        else:
            lines += [c("No published entries in this category yet.", "该分类暂未发布案例。"), ""]

    lines += heading("using", "📚 How to use", "📚 如何使用")
    lines += [
        "1. " + c("Pick a category or filter cases by `T2V`, `I2V`, or `Omni-Reference`.", "按场景分类或任务类型（`T2V` / `I2V` / `Omni-Reference`）挑选案例。"),
        "2. " + c("Use `short_prompt` for quick tests, or copy `structured_prompt` (PE timeline + audio events) for deterministic control.", "快速试跑可直接复制 `short_prompt`；需要稳定镜头与口型/音效对齐时请使用 `structured_prompt`（PE 时间轴）。"),
        "3. " + c("Watch the linked audio-enabled MP4 before running `8× Hopper` local inference or cloud generation.", "建议先点击外部有声 MP4 确认节奏与音效表现，再在本地 8× Hopper 或云端生成平台复现。"),
        "",
    ]

    lines += heading("contribute", "🤝 How to contribute", "🤝 如何贡献")
    lines += [
        c(
            "Add entries to `content/prompts.json` using `templates/prompt.json`, keep MP4 files outside Git (`video_url` only), and run `scripts/build_readme.py` + `scripts/validate.py` before opening a PR.",
            "请按 `templates/prompt.json` 格式向 `content/prompts.json` 补充条目；视频一律外链填 `video_url`，仓库仅存 `<= 500 KB` 预览图，并在提 PR 前运行生成与校验脚本。",
        ),
        "",
        md_link(c("Contribution guide", "贡献指南"), "CONTRIBUTING.md")
        + " · "
        + md_link(c("Prompt entry checklist", "案例录入规范"), "templates/PROMPT_CARD.md")
        + " · "
        + md_link(c("Submit via Issue form", "通过表单提交案例"), f"{repo}/issues/new?template=submit-prompt.yml"),
        "",
    ]

    lines += heading("license", "📄 License & Attribution", "📄 许可证与署名")
    lines += [
        c(
            "Repository scripts, templates, `SKILL.md`, and original SVG artwork are licensed under MIT. Third-party prompts and videos retain their original creator rights and item-level terms. README layout is adapted from YouMind OpenLab under CC BY 4.0.",
            "仓库代码、模板、`SKILL.md` 与原创 SVG 图形采用 MIT 协议；第三方提示词与视频保留原作者权利与逐项条款；README 版式结构参考 YouMind OpenLab（CC BY 4.0）。",
        ),
        "",
        md_link(c("MIT License", "MIT 许可证"), "LICENSE")
        + " · "
        + md_link(c("Attribution & License Scope", "署名与许可范围"), "docs/ATTRIBUTION.md"),
        "",
        "---",
        "",
        md_link("↑ " + c("Back to top", "返回顶部"), "#top")
        + " · "
        + md_link(c("Star on GitHub", "在 GitHub 点 Star"), repo)
        + " · "
        + md_link(c("Curated by {brand}", "由 {brand} 维护").format(brand=brand["name"]), tracked_url(brand["home_url"], "footer", language, config)),
        "",
    ]
    return "\n".join(lines)


def outputs(config: dict, prompts: list[dict]) -> dict[Path, str]:
    """Compute all deterministic generated Markdown and SVG badge outputs."""
    cms_stats = read_cms_stats()
    result: dict[Path, str] = {
        ROOT / filename(lang): render_home(config, prompts, lang, cms_stats)
        for lang in LANGUAGES
    }
    if config["presentation"]["generate_case_pages"]:
        for item in published(prompts):
            for lang in DETAIL_LANGUAGES:
                result[ROOT / case_page_path(item, lang)] = (
                    GENERATED_MARKER + "\n\n" + render_case_card(item, config, lang, standalone=True)
                )
    result.update(asset_outputs())
    return result


def stale_case_pages(expected: dict[Path, str]) -> list[Path]:
    """Find previously generated case pages that no longer correspond to published entries."""
    cases_dir = ROOT / "cases"
    if not cases_dir.exists():
        return []
    return [
        path
        for path in cases_dir.glob("*/README*.md")
        if path not in expected and path.read_text(encoding="utf-8").startswith(GENERATED_MARKER)
    ]


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--check", action="store_true", help="Exit non-zero if generated files are stale.")
    args = parser.parse_args()

    from validate import validate
    errors, _ = validate(check_links=False)
    if errors:
        for error in errors:
            print(f"ERROR: {error}", file=sys.stderr)
        return 1

    config, prompts = load_data()
    expected = outputs(config, prompts)
    stale = stale_case_pages(expected)
    changed = [path for path, content in expected.items() if not path.exists() or path.read_text(encoding="utf-8") != content]

    if args.check:
        for path in changed + stale:
            print(f"OUTDATED: {path.relative_to(ROOT)}")
        if changed or stale:
            print("Run: python3 scripts/build_readme.py")
            return 1
        print(f"Generated files are current ({len(expected)} files; {len(published(prompts))} published prompts).")
        return 0

    for path, content in expected.items():
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(content, encoding="utf-8")
    for path in stale:
        path.unlink()
        if not any(path.parent.iterdir()):
            path.parent.rmdir()
    print(f"Built {len(expected)} files; {len(published(prompts))} published prompts.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
