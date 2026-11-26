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


def _shadow_llm_call(
    api_key: str,
    provider: str,
    model: str,
    api_base_url: str,
    system_prompt: str,
    user_prompt: str,
) -> str:
    """Invoke OpenRouter, FastRouter, Gemini, or custom OpenAI-compatible model for Shadow Narrator."""
    import urllib.request

    prov = (provider or "").strip().lower()
    if not prov:
        if (model or "").startswith("fastrouter/") or "fastrouter.ai" in (api_base_url or ""):
            prov = "fastrouter"
        elif api_key.startswith("sk-or-") or (model or "").startswith("openrouter/"):
            prov = "openrouter"
        elif api_base_url:
            prov = "custom"
        elif api_key.startswith("AIza"):
            prov = "gemini"
        else:
            prov = "openrouter"

    if prov == "gemini":
        clean_model = (model or "gemini-2.5-flash").split("/")[-1]
        url = f"https://generativelanguage.googleapis.com/v1beta/models/{clean_model}:generateContent?key={api_key}"
        body = {
            "contents": [{"role": "user", "parts": [{"text": user_prompt}]}],
            "systemInstruction": {"parts": [{"text": system_prompt}]},
        }
        req = urllib.request.Request(url, data=json.dumps(body).encode("utf-8"), headers={"Content-Type": "application/json"})
        with urllib.request.urlopen(req, timeout=30) as resp:
            data = json.loads(resp.read().decode("utf-8"))
            return data["candidates"][0]["content"]["parts"][0]["text"].strip()

    if prov == "fastrouter":
        url = api_base_url or "https://api.fastrouter.ai/api/v1/chat/completions"
        target_model = model or "openai/gpt-4o-mini"
    elif prov == "custom" and api_base_url:
        url = api_base_url
        target_model = model or "gpt-4o-mini"
    else:
        url = api_base_url or "https://openrouter.ai/api/v1/chat/completions"
        target_model = model or "anthropic/claude-3.5-sonnet"

    for prefix in ("openrouter/", "fastrouter/"):
        if target_model.startswith(prefix):
            target_model = target_model[len(prefix):]

    headers = {
        "Content-Type": "application/json",
        "Authorization": f"Bearer {api_key}",
    }
    if prov == "openrouter":
        headers["HTTP-Referer"] = "http://localhost:8000"
        headers["X-Title"] = "Whimsy Shadow Narrator"

    body = {
        "model": target_model,
        "messages": [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt},
        ],
        "temperature": 0.5,
        "max_tokens": 500,
    }
    req = urllib.request.Request(url, data=json.dumps(body).encode("utf-8"), headers=headers)
    with urllib.request.urlopen(req, timeout=35) as resp:
        data = json.loads(resp.read().decode("utf-8"))
        return data["choices"][0]["message"]["content"].strip()


def consult_shadow_narrator(
    root_dir: str,
    campaign_id: str,
    query: str,
    api_key: str = None,
    provider: str = None,
    model: str = None,
    api_base_url: str = None,
    post_to_channel: bool = False,
    apply_recal: bool = False,
) -> dict:
    """
    Synthesizes out-of-character continuity, pacing, and steering guidance from the campaign's
    living steering, status, recent turns, and agent channel. Optionally posts the directive to
    IDEAS/agent_channel.md for the Active GM.
    """
    cdir = os.path.join(root_dir, "CAMPAIGNS", campaign_id)
    steering_file = os.path.join(cdir, "IDEAS", "narrative_steering.md")
    status_file = os.path.join(cdir, "GAMEPLAY", "status.json")
    turns_dir = os.path.join(cdir, "TURNS", "ACTIVE")

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

    recent_turns = []
    if os.path.isdir(turns_dir):
        turn_files = sorted(f for f in os.listdir(turns_dir) if f.endswith(".md"))[-3:]
        for tf in turn_files:
            try:
                with open(os.path.join(turns_dir, tf), "r", encoding="utf-8") as f:
                    recent_turns.append(f"--- {tf} ---\n{f.read()[:1500]}")
            except Exception:
                pass

    turn_num = int(status_data.get("turn", 1) or 1)
    pacing = status_data.get("pacing_state", {})
    zoom = pacing.get("zoom_level", "detailed_scene")
    intensity = pacing.get("narrative_intensity", 1)
    location = pacing.get("current_location", status_data.get("scene_anchor", {}).get("location", "Unknown"))
    conflicts = pacing.get("active_conflicts", [])
    threads = status_data.get("public_state", {}).get("open_threads", [])
    clocks = status_data.get("clocks", [])
    clocks_summary = ", ".join(f"{c.get('label', c.get('id'))} ({c.get('current', 0)}/{c.get('max', 4)})" for c in clocks) or "None"

    advice_text = ""
    directive_text = ""
    used_llm = False

    try:
        from ENGINE.engine import resolve_llm_config
    except ImportError:
        from engine import resolve_llm_config

    llm_cfg = resolve_llm_config({
        "apiKey": api_key,
        "provider": provider,
        "model": model,
        "apiBaseUrl": api_base_url,
    })
    resolved_key = None if llm_cfg.get("credential_error") else (llm_cfg.get("api_key") or None)

    if resolved_key and query.strip():
        sys_prompt = (
            "You are the Shadow Narrator & Campaign Architect (out-of-character overseer) for Whimsy CYOA.\n"
            "Rules:\n"
            "- NEVER resolve player choices or write in-character turn prose.\n"
            "- Speak plainly and concisely out-of-character to the player/GM.\n"
            "- Check grounding, pacing (Zero Micro-Scene Rule), clocks, and CORE-003 style contract.\n"
            "- Provide:\n"
            "  1) Concise diagnostic/answer to the player's question.\n"
            "  2) A crisp 1-2 sentence `ACTIVE GM DIRECTIVE:` for the next turn."
        )
        user_prompt = (
            f"Campaign: {campaign_id} | Turn: {turn_num} | Location: {location}\n"
            f"Focus: {zoom} | Intensity: {intensity}/5 | Clocks: {clocks_summary}\n"
            f"Open Threads: {', '.join(threads) if threads else 'None'}\n\n"
            f"Narrative Steering:\n{steering_text[:2000]}\n\n"
            f"Recent Turns:\n{chr(10).join(recent_turns)[:3000]}\n\n"
            f"Player Meta-Query / Steering Request:\n{query.strip()}"
        )
        try:
            advice_text = _shadow_llm_call(
                resolved_key,
                llm_cfg.get("provider"),
                llm_cfg.get("model"),
                llm_cfg.get("api_base"),
                sys_prompt,
                user_prompt,
            )
            used_llm = True
            dir_match = re.search(r"ACTIVE GM DIRECTIVE:\s*(.+)", advice_text, re.IGNORECASE | re.DOTALL)
            if dir_match:
                directive_text = dir_match.group(1).strip().splitlines()[0].strip()
        except Exception:
            advice_text = ""

    if not advice_text:
        clean_q = query.strip() or "General pacing and continuity check"
        directive_text = (
            f"Honor player meta-steering ('{clean_q}') while keeping zoom at `{zoom}`, "
            f"intensity at {intensity}/5, and grounding consequences in {location}."
        )
        response = [
            f"**Shadow Narrator Advisory** for *{campaign_id}* (Turn {turn_num}):",
            "",
            f"- **Current Anchor**: {location} (Intensity: {intensity}/5, Zoom: `{zoom}`)",
            f"- **Active Clocks**: {clocks_summary}",
            f"- **Open Threads**: {', '.join(threads) if threads else 'None pending'}",
            f"- **Active Conflicts**: {', '.join(conflicts) if conflicts else 'None unresolved'}",
            "",
            f"**Steering Response to '{clean_q}':**",
            f"Maintain causal continuity and CORE-003 unadorned prose. {directive_text}",
            "",
            f"**Active GM Directive**: {directive_text}",
        ]
        advice_text = "\n".join(response)
    elif not directive_text:
        directive_text = f"Incorporate Shadow Narrator guidance on '{query.strip()}': keep prose grounded in {location} at intensity {intensity}/5."

    channel_messages = None
    if post_to_channel and os.path.isdir(cdir):
        try:
            from ENGINE.agent_channel import AgentChannelManager
        except ImportError:
            from agent_channel import AgentChannelManager
        mgr = AgentChannelManager(cdir)
        channel_content = directive_text
        if apply_recal:
            channel_content += f" [RECAL: {query.strip()} - Expires: Turn {turn_num + 5}]"
        channel_messages = mgr.post_message(
            sender="SHADOW",
            recipient="ACTIVE",
            content=channel_content,
            turn=turn_num,
        )

    return {
        "status": "success",
        "campaign_id": campaign_id,
        "query": query,
        "advice": advice_text,
        "directive": directive_text,
        "used_llm": used_llm,
        "posted_to_channel": bool(post_to_channel and channel_messages is not None),
        "channel_messages": channel_messages,
        "steering": steering_text,
        "pacing": pacing,
    }
