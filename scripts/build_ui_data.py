#!/usr/bin/env python3
"""Build the UI's bundled data files from public repo campaigns.

Ships public campaigns (sample_campaign, template_campaign) if present;
private campaigns are loaded at runtime via the local engine or File System Access API
and are never bundled here.

Usage:  python3 scripts/build_ui_data.py
"""
import json
import os
import re
import sys

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

UI = os.path.join(ROOT, "UI")
PUBLIC_CAMPAIGNS = ["sample_campaign", "template_campaign"]


def read(path):
    if not os.path.exists(path):
        return ""
    with open(path, "r", encoding="utf-8") as f:
        return f.read()


def read_json(path):
    if not os.path.exists(path):
        return None
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


def write_json(path, data):
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2, ensure_ascii=False)
        f.write("\n")


def _iter_public_campaign_dirs():
    for cname in PUBLIC_CAMPAIGNS:
        cdir = os.path.join(ROOT, "CAMPAIGNS", cname)
        cfg_path = os.path.join(cdir, "campaign_config.json")
        if os.path.isdir(cdir) and os.path.isfile(cfg_path):
            yield cname, cdir


def build_campaign_configs():
    configs = {}
    for cname, cdir in _iter_public_campaign_dirs():
        config = read_json(os.path.join(cdir, "campaign_config.json"))
        if config:
            configs[config.get("id", cname)] = config
    return configs


def build_gameplay_manifest():
    manifest = {}
    for cname, cdir in _iter_public_campaign_dirs():
        config = read_json(os.path.join(cdir, "campaign_config.json")) or {}
        cid = config.get("id", cname)
        gameplay = os.path.join(cdir, "GAMEPLAY")

        active_dir = os.path.join(cdir, "TURNS", "ACTIVE")
        active_turns = []
        if os.path.isdir(active_dir):
            for name in sorted(os.listdir(active_dir)):
                if name.endswith(".md"):
                    active_turns.append({
                        "name": name,
                        "content": read(os.path.join(active_dir, name)),
                    })

        agent_channel = []
        try:
            from ENGINE.agent_channel import AgentChannelManager
            agent_channel = AgentChannelManager(cdir).load_messages(force_disk=True)
        except Exception:
            pass

        ontology_json = (
            read_json(os.path.join(cdir, "ontology.json"))
            or read_json(os.path.join(cdir, "WORLD_FOUNDATION", "ontology.json"))
        )

        entry = {
            "status": read(os.path.join(gameplay, "status.md")),
            "relations": read(os.path.join(gameplay, "relations.md")),
            "items": read(os.path.join(gameplay, "items.md")),
            "upcoming_hooks": read(os.path.join(gameplay, "upcoming_hooks.md")),
            "status_json": read_json(os.path.join(gameplay, "status.json")) or {},
            "relations_json": read_json(os.path.join(gameplay, "relations.json")) or {},
            "items_json": read_json(os.path.join(gameplay, "items.json")) or {},
            "ontology_json": ontology_json,
            "active_turns": active_turns,
            "narrative_steering": read(os.path.join(cdir, "IDEAS", "narrative_steering.md")),
            "agent_channel": agent_channel,
        }
        manifest[cid] = entry
    return manifest


def _collect_bible_articles(cdir):
    bible = os.path.join(cdir, "WORLD_BIBLE")
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


def build_world_bible_data():
    per_campaign = {}
    for cname, cdir in _iter_public_campaign_dirs():
        config = read_json(os.path.join(cdir, "campaign_config.json")) or {}
        cid = config.get("id", cname)
        per_campaign[cid] = _collect_bible_articles(cdir)
    if len(per_campaign) == 1:
        return next(iter(per_campaign.values()))
    return per_campaign


def main():
    write_json(os.path.join(UI, "campaign_configs.json"), build_campaign_configs())
    write_json(os.path.join(UI, "gameplay_manifest.json"), build_gameplay_manifest())
    write_json(os.path.join(UI, "world_bible_data.json"), build_world_bible_data())
    print("Regenerated UI/campaign_configs.json, UI/gameplay_manifest.json, UI/world_bible_data.json")


if __name__ == "__main__":
    main()
