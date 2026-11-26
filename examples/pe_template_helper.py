#!/usr/bin/env python3
"""Helper CLI to scaffold MAGI-2 PE JSON templates and export samples.json."""

from __future__ import annotations

import argparse
import copy
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def load_pe_template(mode: str) -> dict:
    """Load the T2V or I2V structured Prompt Enhancement template."""
    if mode not in {"t2v", "i2v"}:
        raise ValueError(f"Unsupported mode {mode!r}; expected 't2v' or 'i2v'.")
    path = ROOT / "examples" / f"{mode}_pe_template.json"
    return json.loads(path.read_text(encoding="utf-8"))


def scaffold_pe(mode: str, prompt_text: str = "", aspect_ratio: str = "16:9", duration: float = 10.0) -> dict:
    """Create a populated T2V or I2V PE JSON object from the repository template."""
    data = copy.deepcopy(load_pe_template(mode))
    if mode == "t2v":
        data["global_layer"]["description"] = prompt_text
        data["global_layer"]["video_metadata"]["aspect_ratio"] = aspect_ratio
        data["global_layer"]["video_metadata"]["duration"] = float(duration)
        if data["dynamic_layer"]["timeline_segments"]:
            data["dynamic_layer"]["timeline_segments"][0]["segment_basic_info"]["segment_description"] = prompt_text
    else:
        data["global_caption"]["core_caption"] = prompt_text
        if data["shot_timeline"]:
            data["shot_timeline"][0]["shot_caption"] = prompt_text
            data["shot_timeline"][0]["time_range_seconds"] = [0.0, float(duration)]
    return data


def export_samples(prompts: list[dict], *, prefer_structured: bool = True) -> list[dict]:
    """Convert published prompt records into SandAI-org/MAGI-2-preview samples.json entries."""
    samples: list[dict] = []
    for item in prompts:
        if item.get("status") != "published" or item.get("prompt_status") != "public":
            continue
        structured = item.get("structured_prompt")
        short_prompt = str(item.get("short_prompt") or "").strip()
        if prefer_structured and structured:
            prompt_value = json.dumps(structured, ensure_ascii=False) if isinstance(structured, (dict, list)) else str(structured).strip()
        else:
            prompt_value = short_prompt
        if not prompt_value:
            continue
        entry: dict[str, str] = {"prompt": prompt_value}
        for ref in item.get("omni_references", []):
            if ref.get("kind") == "image" and ref.get("path"):
                entry["image"] = ref["path"]
                break
        samples.append(entry)
    return samples


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    subparsers = parser.add_subparsers(dest="command", required=True)

    scaffold_cmd = subparsers.add_parser("scaffold", help="Generate a T2V or I2V PE JSON skeleton.")
    scaffold_cmd.add_argument("--mode", choices=("t2v", "i2v"), default="t2v")
    scaffold_cmd.add_argument("--prompt", default="", help="Seed description text.")
    scaffold_cmd.add_argument("--aspect-ratio", default="16:9")
    scaffold_cmd.add_argument("--duration", type=float, default=10.0)
    scaffold_cmd.add_argument("--out", help="Output JSON file path; prints to stdout if omitted.")

    export_cmd = subparsers.add_parser("export", help="Export published prompts to MAGI-2-preview samples.json.")
    export_cmd.add_argument("--input", default=str(ROOT / "content" / "prompts.json"))
    export_cmd.add_argument("--out", help="Output samples.json path; prints to stdout if omitted.")
    export_cmd.add_argument("--short-only", action="store_true", help="Prefer short_prompt over structured_prompt.")

    args = parser.parse_args()
    if args.command == "scaffold":
        payload = json.dumps(
            scaffold_pe(args.mode, args.prompt, args.aspect_ratio, args.duration),
            indent=2,
            ensure_ascii=False,
        )
    else:
        prompts = json.loads(Path(args.input).read_text(encoding="utf-8"))
        payload = json.dumps(export_samples(prompts, prefer_structured=not args.short_only), indent=2, ensure_ascii=False)

    if args.out:
        out_path = Path(args.out)
        out_path.parent.mkdir(parents=True, exist_ok=True)
        out_path.write_text(payload + "\n", encoding="utf-8")
        print(f"Wrote {out_path}")
    else:
        print(payload)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
