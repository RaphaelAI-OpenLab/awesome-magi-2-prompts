"""Tests for GitHub Pages static audio-video cheat sheet generator."""

import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))

from build_pages import build_dataset, render_html, render_robots, render_sitemap
from common import load_data
from test_collection import make_sample_prompt


class PagesTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.config, cls.prompts = load_data()

    def test_empty_dataset_renders_valid_html_with_plausible_and_seo(self):
        records = build_dataset(self.config, [])
        self.assertEqual(records, [])
        html_doc = render_html(self.config, records)
        self.assertIn('<link rel="canonical" href="https://raphaelai-openlab.github.io/awesome-magi-2-prompts/" />', html_doc)
        self.assertIn("https://plau.colorepistle.com/js/script.outbound-links.js", html_doc)
        self.assertIn('"@type": "TechArticle"', html_doc)
        self.assertIn("No published video cases yet", html_doc)

    def test_published_record_serializes_video_and_structured_prompt(self):
        item = make_sample_prompt()
        records = build_dataset(self.config, [item])
        self.assertEqual(len(records), 1)
        self.assertEqual(records[0]["video_url"], "https://cdn.example.com/magi2/sample.mp4")
        self.assertTrue(records[0]["has_prompt"])
        self.assertIn("Rainy cafe", records[0]["structured_prompt"])

    def test_robots_and_sitemap_reference_canonical_pages_url(self):
        url = "https://raphaelai-openlab.github.io/awesome-magi-2-prompts/"
        self.assertIn(f"Sitemap: {url}sitemap.xml", render_robots(url))
        self.assertIn(f"<loc>{url}</loc>", render_sitemap(url, "2026-11-26"))


if __name__ == "__main__":
    unittest.main()
