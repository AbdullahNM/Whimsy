#!/usr/bin/env python3
"""itch.io project metadata generator for Whimsy campaigns.

Generates:
  - dist/<campaign_id>/itch_metadata.json (machine-readable metadata)
  - dist/<campaign_id>/ITCH_LISTING.md (ready-to-paste itch.io project dashboard listing)

Usage:
  python scripts/itch_meta.py --campaign <id> [--out <dir>]
"""

import argparse
import json
import os
import re
import sys

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
CAMPAIGNS_DIR = os.path.join(ROOT, "CAMPAIGNS")


def read_file(path: str) -> str:
    if os.path.exists(path):
        with open(path, "r", encoding="utf-8") as f:
            return f.read()
    return ""


def read_json(path: str) -> dict:
    if os.path.exists(path):
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    return {}


def slugify_tag(text: str) -> str:
    """Normalize text into an itch.io compatible tag."""
    tag = text.strip().lower()
    tag = re.sub(r"[^a-z0-9\-]+", "-", tag)
    tag = re.sub(r"-+", "-", tag).strip("-")
    return tag


def derive_genre_tags(genre: str) -> list[str]:
    """Derive relevant itch.io tags from campaign genre string."""
    genre_lower = genre.lower()
    tags = []

    genre_map = [
        ("sci-fi", ["sci-fi", "science-fiction"]),
        ("cyberpunk", ["cyberpunk", "sci-fi"]),
        ("fantasy", ["fantasy", "magic"]),
        ("mystery", ["mystery", "investigation"]),
        ("horror", ["horror", "psychological-horror"]),
        ("post-apocalyptic", ["post-apocalyptic", "survival"]),
        ("space", ["space", "sci-fi"]),
        ("steampunk", ["steampunk", "alternate-history"]),
        ("rpg", ["rpg", "role-playing"]),
        ("adventure", ["adventure"]),
        ("cyoa", ["cyoa", "choose-your-own-adventure"]),
    ]

    for key, mapped in genre_map:
        if key in genre_lower:
            for t in mapped:
                if t not in tags:
                    tags.append(t)

    # General fallback tags for consequence-driven CYOA
    default_tags = ["adventure", "choice-matter", "simulation"]
    for t in default_tags:
        if t not in tags:
            tags.append(t)

    return tags


def generate_itch_metadata(
    campaign_id: str,
    out_dir: str = None,
    root_dir: str = None
) -> tuple[dict, str]:
    """Generate itch.io metadata json and markdown listing for a campaign.

    Args:
        campaign_id: ID of the campaign in CAMPAIGNS/<id>.
        out_dir: Target output directory (defaults to dist/<campaign_id>).
        root_dir: Whimsy repository root.

    Returns:
        tuple of (metadata_dict, markdown_content).
    """
    repo_root = os.path.abspath(root_dir or ROOT)
    camp_dir = os.path.join(repo_root, "CAMPAIGNS", campaign_id)

    if not os.path.isdir(camp_dir):
        raise FileNotFoundError(f"Campaign directory not found: {camp_dir}")

    config_path = os.path.join(camp_dir, "campaign_config.json")
    config = read_json(config_path)

    foundation_path = os.path.join(camp_dir, "WORLD_FOUNDATION", "world_foundation.json")
    foundation = read_json(foundation_path)

    primer_path = os.path.join(camp_dir, "WORLD_BIBLE", "CORE", "setting_primer.md")
    primer = read_file(primer_path)

    status_path = os.path.join(camp_dir, "GAMEPLAY", "status.json")
    status = read_json(status_path)

    # Extract metadata fields
    title = config.get("title") or foundation.get("world_name") or campaign_id.replace("_", " ").title()
    genre = config.get("genre", "Custom CYOA Universe")

    tagline = (
        config.get("tagline")
        or config.get("short_tagline")
        or f"A consequence-driven {genre} interactive fiction."
    )
    if len(tagline) > 100:
        tagline = tagline[:97] + "..."

    # Build description
    overview = (
        config.get("description")
        or foundation.get("overview")
        or (primer.split("\n\n")[1] if "\n\n" in primer else primer)
        or f"An immersive consequence-driven interactive CYOA campaign set in {title}."
    )

    character_name = status.get("character", {}).get("name", "The Protagonist")
    character_archetype = status.get("character", {}).get("archetype", "Operative")

    long_description = (
        f"{overview.strip()}\n\n"
        f"Step into the boots of **{character_name}**, {character_archetype}. "
        "Every choice you make irreversibly shapes the narrative through explicit mathematical "
        "receipts, relationship standing, and branching world states. "
        "Powered by Whimsy's browser runtime with instant offline responsiveness, deterministic turn "
        "resolution, and persistent IndexedDB save states."
    )

    # Tags: required base tags + genre tags + custom config tags
    base_tags = ["interactive-fiction", "text-based", "cyoa"]
    derived_tags = derive_genre_tags(genre)
    config_tags = [slugify_tag(t) for t in config.get("tags", []) if t]

    seen = set()
    tags = []
    for t in base_tags + derived_tags + config_tags:
        cleaned = slugify_tag(t)
        if cleaned and cleaned not in seen:
            seen.add(cleaned)
            tags.append(cleaned)

    # Embed specs
    embed_settings = {
        "width": 1024,
        "height": 768,
        "responsive": True,
        "mobile_friendly": True,
        "fullscreen_button": True,
        "orientation": "any"
    }

    # Pricing recommendations
    pricing = {
        "type": "pwyw",
        "min_price": 0.0,
        "suggested_price": 2.99,
        "currency": "USD",
        "notes": "Free-to-play browser first with Pay-What-You-Want donation enabled."
    }

    metadata = {
        "campaign_id": campaign_id,
        "title": title,
        "tagline": tagline,
        "description": long_description,
        "genre": genre,
        "tags": tags,
        "embed": embed_settings,
        "mobile_friendly": True,
        "classification": "game",
        "kind_of_project": "html",
        "pricing": pricing
    }

    # Markdown Listing
    tags_string = ", ".join(tags)
    markdown_listing = f"""# itch.io Project Listing: {title}

> **Whimsy Distribution Metadata**  
> Generated for campaign `{campaign_id}`. Use the values below to fill out the itch.io project dashboard (`https://itch.io/game/new` or `https://itch.io/game/edit/<id>`).

---

## 1. Project Dashboard Form Fields

| itch.io Dashboard Field | Value | Notes |
|:------------------------|:------|:------|
| **Title** | `{title}` | Matches campaign title |
| **Short description or tagline** | `{tagline}` | Under 100 characters |
| **Classification** | **Games** | Must be Games |
| **Kind of project** | **HTML** | *You have a ZIP or HTML file that will be played in the browser* |
| **Release status** | **Released** | Ready to play |
| **Pricing** | **$0 or donate (Pay what you want)** | Suggested: `$2.99`. Browser IF audience rewards free-to-play with optional donations. |
| **Viewport Dimensions** | `1024` × `768` | Check **Responsive** and **Fullscreen button** |
| **Mobile Friendly** | **Enabled** (checked) | Fully verified with 44px touch targets and responsive UI |
| **Automatically start** | **Enabled** (checked) | Loads immediately on page view |

---

## 2. Tags to Add

```
{tags_string}
```

*Required baseline tags:* `interactive-fiction`, `text-based`, `cyoa`  
*Genre & theme tags:* {', '.join(derived_tags)}

---

## 3. Store Page Description (Copy & Paste to itch.io Description)

```markdown
# {title}

**{tagline}**

---

### Premise
{overview.strip()}

You play as **{character_name}**, {character_archetype}. Every contract accepted, every alley explored, and every alliance forged carries tangible consequences recorded in your status docket.

### Key Features
- **Consequence-Driven CYOA**: No superficial choice illusions. Every decision writes to your character record with arithmetic receipts, shifting faction standings, and lasting narrative repercussions.
- **100% Offline & Instant**: Zero loading lag, zero server waiting, zero external dependencies. Powered by Whimsy's local deterministic execution engine.
- **Persistent In-Browser Saves**: Your choices and history persist automatically in IndexedDB across visits and browser restarts, with one-click JSON save export/import.
- **Mobile-Optimized Interface**: Engineered with high-contrast accessibility, thumb-friendly 44px minimum touch targets, and dynamic responsive layouts for phone and desktop.
- **Multi-Tier Narration Engine**: Ships standard with instant Authored narration (100% free & keyless). Players can optionally plug in their own local LLM (Ollama/vLLM) or Cloud API keys (Gemini / OpenRouter) for expansive prose.

### How to Play
1. Click **Play Game** above to launch directly in your browser.
2. Read the situation and select from the numbered tactical choices, or type a custom action into the prompt.
3. Review your dossier tabs on the left (Status, Relations, Inventory, World Lore) to plan your strategy.
```

---

## 4. Community Showcase Entry
- **Interactive Fiction Showcase**: This title is eligible for the itch.io year-long Interactive Fiction Showcase.
- **VNDB Entry**: Submit under Visual Novel Database (VNDB) using the tags: Interactive Fiction, Choice-Driven Narrative, Text-Based CYOA.
"""

    # Target directory
    target_dir = os.path.abspath(out_dir or os.path.join(repo_root, "dist", campaign_id))
    os.makedirs(target_dir, exist_ok=True)

    json_path = os.path.join(target_dir, "itch_metadata.json")
    with open(json_path, "w", encoding="utf-8") as f:
        json.dump(metadata, f, indent=2, ensure_ascii=False)
        f.write("\n")

    md_path = os.path.join(target_dir, "ITCH_LISTING.md")
    with open(md_path, "w", encoding="utf-8") as f:
        f.write(markdown_listing)

    return metadata, markdown_listing


def main():
    parser = argparse.ArgumentParser(description="Generate itch.io metadata and listing for a Whimsy campaign.")
    parser.add_argument("--campaign", required=True, help="Campaign ID (e.g. template_campaign)")
    parser.add_argument("--out", default=None, help="Output directory (defaults to dist/<campaign_id>)")
    args = parser.parse_args()

    try:
        metadata, _ = generate_itch_metadata(args.campaign, args.out)
        out_dest = args.out or os.path.join("dist", args.campaign)
        print(f"Generated itch.io metadata for campaign '{args.campaign}' in {out_dest}/")
        print(f"  - Title: {metadata['title']}")
        print(f"  - Genre: {metadata['genre']}")
        print(f"  - Tags: {', '.join(metadata['tags'])}")
    except Exception as e:
        print(f"Error generating itch.io metadata: {e}", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
