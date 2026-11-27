#!/usr/bin/env python3
"""Pull MAGI-2 materials from Directus CMS into content/prompts.json and lightweight posters."""

from __future__ import annotations

import argparse
import copy
from datetime import datetime, timezone
import json
import math
import os
from pathlib import Path
import re
import shutil
import subprocess
import sys
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode, urlsplit
from urllib.request import Request, urlopen

from common import ROOT, read_json

CMS_SYNC_STATE_PATH = "content/cms-sync-state.json"
DEFAULT_MEDIA_BASE_URL = "https://awesome.raphael.app/materials/"
PAGE_SIZE = 100
FIELDS = (
    "id,title,prompt,status,author_x_url,source_post_url,source_published_at,"
    "tags,notes,date_created,date_updated,image_url,r2_object_key"
)
ALLOWED_STATUSES = {"ready", "published"}
MAX_POSTER_BYTES = 450 * 1024
SOFT_POSTER_BYTES = 200 * 1024

CATEGORY_KEYWORDS = (
    ("omni-reference", ("omni-ref", "omni reference", "参考图", "character-sheet", "character sheet", "reference image", "strict identity", "换装")),
    ("product-commercials", ("ad", "commercial", "lookbook", "fashion", "shoe", "product", "brand", "广告", "时装", "商业", "带货")),
    ("dialogue-lip-sync", ("dialogue", "lip-sync", "lip sync", "spoken", "对白", "台词", "口型", "笑谈", "约会")),
    ("sfx-ambience", ("edm", "music", "soundtrack", "sfx", "ambience", "diegetic", "配乐", "音效", "环境音", "笛子", "锣鼓")),
    ("cinematic-animation", ("anime", "animation", "2d", "3d", "cartoon", "wuxia", "martial", "武侠", "动画", "短剧", "手绘", "萌宠")),
    ("multi-shot-storytelling", ("multi-shot", "timeline", "episode", "shot", "hard cut", "comedy", "闹剧", "喜剧", "分镜", "短片")),
)


def media_base_url(config: dict) -> str:
    cms = config.get("cms") or {}
    base = str(cms.get("media_base_url") or DEFAULT_MEDIA_BASE_URL).strip()
    return base if base.endswith("/") else base + "/"


def is_approved_media_url(url: str | None, config: dict) -> bool:
    if not isinstance(url, str) or not url.strip():
        return False
    base = media_base_url(config)
    if not url.startswith(base):
        return False
    parts = urlsplit(url)
    return (
        parts.scheme == "https"
        and bool(parts.hostname)
        and not parts.username
        and not parts.query
        and not parts.fragment
        and not re.search(r"[\s<>]", url)
    )


def validate_cms_env(base_url: str, token: str, collection: str) -> None:
    parsed = urlsplit(base_url)
    if (
        parsed.scheme != "https"
        or not parsed.hostname
        or parsed.path not in ("", "/")
        or parsed.query
        or parsed.fragment
        or parsed.username is not None
        or not re.fullmatch(r"[A-Za-z0-9._~-]+", token)
        or not re.fullmatch(r"[A-Za-z0-9_]+", collection)
    ):
        raise ValueError("Set CMS_BASE_URL to the HTTPS origin, configure CMS_READ_TOKEN, and check cms.collection.")


def fetch_all_materials(base_url: str, token: str, collection: str) -> list[dict]:
    """Fetch all records from Directus magi2_materials with deterministic pagination."""
    validate_cms_env(base_url, token, collection)
    rows: list[dict] = []
    offset = 0
    while True:
        query = urlencode({
            "fields": FIELDS,
            "sort": "-date_created,-id",
            "limit": PAGE_SIZE,
            "offset": offset,
        })
        request = Request(
            f"{base_url.rstrip('/')}/items/{collection}?{query}",
            headers={"Accept": "application/json", "User-Agent": "Raphael-MAGI2-CMS-Sync/2.0"},
        )
        request.add_unredirected_header("Authorization", f"Bearer {token}")
        with urlopen(request, timeout=30) as response:
            payload = json.load(response)
        batch = payload.get("data")
        if not isinstance(batch, list):
            raise ValueError("CMS returned an invalid items payload.")
        rows.extend(batch)
        if len(batch) < PAGE_SIZE:
            break
        offset += PAGE_SIZE
    return rows


def normalize_https_url(value: str | None) -> str | None:
    if not isinstance(value, str):
        return None
    cleaned = value.strip()
    if not cleaned:
        return None
    parts = urlsplit(cleaned)
    if parts.scheme != "https" or not parts.hostname or parts.username or re.search(r"[\s<>]", cleaned):
        return None
    return cleaned


def iso_date_part(value: str | None) -> str | None:
    if not isinstance(value, str) or len(value) < 10:
        return None
    candidate = value[:10]
    if re.fullmatch(r"\d{4}-\d{2}-\d{2}", candidate):
        return candidate
    return None


def extract_author_handle(author_url: str | None, source_url: str | None) -> str:
    for candidate in (author_url, source_url):
        if not candidate:
            continue
        parts = urlsplit(candidate)
        host = (parts.hostname or "").lower().removeprefix("www.")
        segments = [seg for seg in parts.path.split("/") if seg]
        if host in ("x.com", "twitter.com") and segments:
            return "@" + segments[0].lstrip("@")
        if host == "github.com" and segments:
            return "@" + segments[0]
    return "Community"


def detect_prompt_language(prompt: str) -> str:
    cjk = len(re.findall(r"[\u4e00-\u9fff]", prompt))
    latin = len(re.findall(r"[A-Za-z]", prompt))
    return "zh-CN" if cjk >= 20 and cjk * 3 >= latin else "en"


def classify_category(title: str, prompt: str, tags: list[str], valid_categories: set[str]) -> str:
    haystack = " ".join([title, prompt[:1200], " ".join(tags)]).lower()
    for category_id, keywords in CATEGORY_KEYWORDS:
        if category_id in valid_categories and any(kw in haystack for kw in keywords):
            return category_id
    return "multi-shot-storytelling" if "multi-shot-storytelling" in valid_categories else sorted(valid_categories)[0]


def infer_task_type(prompt: str) -> str:
    lower = prompt[:1200].lower()
    if any(k in lower for k in ("omni-ref", "character-sheet", "character sheet", "参考图", "reference image", "strict identity")):
        return "omni-ref"
    if any(k in lower for k in ("image-to-video", "i2v", "first frame", "图生视频", "首帧参考")):
        return "i2v"
    return "t2v"


def infer_audio_mode(prompt: str, has_audio: bool) -> str:
    if not has_audio:
        return "silent"
    lower = prompt[:1600].lower()
    has_dialogue = any(k in lower for k in ("dialogue", "says", "speaks", "台词", "对白", "国语配音", "对话"))
    has_music = any(k in lower for k in ("music", "soundtrack", "edm", "配乐", "笛子", "锣鼓", "beat"))
    has_sfx = any(k in lower for k in ("sfx", "diegetic", "ambience", "rain", "音效", "环境音", "雨声", "吆喝"))
    if has_dialogue and (has_music or has_sfx):
        return "mixed"
    if has_dialogue:
        return "dialogue"
    if has_music:
        return "music"
    if has_sfx:
        return "sfx"
    return "mixed"


def format_aspect_ratio(width: int | None, height: int | None) -> str | None:
    if not width or not height:
        return None
    ratio = width / height
    known = ((16 / 9, "16:9"), (9 / 16, "9:16"), (1.0, "1:1"), (4 / 3, "4:3"), (3 / 4, "3:4"), (2.35, "2.35:1"), (21 / 9, "21:9"))
    for target, label in known:
        if abs(ratio - target) <= 0.08:
            return label
    g = math.gcd(width, height)
    return f"{width // g}:{height // g}"


def format_resolution(width: int | None, height: int | None) -> str | None:
    if not width or not height:
        return None
    short_edge = min(width, height)
    if short_edge >= 2000:
        return "4K"
    if short_edge >= 1000:
        return "1080p"
    if short_edge >= 680:
        return "720p"
    return f"{short_edge}p"


def probe_remote_video(video_url: str) -> dict:
    """Inspect remote R2 MP4 stream headers using ffprobe without saving the video."""
    result = {"duration_sec": None, "fps": None, "resolution": None, "aspect_ratio": None, "has_audio": True}
    if not shutil.which("ffprobe"):
        return result
    try:
        proc = subprocess.run(
            [
                "ffprobe", "-v", "error", "-print_format", "json",
                "-show_format", "-show_streams", video_url,
            ],
            capture_output=True,
            text=True,
            timeout=25,
            check=False,
        )
        if proc.returncode != 0 or not proc.stdout.strip():
            return result
        meta = json.loads(proc.stdout)
        streams = meta.get("streams") or []
        vstream = next((s for s in streams if s.get("codec_type") == "video"), None)
        astream = next((s for s in streams if s.get("codec_type") == "audio"), None)
        result["has_audio"] = astream is not None
        dur_raw = (meta.get("format") or {}).get("duration") or (vstream or {}).get("duration")
        if dur_raw:
            result["duration_sec"] = round(float(dur_raw), 1)
        if vstream:
            w = int(vstream.get("width") or 0) or None
            h = int(vstream.get("height") or 0) or None
            result["resolution"] = format_resolution(w, h)
            result["aspect_ratio"] = format_aspect_ratio(w, h)
            rate = str(vstream.get("avg_frame_rate") or vstream.get("r_frame_rate") or "")
            if "/" in rate:
                num, den = rate.split("/", 1)
                if float(den) > 0:
                    fps_val = round(float(num) / float(den))
                    if 1 <= fps_val <= 120:
                        result["fps"] = fps_val
    except (OSError, ValueError, subprocess.SubprocessError, json.JSONDecodeError):
        return result
    return result


def extract_poster_frame(video_url: str, target_path: Path, duration_sec: float | None) -> bool:
    """Extract one lightweight JPEG poster frame (<= 450 KB) from a remote R2 MP4."""
    if not shutil.which("ffmpeg"):
        return False
    target_path.parent.mkdir(parents=True, exist_ok=True)
    seek = "1.2"
    if duration_sec and duration_sec > 0:
        seek = f"{min(1.5, max(0.2, duration_sec / 3.0)):.2f}"

    for quality in ("4", "7", "10"):
        try:
            proc = subprocess.run(
                [
                    "ffmpeg", "-y", "-v", "error", "-ss", seek, "-i", video_url,
                    "-frames:v", "1", "-vf", "scale='min(960,iw)':-2", "-q:v", quality,
                    str(target_path),
                ],
                capture_output=True,
                timeout=35,
                check=False,
            )
            if proc.returncode != 0 or not target_path.is_file():
                continue
            data = target_path.read_bytes()
            if not data.startswith(b"\xff\xd8\xff"):
                continue
            if len(data) <= SOFT_POSTER_BYTES or (quality == "10" and len(data) <= MAX_POSTER_BYTES):
                return True
        except (OSError, subprocess.SubprocessError):
            break

    if target_path.exists():
        target_path.unlink()
    try:
        if target_path.parent.exists() and not any(target_path.parent.iterdir()):
            target_path.parent.rmdir()
    except OSError:
        pass
    return False


def build_summary(title: str, prompt: str, author: str) -> dict[str, str]:
    cleaned = re.sub(r"\s+", " ", prompt).strip()
    snippet = cleaned[:130].rstrip() + ("…" if len(cleaned) > 130 else "")
    return {
        "en": f"Community MAGI-2 video case ({author}): {title}." if detect_prompt_language(prompt) == "zh-CN" else snippet,
        "zh-CN": f"社区 MAGI-2 视频案例（{author}）：{title}。",
    }


def make_new_prompt_entry(
    row: dict,
    slug: str,
    config: dict,
    template: dict,
    *,
    extract_media: bool = True,
) -> dict:
    valid_categories = {cat["id"] for cat in config["categories"]}
    title = str(row.get("title") or "").strip()
    prompt = str(row.get("prompt") or "").strip()
    raw_tags = row.get("tags")
    tags = [str(tag).strip().lower() for tag in raw_tags if str(tag).strip()] if isinstance(raw_tags, list) else []

    video_url = normalize_https_url(row.get("image_url"))
    if video_url and not is_approved_media_url(video_url, config):
        video_url = None
    if not video_url and isinstance(row.get("r2_object_key"), str) and row["r2_object_key"].strip():
        key = row["r2_object_key"].strip().lstrip("/")
        base_parts = urlsplit(media_base_url(config))
        candidate = f"{base_parts.scheme}://{base_parts.netloc}/{key}"
        if is_approved_media_url(candidate, config):
            video_url = candidate

    source_url = normalize_https_url(row.get("source_post_url"))
    author_url = normalize_https_url(row.get("author_x_url"))
    author = extract_author_handle(author_url, source_url)
    added_at = iso_date_part(row.get("date_created")) or datetime.now(timezone.utc).strftime("%Y-%m-%d")
    published_at = iso_date_part(row.get("source_published_at"))

    media_meta = probe_remote_video(video_url) if (extract_media and video_url) else {
        "duration_sec": None, "fps": None, "resolution": None, "aspect_ratio": None, "has_audio": True
    }
    poster_rel = f"assets/examples/{slug}/preview.jpg"
    poster_ok = False
    if extract_media and video_url:
        poster_file = ROOT / poster_rel
        if poster_file.is_file() and poster_file.stat().st_size <= MAX_POSTER_BYTES:
            poster_ok = True
        else:
            poster_ok = extract_poster_frame(video_url, poster_file, media_meta.get("duration_sec"))

    category = classify_category(title, prompt, tags, valid_categories)
    task_type = infer_task_type(prompt)
    prompt_lang = detect_prompt_language(prompt)
    has_audio = bool(media_meta.get("has_audio", True))
    audio_mode = infer_audio_mode(prompt, has_audio)

    is_short = len(prompt) <= 450 and "\n\n" not in prompt
    notes_raw = str(row.get("notes") or "").strip()

    entry = copy.deepcopy(template)
    entry.update({
        "id": slug,
        "status": "published",
        "title": {"en": title, "zh-CN": title},
        "summary": build_summary(title, prompt, author),
        "category": category,
        "tags": sorted(set(tags + [task_type, "cms-synced"])),
        "origin": "community" if source_url else "original",
        "prompt_status": "public",
        "prompt_language": prompt_lang,
        "short_prompt": prompt if is_short else "",
        "structured_prompt": None if is_short else prompt,
        "omni_references": [],
        "model": {
            "family": config["project"]["model_family"],
            "variant": "flagship",
            "api_model_id": None,
        },
        "parameters": {
            "task_type": task_type,
            "duration_sec": media_meta.get("duration_sec"),
            "fps": media_meta.get("fps"),
            "resolution": media_meta.get("resolution"),
            "aspect_ratio": media_meta.get("aspect_ratio"),
            "has_audio": has_audio,
            "audio_mode": audio_mode,
        },
        "preview": {
            "path": poster_rel if poster_ok else "",
            "alt": {
                "en": f"Preview still frame from {title} MAGI-2 clip" if poster_ok else "",
                "zh-CN": f"MAGI-2 案例《{title}》视频封面帧" if poster_ok else "",
            },
        },
        "video_url": video_url,
        "source": {
            "url": source_url,
            "author": author,
            "author_url": author_url,
            "platform": "X" if source_url and ("x.com" in source_url or "twitter.com" in source_url) else "Community",
            "published_at": published_at,
        },
        "verification": {
            "status": "source-only",
            "tested_at": None,
            "tested_on": "",
            "notes": {"en": "", "zh-CN": ""},
        },
        "rights": {
            "prompt": "source-attributed",
            "preview": "source-attributed" if poster_ok else "link-only",
            "video": "link-only",
            "credit": author,
            "license_url": None,
        },
        "added_at": added_at,
        "featured": False,
        "links": {
            "case_detail_url": None,
            "generate_url": None,
            "generate_url_verified_at": None,
        },
        "notes": {
            "en": notes_raw or "Synced automatically from Directus CMS magi2_materials.",
            "zh-CN": notes_raw or "由 GitHub Actions 从 Directus CMS magi2_materials 自动同步。",
        },
    })
    return entry


def read_sync_state() -> dict:
    path = ROOT / CMS_SYNC_STATE_PATH
    if not path.is_file():
        return {"collection": "magi2_materials", "synced_at": None, "total_cms_records": 0, "id_map": {}}
    return read_json(CMS_SYNC_STATE_PATH)


def sync_to_disk(
    base_url: str,
    token: str,
    *,
    force_timestamp: bool = False,
    extract_media: bool = True,
    now: datetime | None = None,
) -> tuple[bool, int, int]:
    config = read_json("site.config.json")
    template = read_json("templates/prompt.json")
    prompts = read_json("content/prompts.json")
    collection = str((config.get("cms") or {}).get("collection") or "magi2_materials")
    raw_rows = fetch_all_materials(base_url, token, collection)

    prev_state = read_sync_state()
    id_map: dict[str, str] = dict(prev_state.get("id_map") or {})

    by_id = {item["id"]: item for item in prompts if item.get("id")}
    by_video = {item["video_url"]: item["id"] for item in prompts if item.get("video_url")}
    by_source = {
        (item.get("source") or {}).get("url"): item["id"]
        for item in prompts
        if (item.get("source") or {}).get("url")
    }

    added_count = 0
    updated_prompts = copy.deepcopy(prompts)
    updated_by_id = {item["id"]: item for item in updated_prompts if item.get("id")}

    for row in raw_rows:
        status = str(row.get("status") or "").strip().lower()
        if status and status not in ALLOWED_STATUSES:
            continue
        cms_id = str(row.get("id") or "").strip()
        title = str(row.get("title") or "").strip()
        prompt_text = str(row.get("prompt") or "").strip()
        if not cms_id or not title or not prompt_text:
            continue

        video_url = normalize_https_url(row.get("image_url"))
        source_url = normalize_https_url(row.get("source_post_url"))

        existing_id = id_map.get(cms_id)
        if existing_id not in updated_by_id:
            existing_id = None
        if not existing_id and video_url and video_url in by_video:
            existing_id = by_video[video_url]
        if not existing_id and source_url and source_url in by_source:
            existing_id = by_source[source_url]

        if existing_id:
            id_map[cms_id] = existing_id
            # Preserve curated fields; only backfill video_url if missing.
            existing_item = updated_by_id[existing_id]
            if not existing_item.get("video_url") and video_url and is_approved_media_url(video_url, config):
                existing_item["video_url"] = video_url
            continue

        short_hex = re.sub(r"[^a-z0-9]", "", cms_id.lower())[:8]
        slug = f"cms-{short_hex}"
        if slug in updated_by_id:
            slug = f"cms-{re.sub(r'[^a-z0-9]', '', cms_id.lower())[:12]}"

        entry = make_new_prompt_entry(row, slug, config, template, extract_media=extract_media)
        updated_prompts.append(entry)
        updated_by_id[slug] = entry
        id_map[cms_id] = slug
        if entry.get("video_url"):
            by_video[entry["video_url"]] = slug
        if (entry.get("source") or {}).get("url"):
            by_source[entry["source"]["url"]] = slug
        added_count += 1

    total_count = len(raw_rows)
    sorted_id_map = dict(sorted(id_map.items()))
    data_changed = (
        updated_prompts != prompts
        or sorted_id_map != dict(sorted((prev_state.get("id_map") or {}).items()))
        or total_count != prev_state.get("total_cms_records")
        or prev_state.get("collection") != collection
        or not (ROOT / CMS_SYNC_STATE_PATH).is_file()
    )

    if not data_changed and not force_timestamp:
        return False, added_count, total_count

    ts = (now or datetime.now(timezone.utc)).astimezone(timezone.utc).replace(microsecond=0)
    (ROOT / "content" / "prompts.json").write_text(
        json.dumps(updated_prompts, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    state_payload = {
        "collection": collection,
        "cms_base_url": base_url.rstrip("/"),
        "media_base_url": media_base_url(config),
        "synced_at": ts.strftime("%Y-%m-%dT%H:%M:%SZ"),
        "total_cms_records": total_count,
        "id_map": sorted_id_map,
    }
    (ROOT / CMS_SYNC_STATE_PATH).write_text(
        json.dumps(state_payload, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    return True, added_count, total_count


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--force-timestamp", action="store_true", help="Refresh synced_at even when CMS data is unchanged.")
    parser.add_argument("--no-media-probe", action="store_true", help="Skip ffprobe/ffmpeg poster extraction.")
    args = parser.parse_args()
    try:
        changed, added_count, total_count = sync_to_disk(
            os.environ.get("CMS_BASE_URL", ""),
            os.environ.get("CMS_READ_TOKEN", ""),
            force_timestamp=args.force_timestamp,
            extract_media=not args.no_media_probe,
        )
    except HTTPError as exc:
        print(f"MAGI-2 CMS sync request failed (HTTP {exc.code}).", file=sys.stderr)
        return 1
    except (URLError, OSError, ValueError, KeyError, IndexError, TypeError) as exc:
        print(f"MAGI-2 CMS sync failed: {exc}", file=sys.stderr)
        return 1

    if changed:
        print(f"Synced MAGI-2 CMS materials: +{added_count} new prompts (CMS total: {total_count}).")
    else:
        print(f"No MAGI-2 CMS changes detected (CMS total: {total_count}); skipped timestamp churn.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
