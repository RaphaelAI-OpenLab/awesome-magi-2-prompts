"""Tests for MAGI-2 PE scaffolding and samples.json export helper."""

import json
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "examples"))
sys.path.insert(0, str(Path(__file__).resolve().parent))

from pe_template_helper import export_samples, scaffold_pe
from test_collection import make_sample_prompt


class PeHelperTests(unittest.TestCase):
    def test_scaffold_t2v_and_i2v_preserve_required_top_level_keys(self):
        t2v = scaffold_pe("t2v", "Red fox in snow", aspect_ratio="9:16", duration=10.0)
        self.assertEqual(set(t2v.keys()), {"global_layer", "dynamic_layer"})
        self.assertEqual(t2v["global_layer"]["video_metadata"]["aspect_ratio"], "9:16")
        self.assertEqual(t2v["global_layer"]["description"], "Red fox in snow")

        i2v = scaffold_pe("i2v", "Camera pushes slowly toward the window")
        self.assertEqual(
            set(i2v.keys()),
            {"global_caption", "reference_bank", "shot_timeline", "audio_event_timeline", "visible_text", "generation_requirements"},
        )
        self.assertEqual(i2v["global_caption"]["core_caption"], "Camera pushes slowly toward the window")

    def test_export_samples_handles_empty_and_published_items(self):
        self.assertEqual(export_samples([]), [])

        item = make_sample_prompt()
        item["omni_references"] = [
            {"kind": "image", "path": "assets/references/sample-rainy-cafe/frame.png", "url": None, "description": {"en": "First frame", "zh-CN": "首帧"}}
        ]
        exported = export_samples([item])
        self.assertEqual(len(exported), 1)
        self.assertEqual(exported[0]["image"], "assets/references/sample-rainy-cafe/frame.png")
        self.assertEqual(json.loads(exported[0]["prompt"]), {"global_layer": {"context": "Rainy cafe"}})

        short_exported = export_samples([item], prefer_structured=False)
        self.assertEqual(short_exported[0]["prompt"], item["short_prompt"])


if __name__ == "__main__":
    unittest.main()
