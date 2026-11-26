"""Regression tests for MAGI-2 config, dataset schema, media limits, and README build."""

import copy
import json
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))

from build_readme import outputs, render_home, stale_case_pages
from common import GENERATED_MARKER, ROOT, load_data, read_json
from validate import MAX_LOCAL_IMAGE_BYTES, schema_errors, validate, validate_prompts, validate_repo_hygiene


def make_sample_prompt(item_id: str = "sample-rainy-cafe") -> dict:
    """Create a complete valid prompt entry from templates/prompt.json for tests."""
    template = copy.deepcopy(read_json("templates/prompt.json"))
    template.update({
        "id": item_id,
        "status": "published",
        "title": {"en": "Rainy Cafe Barista Dialogue", "zh-CN": "雨天咖啡馆对白"},
        "summary": {"en": "Single take with ambient rain and spoken line.", "zh-CN": "单镜头雨声环境音与人物对白。"},
        "category": "dialogue-lip-sync",
        "tags": ["dialogue", "audio-sync"],
        "origin": "official",
        "prompt_status": "public",
        "prompt_language": "en",
        "short_prompt": "A barista places a ceramic cup on a saucer and greets a guest on a rainy afternoon.",
        "structured_prompt": {"global_layer": {"context": "Rainy cafe"}},
        "video_url": "https://cdn.example.com/magi2/sample.mp4",
        "added_at": "2026-11-26",
        "featured": True,
    })
    template["source"].update({
        "url": "https://sand.ai/blog/magi-2-preview",
        "author": "Sand.ai",
        "platform": "Sand.ai",
        "published_at": "2026-08-04",
    })
    template["rights"].update({"prompt": "source-attributed", "preview": "link-only", "video": "link-only", "credit": "Sand.ai"})
    return template


class CollectionTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.config, cls.prompts = load_data()

    def test_current_repo_validates_cleanly(self):
        errors, _ = validate(release=True)
        self.assertEqual(errors, [])

    def test_generated_files_are_up_to_date(self):
        expected = outputs(self.config, self.prompts)
        self.assertEqual(stale_case_pages(expected), [])
        for path, expected_text in expected.items():
            self.assertTrue(path.exists(), f"Missing generated file: {path}")
            self.assertEqual(path.read_text(encoding="utf-8"), expected_text, str(path))

    def test_cms_stats_replacement_matches_generated_readmes(self):
        import datetime as dt
        from sync_cms_stats import CmsStats, replace_readme_stats
        stats = CmsStats(10, dt.datetime(2026, 11, 26, 8, 0, 0, tzinfo=dt.timezone.utc))
        for lang, name in (("en", "README.md"), ("zh-CN", "README.zh-CN.md")):
            text = (ROOT / name).read_text(encoding="utf-8")
            updated = replace_readme_stats(text, lang, stats)
            self.assertIn("<!-- cms-stats 10 2026-11-26T08:00:00Z -->", updated)
            self.assertNotIn("CMS materials", updated)
            self.assertNotIn("CMS 素材总数", updated)
            self.assertIn("UTC 08:00:00", updated)

    def test_empty_mvp_renders_placeholder_without_dead_links(self):
        readme_en = render_home(self.config, [], "en", None)
        readme_zh = render_home(self.config, [], "zh-CN", None)
        self.assertIn("gallery-placeholder.svg", readme_en)
        self.assertIn("gallery-placeholder.svg", readme_zh)
        self.assertIn("https://raphael.app/ai-video-generator", readme_en)
        self.assertNotIn("magi-2-prompts", readme_en.split("https://raphael.app/")[1].split("\n")[0])

    def test_published_entry_renders_case_pages_and_dual_prompts(self):
        item = make_sample_prompt()
        schema = read_json("content/schema.json")
        self.assertEqual(schema_errors([item], schema, "prompts", schema), [])
        generated = outputs(self.config, [item])
        en_readme = generated[ROOT / "README.md"]
        self.assertIn("Rainy Cafe Barista Dialogue", en_readme)
        self.assertIn("https://cdn.example.com/magi2/sample.mp4", en_readme)
        self.assertIn("cases/sample-rainy-cafe/README.md", en_readme)
        self.assertIn(ROOT / "cases/sample-rainy-cafe/README.md", generated)
        self.assertIn(ROOT / "cases/sample-rainy-cafe/README.zh-CN.md", generated)

    def test_rejects_public_prompt_without_text_and_featured_without_prompt(self):
        item = make_sample_prompt()
        item["short_prompt"] = ""
        item["structured_prompt"] = None
        errors: list[str] = []
        validate_prompts(self.config, [item], errors, [], release=False)
        self.assertTrue(any("short_prompt or structured_prompt" in e for e in errors))
        self.assertTrue(any("featured cases must include" in e for e in errors))

    def test_rejects_mp4_or_oversized_images_in_repo(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "assets" / "examples" / "demo").mkdir(parents=True)
            (root / "assets" / "examples" / "demo" / "clip.mp4").write_bytes(b"\x00\x00\x00\x18ftypmp42")
            (root / "assets" / "examples" / "demo" / "big.png").write_bytes(b"\x89PNG\r\n\x1a\n" + b"0" * (MAX_LOCAL_IMAGE_BYTES + 10))
            errors: list[str] = []
            with patch("validate.ROOT", root):
                validate_repo_hygiene(errors)
            self.assertTrue(any("clip.mp4" in e for e in errors))
            self.assertTrue(any("exceeds 500 KB" in e for e in errors))

    def test_stale_case_page_cleanup_only_targets_generated_files(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            stale_file = root / "cases" / "old-case" / "README.md"
            stale_file.parent.mkdir(parents=True)
            stale_file.write_text(GENERATED_MARKER + "\n\nOld.\n", encoding="utf-8")
            manual_file = root / "cases" / "manual-case" / "README.md"
            manual_file.parent.mkdir(parents=True)
            manual_file.write_text("# Hand-written note\n", encoding="utf-8")
            with patch("build_readme.ROOT", root):
                self.assertEqual(stale_case_pages({}), [stale_file])


if __name__ == "__main__":
    unittest.main()
