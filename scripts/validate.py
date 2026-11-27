#!/usr/bin/env python3
"""Validate site config, MAGI-2 prompt dataset, media weight limits, and links."""

from __future__ import annotations

import argparse
import datetime as dt
import html
import json
import re
import sys
from pathlib import Path
from urllib.parse import unquote, urlsplit

from common import ROOT, has_copyable_prompt, is_brand_url, load_data, published, read_json

MAX_LOCAL_IMAGE_BYTES = 500 * 1024
DISALLOWED_GIT_MEDIA_SUFFIXES = {".mp4", ".mov", ".webm", ".mkv", ".avi", ".wav", ".mp3", ".m4a", ".flac"}
ALLOWED_IMAGE_SUFFIXES = {".png", ".jpg", ".jpeg", ".webp", ".gif", ".svg"}


def schema_errors(value, schema: dict, path: str, root: dict) -> list[str]:
    """Validate the subset of JSON Schema Draft 2020-12 used by content/schema.json."""
    if "$ref" in schema:
        schema = root["$defs"][schema["$ref"].split("/")[-1]]
    errors: list[str] = []
    types = schema.get("type", [])
    types = [types] if isinstance(types, str) else types
    matches = {
        "null": value is None,
        "object": isinstance(value, dict),
        "array": isinstance(value, list),
        "string": isinstance(value, str),
        "boolean": isinstance(value, bool),
        "integer": isinstance(value, int) and not isinstance(value, bool),
        "number": isinstance(value, (int, float)) and not isinstance(value, bool),
    }
    if types and not any(matches.get(kind, False) for kind in types):
        return [f"{path}: expected {' or '.join(types)}"]
    if "enum" in schema and value not in schema["enum"]:
        errors.append(f"{path}: value {value!r} is not in allowed options")
    if isinstance(value, str) and "pattern" in schema and not re.fullmatch(schema["pattern"], value):
        errors.append(f"{path}: invalid format")
    if isinstance(value, dict):
        properties = schema.get("properties", {})
        for key in schema.get("required", []):
            if key not in value:
                errors.append(f"{path}.{key}: missing required field")
        for key, child in value.items():
            if key in properties:
                errors.extend(schema_errors(child, properties[key], f"{path}.{key}", root))
            elif schema.get("additionalProperties") is False:
                errors.append(f"{path}.{key}: unknown field")
            elif isinstance(schema.get("additionalProperties"), dict):
                errors.extend(schema_errors(child, schema["additionalProperties"], f"{path}.{key}", root))
    if isinstance(value, list) and "items" in schema:
        for index, child in enumerate(value):
            errors.extend(schema_errors(child, schema["items"], f"{path}[{index}]", root))
    return errors


def is_date(value) -> bool:
    """Check strict YYYY-MM-DD calendar date format."""
    if not isinstance(value, str) or not re.fullmatch(r"\d{4}-\d{2}-\d{2}", value):
        return False
    try:
        dt.date.fromisoformat(value)
        return True
    except ValueError:
        return False


def is_https_url(value) -> bool:
    """Check strict HTTPS URL without credentials or whitespace."""
    if not isinstance(value, str):
        return False
    try:
        parts = urlsplit(value)
    except ValueError:
        return False
    return parts.scheme == "https" and bool(parts.hostname) and not parts.username and not re.search(r"[\s<>]", value)


def media_mime(data: bytes) -> str | None:
    """Sniff actual file format from header bytes rather than extension."""
    if data.startswith(b"\x89PNG\r\n\x1a\n"):
        return "image/png"
    if data.startswith(b"\xff\xd8\xff"):
        return "image/jpeg"
    if data.startswith(b"RIFF") and data[8:12] == b"WEBP":
        return "image/webp"
    if data.startswith((b"GIF87a", b"GIF89a")):
        return "image/gif"
    if len(data) >= 12 and data[4:8] == b"ftyp":
        return "video/mp4"
    if b"<svg" in data[:1024]:
        return "image/svg+xml"
    return None


def check_local_image(path: str, expected_prefix: str, label: str, errors: list[str]) -> None:
    """Ensure a local image stays inside expected_prefix, <= 500 KB, and is not video/audio."""
    if not isinstance(path, str) or not path.strip():
        errors.append(f"{label}: expected a non-empty local path")
        return
    if urlsplit(path).scheme:
        errors.append(f"{label}: local repository file path expected, not a remote URL")
        return
    if not path.startswith(expected_prefix) or ".." in Path(path).parts:
        errors.append(f"{label}: path must stay inside {expected_prefix}")
        return
    candidate = (ROOT / path).resolve()
    if not candidate.is_relative_to(ROOT.resolve()) or not candidate.is_file():
        errors.append(f"{label}: file does not exist: {path}")
        return
    if candidate.suffix.lower() not in ALLOWED_IMAGE_SUFFIXES:
        errors.append(f"{label}: unsupported local preview suffix {candidate.suffix}")
        return
    data = candidate.read_bytes()
    if len(data) > MAX_LOCAL_IMAGE_BYTES:
        errors.append(f"{label}: local preview exceeds 500 KB ({len(data)} bytes)")
    mime = media_mime(data)
    if mime == "video/mp4" or mime is None:
        errors.append(f"{label}: invalid or video payload inside Git image slot")


def validate_config(config, errors: list[str]) -> None:
    """Validate site.config.json structure, GitHub About/Topics limits, and brand URLs."""
    if not isinstance(config, dict):
        errors.append("site.config.json: expected an object")
        return
    required = {
        "project": [
            "name", "repository_slug", "repository_owner", "default_branch",
            "model_family", "official_release_date", "official_url",
            "model_docs_url", "huggingface_url", "model_ids",
        ],
        "github": ["description", "homepage", "topics"],
        "brand": ["name", "home_url", "gallery_url", "model_page_url", "model_available", "model_support_verified_at"],
        "tracking": ["utm_source", "utm_medium", "utm_campaign"],
        "cms": ["collection"],
        "presentation": ["updated_at", "featured_limit", "latest_limit", "generate_case_pages", "featured_case_ids"],
    }
    for section, fields in required.items():
        if not isinstance(config.get(section), dict):
            errors.append(f"site.config.json.{section}: expected an object")
            continue
        for field in fields:
            if field not in config[section]:
                errors.append(f"site.config.json.{section}.{field}: missing required field")
    if not isinstance(config.get("categories"), list) or not config["categories"]:
        errors.append("site.config.json.categories: expected a non-empty array")
    if errors:
        return

    project = config["project"]
    github = config["github"]
    brand = config["brand"]
    presentation = config["presentation"]

    for key in ("name", "repository_slug", "repository_owner", "default_branch", "model_family"):
        if not isinstance(project[key], str) or not project[key].strip():
            errors.append(f"project.{key}: expected non-empty text")
    if not re.fullmatch(r"[A-Za-z0-9-]+", project["repository_owner"]):
        errors.append("project.repository_owner: invalid GitHub owner")
    if not re.fullmatch(r"[A-Za-z0-9_.-]+", project["repository_slug"]):
        errors.append("project.repository_slug: invalid repository slug")
    for key in ("official_url", "model_docs_url", "huggingface_url"):
        if not is_https_url(project[key]):
            errors.append(f"project.{key}: expected HTTPS URL")
    if not is_date(project["official_release_date"]):
        errors.append("project.official_release_date: expected YYYY-MM-DD")
    if not isinstance(project["model_ids"], list) or not project["model_ids"]:
        errors.append("project.model_ids: expected non-empty list")

    desc = github["description"]
    if not isinstance(desc, str) or not desc.strip():
        errors.append("github.description: required")
    elif len(desc) > 125:
        errors.append(f"github.description: must be <= 125 chars (got {len(desc)})")
    if not is_https_url(github["homepage"]):
        errors.append("github.homepage: expected HTTPS URL")
    topics = github["topics"]
    if not isinstance(topics, list) or len(topics) != 20:
        errors.append("github.topics: expected exactly 20 topics for GitHub About")
    else:
        if len(set(topics)) != len(topics):
            errors.append("github.topics: duplicate topics found")
        for topic in topics:
            if not isinstance(topic, str) or not re.fullmatch(r"[a-z0-9][a-z0-9-]{0,49}", topic):
                errors.append(f"github.topics: invalid GitHub topic slug {topic!r}")

    if not isinstance(brand["name"], str) or not brand["name"].strip():
        errors.append("brand.name: expected non-empty text")
    if not is_https_url(brand["home_url"]):
        errors.append("brand.home_url: expected HTTPS URL")
    for key in ("gallery_url", "model_page_url"):
        if brand[key] is not None and not is_https_url(brand[key]):
            errors.append(f"brand.{key}: expected HTTPS URL or null")
        elif brand[key] and not is_brand_url(brand[key], config):
            errors.append(f"brand.{key}: must stay on the brand domain")
    if not isinstance(brand["model_available"], bool):
        errors.append("brand.model_available: expected boolean")
    if brand["model_support_verified_at"] is not None and not is_date(brand["model_support_verified_at"]):
        errors.append("brand.model_support_verified_at: expected YYYY-MM-DD or null")
    if brand["model_available"] and (not brand["model_page_url"] or not is_date(brand["model_support_verified_at"])):
        errors.append("brand.model_available=true requires model_page_url and model_support_verified_at")

    if set(config["tracking"]) != {"utm_source", "utm_medium", "utm_campaign"}:
        errors.append("tracking: expected utm_source, utm_medium, and utm_campaign")
    if not re.fullmatch(r"[A-Za-z0-9_]+", str(config["cms"].get("collection", ""))):
        errors.append("cms.collection: invalid collection identifier")
    if config["cms"].get("media_base_url") is not None and not is_https_url(config["cms"]["media_base_url"]):
        errors.append("cms.media_base_url: expected HTTPS URL")

    try:
        updated = dt.datetime.fromisoformat(presentation["updated_at"])
        if updated.utcoffset() != dt.timedelta(0):
            raise ValueError("UTC required")
    except (TypeError, ValueError):
        errors.append("presentation.updated_at: expected ISO 8601 UTC timestamp")
    for key in ("featured_limit", "latest_limit"):
        if not isinstance(presentation[key], int) or isinstance(presentation[key], bool) or not 1 <= presentation[key] <= 30:
            errors.append(f"presentation.{key}: expected integer 1..30")
    featured_ids = presentation["featured_case_ids"]
    if not isinstance(featured_ids, list) or len(featured_ids) != len(set(featured_ids)):
        errors.append("presentation.featured_case_ids: expected unique ID list")

    seen_categories = set()
    for index, category in enumerate(config["categories"]):
        label = f"categories[{index}]"
        if not isinstance(category, dict) or not all(k in category for k in ("id", "label", "website_url")):
            errors.append(f"{label}: missing id, label, or website_url")
            continue
        cid = category["id"]
        if not isinstance(cid, str) or not re.fullmatch(r"[a-z0-9]+(?:-[a-z0-9]+)*", cid):
            errors.append(f"{label}.id: expected lowercase slug")
        elif cid in seen_categories:
            errors.append(f"{label}.id: duplicate category ID")
        else:
            seen_categories.add(cid)
        if not isinstance(category["label"], dict) or not all(
            isinstance(category["label"].get(lang), str) and category["label"][lang].strip()
            for lang in ("en", "zh-CN")
        ):
            errors.append(f"{label}.label: en and zh-CN labels required")
        url = category["website_url"]
        if url is not None and (not is_https_url(url) or not is_brand_url(url, config)):
            errors.append(f"{label}.website_url: expected HTTPS brand URL or null")


def validate_prompts(config: dict, prompts: list[dict], errors: list[str], warnings: list[str], *, release: bool) -> None:
    """Validate prompt records, media separation, and featured slot quality gates."""
    categories = {cat["id"] for cat in config["categories"]}
    seen_ids: set[str] = set()
    published_ids: set[str] = set()
    by_id: dict[str, dict] = {}

    for index, item in enumerate(prompts):
        label = f"prompts[{index}] ({item.get('id') or 'unnamed'})"
        item_id = item["id"]
        if item_id:
            if item_id in seen_ids:
                errors.append(f"{label}: duplicate ID")
            seen_ids.add(item_id)
            by_id[item_id] = item

        for section, key in (
            ("source", "url"),
            ("source", "author_url"),
            ("rights", "license_url"),
            ("links", "case_detail_url"),
            ("links", "generate_url"),
        ):
            val = item[section][key]
            if val is not None and not is_https_url(val):
                errors.append(f"{label}.{section}.{key}: expected HTTPS URL or null")
            if val and section == "links" and not is_brand_url(val, config):
                errors.append(f"{label}.{section}.{key}: must point to brand domain")
        if item["video_url"] is not None and not is_https_url(item["video_url"]):
            errors.append(f"{label}.video_url: expected HTTPS URL or null")

        for field_name, val in (
            ("added_at", item["added_at"]),
            ("source.published_at", item["source"]["published_at"]),
            ("verification.tested_at", item["verification"]["tested_at"]),
            ("links.generate_url_verified_at", item["links"]["generate_url_verified_at"]),
        ):
            if val is not None and not is_date(val):
                errors.append(f"{label}.{field_name}: expected YYYY-MM-DD or null")

        if item["status"] != "published":
            continue
        published_ids.add(item_id)
        for field_name, val in (
            ("id", item_id),
            ("title.en", item["title"]["en"]),
            ("prompt_language", item["prompt_language"]),
            ("source.author", item["source"]["author"]),
        ):
            if not str(val).strip():
                errors.append(f"{label}.{field_name}: required for published entries")
        if item["category"] not in categories:
            errors.append(f"{label}.category: unknown category {item['category']!r}")
        if not is_date(item["added_at"]):
            errors.append(f"{label}.added_at: required for published entries")
        if item["prompt_status"] == "public" and not has_copyable_prompt(item):
            errors.append(f"{label}: prompt_status=public requires non-empty short_prompt or structured_prompt")
        if item["featured"] and not has_copyable_prompt(item):
            errors.append(f"{label}: featured cases must include a copyable public prompt")

        family = item["model"]["family"]
        if family is not None and family != config["project"]["model_family"]:
            errors.append(f"{label}.model.family: expected {config['project']['model_family']!r} or null")
        api_id = item["model"]["api_model_id"]
        if api_id and api_id not in config["project"]["model_ids"]:
            errors.append(f"{label}.model.api_model_id: unknown model ID {api_id!r}")
        if item["origin"] in ("official", "community") and not item["source"]["url"]:
            errors.append(f"{label}.source.url: official/community cases require source URL")

        preview_path = item["preview"]["path"]
        if item["rights"]["preview"] == "link-only":
            if preview_path:
                errors.append(f"{label}: link-only preview must leave preview.path empty")
        elif preview_path:
            if item["rights"]["preview"] == "unknown":
                errors.append(f"{label}.rights.preview: do not embed local media with unknown rights")
            check_local_image(preview_path, f"assets/examples/{item_id}/", f"{label}.preview.path", errors)
            if not item["preview"]["alt"]["en"].strip():
                errors.append(f"{label}.preview.alt.en: alt text required")
        else:
            errors.append(f"{label}.preview.path: add local preview image or set rights.preview=link-only")

        for ref_index, ref in enumerate(item["omni_references"]):
            if ref["path"]:
                check_local_image(
                    ref["path"],
                    f"assets/references/{item_id}/",
                    f"{label}.omni_references[{ref_index}].path",
                    errors,
                )
            if ref["url"] is not None and not is_https_url(ref["url"]):
                errors.append(f"{label}.omni_references[{ref_index}].url: expected HTTPS URL or null")

        if item["links"]["generate_url"] and (
            not config["brand"]["model_available"] or not is_date(item["links"]["generate_url_verified_at"])
        ):
            errors.append(f"{label}.links.generate_url: requires model_available=true and verification date")

        if release and item["rights"]["prompt"] == "unknown":
            warnings.append(f"{label}.rights.prompt: terms not yet recorded")

    for fid in config["presentation"]["featured_case_ids"]:
        if fid not in published_ids:
            errors.append(f"presentation.featured_case_ids: {fid!r} is not a published case")
        elif not has_copyable_prompt(by_id[fid]):
            errors.append(f"presentation.featured_case_ids: {fid!r} lacks a copyable public prompt")


def validate_repo_hygiene(errors: list[str]) -> None:
    """Prevent accidental commit of large video/audio files or oversized images."""
    for path in ROOT.rglob("*"):
        if not path.is_file():
            continue
        rel = path.relative_to(ROOT)
        if rel.parts[0] in {".git", "__pycache__", "dist"}:
            continue
        if path.suffix.lower() in DISALLOWED_GIT_MEDIA_SUFFIXES:
            errors.append(f"{rel}: binary video/audio files must not be stored in Git")
        elif rel.parts[0] == "assets" and path.suffix.lower() in ALLOWED_IMAGE_SUFFIXES:
            if path.stat().st_size > MAX_LOCAL_IMAGE_BYTES:
                errors.append(f"{rel}: image exceeds 500 KB limit ({path.stat().st_size} bytes)")


def validate_examples(errors: list[str]) -> None:
    """Verify bundled developer PE templates parse as valid JSON."""
    for name in ("t2v_pe_template.json", "i2v_pe_template.json", "demo_samples.example.json"):
        path = ROOT / "examples" / name
        if not path.is_file():
            errors.append(f"examples/{name}: missing template file")
            continue
        try:
            json.loads(path.read_text(encoding="utf-8"))
        except json.JSONDecodeError as exc:
            errors.append(f"examples/{name}: invalid JSON ({exc})")


def markdown_link_errors() -> list[str]:
    """Validate all repository-local Markdown links and explicit HTML/heading anchors."""
    errors: list[str] = []
    anchors: dict[Path, set[str]] = {}
    paths = (
        list(ROOT.glob("*.md"))
        + list((ROOT / "docs").glob("*.md"))
        + list((ROOT / "templates").glob("*.md"))
        + list((ROOT / "cases").glob("*/README*.md"))
    )
    for path in paths:
        text = path.read_text(encoding="utf-8")
        prose = re.sub(r"(?ms)^(`{3,}|~{3,}).*?^\1[^\n]*$", "", text)
        targets = re.findall(r"!?\[[^\]\n]*\]\(([^\s)]+)(?:\s+[^)]*)?\)", prose)
        targets += re.findall(r'(?:href|src)="([^"]+)"', prose)
        for raw in targets:
            target = html.unescape(raw)
            if "{{" in target or urlsplit(target).scheme or target.startswith("//"):
                continue
            parts = urlsplit(target)
            linked = (path.parent / unquote(parts.path)).resolve() if parts.path else path
            if not linked.is_relative_to(ROOT.resolve()) or not linked.exists():
                errors.append(f"{path.relative_to(ROOT)}: local target does not exist: {target}")
                continue
            if parts.fragment and linked.suffix == ".md":
                if linked not in anchors:
                    contents = linked.read_text(encoding="utf-8")
                    explicit = set(re.findall(r'<a\s+(?:id|name)="([^"]+)"', contents))
                    headings = {
                        re.sub(r"[^\w\- ]", "", h.lower()).replace(" ", "-")
                        for h in re.findall(r"^#+ (.+)$", contents, re.M)
                    }
                    anchors[linked] = explicit | headings
                if unquote(parts.fragment) not in anchors[linked]:
                    errors.append(f"{path.relative_to(ROOT)}: anchor does not exist: {target}")
    return errors


def validate(*, release: bool = False, check_links: bool = True) -> tuple[list[str], list[str]]:
    """Run full validation across config, dataset, media hygiene, templates, and links."""
    errors: list[str] = []
    warnings: list[str] = []
    try:
        config, prompts = load_data()
        schema = read_json("content/schema.json")
        template = read_json("templates/prompt.json")
    except (OSError, json.JSONDecodeError) as exc:
        return [str(exc)], warnings

    validate_config(config, errors)
    errors.extend(schema_errors(prompts, schema, "prompts", schema))
    errors.extend(schema_errors([template], schema, "template", schema))
    if errors:
        return errors, warnings

    validate_prompts(config, prompts, errors, warnings, release=release)
    state_path = ROOT / "content" / "cms-sync-state.json"
    if state_path.is_file():
        try:
            state = read_json("content/cms-sync-state.json")
            id_map = state.get("id_map")
            known_ids = {item["id"] for item in prompts if item.get("id")}
            if not isinstance(id_map, dict):
                errors.append("content/cms-sync-state.json.id_map: expected an object")
            else:
                for cms_id, prompt_id in id_map.items():
                    if prompt_id not in known_ids:
                        errors.append(f"content/cms-sync-state.json.id_map[{cms_id}]: unknown prompt ID {prompt_id!r}")
        except (OSError, json.JSONDecodeError) as exc:
            errors.append(f"content/cms-sync-state.json: {exc}")
    validate_repo_hygiene(errors)
    validate_examples(errors)
    for asset in ("assets/header.svg", "assets/gallery-placeholder.svg"):
        if not (ROOT / asset).is_file():
            errors.append(f"{asset}: missing required SVG asset")

    if release and not published(prompts):
        errors.append("Release: at least one published MAGI-2 prompt entry is required")
    if check_links:
        errors.extend(markdown_link_errors())
    return errors, warnings


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--release", action="store_true", help="Also require >= 1 published prompt.")
    args = parser.parse_args()
    errors, warnings = validate(release=args.release)
    for warning in warnings:
        print(f"NOTE: {warning}")
    for error in errors:
        print(f"ERROR: {error}", file=sys.stderr)
    if errors:
        print(f"Validation failed ({len(errors)} issues).", file=sys.stderr)
        return 1
    _, prompts = load_data()
    print(f"Validation passed: {len(published(prompts))} published prompts, {sum(p['status'] == 'draft' for p in prompts)} drafts.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
