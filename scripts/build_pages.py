#!/usr/bin/env python3
"""Build a lightweight GitHub Pages audio-video prompt & PE cheat sheet."""

from __future__ import annotations

import argparse
import datetime as dt
import html
import json
from pathlib import Path

from common import format_structured_prompt, has_copyable_prompt, load_data, published, repo_url, tracked_url

PAGES_URL_TEMPLATE = "https://{owner_lower}.github.io/{slug}/"


def build_dataset(config: dict, prompts: list[dict]) -> list[dict]:
    """Serialize published MAGI-2 entries into a client-side filterable dataset."""
    owner = config["project"]["repository_owner"]
    slug = config["project"]["repository_slug"]
    branch = config["project"]["default_branch"]
    raw_base = f"https://raw.githubusercontent.com/{owner}/{slug}/{branch}/"
    cat_labels = {cat["id"]: cat["label"]["en"] for cat in config["categories"]}

    records = []
    for item in published(prompts):
        preview_rel = item["preview"].get("path", "")
        records.append({
            "id": item["id"],
            "title": item["title"]["en"],
            "title_zh": item["title"].get("zh-CN", ""),
            "category": item["category"],
            "category_label": cat_labels.get(item["category"], item["category"]),
            "origin": item["origin"],
            "task_type": item["parameters"]["task_type"],
            "duration_sec": item["parameters"]["duration_sec"],
            "resolution": item["parameters"]["resolution"] or "1080p",
            "has_audio": bool(item["parameters"]["has_audio"]),
            "audio_mode": item["parameters"]["audio_mode"],
            "variant": item["model"]["variant"],
            "has_prompt": has_copyable_prompt(item),
            "short_prompt": item.get("short_prompt", "").strip(),
            "structured_prompt": format_structured_prompt(item.get("structured_prompt")),
            "poster": raw_base + preview_rel if preview_rel else "",
            "video_url": item.get("video_url") or "",
            "author": item["source"]["author"],
            "source_url": item["source"].get("url") or "",
            "anchor_url": f"https://github.com/{owner}/{slug}#case-{item['id']}",
        })
    return records


def render_html(config: dict, records: list[dict]) -> str:
    """Render static index.html with audio-video player support, SEO schema, and Plausible."""
    owner = config["project"]["repository_owner"]
    slug = config["project"]["repository_slug"]
    repository = repo_url(config)
    pages_url = PAGES_URL_TEMPLATE.format(owner_lower=owner.lower(), slug=slug)
    cta_url = tracked_url(config["brand"]["gallery_url"], "github_pages_cta", "en", config)
    updated_date = dt.datetime.now(dt.timezone.utc).strftime("%Y-%m-%d")
    plausible_domain = config["pages"]["plausible_domain"]
    plausible_script = config["pages"]["plausible_script_url"]

    categories = [{"id": cat["id"], "label": cat["label"]["en"]} for cat in config["categories"]]
    payload = json.dumps({"categories": categories, "records": records}, ensure_ascii=False).replace("</", "<\\/")
    json_ld = json.dumps({
        "@context": "https://schema.org",
        "@type": "TechArticle",
        "headline": "Awesome MAGI-2 Prompts — Audio-Video & Structured PE Cheat Sheet",
        "description": config["github"]["description"],
        "url": pages_url,
        "dateModified": updated_date,
        "author": {"@type": "Organization", "name": owner, "url": f"https://github.com/{owner}"},
        "codeRepository": repository,
        "license": f"{repository}/blob/main/LICENSE",
    }, ensure_ascii=False).replace("</", "<\\/")

    return f"""<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8" />
  <meta name="viewport" content="width=device-width, initial-scale=1" />
  <title>Awesome MAGI-2 Prompts · Audio-Video &amp; PE Cheat Sheet</title>
  <meta name="description" content="{html.escape(config['github']['description'], quote=True)}" />
  <link rel="canonical" href="{html.escape(pages_url, quote=True)}" />
  <meta property="og:type" content="website" />
  <meta property="og:title" content="Awesome MAGI-2 Prompts — Audio-Video &amp; PE Cheat Sheet" />
  <meta property="og:description" content="{html.escape(config['github']['description'], quote=True)}" />
  <meta property="og:url" content="{html.escape(pages_url, quote=True)}" />
  <script type="application/ld+json">{json_ld}</script>
  <script defer data-domain="{html.escape(plausible_domain, quote=True)}" src="{html.escape(plausible_script, quote=True)}"></script>
  <script>window.plausible = window.plausible || function() {{ (window.plausible.q = window.plausible.q || []).push(arguments); }};</script>
  <style>
    :root {{ color-scheme: dark; --bg: #0b1120; --card: #111827; --border: #1f2937; --fg: #f8fafc; --muted: #94a3b8; --accent: #f97316; }}
    * {{ box-sizing: border-box; }}
    body {{ margin: 0; font-family: system-ui, -apple-system, sans-serif; background: var(--bg); color: var(--fg); line-height: 1.5; }}
    .wrap {{ max-width: 1120px; margin: 0 auto; padding: 28px 20px 64px; }}
    header {{ display: flex; flex-wrap: wrap; justify-content: space-between; gap: 16px; align-items: center; border-bottom: 1px solid var(--border); padding-bottom: 20px; }}
    h1 {{ margin: 0 0 6px; font-size: 1.75rem; }}
    .sub {{ margin: 0; color: var(--muted); font-size: 0.95rem; }}
    .actions {{ display: flex; gap: 10px; flex-wrap: wrap; }}
    .btn {{ display: inline-flex; align-items: center; padding: 9px 14px; border-radius: 8px; border: 1px solid var(--border); background: var(--card); color: var(--fg); text-decoration: none; font-size: 0.9rem; cursor: pointer; }}
    .btn.primary {{ background: var(--accent); border-color: var(--accent); color: #0f172a; font-weight: 600; }}
    .toolbar {{ display: flex; flex-wrap: wrap; gap: 10px; margin: 22px 0; }}
    input, select {{ padding: 9px 12px; border-radius: 8px; border: 1px solid var(--border); background: var(--card); color: var(--fg); font-size: 0.9rem; }}
    input {{ flex: 1 1 240px; }}
    .grid {{ display: grid; grid-template-columns: repeat(auto-fill, minmax(320px, 1fr)); gap: 18px; }}
    .card {{ background: var(--card); border: 1px solid var(--border); border-radius: 12px; padding: 16px; display: flex; flex-direction: column; gap: 10px; }}
    video, .poster {{ width: 100%; border-radius: 8px; background: #020617; max-height: 220px; object-fit: cover; }}
    .meta {{ display: flex; gap: 6px; flex-wrap: wrap; font-size: 0.78rem; color: var(--muted); }}
    .tag {{ background: #1e293b; padding: 2px 8px; border-radius: 999px; }}
    pre {{ margin: 0; padding: 10px; border-radius: 8px; background: #020617; font-size: 0.8rem; overflow-x: auto; max-height: 120px; }}
    .empty {{ padding: 40px 24px; text-align: center; border: 1px dashed var(--border); border-radius: 12px; color: var(--muted); }}
  </style>
</head>
<body>
  <div class="wrap">
    <header>
      <div>
        <h1>MAGI-2 Prompts &amp; PE Audio-Video Player</h1>
        <p class="sub">Playable audio-enabled MAGI-2 clips, one-click short prompts, and structured PE JSON templates.</p>
      </div>
      <div class="actions">
        <a class="btn" href="{html.escape(repository, quote=True)}">★ Star on GitHub</a>
        <a class="btn primary" href="{html.escape(cta_url, quote=True)}">Generate AI Videos on Raphael →</a>
      </div>
    </header>
    <div class="toolbar">
      <input id="q" type="search" placeholder="Search prompts, dialogue, camera, or author..." />
      <select id="task">
        <option value="">All Tasks</option>
        <option value="t2v">Text-to-Video (T2V)</option>
        <option value="i2v">Image-to-Video (I2V)</option>
        <option value="omni-ref">Omni-Reference</option>
      </select>
      <select id="cat"><option value="">All Categories</option></select>
      <label class="btn"><input id="audio" type="checkbox" style="margin-right:6px" /> Audio only</label>
    </div>
    <div id="mount"></div>
  </div>
  <script>
    const DATA = {payload};
    const catSel = document.getElementById("cat");
    DATA.categories.forEach(c => {{
      const opt = document.createElement("option");
      opt.value = c.id;
      opt.textContent = c.label;
      catSel.appendChild(opt);
    }});
    function copyText(text, eventName) {{
      navigator.clipboard.writeText(text);
      window.plausible(eventName);
    }}
    function render() {{
      const q = document.getElementById("q").value.trim().toLowerCase();
      const task = document.getElementById("task").value;
      const cat = catSel.value;
      const audioOnly = document.getElementById("audio").checked;
      const list = DATA.records.filter(r => {{
        if (task && r.task_type !== task) return false;
        if (cat && r.category !== cat) return false;
        if (audioOnly && !r.has_audio) return false;
        if (!q) return true;
        return [r.title, r.title_zh, r.short_prompt, r.structured_prompt, r.author].join(" ").toLowerCase().includes(q);
      }});
      const mount = document.getElementById("mount");
      if (!list.length) {{
        mount.innerHTML = '<div class="empty"><strong>No published video cases yet</strong><p>Templates and validator pipelines are active. Playable MAGI-2 clips and PE JSON cards will appear here once added to <code>content/prompts.json</code>.</p></div>';
        return;
      }}
      const grid = document.createElement("div");
      grid.className = "grid";
      list.forEach(r => {{
        const card = document.createElement("article");
        card.className = "card";
        if (r.video_url) {{
          const vid = document.createElement("video");
          vid.controls = true;
          vid.playsInline = true;
          vid.preload = "metadata";
          if (r.poster) vid.poster = r.poster;
          vid.src = r.video_url;
          vid.addEventListener("play", () => window.plausible("Play Video"), {{ once: true }});
          card.appendChild(vid);
        }} else if (r.poster) {{
          const img = document.createElement("img");
          img.className = "poster";
          img.src = r.poster;
          img.alt = r.title;
          card.appendChild(img);
        }}
        const titleEl = document.createElement("strong");
        titleEl.textContent = r.title;
        card.appendChild(titleEl);
        const meta = document.createElement("div");
        meta.className = "meta";
        [r.task_type.toUpperCase(), `${{r.duration_sec || "—"}}s · ${{r.resolution}}`, r.has_audio ? r.audio_mode : "silent"].forEach(label => {{
          const tag = document.createElement("span");
          tag.className = "tag";
          tag.textContent = label;
          meta.appendChild(tag);
        }});
        card.appendChild(meta);
        const previewText = r.short_prompt || (r.structured_prompt ? r.structured_prompt.slice(0, 320) + (r.structured_prompt.length > 320 ? "…" : "") : "");
        if (previewText) {{
          const pre = document.createElement("pre");
          pre.textContent = previewText;
          card.appendChild(pre);
        }}
        const actions = document.createElement("div");
        actions.className = "actions";
        if (r.short_prompt) {{
          const b1 = document.createElement("button");
          b1.className = "btn";
          b1.textContent = "Copy Prompt";
          b1.onclick = () => copyText(r.short_prompt, "Copy Prompt");
          actions.appendChild(b1);
        }}
        if (r.structured_prompt) {{
          const b2 = document.createElement("button");
          b2.className = "btn";
          b2.textContent = r.short_prompt ? "Copy PE / Timeline" : "Copy Full Prompt";
          b2.onclick = () => copyText(r.structured_prompt, r.short_prompt ? "Copy PE JSON" : "Copy Prompt");
          actions.appendChild(b2);
        }}
        const gh = document.createElement("a");
        gh.className = "btn";
        gh.href = r.anchor_url;
        gh.textContent = "GitHub Case →";
        actions.appendChild(gh);
        card.appendChild(actions);
        grid.appendChild(card);
      }});
      mount.innerHTML = "";
      mount.appendChild(grid);
    }}
    ["q", "task", "cat", "audio"].forEach(id => document.getElementById(id).addEventListener("input", render));
    render();
  </script>
</body>
</html>
"""


def render_robots(pages_url: str) -> str:
    """Render robots.txt allowing full crawling of GitHub Pages."""
    return f"User-agent: *\nAllow: /\n\nSitemap: {pages_url}sitemap.xml\n"


def render_sitemap(pages_url: str, updated_date: str) -> str:
    """Render minimal sitemap.xml for the GitHub Pages index."""
    return (
        '<?xml version="1.0" encoding="UTF-8"?>\n'
        '<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">\n'
        f"  <url><loc>{html.escape(pages_url)}</loc><lastmod>{updated_date}</lastmod></url>\n"
        "</urlset>\n"
    )


def build_site(out_dir: Path) -> Path:
    """Build static GitHub Pages files into out_dir."""
    config, prompts = load_data()
    owner = config["project"]["repository_owner"]
    slug = config["project"]["repository_slug"]
    pages_url = PAGES_URL_TEMPLATE.format(owner_lower=owner.lower(), slug=slug)
    updated_date = dt.datetime.now(dt.timezone.utc).strftime("%Y-%m-%d")
    records = build_dataset(config, prompts)

    out_dir.mkdir(parents=True, exist_ok=True)
    (out_dir / ".nojekyll").write_text("", encoding="utf-8")
    (out_dir / "index.html").write_text(render_html(config, records), encoding="utf-8")
    (out_dir / "robots.txt").write_text(render_robots(pages_url), encoding="utf-8")
    (out_dir / "sitemap.xml").write_text(render_sitemap(pages_url, updated_date), encoding="utf-8")
    return out_dir


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--out", default="_site", help="Output directory for built static site.")
    args = parser.parse_args()
    out_dir = build_site(Path(args.out))
    print(f"Built GitHub Pages cheat sheet in {out_dir}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
