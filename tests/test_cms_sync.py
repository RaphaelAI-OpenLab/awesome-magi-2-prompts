"""Tests for MAGI-2 Directus CMS pull, curated preservation, and huge-prompt protection."""

from datetime import datetime, timezone
import json
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))

from build_readme import render_case_card
from common import load_data, read_json
from sync_cms_materials import CMS_SYNC_STATE_PATH, is_approved_media_url, sync_to_disk


class Magi2CmsSyncTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.config, cls.prompts = load_data()
        cls.template = read_json("templates/prompt.json")

    def test_r2_allowlist_checks_prefix(self):
        self.assertTrue(is_approved_media_url("https://awesome.raphael.app/materials/demo.mp4", self.config))
        self.assertFalse(is_approved_media_url("https://video.twimg.com/demo.mp4", self.config))

    def test_sync_preserves_curated_adds_new_and_avoids_churn(self):
        curated = self.prompts[0]
        raw_rows = [
            {
                "id": "0ef6d2e1-fc30-456b-bd10-62de0709a0b8",
                "title": "Should Not Overwrite Curated Title",
                "prompt": "Should not overwrite curated prompt",
                "status": "ready",
                "author_x_url": curated["source"]["author_url"],
                "source_post_url": curated["source"]["url"],
                "source_published_at": "2026-11-25T00:00:00Z",
                "tags": None,
                "notes": "",
                "date_created": "2026-11-26T07:29:23Z",
                "image_url": curated["video_url"],
                "r2_object_key": "materials/existing.mp4",
            },
            {
                "id": "fb4c34de-1b17-45d7-ba1b-1045b5b66553",
                "title": "Rainy Rooftop Wuxia Short",
                "prompt": "1970s Hong Kong wuxia cinema rooftop duel in heavy studio rain with synced steel clashes.",
                "status": "ready",
                "author_x_url": "https://x.com/abulu8",
                "source_post_url": "https://x.com/abulu8/status/2125950604694667400",
                "source_published_at": "2026-11-26T13:51:37Z",
                "tags": ["wuxia"],
                "notes": "Creator reported MAGI-2.",
                "date_created": "2026-11-27T08:08:34Z",
                "image_url": "https://awesome.raphael.app/materials/9c81bb45-bca0-4b76-aabb-3812af843d74.mp4",
                "r2_object_key": "materials/9c81bb45-bca0-4b76-aabb-3812af843d74.mp4",
            },
        ]
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "content").mkdir()
            (root / "templates").mkdir()
            (root / "site.config.json").write_text(json.dumps(self.config), encoding="utf-8")
            (root / "templates" / "prompt.json").write_text(json.dumps(self.template), encoding="utf-8")
            (root / "content" / "prompts.json").write_text(json.dumps([curated]), encoding="utf-8")
            with (
                patch("sync_cms_materials.ROOT", root),
                patch("common.ROOT", root),
                patch("sync_cms_materials.fetch_all_materials", return_value=raw_rows),
            ):
                changed1, added1, total1 = sync_to_disk(
                    "https://raphael-cms.colorepistle.com",
                    "token-123",
                    extract_media=False,
                    now=datetime(2026, 11, 27, 8, 30, tzinfo=timezone.utc),
                )
                self.assertTrue(changed1)
                self.assertEqual((added1, total1), (1, 2))
                updated = json.loads((root / "content" / "prompts.json").read_text(encoding="utf-8"))
                self.assertEqual(len(updated), 2)
                self.assertEqual(updated[0]["title"], curated["title"])
                self.assertEqual(updated[1]["id"], "cms-fb4c34de")
                self.assertEqual(updated[1]["rights"]["preview"], "link-only")

                changed2, added2, _ = sync_to_disk(
                    "https://raphael-cms.colorepistle.com",
                    "token-123",
                    extract_media=False,
                    now=datetime(2026, 11, 27, 12, 30, tzinfo=timezone.utc),
                )
                self.assertFalse(changed2)
                self.assertEqual(added2, 0)
                state = json.loads((root / CMS_SYNC_STATE_PATH).read_text(encoding="utf-8"))
                self.assertEqual(state["synced_at"], "2026-11-27T08:30:00Z")

    def test_huge_structured_prompt_truncates_in_root_but_stays_full_on_case_page(self):
        item = json.loads(json.dumps(self.prompts[0]))
        item["structured_prompt"] = "SHOT " * 2000
        root_card = render_case_card(item, self.config, "en", standalone=False)
        case_card = render_case_card(item, self.config, "en", standalone=True)
        self.assertIn("truncated in root README", root_card)
        self.assertIn("cases/" + item["id"] + "/README.md", root_card)
        self.assertNotIn("truncated in root README", case_card)
        self.assertIn(item["structured_prompt"].strip(), case_card)


if __name__ == "__main__":
    unittest.main()
