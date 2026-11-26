# Prompt Entry Checklist / 案例录入模板

Use `templates/prompt.json` as the canonical structure when adding a record to `content/prompts.json`.

## Required rules for `published` entries

1. **Identity & classification**
   - `id`: unique lowercase slug (e.g. `cafe-rain-barista-dialogue`).
   - `category`: one of the IDs defined in `site.config.json`.
   - `origin`: `original` (curated/tested by us), `official` (Sand.ai demo/repo), or `community` (creator post).
2. **Dual-track prompt (`short_prompt` + `structured_prompt`)**
   - `prompt_status`: `public` (exact prompt available), `not-public` (source withheld prompt), or `unverified`.
   - When `prompt_status` is `public`, `short_prompt` and/or `structured_prompt` must be non-empty. Never invent prompts when `prompt_status != "public"`.
3. **Media separation (no `.mp4` in Git)**
   - Store the playable 1080p MP4 URL (e.g. Cloudflare R2 or official demo MP4) in `video_url`.
   - Store an optional lightweight still cover image (`<= 500 KB`, `.webp` / `.jpg` / `.png`) at `assets/examples/<id>/preview.webp`.
4. **Omni-Reference inputs (`omni_references`)**
   - Record each reference `image`, `video`, or `audio` item cleanly; local thumbnails under `assets/references/<id>/` must also stay `<= 500 KB`.
5. **Featured eligibility**
   - Any entry listed in `site.config.json` `presentation.featured_case_ids` or marked `"featured": true` MUST have `prompt_status == "public"` and copyable prompt text.
