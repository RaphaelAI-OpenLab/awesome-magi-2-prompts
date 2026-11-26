#!/usr/bin/env python3
"""Sync only the MAGI-2 Directus CMS count and timestamp into root READMEs."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
import json
import os
import re
import sys
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode, urlsplit
from urllib.request import Request, urlopen

from common import ROOT, read_json
from i18n import LANGUAGES, filename, ui

MARKER = re.compile(r"^<!-- cms-stats (pending|([0-9]+) ([0-9TZ:-]+)) -->$", re.M)


@dataclass(frozen=True)
class CmsStats:
    count: int
    synced_at: datetime


def stats_marker(stats: CmsStats | None) -> str:
    """Serialize CMS sync state as an HTML comment marker."""
    if stats is None:
        return "<!-- cms-stats pending -->"
    return f"<!-- cms-stats {stats.count} {stats.synced_at:%Y-%m-%dT%H:%M:%SZ} -->"


def read_cms_stats() -> CmsStats | None:
    """Preserve existing CMS statistics from README.md across README rebuilds."""
    readme = ROOT / filename("en")
    match = MARKER.search(readme.read_text(encoding="utf-8")) if readme.exists() else None
    if match is None or match[1] == "pending":
        return None
    return CmsStats(int(match[2]), datetime.fromisoformat(match[3]))


def cms_rows(language: str, stats: CmsStats | None, fallback_time: datetime) -> tuple[str, ...]:
    """Render the last-updated row for the statistics table."""
    updated = (stats.synced_at if stats else fallback_time).astimezone(timezone.utc)
    if language == "zh-CN":
        weekday = "一二三四五六日"[updated.weekday()]
        updated_label = f"{updated.year}年{updated.month}月{updated.day}日星期{weekday} UTC {updated:%H:%M:%S}"
    else:
        updated_label = f"{updated:%Y-%m-%d} UTC {updated:%H:%M:%S}"
    updated_name = ui("Last updated", "最后更新", language)
    return (f"| 🔄 {updated_name} | **{updated_label}** |",)


def replace_readme_stats(content: str, language: str, stats: CmsStats) -> str:
    """Update the CMS marker and statistics rows inside an existing README."""
    content, replaced = MARKER.subn(lambda _: stats_marker(stats), content)
    if replaced != 1:
        raise ValueError(f"Expected one CMS statistics marker in {filename(language)}.")
    for row in cms_rows(language, stats, stats.synced_at):
        prefix = row.split(" | **", 1)[0]
        pattern = rf"^{re.escape(prefix)} \| \*\*[^\n]+\*\* \|$"
        content, replaced = re.subn(pattern, lambda _: row, content, flags=re.M)
        if replaced != 1:
            raise ValueError(f"Expected one row for {prefix[2:]} in {filename(language)}.")
    return content


def fetch_material_count(base_url: str, token: str, collection: str) -> int:
    """Fetch aggregate record count from the configured Directus CMS collection."""
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
        raise ValueError("Set CMS_BASE_URL to the HTTPS origin, configure CMS_READ_TOKEN, and check collection name.")
    query = urlencode({"aggregate[count]": "id"})
    request = Request(
        f"{base_url.rstrip('/')}/items/{collection}?{query}",
        headers={"Accept": "application/json", "User-Agent": "Raphael-MAGI2-CMS-Stats/1.0"},
    )
    request.add_unredirected_header("Authorization", f"Bearer {token}")
    with urlopen(request, timeout=20) as response:
        rows = json.load(response)["data"]

    count = rows[0]["count"]["id"]
    if type(count) is int and count >= 0:
        return count
    if isinstance(count, str) and re.fullmatch(r"[0-9]+", count):
        return int(count)
    raise ValueError("CMS returned an invalid material count.")


def main() -> int:
    try:
        config = read_json("site.config.json")
        collection = config.get("cms", {}).get("collection", "magi2_materials")
        count = fetch_material_count(
            os.environ.get("CMS_BASE_URL", ""),
            os.environ.get("CMS_READ_TOKEN", ""),
            collection,
        )
        stats = CmsStats(count, datetime.now(timezone.utc).replace(microsecond=0))
        updates = {}
        for language in LANGUAGES:
            path = ROOT / filename(language)
            updates[path] = replace_readme_stats(path.read_text(encoding="utf-8"), language, stats)
        for path, content in updates.items():
            path.write_text(content, encoding="utf-8")
    except HTTPError as exc:
        print(f"CMS statistics request failed (HTTP {exc.code}).", file=sys.stderr)
        return 1
    except (URLError, OSError, ValueError, KeyError, IndexError, TypeError) as exc:
        print(f"CMS statistics sync failed: {exc}", file=sys.stderr)
        return 1
    print(f"Synced {count} CMS materials ({collection}) to {len(updates)} READMEs.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
