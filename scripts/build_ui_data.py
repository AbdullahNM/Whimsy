#!/usr/bin/env python3
"""Build the UI's bundled data files from CAMPAIGNS/template_campaign.

The UI ships with the generic template campaign only; private campaigns are
loaded at runtime via the File System Access API and are never bundled here.

Usage:  python3 scripts/build_ui_data.py
"""
import json
import os
import re

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
UI = os.path.join(ROOT, "UI")
TEMPLATE = os.path.join(ROOT, "CAMPAIGNS", "template_campaign")


def read(path):
    with open(path, "r", encoding="utf-8") as f:
        return f.read()


def read_json(path):
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


def write_json(path, data):
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2, ensure_ascii=False)
        f.write("\n")


def build_campaign_configs():
    config = read_json(os.path.join(TEMPLATE, "campaign_config.json"))
    return {config["id"]: config}


def build_gameplay_manifest():
    config = read_json(os.path.join(TEMPLATE, "campaign_config.json"))
    cid = config["id"]
    gameplay = os.path.join(TEMPLATE, "GAMEPLAY")

    active_dir = os.path.join(TEMPLATE, "TURNS", "ACTIVE")
    active_turns = []
    for name in sorted(os.listdir(active_dir)):
        if name.endswith(".md"):
            active_turns.append({
                "name": name,
                "content": read(os.path.join(active_dir, name)),
            })

    entry = {
        "status": read(os.path.join(gameplay, "status.md")),
        "relations": read(os.path.join(gameplay, "relations.md")),
        "items": read(os.path.join(gameplay, "items.md")),
        "upcoming_hooks": read(os.path.join(gameplay, "upcoming_hooks.md")),
        "status_json": read_json(os.path.join(gameplay, "status.json")),
        "relations_json": read_json(os.path.join(gameplay, "relations.json")),
        "items_json": read_json(os.path.join(gameplay, "items.json")),
        "active_turns": active_turns,
        "narrative_steering": read(os.path.join(TEMPLATE, "IDEAS", "narrative_steering.md")),
    }
    return {cid: entry}


def build_world_bible_data():
    bible = os.path.join(TEMPLATE, "WORLD_BIBLE")
    data = {}
    if not os.path.isdir(bible):
        return data
    for cat in sorted(os.listdir(bible)):
        cat_dir = os.path.join(bible, cat)
        if not os.path.isdir(cat_dir):
            continue
        articles = []
        for name in sorted(os.listdir(cat_dir)):
            if not name.endswith(".md"):
                continue
            content = read(os.path.join(cat_dir, name))
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


def main():
    write_json(os.path.join(UI, "campaign_configs.json"), build_campaign_configs())
    write_json(os.path.join(UI, "gameplay_manifest.json"), build_gameplay_manifest())
    write_json(os.path.join(UI, "world_bible_data.json"), build_world_bible_data())
    print("Regenerated UI/campaign_configs.json, UI/gameplay_manifest.json, UI/world_bible_data.json")


if __name__ == "__main__":
    main()
