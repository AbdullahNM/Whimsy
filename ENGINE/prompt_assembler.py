import os
import glob
import json
import re
from typing import Any
try:
    from ENGINE.turn_archiver import load_active_turns
except ImportError:
    from turn_archiver import load_active_turns

try:
    from ENGINE.retrieval import HybridRetriever
except ImportError:
    try:
        from retrieval import HybridRetriever
    except ImportError:
        HybridRetriever = None

class PromptAssembler:
    DEFAULT_RULES_CHAR_BUDGET = 8000
    DEFAULT_WORLD_FOUNDATION_CHAR_BUDGET = 6000
    DEFAULT_ACTIVE_TURNS_BUDGET = 5
    DEFAULT_IDEAS_CHAR_BUDGET = 4000

    def __init__(self, root_dir: str):
        self.root_dir = root_dir
        self.global_dir = os.path.join(root_dir, "GLOBAL")
        self.campaigns_dir = os.path.join(root_dir, "CAMPAIGNS")
        self._retrievers = {}

    def get_campaign_budget_config(self, campaign_name: str) -> dict:
        """
        Loads the configured section budget from campaign_config.json
        (supporting 'token_budget' or 'char_budget' blocks).
        """
        cfg_path = os.path.join(self.campaigns_dir, campaign_name, "campaign_config.json")
        if not os.path.exists(cfg_path) and os.path.isdir(campaign_name):
            cfg_path = os.path.join(campaign_name, "campaign_config.json")
        if os.path.exists(cfg_path):
            try:
                with open(cfg_path, "r", encoding="utf-8") as f:
                    cfg = json.load(f)
                b_cfg = cfg.get("token_budget")
                if b_cfg is None:
                    b_cfg = cfg.get("char_budget")
                if isinstance(b_cfg, dict):
                    budget = {
                        "rules_char_budget": b_cfg.get("rules_char_budget", self.DEFAULT_RULES_CHAR_BUDGET),
                        "world_foundation_char_budget": b_cfg.get("world_foundation_char_budget", self.DEFAULT_WORLD_FOUNDATION_CHAR_BUDGET),
                        "active_turns_budget": b_cfg.get("active_turns_budget", self.DEFAULT_ACTIVE_TURNS_BUDGET),
                        "ideas_char_budget": b_cfg.get("ideas_char_budget", self.DEFAULT_IDEAS_CHAR_BUDGET),
                    }
                    for k, v in b_cfg.items():
                        if k not in budget:
                            budget[k] = v
                    return budget
            except Exception:
                pass
        return {}

    def _resolve_budget(self, campaign_name: str, token_budget: dict = None) -> dict:
        budget = dict(self.get_campaign_budget_config(campaign_name))
        if token_budget:
            merged = {
                "rules_char_budget": token_budget.get("rules_char_budget", budget.get("rules_char_budget", self.DEFAULT_RULES_CHAR_BUDGET)),
                "world_foundation_char_budget": token_budget.get("world_foundation_char_budget", budget.get("world_foundation_char_budget", self.DEFAULT_WORLD_FOUNDATION_CHAR_BUDGET)),
                "active_turns_budget": token_budget.get("active_turns_budget", budget.get("active_turns_budget", self.DEFAULT_ACTIVE_TURNS_BUDGET)),
                "ideas_char_budget": token_budget.get("ideas_char_budget", budget.get("ideas_char_budget", self.DEFAULT_IDEAS_CHAR_BUDGET)),
            }
            for k, v in token_budget.items():
                if k not in merged:
                    merged[k] = v
            return merged
        return budget

    def load_global_rules(self, max_chars: int = None) -> str:
        rule_files = sorted(glob.glob(os.path.join(self.global_dir, "CORE-*.md")))
        contents = []
        for rf in rule_files:
            with open(rf, "r", encoding="utf-8") as f:
                contents.append(f"=== {os.path.basename(rf)} ===\n{f.read()}")
        text = "\n\n".join(contents)
        if max_chars is not None and len(text) > max_chars:
            trunc_msg = "\n... [TRUNCATED DUE TO RULES BUDGET]"
            avail = max(0, max_chars - len(trunc_msg))
            cut_idx = text.rfind("\n", 0, avail)
            if cut_idx == -1:
                cut_idx = avail
            text = text[:cut_idx].rstrip() + trunc_msg
        return text

    def load_campaign_state(self, campaign_name: str) -> str:
        state_path = os.path.join(self.campaigns_dir, campaign_name, "STATE", "public_ledger.md")
        if os.path.exists(state_path):
            with open(state_path, "r", encoding="utf-8") as f:
                return f"=== STATE: PUBLIC_LEDGER ===\n{f.read()}"
        return ""

    def load_campaign_agents_directives(self, campaign_name: str) -> str:
        agents_path = os.path.join(self.campaigns_dir, campaign_name, "AGENTS.md")
        if not os.path.exists(agents_path) and os.path.isdir(campaign_name):
            agents_path = os.path.join(campaign_name, "AGENTS.md")
        if os.path.exists(agents_path):
            with open(agents_path, "r", encoding="utf-8") as f:
                return f"=== CAMPAIGN DIRECTIVES & PROGRESSION DOCTRINE: AGENTS.MD ===\n{f.read()}"
        return ""

    def load_campaign_config(self, campaign_name: str) -> str:
        cfg_path = os.path.join(self.campaigns_dir, campaign_name, "campaign_config.json")
        if not os.path.exists(cfg_path) and os.path.isdir(campaign_name):
            cfg_path = os.path.join(campaign_name, "campaign_config.json")
        if os.path.exists(cfg_path):
            try:
                with open(cfg_path, "r", encoding="utf-8") as f:
                    cfg = json.load(f)
                return f"=== CAMPAIGN CONFIGURATION & METRICS ===\n{json.dumps(cfg, indent=2)}"
            except Exception:
                pass
        return ""

    def get_campaign_retrieval_config(self, campaign_name: str) -> dict:
        cfg_path = os.path.join(self.campaigns_dir, campaign_name, "campaign_config.json")
        if not os.path.exists(cfg_path) and os.path.isdir(campaign_name):
            cfg_path = os.path.join(campaign_name, "campaign_config.json")
        if os.path.exists(cfg_path):
            try:
                with open(cfg_path, "r", encoding="utf-8") as f:
                    cfg = json.load(f)
                    return cfg.get("retrieval", {})
            except Exception:
                pass
        return {}

    def get_retriever(self, campaign_name: str, retrieval_cfg: dict = None):
        if HybridRetriever is None:
            return None
        if campaign_name not in self._retrievers:
            campaign_dir = os.path.join(self.campaigns_dir, campaign_name)
            if not os.path.exists(campaign_dir) and os.path.isdir(campaign_name):
                campaign_dir = campaign_name
            if not os.path.exists(campaign_dir):
                return None
            cfg = retrieval_cfg or self.get_campaign_retrieval_config(campaign_name)
            char_budget = cfg.get("char_budget", 16000)
            max_passages = cfg.get("max_passages", 5)
            self._retrievers[campaign_name] = HybridRetriever(
                campaign_dir=campaign_dir,
                char_budget=char_budget,
                max_passages=max_passages
            )
        return self._retrievers[campaign_name]

    def load_campaign_gameplay(self, campaign_name: str) -> str:
        gameplay_dir = os.path.join(self.campaigns_dir, campaign_name, "GAMEPLAY")
        if not os.path.exists(gameplay_dir) and os.path.isdir(campaign_name):
            gameplay_dir = os.path.join(campaign_name, "GAMEPLAY")
        if not os.path.exists(gameplay_dir):
            return self.load_campaign_state(campaign_name)

        sections = []
        for gfile in ["status.md", "relations.md", "items.md", "upcoming_hooks.md"]:
            path = os.path.join(gameplay_dir, gfile)
            if os.path.exists(path):
                with open(path, "r", encoding="utf-8") as f:
                    sections.append(f"=== GAMEPLAY: {gfile.replace('.md', '').upper()} ===\n{f.read()}")

        if not sections:
            return self.load_campaign_state(campaign_name)

        return "\n\n".join(sections)

    def load_campaign_ideas(self, campaign_name: str, max_chars: int = None) -> str:
        ideas_dir = os.path.join(self.campaigns_dir, campaign_name, "IDEAS")
        if not os.path.exists(ideas_dir) and os.path.isdir(campaign_name):
            ideas_dir = os.path.join(campaign_name, "IDEAS")
        if not os.path.exists(ideas_dir):
            return ""

        sections = []
        for ifile in sorted(glob.glob(os.path.join(ideas_dir, "*.md"))):
            with open(ifile, "r", encoding="utf-8") as f:
                sections.append(f"=== STORY STEERING & IDEAS: {os.path.basename(ifile)} ===\n{f.read()}")
        text = "\n\n".join(sections)
        if max_chars is not None and len(text) > max_chars:
            trunc_msg = "\n... [TRUNCATED DUE TO IDEAS BUDGET]"
            avail = max(0, max_chars - len(trunc_msg))
            cut_idx = text.rfind("\n", 0, avail)
            if cut_idx == -1:
                cut_idx = avail
            text = text[:cut_idx].rstrip() + trunc_msg
        return text

    def load_agent_channel(self, campaign_name: str) -> str:
        channel_path = os.path.join(self.campaigns_dir, campaign_name, "IDEAS", "agent_channel.md")
        if not os.path.exists(channel_path) and os.path.isdir(campaign_name):
            channel_path = os.path.join(campaign_name, "IDEAS", "agent_channel.md")
        if os.path.exists(channel_path):
            with open(channel_path, "r", encoding="utf-8") as f:
                return f"=== INTER-NARRATOR COORDINATION: AGENT_CHANNEL.MD ===\n{f.read()}"
        return ""

    def load_world_bible(self, campaign_name: str, specific_categories: list[str] = None) -> str:
        bible_dir = os.path.join(self.campaigns_dir, campaign_name, "WORLD_BIBLE")
        if not os.path.exists(bible_dir) and os.path.isdir(campaign_name):
            bible_dir = os.path.join(campaign_name, "WORLD_BIBLE")
        if not os.path.exists(bible_dir):
            return ""

        sections = []
        categories = ["CORE", "PLACES", "PEOPLE", "FACTIONS", "LORE", "GUIDES"]
        if specific_categories:
            categories = [c.upper() for c in specific_categories]

        for cat in categories:
            cat_dir = os.path.join(bible_dir, cat)
            if os.path.isdir(cat_dir):
                cat_docs = sorted(glob.glob(os.path.join(cat_dir, "*.md")))
                for doc in cat_docs:
                    name = os.path.splitext(os.path.basename(doc))[0]
                    with open(doc, "r", encoding="utf-8") as f:
                        sections.append(f"=== WORLD BIBLE [{cat}]: {name.upper()} ===\n{f.read()}")

        # Also load root overview if exists
        overview_path = os.path.join(bible_dir, "overview.md")
        if os.path.exists(overview_path) and not specific_categories:
            with open(overview_path, "r", encoding="utf-8") as f:
                sections.insert(0, f"=== WORLD BIBLE [OVERVIEW] ===\n{f.read()}")

        return "\n\n".join(sections)

    def load_campaign_ontology(self, campaign_name: str) -> str:
        candidates = [
            os.path.join(self.campaigns_dir, campaign_name, "ontology.json"),
            os.path.join(self.campaigns_dir, campaign_name, "WORLD_FOUNDATION", "ontology.json"),
        ]
        if os.path.isdir(campaign_name):
            candidates.extend([
                os.path.join(campaign_name, "ontology.json"),
                os.path.join(campaign_name, "WORLD_FOUNDATION", "ontology.json"),
            ])
        ontology_path = next((c for c in candidates if os.path.exists(c)), None)
        if not ontology_path:
            return ""

        try:
            with open(ontology_path, "r", encoding="utf-8") as f:
                data = json.load(f)

            lines = ["=== ACTIVE CAMPAIGN ONTOLOGY & KINSHIP GRAPH (ZERO TOKEN COLLISION) ==="]

            # Disambiguation rules
            rules = data.get("disambiguation_rules", [])
            if rules:
                lines.append("\n## MANDATORY DISAMBIGUATION RULES (PREVENT TOKEN COLLISION)")
                for r in rules:
                    lines.append(f"- **{r.get('rule_id')}**: {r.get('operational_guardrail')}")

            # Characters lookup
            chars = dict(data.get("characters", {}))
            for ent in data.get("entities", []):
                if isinstance(ent, dict) and ent.get("id"):
                    chars.setdefault(ent["id"], ent)

            # Cohort Rosters
            cohorts = data.get("cohort_rosters", {})
            if cohorts:
                lines.append("\n## ACADEMY COHORTS & PEER FORMATIONS")
                for c_id, c in cohorts.items():
                    m_names = []
                    for m_id in c.get("members", []):
                        m_char = chars.get(m_id, {})
                        m_names.append(m_char.get("name", m_id))
                    members_str = ", ".join(m_names)
                    lines.append(f"- **{c.get('cohort_name')}** ({c.get('tactical_doctrine')}): {members_str}")

            # Relational Graph (Kinship, Rivalry, Mentorship, Romance)
            edges = data.get("relational_graph_edges", []) or data.get("relationships", [])
            if edges:
                lines.append("\n## KEY RELATIONAL GRAPH EDGES (KINSHIP, RIVALRY, MENTORSHIP, ROMANCE)")
                for e in edges:
                    src = chars.get(e.get("source"), {}).get("name", e.get("source"))
                    tgt = chars.get(e.get("target"), {}).get("name", e.get("target"))
                    desc = e.get("description") or e.get("context") or ""
                    desc_str = f": {desc}" if desc else ""
                    lines.append(f"- {src} --[{e.get('type')}]--> {tgt}{desc_str}")

            return "\n".join(lines)
        except Exception as e:
            return f"=== ONTOLOGY LOAD ERROR: {str(e)} ==="

    def load_world_foundation(
        self,
        campaign_name: str,
        scene_anchor: Any = None,
        active_conflicts: list = None,
        char_budget: int = None,
        max_chars: int = None,
        filter_relevant: bool = False
    ) -> str:
        """
        Loads world-first foundation specification data and formats it into
        epistemic categories for the system prompt. Canon secrets/mysteries are
        strictly hidden from protagonist view unless flagged as discovered.

        Supports progressive disclosure by filtering factions, NPC knowledge,
        and rumors to those relevant to the current scene_anchor or active conflicts.
        Clamps output gracefully to configured character budget.
        """
        candidates = [
            os.path.join(self.campaigns_dir, campaign_name, "WORLD_FOUNDATION", "world_foundation.json"),
            os.path.join(self.campaigns_dir, campaign_name, "world_foundation.json"),
        ]
        wf_path = None
        for cand in candidates:
            if os.path.exists(cand):
                wf_path = cand
                break

        if not wf_path:
            wf_dir = os.path.join(self.campaigns_dir, campaign_name, "WORLD_FOUNDATION")
            if os.path.isdir(wf_dir):
                jsons = sorted(glob.glob(os.path.join(wf_dir, "*.json")))
                if jsons:
                    wf_path = jsons[0]

        # Support direct directory path passed as campaign_name
        if not wf_path and os.path.isdir(campaign_name):
            direct_candidates = [
                os.path.join(campaign_name, "WORLD_FOUNDATION", "world_foundation.json"),
                os.path.join(campaign_name, "world_foundation.json"),
            ]
            for cand in direct_candidates:
                if os.path.exists(cand):
                    wf_path = cand
                    break

        if not wf_path or not os.path.exists(wf_path):
            return ""

        effective_budget = max_chars if max_chars is not None else char_budget

        try:
            with open(wf_path, "r", encoding="utf-8") as f:
                data = json.load(f)

            # Progressive disclosure relevance filtering
            if scene_anchor is not None or active_conflicts is not None:
                filter_relevant = True

            if filter_relevant and scene_anchor is None and active_conflicts is None:
                status_candidates = [
                    os.path.join(self.campaigns_dir, campaign_name, "GAMEPLAY", "status.json"),
                    os.path.join(campaign_name, "GAMEPLAY", "status.json") if os.path.isdir(campaign_name) else None
                ]
                for sc in status_candidates:
                    if sc and os.path.exists(sc):
                        try:
                            with open(sc, "r", encoding="utf-8") as sf:
                                sdata = json.load(sf)
                            scene_anchor = sdata.get("scene_anchor", {})
                            active_conflicts = sdata.get("pacing_state", {}).get("active_conflicts", [])
                            break
                        except Exception:
                            pass

            should_filter = bool(filter_relevant and (scene_anchor or active_conflicts))

            anchor_lower = ""
            keywords = set()
            if should_filter:
                anchor_parts = []
                if isinstance(scene_anchor, dict):
                    if scene_anchor.get("location"):
                        anchor_parts.append(str(scene_anchor["location"]))
                    if scene_anchor.get("context"):
                        anchor_parts.append(str(scene_anchor["context"]))
                elif scene_anchor:
                    anchor_parts.append(str(scene_anchor))

                if active_conflicts:
                    for c in active_conflicts:
                        if isinstance(c, dict):
                            anchor_parts.extend(str(v) for v in c.values())
                        else:
                            anchor_parts.append(str(c))

                anchor_text = " ".join(anchor_parts)
                anchor_lower = anchor_text.lower()

                stopwords = {
                    "the", "and", "for", "with", "that", "this", "from", "are", "were", "was",
                    "has", "had", "have", "not", "but", "into", "onto", "out", "over", "under",
                    "about", "after", "all", "any", "been", "being", "both", "each", "few",
                    "more", "most", "other", "some", "such", "than", "too", "very", "can",
                    "will", "just", "should", "now"
                }
                tokens = set(re.findall(r'[a-zA-Z0-9_\-]+', anchor_lower))
                keywords = {t for t in tokens if len(t) >= 3 and t not in stopwords}

            def is_text_relevant(text: str) -> bool:
                if not text:
                    return False
                t_low = text.lower()
                t_tokens = set(re.findall(r'[a-zA-Z0-9_\-]+', t_low))
                if keywords & t_tokens:
                    return True
                for kw in keywords:
                    if len(kw) >= 4 and kw in t_low:
                        return True
                return False

            def is_faction_relevant(fac: Any) -> bool:
                if not should_filter:
                    return True
                if not isinstance(fac, dict):
                    return is_text_relevant(str(fac))
                f_id = str(fac.get("id", "")).lower()
                f_name = str(fac.get("name", "")).lower()
                if f_id and (f_id in anchor_lower or any(kw in f_id for kw in keywords if len(kw) >= 4)):
                    return True
                if f_name and (f_name in anchor_lower or any(kw in f_name for kw in keywords if len(kw) >= 4)):
                    return True
                if is_text_relevant(fac.get("agenda", "")):
                    return True
                for obj in fac.get("objectives", []):
                    if is_text_relevant(str(obj)):
                        return True
                for t in fac.get("tensions", []):
                    if isinstance(t, dict):
                        if is_text_relevant(str(t.get("target_entity", ""))) or is_text_relevant(str(t.get("source_of_friction", ""))):
                            return True
                    elif is_text_relevant(str(t)):
                        return True
                return False

            def is_npc_relevant(n_id: str, kn_data: Any) -> bool:
                if not should_filter:
                    return True
                n_low = n_id.lower()
                if n_low in anchor_lower or any(kw in n_low for kw in keywords if len(kw) >= 4):
                    return True
                if isinstance(kn_data, dict):
                    for k_item in kn_data.get("knows", []):
                        if is_text_relevant(str(k_item)):
                            return True
                    for dk_item in kn_data.get("does_not_know", []):
                        if is_text_relevant(str(dk_item)):
                            return True
                    for fb_item in kn_data.get("falsely_believes", []):
                        if is_text_relevant(str(fb_item)):
                            return True
                elif is_text_relevant(str(kn_data)):
                    return True
                return False

            def is_rumor_relevant(rum: Any) -> bool:
                if not should_filter:
                    return True
                if isinstance(rum, dict):
                    r_id = str(rum.get("id", "")).lower()
                    if r_id and r_id in anchor_lower:
                        return True
                    if is_text_relevant(str(rum.get("claim", ""))):
                        return True
                    if is_text_relevant(str(rum.get("believed_by", ""))):
                        return True
                    if is_text_relevant(str(rum.get("origin", ""))):
                        return True
                elif is_text_relevant(str(rum)):
                    return True
                return False

            lines = ["=== WORLD FOUNDATION & EPISTEMIC SEPARATION ==="]

            # 1. Immutable Facts (Core: ALWAYS INCLUDED)
            immutable_facts = data.get("immutable_facts", [])
            if immutable_facts:
                lines.append("\n## 1. IMMUTABLE FACTS (UNALTERABLE GROUND TRUTHS)")
                for fact in immutable_facts:
                    if isinstance(fact, dict):
                        cat = fact.get("category", "General").upper()
                        stmt = fact.get("statement") or fact.get("fact") or fact.get("description", "")
                        f_id = fact.get("id")
                        prefix = f"[{f_id}] [{cat}]" if f_id else f"[{cat}]"
                        lines.append(f"- {prefix}: {stmt}")
                    else:
                        lines.append(f"- {fact}")

            # 2. Mutable World State (Core: ALWAYS INCLUDED)
            mutable_state = data.get("mutable_world_state", {})
            if mutable_state:
                lines.append("\n## 2. MUTABLE WORLD STATE (DYNAMIC GEOPOLITICAL & ENVIRONMENTAL STATE)")
                if isinstance(mutable_state, dict):
                    if "active_epoch" in mutable_state:
                        lines.append(f"- Active Epoch/Climate: {mutable_state['active_epoch']}")
                    if "factions_control" in mutable_state and isinstance(mutable_state["factions_control"], dict):
                        lines.append("- Faction Territorial & Administrative Control:")
                        for entity, ctrl in mutable_state["factions_control"].items():
                            lines.append(f"  * {entity}: {ctrl}")
                    if "resource_distribution" in mutable_state and isinstance(mutable_state["resource_distribution"], dict):
                        lines.append("- Resource Distribution & Scarcity:")
                        for res, dist in mutable_state["resource_distribution"].items():
                            lines.append(f"  * {res}: {dist}")
                    if "global_tensions_index" in mutable_state:
                        lines.append(f"- Global Tensions Index: {mutable_state['global_tensions_index']}")
                    if "dynamic_flags" in mutable_state and isinstance(mutable_state["dynamic_flags"], dict):
                        lines.append("- Dynamic World Flags:")
                        for k, v in mutable_state["dynamic_flags"].items():
                            lines.append(f"  * {k}: {v}")
                else:
                    lines.append(f"- {mutable_state}")

            # 3. Factions & Tensions (Progressive Disclosure)
            all_factions = data.get("factions_and_tensions", [])
            factions = [f for f in all_factions if is_faction_relevant(f)]
            if factions:
                lines.append("\n## 3. INDEPENDENT FACTIONS & ACTIVE TENSIONS")
                for fac in factions:
                    if isinstance(fac, dict):
                        fac_name = fac.get("name", fac.get("id", "Unknown Faction"))
                        agenda = fac.get("agenda", "")
                        lines.append(f"- **{fac_name}**" + (f" ({agenda})" if agenda else ""))
                        objs = fac.get("objectives", [])
                        if objs:
                            lines.append(f"  * Autonomous Objectives: {'; '.join(objs)}")
                        tens = fac.get("tensions", [])
                        if tens:
                            for t in tens:
                                if isinstance(t, dict):
                                    tgt = t.get("target_entity") or t.get("target_faction_or_entity", "Unknown Target")
                                    fric = t.get("source_of_friction", "")
                                    intens = t.get("intensity", "unspecified")
                                    lines.append(f"  * Tension with {tgt} [{intens}]: {fric}")
                                else:
                                    lines.append(f"  * Tension: {t}")
                    else:
                        lines.append(f"- {fac}")

            # 4. NPC Epistemic Knowledge Map (Progressive Disclosure)
            all_npc_kn = data.get("npc_knowledge", {})
            if isinstance(all_npc_kn, dict):
                npc_kn = {n: k for n, k in all_npc_kn.items() if is_npc_relevant(n, k)}
            elif isinstance(all_npc_kn, list):
                npc_kn = [item for item in all_npc_kn if is_text_relevant(str(item))]
            else:
                npc_kn = all_npc_kn

            if npc_kn:
                lines.append("\n## 4. NPC EPISTEMIC KNOWLEDGE MAP (BOUNDARIES & MISCONCEPTIONS)")
                if isinstance(npc_kn, dict):
                    for npc_id, kn in npc_kn.items():
                        lines.append(f"- **{npc_id}**:")
                        if isinstance(kn, dict):
                            knows = kn.get("knows", [])
                            does_not_know = kn.get("does_not_know", [])
                            falsely_believes = kn.get("falsely_believes", [])
                            lines.append(f"  * Verified Known Truths: {', '.join(knows) if knows else 'None'}")
                            lines.append(f"  * Ignorant Of (Does NOT Know): {', '.join(does_not_know) if does_not_know else 'None'}")
                            lines.append(f"  * False Beliefs (Misconceptions): {', '.join(falsely_believes) if falsely_believes else 'None'}")
                        else:
                            lines.append(f"  * Knowledge: {kn}")
                elif isinstance(npc_kn, list):
                    for item in npc_kn:
                        lines.append(f"- {item}")

            # 5. Rumors & Beliefs (Progressive Disclosure)
            all_rumors = data.get("rumors_and_beliefs", [])
            rumors = [r for r in all_rumors if is_rumor_relevant(r)]
            if rumors:
                lines.append("\n## 5. RUMORS, FOLKTALES & SUBJECTIVE BELIEFS")
                for rum in rumors:
                    if isinstance(rum, dict):
                        claim = rum.get("claim", "")
                        believed_by = rum.get("believed_by", "Common Lore")
                        veracity = rum.get("veracity", "unverified")
                        lines.append(f"- \"{claim}\" (Believed by: {believed_by} | Veracity: {veracity})")
                    else:
                        lines.append(f"- {rum}")

            # 6. Unresolved Mysteries (Hidden from protagonist view unless discovered)
            mysteries = data.get("unresolved_mysteries", [])
            if mysteries:
                lines.append("\n## 6. CANON SECRETS & UNRESOLVED MYSTERIES")
                for myst in mysteries:
                    if isinstance(myst, dict):
                        m_title = myst.get("title", myst.get("id", "Secret"))
                        m_truth = myst.get("secret_truth") or myst.get("truth") or myst.get("description", "")
                        discovered = bool(myst.get("discovered", False))
                        cond = myst.get("discovery_conditions", "In-world investigation required")
                        if discovered:
                            lines.append(f"- [DISCOVERED] **{m_title}**: {m_truth}")
                        else:
                            lines.append(f"- [HIDDEN FROM PROTAGONIST VIEW - CANON SECRET] **{m_title}**: {m_truth} (Discovery condition: {cond})")
                    else:
                        lines.append(f"- [HIDDEN FROM PROTAGONIST VIEW - CANON SECRET] {myst}")

            rendered_text = "\n".join(lines)

            # Budget clamping
            if effective_budget is not None and len(rendered_text) > effective_budget:
                trunc_msg = "\n... [TRUNCATED DUE TO WORLD FOUNDATION BUDGET]"
                avail = max(0, effective_budget - len(trunc_msg))
                cut_idx = rendered_text.rfind("\n", 0, avail)
                if cut_idx == -1:
                    cut_idx = avail
                rendered_text = rendered_text[:cut_idx].rstrip() + trunc_msg

            return rendered_text
        except Exception as e:
            return f"=== WORLD FOUNDATION LOAD ERROR: {str(e)} ==="

    def build_static_prefix(
        self,
        campaign_name: str,
        active_topics: list[str] = None,
        query: str = None,
        retrieval_enabled: bool = None,
        scene_anchor: Any = None,
        active_conflicts: list = None,
        token_budget: dict = None,
        filter_relevant: bool = False
    ) -> str:
        """
        Builds a deterministic, byte-stable static prefix for Prompt Caching (KV-cache).
        Consists of Core Codex Rules + Campaign Style Contract & Directives +
        Ontology + Immutable World Foundation Facts + Relevant Lore.
        """
        budget_cfg = self._resolve_budget(campaign_name, token_budget)
        rules_budget = budget_cfg.get("rules_char_budget")
        wf_budget = budget_cfg.get("world_foundation_char_budget")
        if budget_cfg.get("progressive_disclosure"):
            filter_relevant = True

        global_rules = self.load_global_rules(max_chars=rules_budget)
        campaign_directives = self.load_campaign_agents_directives(campaign_name)
        campaign_config = self.load_campaign_config(campaign_name)
        campaign_ontology = self.load_campaign_ontology(campaign_name)

        world_foundation = self.load_world_foundation(
            campaign_name,
            scene_anchor=scene_anchor,
            active_conflicts=active_conflicts,
            char_budget=wf_budget,
            filter_relevant=filter_relevant
        )

        # Determine retrieval mode
        retrieval_cfg = self.get_campaign_retrieval_config(campaign_name)
        should_use_retrieval = (
            retrieval_enabled
            if retrieval_enabled is not None
            else retrieval_cfg.get("enabled", False)
        )

        world_lore = ""
        if should_use_retrieval and HybridRetriever is not None:
            retriever = self.get_retriever(campaign_name, retrieval_cfg)
            if retriever:
                search_query = query or ""
                if not search_query and active_topics:
                    search_query = " ".join(active_topics)
                if not search_query:
                    # Construct default query from active gameplay status coordinates
                    status_path = os.path.join(self.campaigns_dir, campaign_name, "GAMEPLAY", "status.json")
                    if not os.path.exists(status_path) and os.path.isdir(campaign_name):
                        status_path = os.path.join(campaign_name, "GAMEPLAY", "status.json")
                    if os.path.exists(status_path):
                        try:
                            with open(status_path, "r", encoding="utf-8") as f:
                                sdata = json.load(f)
                            loc = sdata.get("scene_anchor", {}).get("location", "")
                            ctx = sdata.get("scene_anchor", {}).get("context", "")
                            obj = sdata.get("pacing_state", {}).get("scene_objective", "")
                            search_query = f"{loc} {ctx} {obj}".strip()
                        except Exception:
                            pass

                char_budget = retrieval_cfg.get("char_budget", 16000)
                max_passages = retrieval_cfg.get("max_passages", 5)
                world_lore = retriever.retrieve_formatted(
                    query=search_query,
                    max_passages=max_passages,
                    char_budget=char_budget,
                    category_filter=active_topics
                )

        if not world_lore:
            world_lore = self.load_world_bible(campaign_name, active_topics)

        parts = [
            "You are the Game Master, Rules Arbiter, and World Simulator for a Choice-driven RPG engine.\n\n"
            "# 1. GLOBAL SYSTEM CONSTRAINTS (AUTHORITATIVE & IMMUTABLE)\n"
            f"{global_rules}"
        ]

        if campaign_directives:
            parts.append(f"# 2.1 CAMPAIGN-SPECIFIC DIRECTIVES & PROGRESSION DOCTRINE\n{campaign_directives}")

        if campaign_config:
            parts.append(f"# 2.2 CAMPAIGN METRICS & CONFIGURATION\n{campaign_config}")

        if campaign_ontology:
            parts.append(f"# 3. ONTOLOGY, KINSHIP & DISAMBIGUATION RULES\n{campaign_ontology}")

        if world_foundation:
            parts.append(f"# 3.1 WORLD FOUNDATION & EPISTEMIC BOUNDARIES\n{world_foundation}")

        if world_lore:
            parts.append(f"# 4. WORLD BIBLE & RELEVANT LORE\n{world_lore}")

        return "\n\n".join(parts) + "\n\n"

    def build_dynamic_suffix(
        self,
        campaign_name: str,
        calibration_advisory: str = None,
        action: str = None,
        turn: int = None,
        token_budget: dict = None
    ) -> str:
        """
        Builds dynamic turn context:
        Recent Turns + Gameplay Status + Dynamic Ideas + Calibration Advisory + Current Turn Action.
        """
        budget_cfg = self._resolve_budget(campaign_name, token_budget)
        turns_budget = budget_cfg.get("active_turns_budget")
        ideas_budget = budget_cfg.get("ideas_char_budget")

        campaign_dir = os.path.join(self.campaigns_dir, campaign_name)
        if not os.path.exists(campaign_dir) and os.path.isdir(campaign_name):
            campaign_dir = campaign_name

        active_turns = load_active_turns(campaign_dir)
        if active_turns and turns_budget is not None and turns_budget > 0:
            active_turns = active_turns[-turns_budget:]

        turns_text = ""
        if active_turns:
            turn_blocks = [f"=== RECENT TURN: {t['file']} ===\n{t['content']}" for t in active_turns]
            turns_text = "# 6. RECENT TURNS & IMMEDIATE HISTORY (ROLLING BUFFER)\n" + "\n\n".join(turn_blocks)

        campaign_gameplay = self.load_campaign_gameplay(campaign_name)
        narrative_ideas = self.load_campaign_ideas(campaign_name, max_chars=ideas_budget)

        if calibration_advisory is None:
            try:
                from ENGINE.calibration import get_calibration_advisory
                adv = get_calibration_advisory(self.root_dir, campaign_name)
                calibration_advisory = adv.advisory_prompt
            except Exception:
                try:
                    from calibration import get_calibration_advisory
                    adv = get_calibration_advisory(self.root_dir, campaign_name)
                    calibration_advisory = adv.advisory_prompt
                except Exception:
                    calibration_advisory = ""

        advisory_section = ""
        if calibration_advisory:
            advisory_section = f"# 1.1 DYNAMIC AGENT CALIBRATION ADVISORY (SELF-CORRECTION DIRECTIVES)\n{calibration_advisory}"

        parts = []
        if turns_text:
            parts.append(turns_text)
        if campaign_gameplay:
            parts.append(f"# 2. ACTIVE CAMPAIGN GAMEPLAY & STATE\n{campaign_gameplay}")
        if narrative_ideas:
            parts.append(f"# 5. STORY STEERING & NARRATIVE SEEDS\n{narrative_ideas}")
        if advisory_section:
            parts.append(advisory_section)
        if action:
            turn_str = f" (Turn {turn})" if turn is not None else ""
            parts.append(f"# 7. CURRENT TURN ACTION{turn_str}\nPlayer Action: {action}")

        return "\n\n".join(parts) + "\n" if parts else ""

    def build_system_prompt(
        self,
        campaign_name: str,
        active_topics: list[str] = None,
        query: str = None,
        retrieval_enabled: bool = None,
        calibration_advisory: str = None,
        action: str = None,
        turn: int = None,
        scene_anchor: Any = None,
        active_conflicts: list = None,
        token_budget: dict = None,
        filter_relevant: bool = False
    ) -> str:
        static_prefix = self.build_static_prefix(
            campaign_name=campaign_name,
            active_topics=active_topics,
            query=query,
            retrieval_enabled=retrieval_enabled,
            scene_anchor=scene_anchor,
            active_conflicts=active_conflicts,
            token_budget=token_budget,
            filter_relevant=filter_relevant
        )
        dynamic_suffix = self.build_dynamic_suffix(
            campaign_name=campaign_name,
            calibration_advisory=calibration_advisory,
            action=action,
            turn=turn,
            token_budget=token_budget
        )
        return static_prefix + dynamic_suffix


def assemble_prompt(
    campaign_name: str,
    root_dir: str = ".",
    query: str = None,
    retrieval_enabled: bool = None,
    calibration_advisory: str = None,
    action: str = None,
    turn: int = None,
    scene_anchor: Any = None,
    active_conflicts: list = None,
    token_budget: dict = None,
    active_topics: list[str] = None,
    filter_relevant: bool = False
) -> str:
    assembler = PromptAssembler(root_dir)
    return assembler.build_system_prompt(
        campaign_name,
        active_topics=active_topics,
        query=query,
        retrieval_enabled=retrieval_enabled,
        calibration_advisory=calibration_advisory,
        action=action,
        turn=turn,
        scene_anchor=scene_anchor,
        active_conflicts=active_conflicts,
        token_budget=token_budget,
        filter_relevant=filter_relevant
    )

