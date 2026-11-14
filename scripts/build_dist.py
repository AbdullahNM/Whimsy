#!/usr/bin/env python3
"""Distribution packaging for Whimsy campaigns (itch.io HTML5 & standalone).

Builds a self-contained distribution package for a campaign:
  - Produces dist/<id>/index.html: single self-contained playable HTML file
    with all scripts, CSS, campaign manifest, and runtime inlined (zero external dependencies).
  - Produces dist/<id>/<id>.zip: zip archive containing index.html at root (itch.io HTML5 spec).
  - Produces dist/<id>/itch_metadata.json and dist/<id>/ITCH_LISTING.md via scripts/itch_meta.py.
  - Enforces R9 (Private-campaign safety): build-time assertion verifying exactly
    one campaign id is bundled and no personal or other campaign directories are leaked.

Usage:
  python scripts/build_dist.py --campaign <id> [--out <dir>]
"""

import argparse
import base64
import json
import os
import re
import sys
import zipfile

# Add repo root to path for importing sibling scripts
ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

from scripts.itch_meta import generate_itch_metadata


class CampaignSafetyError(AssertionError):
    """Raised when R9 Private-campaign safety assertions fail."""
    pass


def read_text(path: str) -> str:
    with open(path, "r", encoding="utf-8") as f:
        return f.read()


def read_json_file(path: str) -> dict:
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


def get_base64_data_uri(path: str, mime_type: str = "image/png") -> str:
    if os.path.exists(path):
        with open(path, "rb") as f:
            b64 = base64.b64encode(f.read()).decode("ascii")
            return f"data:{mime_type};base64,{b64}"
    return ""


def build_campaign_configs(campaign_dir: str, campaign_id: str) -> dict:
    config_path = os.path.join(campaign_dir, "campaign_config.json")
    if not os.path.exists(config_path):
        raise FileNotFoundError(f"Missing campaign_config.json in {campaign_dir}")
    config = read_json_file(config_path)
    cid = config.get("id") or campaign_id
    return {cid: config}


def build_gameplay_manifest(campaign_dir: str, campaign_id: str) -> dict:
    config_path = os.path.join(campaign_dir, "campaign_config.json")
    config = read_json_file(config_path) if os.path.exists(config_path) else {}
    cid = config.get("id") or campaign_id

    gameplay_dir = os.path.join(campaign_dir, "GAMEPLAY")
    active_dir = os.path.join(campaign_dir, "TURNS", "ACTIVE")
    active_turns = []
    if os.path.isdir(active_dir):
        for name in sorted(os.listdir(active_dir)):
            if name.endswith(".md"):
                active_turns.append({
                    "name": name,
                    "content": read_text(os.path.join(active_dir, name)),
                })

    status_md = os.path.join(gameplay_dir, "status.md")
    status_json = os.path.join(gameplay_dir, "status.json")
    relations_md = os.path.join(gameplay_dir, "relations.md")
    relations_json = os.path.join(gameplay_dir, "relations.json")
    items_md = os.path.join(gameplay_dir, "items.md")
    items_json = os.path.join(gameplay_dir, "items.json")
    hooks_md = os.path.join(gameplay_dir, "upcoming_hooks.md")
    steering_md = os.path.join(campaign_dir, "IDEAS", "narrative_steering.md")

    entry = {
        "status": read_text(status_md) if os.path.exists(status_md) else "",
        "relations": read_text(relations_md) if os.path.exists(relations_md) else "",
        "items": read_text(items_md) if os.path.exists(items_md) else "",
        "upcoming_hooks": read_text(hooks_md) if os.path.exists(hooks_md) else "",
        "status_json": read_json_file(status_json) if os.path.exists(status_json) else {},
        "relations_json": read_json_file(relations_json) if os.path.exists(relations_json) else {},
        "items_json": read_json_file(items_json) if os.path.exists(items_json) else {},
        "active_turns": active_turns,
        "narrative_steering": read_text(steering_md) if os.path.exists(steering_md) else "",
    }
    return {cid: entry}


def build_world_bible_data(campaign_dir: str) -> dict:
    bible_dir = os.path.join(campaign_dir, "WORLD_BIBLE")
    data = {}
    if not os.path.isdir(bible_dir):
        return data

    for cat in sorted(os.listdir(bible_dir)):
        cat_dir = os.path.join(bible_dir, cat)
        if not os.path.isdir(cat_dir):
            continue
        articles = []
        for name in sorted(os.listdir(cat_dir)):
            if not name.endswith(".md"):
                continue
            content = read_text(os.path.join(cat_dir, name))
            m = re.search(r"^#\s+(.+)$", content, re.MULTILINE)
            title = m.group(1).strip() if m else os.path.splitext(name)[0].replace("_", " ").title()
            articles.append({
                "id": os.path.splitext(name)[0],
                "title": title,
                "content": content,
            })
        if articles:
            data[cat] = articles
    return data


def verify_single_campaign_safety(
    campaign_id,
    campaign_configs: dict,
    gameplay_manifest: dict,
    world_bible_data: dict = None,
    html_content: str = None,
    repo_root: str = None,
    campaign_dir: str = None,
) -> None:
    """Enforce R9 (Private-campaign safety).

    Build-time assertion verifying:
      1. Exactly one campaign id is bundled (no multiple campaign IDs).
      2. No directory traversal or unauthorized campaign paths.
      3. No personal or other campaign directories are leaked.
      4. Bundled configs and manifest strictly contain only this single campaign ID.
    """
    root = os.path.abspath(repo_root or ROOT)
    campaigns_root = os.path.join(root, "CAMPAIGNS")

    # 1. Verify campaign_id type and structure
    if not isinstance(campaign_id, str):
        raise CampaignSafetyError(f"R9 Violation: campaign_id must be a single string, got {type(campaign_id).__name__}")

    if not campaign_id.strip():
        raise CampaignSafetyError("R9 Violation: campaign_id cannot be empty.")

    # Rejection of multiple campaigns passed via comma/semicolon/whitespace
    if any(delim in campaign_id for delim in [",", ";", "|", " "]):
        raise CampaignSafetyError(f"R9 Violation: Multiple campaign IDs detected in '{campaign_id}'. Only 1 campaign is allowed per build.")

    # Rejection of path traversal / unauthorized paths
    if ".." in campaign_id or "/" in campaign_id or "\\" in campaign_id:
        raise CampaignSafetyError(f"R9 Violation: Unauthorized path or directory traversal detected in '{campaign_id}'.")

    # 2. Verify campaign directory authorization
    camp_dir = os.path.abspath(campaign_dir or os.path.join(campaigns_root, campaign_id))
    try:
        common = os.path.commonpath([camp_dir, campaigns_root])
    except ValueError:
        raise CampaignSafetyError(f"R9 Violation: Campaign path '{camp_dir}' is outside authorized campaigns root.")

    if os.path.abspath(common) != os.path.abspath(campaigns_root):
        raise CampaignSafetyError(f"R9 Violation: Campaign path '{camp_dir}' escapes authorized directory '{campaigns_root}'.")

    if not os.path.isdir(camp_dir):
        raise CampaignSafetyError(f"R9 Violation: Campaign directory does not exist or is unauthorized: '{camp_dir}'")

    # 3. Assert exactly one campaign in configs
    if not isinstance(campaign_configs, dict):
        raise CampaignSafetyError(f"R9 Violation: campaign_configs must be a dict, got {type(campaign_configs).__name__}")

    if len(campaign_configs) != 1:
        raise CampaignSafetyError(
            f"R9 Violation: Exactly 1 campaign config must be bundled; found {len(campaign_configs)} ({list(campaign_configs.keys())})"
        )

    bundled_id = list(campaign_configs.keys())[0]
    if bundled_id != campaign_id:
        raise CampaignSafetyError(
            f"R9 Violation: Bundled campaign config ID '{bundled_id}' does not match target campaign ID '{campaign_id}'"
        )

    # 4. Assert exactly one campaign in gameplay manifest
    if not isinstance(gameplay_manifest, dict):
        raise CampaignSafetyError(f"R9 Violation: gameplay_manifest must be a dict, got {type(gameplay_manifest).__name__}")

    if len(gameplay_manifest) != 1:
        raise CampaignSafetyError(
            f"R9 Violation: Exactly 1 campaign manifest must be bundled; found {len(gameplay_manifest)} ({list(gameplay_manifest.keys())})"
        )

    manifest_id = list(gameplay_manifest.keys())[0]
    if manifest_id != campaign_id:
        raise CampaignSafetyError(
            f"R9 Violation: Bundled gameplay manifest ID '{manifest_id}' does not match target campaign ID '{campaign_id}'"
        )

    # 5. Check for leaks of other/private campaign directories from CAMPAIGNS/
    if os.path.isdir(campaigns_root):
        all_campaign_dirs = [
            d for d in os.listdir(campaigns_root)
            if os.path.isdir(os.path.join(campaigns_root, d)) and d != campaign_id
        ]
        for other_dir in all_campaign_dirs:
            if other_dir in campaign_configs:
                raise CampaignSafetyError(f"R9 Violation: Leaked other campaign config for '{other_dir}' into bundle.")
            if other_dir in gameplay_manifest:
                raise CampaignSafetyError(f"R9 Violation: Leaked other campaign manifest for '{other_dir}' into bundle.")

    # 6. Check for leaked local/personal paths in bundled HTML
    if html_content:
        leak_patterns = [
            r"c:[\\/]+users[\\/]+",
            r"[\\/]users[\\/]+[a-z0-9_\.\-]+",
            r"[\\/]home[\\/]+[a-z0-9_\.\-]+",
            r"\.worktrees",
            r"\.git[\\/]",
            r"\.agent[\\/]",
        ]
        for pat in leak_patterns:
            if re.search(pat, html_content, re.IGNORECASE):
                raise CampaignSafetyError(f"R9 Violation: Potential local workspace or personal path leak detected matching '{pat}'.")


def build_self_contained_html(
    campaign_id: str,
    repo_root: str = None
) -> tuple[str, dict, dict, dict]:
    """Assemble single self-contained playable HTML string for the given campaign.

    Returns:
        tuple of (html_string, campaign_configs, gameplay_manifest, world_bible_data)
    """
    root = os.path.abspath(repo_root or ROOT)
    ui_dir = os.path.join(root, "UI")
    camp_dir = os.path.join(root, "CAMPAIGNS", campaign_id)

    # 1. Read UI template and styles
    index_html = read_text(os.path.join(ui_dir, "index.html"))
    styles_css = read_text(os.path.join(ui_dir, "styles.css"))

    # 2. Build campaign data
    campaign_configs = build_campaign_configs(camp_dir, campaign_id)
    gameplay_manifest = build_gameplay_manifest(camp_dir, campaign_id)
    world_bible_data = build_world_bible_data(camp_dir)

    # 3. Read runtime scripts
    core_js = read_text(os.path.join(ui_dir, "core", "deterministic_core.js"))
    storage_js = read_text(os.path.join(ui_dir, "storage", "indexeddb.js"))
    authored_js = read_text(os.path.join(ui_dir, "narrator", "authored_narrator.js"))
    local_js = read_text(os.path.join(ui_dir, "narrator", "local_narrator.js"))
    cloud_js = read_text(os.path.join(ui_dir, "narrator", "cloud_narrator.js"))
    tiered_js = read_text(os.path.join(ui_dir, "narrator", "tiered_narrator.js"))
    app_js = read_text(os.path.join(ui_dir, "app.js"))

    # 4. Inlined assets (icons and manifest)
    icon_uri = get_base64_data_uri(os.path.join(ui_dir, "icon.png"), "image/png")
    icon512_uri = get_base64_data_uri(os.path.join(ui_dir, "icon-512.png"), "image/png")

    manifest_json_raw = read_text(os.path.join(ui_dir, "manifest.json"))
    manifest_uri = f"data:application/manifest+json;base64,{base64.b64encode(manifest_json_raw.encode('utf-8')).decode('ascii')}"

    # Replace <link rel="stylesheet">
    html = re.sub(
        r'<link\s+rel="stylesheet"\s+href="styles\.css"\s*\/?>',
        lambda m: f"<style>\n/* Whimsy Styles */\n{styles_css}\n</style>",
        index_html,
        flags=re.IGNORECASE
    )

    # Replace icon links
    if icon_uri:
        html = re.sub(
            r'<link\s+rel="icon"[^>]*href="icon\.png"[^>]*>',
            f'<link rel="icon" type="image/png" href="{icon_uri}">',
            html,
            flags=re.IGNORECASE
        )
    if icon512_uri:
        html = re.sub(
            r'<link\s+rel="apple-touch-icon"[^>]*href="icon-512\.png"[^>]*>',
            f'<link rel="apple-touch-icon" href="{icon512_uri}">',
            html,
            flags=re.IGNORECASE
        )
    if manifest_uri:
        html = re.sub(
            r'<link\s+rel="manifest"[^>]*href="manifest\.json"[^>]*>',
            f'<link rel="manifest" href="{manifest_uri}">',
            html,
            flags=re.IGNORECASE
        )

    # Sanitize JSON payloads for safe inlining inside <script>
    def safe_json_embed(data):
        raw = json.dumps(data, ensure_ascii=False)
        return raw.replace("</script>", "<\\/script>").replace("<!--", "<\\!--")

    # Inlined data script
    data_script = f"""<script>
  /* Inlined Campaign Data for Whimsy CYOA Engine (Single-File Distribution) */
  window.__INLINED_BUILD__ = true;
  window.__BUNDLED_CAMPAIGN_ID__ = {json.dumps(campaign_id)};
  window.__CAMPAIGN_CONFIGS__ = {safe_json_embed(campaign_configs)};
  window.__GAMEPLAY_MANIFEST__ = {safe_json_embed(gameplay_manifest)};
  window.__WORLD_BIBLE_DATA__ = {safe_json_embed(world_bible_data)};
</script>"""

    # Inlined scripts bundle
    inlined_scripts = f"""{data_script}
<script>
/* Inlined: core/deterministic_core.js */
{core_js}
</script>
<script>
/* Inlined: storage/indexeddb.js */
{storage_js}
</script>
<script>
/* Inlined: narrator/authored_narrator.js */
{authored_js}
</script>
<script>
/* Inlined: narrator/local_narrator.js */
{local_js}
</script>
<script>
/* Inlined: narrator/cloud_narrator.js */
{cloud_js}
</script>
<script>
/* Inlined: narrator/tiered_narrator.js */
{tiered_js}
</script>
<script>
/* Inlined: app.js */
{app_js}
</script>"""

    # Replace external <script src="..."> tags with the inlined scripts bundle
    script_regex = re.compile(
        r'<script\s+src="core/deterministic_core\.js"><\/script>\s*'
        r'<script\s+src="storage/indexeddb\.js"><\/script>\s*'
        r'<script\s+src="narrator/authored_narrator\.js"><\/script>\s*'
        r'<script\s+src="narrator/local_narrator\.js"><\/script>\s*'
        r'<script\s+src="narrator/cloud_narrator\.js"><\/script>\s*'
        r'<script\s+src="narrator/tiered_narrator\.js"><\/script>\s*'
        r'<script\s+src="app\.js"><\/script>',
        re.MULTILINE
    )

    if script_regex.search(html):
        html = script_regex.sub(lambda m: inlined_scripts, html, count=1)
    else:
        # Fallback replacement if formatting varies
        for script_name in [
            "core/deterministic_core.js",
            "storage/indexeddb.js",
            "narrator/authored_narrator.js",
            "narrator/local_narrator.js",
            "narrator/cloud_narrator.js",
            "narrator/tiered_narrator.js",
            "app.js"
        ]:
            html = re.sub(rf'<script\s+src="{re.escape(script_name)}"><\/script>', "", html)
        html = html.replace("</body>", f"{inlined_scripts}\n</body>")

    # Update page title with campaign title
    camp_title = campaign_configs[campaign_id].get("title", campaign_id)
    html = re.sub(
        r"<title>.*?</title>",
        f"<title>{camp_title} — Whimsy CYOA Engine</title>",
        html,
        flags=re.IGNORECASE
    )

    return html, campaign_configs, gameplay_manifest, world_bible_data


def build_dist(
    campaign_id: str,
    out_dir: str = None,
    root_dir: str = None,
    generate_meta: bool = True
) -> dict:
    """Build the complete distribution package for a campaign.

    Produces:
      - dist/<id>/index.html
      - dist/<id>/<id>.html
      - dist/<id>/<id>.zip (containing index.html at root)
      - dist/<id>/itch_metadata.json
      - dist/<id>/ITCH_LISTING.md

    Returns:
        dict with paths of generated artefacts.
    """
    root = os.path.abspath(root_dir or ROOT)
    camp_dir = os.path.join(root, "CAMPAIGNS", campaign_id if isinstance(campaign_id, str) else "")

    # Preliminary safety check before assembly
    if not isinstance(campaign_id, str) or any(d in campaign_id for d in [",", ";", "|", " "]):
        raise CampaignSafetyError(f"R9 Violation: Invalid campaign identifier: '{campaign_id}'")

    if ".." in campaign_id or "/" in campaign_id or "\\" in campaign_id:
        raise CampaignSafetyError(f"R9 Violation: Unauthorized path or directory traversal: '{campaign_id}'")

    if not os.path.isdir(camp_dir):
        raise CampaignSafetyError(f"R9 Violation: Campaign directory does not exist or is unauthorized: '{camp_dir}'")

    # Target output directory
    target_dir = os.path.abspath(out_dir or os.path.join(root, "dist", campaign_id))
    os.makedirs(target_dir, exist_ok=True)

    # 1. Assemble single-file playable HTML
    html_content, configs, manifest, bible = build_self_contained_html(campaign_id, root)

    # 2. Strict R9 Safety Assertion Verification
    verify_single_campaign_safety(
        campaign_id=campaign_id,
        campaign_configs=configs,
        gameplay_manifest=manifest,
        world_bible_data=bible,
        html_content=html_content,
        repo_root=root,
        campaign_dir=camp_dir,
    )

    # 3. Write Artefact A: Single self-contained playable .html file
    index_html_path = os.path.join(target_dir, "index.html")
    with open(index_html_path, "w", encoding="utf-8") as f:
        f.write(html_content)

    named_html_path = os.path.join(target_dir, f"{campaign_id}.html")
    with open(named_html_path, "w", encoding="utf-8") as f:
        f.write(html_content)

    # 4. Write Artefact B: Zip archive containing index.html at root (itch.io spec)
    zip_path = os.path.join(target_dir, f"{campaign_id}.zip")
    with zipfile.ZipFile(zip_path, "w", compression=zipfile.ZIP_DEFLATED) as zf:
        # Must place index.html at root of zip archive
        zf.writestr("index.html", html_content.encode("utf-8"))

        # Include app icon and web manifest for itch embed completeness
        ui_dir = os.path.join(root, "UI")
        for asset in ["icon.png", "icon-512.png", "manifest.json"]:
            asset_path = os.path.join(ui_dir, asset)
            if os.path.exists(asset_path):
                zf.write(asset_path, arcname=asset)

    artefacts = {
        "index_html": index_html_path,
        "named_html": named_html_path,
        "zip": zip_path,
        "out_dir": target_dir,
    }

    # 5. Generate itch.io metadata and listing markdown
    if generate_meta:
        metadata, listing = generate_itch_metadata(campaign_id, out_dir=target_dir, root_dir=root)
        artefacts["itch_metadata"] = os.path.join(target_dir, "itch_metadata.json")
        artefacts["itch_listing"] = os.path.join(target_dir, "ITCH_LISTING.md")

    return artefacts


def main():
    parser = argparse.ArgumentParser(description="Build itch.io and single-file distribution package for a Whimsy campaign.")
    parser.add_argument("--campaign", required=True, help="Campaign ID to package (e.g. template_campaign)")
    parser.add_argument("--out", default=None, help="Target output directory (defaults to dist/<campaign_id>)")
    parser.add_argument("--no-meta", action="store_true", help="Skip generating itch_metadata.json and ITCH_LISTING.md")
    args = parser.parse_args()

    try:
        results = build_dist(
            campaign_id=args.campaign,
            out_dir=args.out,
            generate_meta=not args.no_meta
        )
        print(f"Distribution build succeeded for campaign '{args.campaign}':")
        print(f"  - Playable Single HTML: {results['index_html']}")
        print(f"  - itch.io Zip Archive:   {results['zip']}")
        if "itch_metadata" in results:
            print(f"  - itch Metadata:         {results['itch_metadata']}")
            print(f"  - itch Listing:          {results['itch_listing']}")
    except CampaignSafetyError as cse:
        print(f"Build failed: Safety Assertion Violation (R9): {cse}", file=sys.stderr)
        sys.exit(1)
    except Exception as e:
        print(f"Build error: {e}", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
