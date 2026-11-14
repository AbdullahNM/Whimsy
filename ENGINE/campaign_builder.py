import os
import json
import re

def scaffold_campaign(root_dir: str, params: dict) -> dict:
    """
    Scaffolds a new campaign universe conforming to CAMPAIGN_INIT_SPEC.md,
    GLOBAL/SCHEMAS/campaign_init.schema.json, and turn_state.schema.json.
    """
    cid = re.sub(r'[^a-z0-9_-]', '_', params.get("campaign_id", "custom_campaign").lower()).strip('_')
    if not cid:
        cid = "custom_campaign"
        
    title = params.get("title", cid.replace('_', ' ').title())
    genre = params.get("genre", "Custom Adventure")
    mode = params.get("operational_mode", "classic_cyoa")
    pacing = params.get("pacing_profile", "balanced")
    purse = params.get("purse", "500 credits")
    protagonist_name = params.get("protagonist_name", "Protagonist")
    protagonist_role = params.get("protagonist_role", "Explorer")
    premise = params.get("premise", "You stand at the threshold of a new journey, assessing the path ahead.")
    location = params.get("location", "Starting Staging Area")

    campaign_dir = os.path.join(root_dir, "CAMPAIGNS", cid)
    os.makedirs(campaign_dir, exist_ok=True)
    os.makedirs(os.path.join(campaign_dir, "GAMEPLAY"), exist_ok=True)
    os.makedirs(os.path.join(campaign_dir, "IDEAS"), exist_ok=True)
    os.makedirs(os.path.join(campaign_dir, "WORLD_FOUNDATION"), exist_ok=True)
    os.makedirs(os.path.join(campaign_dir, "TURNS", "ACTIVE"), exist_ok=True)
    os.makedirs(os.path.join(campaign_dir, "TURNS", "ARCHIVE"), exist_ok=True)
    
    for cat in ["CORE", "PLACES", "PEOPLE", "FACTIONS", "GUIDES"]:
        cat_dir = os.path.join(campaign_dir, "WORLD_BIBLE", cat)
        os.makedirs(cat_dir, exist_ok=True)
        with open(os.path.join(cat_dir, ".gitkeep"), "w", encoding="utf-8") as f:
            f.write("")

    # 1. campaign_config.json
    config = {
        "id": cid,
        "title": title,
        "genre": genre,
        "operational_mode": mode,
        "pacing_profile": pacing,
        "theme": {
            "bg_dark": "#0d1117",
            "bg_slate": "#161b22",
            "bg_card": "#21262d",
            "gold_primary": "#58a6ff",
            "gold_dim": "#1f6feb",
            "accent_glow": "rgba(88, 166, 255, 0.2)",
            "text_ivory": "#f0f6fc",
            "font_family": "system-ui, -apple-system, sans-serif"
        },
        "style_contract": {
            "mode": "natural_everyday_english",
            "max_sentence_words": 35,
            "prohibited_patterns": [
                "breathtaking prowess",
                "like a true prodigy",
                "little did they know"
            ],
            "ban_stem_calculus_jargon": True,
            "ban_decorative_microsfx": True,
            "ban_forced_cliffhangers": True,
            "ban_narrator_praise": True
        },
        "metrics": [
            {"id": "turn", "label": "Turn", "type": "counter", "path": "turn"},
            {"id": "energy", "label": "Energy", "type": "progress", "color": "#58a6ff", "path": "progression.energy", "max_path": "progression.energy_max"},
            {"id": "stress", "label": "Stress", "type": "progress", "color": "#f85149", "path": "progression.stress", "max_path": "progression.stress_max"},
            {"id": "funds", "label": "Funds", "type": "text", "path": "purse.display"}
        ],
        "entity_header": {
            "title_path": "character.name",
            "subtitle_path": "character.archetype",
            "tag_paths": ["character.origin", "character.faction"]
        }
    }
    with open(os.path.join(campaign_dir, "campaign_config.json"), "w", encoding="utf-8") as f:
        json.dump(config, f, indent=2, ensure_ascii=False)

    # 2. CONFIG.yaml
    with open(os.path.join(campaign_dir, "CONFIG.yaml"), "w", encoding="utf-8") as f:
        f.write(f"campaign_id: {cid}\nmodel: local-antigravity\ntemperature: 0.7\ncontext_turn_budget: 15\n")

    # 3. GAMEPLAY/status.json
    status = {
        "schema_version": 2,
        "campaign_id": cid,
        "turn": 1,
        "timeline": "Act I • Inception",
        "character": {
            "name": protagonist_name,
            "archetype": protagonist_role,
            "origin": "Independent",
            "faction": "Unaligned"
        },
        "progression": {
            "energy": 100,
            "energy_max": 100,
            "stress": 0,
            "stress_max": 100,
            "checkpoint_tokens": 5,
            "checkpoint_max": 5
        },
        "purse": {
            "display": purse,
            "standard_units": 500
        },
        "clocks": [],
        "scene_anchor": {
            "location": location,
            "context": premise,
            "time": "Day 1, 08:00"
        },
        "pacing_state": {
            "scene_type": "exploration",
            "scene_objective": "Survey immediate surroundings and establish baseline footing.",
            "narrative_intensity": 1,
            "zoom_level": "detailed_scene",
            "elapsed_time_minutes": 0,
            "timeline_stamp": "Day 1, 08:00",
            "active_conflicts": [],
            "unresolved_intentions": [],
            "current_location": location,
            "pending_decisions": ["Determine initial objective and explore area"],
            "pacing_profile": pacing,
            "scheduled_events": []
        },
        "public_state": {
            "flags": {},
            "conditions": [],
            "open_threads": ["Initial exploration"]
        },
        "offered_choices": [
            {"index": 1, "text": "Press forward and scout the primary route."},
            {"index": 2, "text": "Inspect the surrounding environment for resources or clues."},
            {"index": 3, "text": "Take stock of your supplies and prepare equipment."},
            {"index": 4, "text": "Seek out locals or contacts to gather initial intelligence."}
        ]
    }
    with open(os.path.join(campaign_dir, "GAMEPLAY", "status.json"), "w", encoding="utf-8") as f:
        json.dump(status, f, indent=2, ensure_ascii=False)

    # 4. GAMEPLAY/status.md
    with open(os.path.join(campaign_dir, "GAMEPLAY", "status.md"), "w", encoding="utf-8") as f:
        f.write(f"# Status — {title}\n\n- **Protagonist:** {protagonist_name} ({protagonist_role})\n- **Turn:** 1\n- **Timeline:** Act I • Inception\n- **Location:** {location}\n- **Purse:** {purse}\n\n{premise}\n")

    # 5. GAMEPLAY/items.json & items.md
    items = {
        "campaign_id": cid,
        "purse": {"display": purse, "units": 500},
        "equipped": [
            {"name": "Standard Field Equipment", "desc": "Essential gear for field navigation and survival.", "condition": "functional"}
        ],
        "inventory": []
    }
    with open(os.path.join(campaign_dir, "GAMEPLAY", "items.json"), "w", encoding="utf-8") as f:
        json.dump(items, f, indent=2, ensure_ascii=False)
    with open(os.path.join(campaign_dir, "GAMEPLAY", "items.md"), "w", encoding="utf-8") as f:
        f.write(f"# Inventory\n\n### Equipped Gear\n- **Standard Field Equipment**: Essential field gear.\n\n### Resources\n- **Purse**: {purse}\n")

    # 6. GAMEPLAY/relations.json & relations.md
    relations = {
        "campaign_id": cid,
        "key_contacts": [
            {"name": "Field Coordinator", "role": "Logistics Dispatcher", "standing": "Neutral", "score": 50}
        ]
    }
    with open(os.path.join(campaign_dir, "GAMEPLAY", "relations.json"), "w", encoding="utf-8") as f:
        json.dump(relations, f, indent=2, ensure_ascii=False)
    with open(os.path.join(campaign_dir, "GAMEPLAY", "relations.md"), "w", encoding="utf-8") as f:
        f.write("# Relations\n\n- **Field Coordinator** [Neutral]: Primary initial contact.\n")

    # 7. GAMEPLAY/upcoming_hooks.md
    with open(os.path.join(campaign_dir, "GAMEPLAY", "upcoming_hooks.md"), "w", encoding="utf-8") as f:
        f.write("### [OPTIONS & TYPABLE REFERENCE]\n1. Press forward and scout the primary route.\n2. Inspect the surrounding environment for resources or clues.\n3. Take stock of your supplies and prepare equipment.\n4. Seek out locals or contacts to gather initial intelligence.\n")

    # 8. IDEAS/narrative_steering.md
    with open(os.path.join(campaign_dir, "IDEAS", "narrative_steering.md"), "w", encoding="utf-8") as f:
        f.write(f"# Narrative Steering — {title}\n\n## Core Arc Trajectory\n- **Pacing Profile:** {pacing.capitalize()}\n- **Operational Mode:** {mode}\n- **Initial Milestone:** Establish footing in {location}.\n\n## Emerging Pressures\n- Observe environment for unfolding regional tensions.\n- Maintain grounded character dialogue and tactical causality.\n")

    # 9. WORLD_FOUNDATION/world_foundation.json
    world_foundation = {
        "schema_version": "1.0.0",
        "campaign_id": cid,
        "immutable_facts": [
            f"The universe operates under the genre rules of {genre}.",
            f"The primary operating environment is centered around {location}."
        ],
        "mutable_world_state": {
            "current_era": "Initial Era",
            "threat_level": "Normal"
        },
        "factions_and_tensions": [],
        "npc_knowledge": {},
        "rumors_and_beliefs": [],
        "unresolved_mysteries": []
    }
    with open(os.path.join(campaign_dir, "WORLD_FOUNDATION", "world_foundation.json"), "w", encoding="utf-8") as f:
        json.dump(world_foundation, f, indent=2, ensure_ascii=False)

    # 10. TURNS/ACTIVE/turn_0001.md
    turn_1 = f"""# Turn 1 — The Threshold

You arrive at {location}. {premise}

The air is quiet as you pause to assess your surroundings. Every decision forward will shape your standing, resources, and trajectory in this universe.

### [OPTIONS & TYPABLE REFERENCE]
1. Press forward and scout the primary route.
2. Inspect the surrounding environment for resources or clues.
3. Take stock of your supplies and prepare equipment.
4. Seek out locals or contacts to gather initial intelligence.

[PROGRESSION/XP RESOLUTION: Previous: 0 | Delta: 0 (Initial Footing) | New Total: 0 / 100]
[CURRENCY/RESOURCE RESOLUTION: Previous: {purse} | Delta: 0 | New Total: {purse}]
[SYS: Turn 1 | Mode: {mode} | Focus: Detailed Scene | Intensity: 1/5 | Checkpoints: 5/5 | Active RECAL: None]
"""
    with open(os.path.join(campaign_dir, "TURNS", "ACTIVE", "turn_0001.md"), "w", encoding="utf-8") as f:
        f.write(turn_1)

    # 11. Rebuild UI bundled manifests
    try:
        from scripts.build_ui_data import main as rebuild_ui
        rebuild_ui()
    except Exception as e:
        # Fallback inline manifest updater
        update_ui_manifests(root_dir)

    return {
        "campaign_id": cid,
        "title": title,
        "config": config,
        "status_data": status
    }


def update_ui_manifests(root_dir: str):
    """Updates campaign_configs.json and gameplay_manifest.json to include all campaigns."""
    ui_dir = os.path.join(root_dir, "UI")
    campaigns_dir = os.path.join(root_dir, "CAMPAIGNS")
    if not os.path.isdir(campaigns_dir):
        return

    all_configs = {}
    all_manifest = {}

    for cname in sorted(os.listdir(campaigns_dir)):
        cdir = os.path.join(campaigns_dir, cname)
        cfile = os.path.join(cdir, "campaign_config.json")
        if os.path.isfile(cfile):
            try:
                with open(cfile, "r", encoding="utf-8") as f:
                    cfg = json.load(f)
                cid = cfg.get("id", cname)
                all_configs[cid] = cfg

                # Build minimal manifest entry
                gp_dir = os.path.join(cdir, "GAMEPLAY")
                active_dir = os.path.join(cdir, "TURNS", "ACTIVE")
                active_turns = []
                if os.path.isdir(active_dir):
                    for tfile in sorted(os.listdir(active_dir)):
                        if tfile.endswith(".md"):
                            with open(os.path.join(active_dir, tfile), "r", encoding="utf-8") as tf:
                                active_turns.append({"name": tfile, "content": tf.read()})

                status_json = {}
                s_json_path = os.path.join(gp_dir, "status.json")
                if os.path.isfile(s_json_path):
                    with open(s_json_path, "r", encoding="utf-8") as sf:
                        status_json = json.load(sf)

                steering = ""
                steering_path = os.path.join(cdir, "IDEAS", "narrative_steering.md")
                if os.path.isfile(steering_path):
                    with open(steering_path, "r", encoding="utf-8") as stf:
                        steering = stf.read()

                all_manifest[cid] = {
                    "status_json": status_json,
                    "active_turns": active_turns,
                    "narrative_steering": steering
                }
            except Exception:
                pass

    if all_configs:
        cfg_out = os.path.join(ui_dir, "campaign_configs.json")
        with open(cfg_out, "w", encoding="utf-8") as f:
            json.dump(all_configs, f, indent=2, ensure_ascii=False)

    if all_manifest:
        man_out = os.path.join(ui_dir, "gameplay_manifest.json")
        with open(man_out, "w", encoding="utf-8") as f:
            json.dump(all_manifest, f, indent=2, ensure_ascii=False)


def consult_shadow_narrator(root_dir: str, campaign_id: str, query: str) -> dict:
    """
    Synthesizes continuity and arc guidance from the campaign's living steering and status files.
    """
    cdir = os.path.join(root_dir, "CAMPAIGNS", campaign_id)
    steering_file = os.path.join(cdir, "IDEAS", "narrative_steering.md")
    status_file = os.path.join(cdir, "GAMEPLAY", "status.json")
    
    steering_text = ""
    if os.path.isfile(steering_file):
        with open(steering_file, "r", encoding="utf-8") as f:
            steering_text = f.read()
            
    status_data = {}
    if os.path.isfile(status_file):
        try:
            with open(status_file, "r", encoding="utf-8") as f:
                status_data = json.load(f)
        except Exception:
            pass

    pacing = status_data.get("pacing_state", {})
    zoom = pacing.get("zoom_level", "detailed_scene")
    intensity = pacing.get("narrative_intensity", 1)
    location = pacing.get("current_location", status_data.get("scene_anchor", {}).get("location", "Unknown"))
    conflicts = pacing.get("active_conflicts", [])
    threads = status_data.get("public_state", {}).get("open_threads", [])

    # Generate grounded response
    response = [
        f"🔮 **Shadow Narrator Advisory** for *{campaign_id}*:",
        "",
        f"- **Current Anchor**: {location} (Intensity: {intensity}/5, Zoom: `{zoom}`)",
        f"- **Open Threads**: {', '.join(threads) if threads else 'None pending'}",
        f"- **Active Conflicts**: {', '.join(conflicts) if conflicts else 'None unresolved'}",
        "",
        f"**Advisory regarding '{query.strip()}':**",
        f"Maintain causal momentum without rushing unearned escalations. Given your current camera zoom ({zoom}) and baseline intensity ({intensity}/5), ensure any dramatic shift is tethered to tangible in-world actions and character choices rather than artificial stakes.",
        "",
        "**Recommended Next Step**: Pursue your primary scene objective while noting any unaddressed ambient clues in your immediate environment."
    ]

    return {
        "status": "success",
        "campaign_id": campaign_id,
        "query": query,
        "advice": "\n".join(response),
        "steering": steering_text,
        "pacing": pacing
    }
