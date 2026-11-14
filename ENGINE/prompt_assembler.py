import os
import glob
import json
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
    def __init__(self, root_dir: str):
        self.root_dir = root_dir
        self.global_dir = os.path.join(root_dir, "GLOBAL")
        self.campaigns_dir = os.path.join(root_dir, "CAMPAIGNS")
        self._retrievers = {}

    def load_global_rules(self) -> str:
        rule_files = sorted(glob.glob(os.path.join(self.global_dir, "CORE-*.md")))
        contents = []
        for rf in rule_files:
            with open(rf, "r", encoding="utf-8") as f:
                contents.append(f"=== {os.path.basename(rf)} ===\n{f.read()}")
        return "\n\n".join(contents)

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

    def load_campaign_ideas(self, campaign_name: str) -> str:
        ideas_dir = os.path.join(self.campaigns_dir, campaign_name, "IDEAS")
        if not os.path.exists(ideas_dir):
            return ""

        sections = []
        for ifile in sorted(glob.glob(os.path.join(ideas_dir, "*.md"))):
            with open(ifile, "r", encoding="utf-8") as f:
                sections.append(f"=== STORY STEERING & IDEAS: {os.path.basename(ifile)} ===\n{f.read()}")
        return "\n\n".join(sections)

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
        ontology_path = os.path.join(self.campaigns_dir, campaign_name, "ontology.json")
        if not os.path.exists(ontology_path):
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
            chars = data.get("characters", {})

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
            edges = data.get("relational_graph_edges", [])
            if edges:
                lines.append("\n## KEY RELATIONAL GRAPH EDGES (KINSHIP, RIVALRY, MENTORSHIP, ROMANCE)")
                for e in edges:
                    src = chars.get(e.get("source"), {}).get("name", e.get("source"))
                    tgt = chars.get(e.get("target"), {}).get("name", e.get("target"))
                    lines.append(f"- {src} --[{e.get('type')}]--> {tgt}: {e.get('description')}")

            return "\n".join(lines)
        except Exception as e:
            return f"=== ONTOLOGY LOAD ERROR: {str(e)} ==="

    def load_world_foundation(self, campaign_name: str) -> str:
        """
        Loads world-first foundation specification data and formats it into
        epistemic categories for the system prompt. Canon secrets/mysteries are
        strictly hidden from protagonist view unless flagged as discovered.
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

        try:
            with open(wf_path, "r", encoding="utf-8") as f:
                data = json.load(f)

            lines = ["=== WORLD FOUNDATION & EPISTEMIC SEPARATION ==="]

            # 1. Immutable Facts
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

            # 2. Mutable World State
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

            # 3. Factions & Tensions
            factions = data.get("factions_and_tensions", [])
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

            # 4. NPC Epistemic Knowledge Map
            npc_kn = data.get("npc_knowledge", {})
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

            # 5. Rumors & Beliefs
            rumors = data.get("rumors_and_beliefs", [])
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

            return "\n".join(lines)
        except Exception as e:
            return f"=== WORLD FOUNDATION LOAD ERROR: {str(e)} ==="

    def build_system_prompt(
        self,
        campaign_name: str,
        active_topics: list[str] = None,
        query: str = None,
        retrieval_enabled: bool = None
    ) -> str:
        global_rules = self.load_global_rules()
        campaign_gameplay = self.load_campaign_gameplay(campaign_name)
        campaign_directives = self.load_campaign_agents_directives(campaign_name)
        campaign_config = self.load_campaign_config(campaign_name)
        campaign_ontology = self.load_campaign_ontology(campaign_name)
        world_foundation = self.load_world_foundation(campaign_name)

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

        narrative_ideas = self.load_campaign_ideas(campaign_name)

        # Load active turns
        campaign_dir = os.path.join(self.campaigns_dir, campaign_name)
        active_turns = load_active_turns(campaign_dir)
        turns_text = ""
        if active_turns:
            turn_blocks = [f"=== RECENT TURN: {t['file']} ===\n{t['content']}" for t in active_turns]
            turns_text = "\n\n# 6. RECENT TURNS & IMMEDIATE HISTORY (ROLLING BUFFER)\n" + "\n\n".join(turn_blocks)

        directives_section = ""
        if campaign_directives:
            directives_section = f"# 2.1 CAMPAIGN-SPECIFIC DIRECTIVES & PROGRESSION DOCTRINE\n{campaign_directives}\n\n"

        config_section = ""
        if campaign_config:
            config_section = f"# 2.2 CAMPAIGN METRICS & CONFIGURATION\n{campaign_config}\n\n"

        ontology_section = ""
        if campaign_ontology:
            ontology_section = f"# 3. ONTOLOGY, KINSHIP & DISAMBIGUATION RULES\n{campaign_ontology}\n\n"

        foundation_section = ""
        if world_foundation:
            foundation_section = f"# 3.1 WORLD FOUNDATION & EPISTEMIC BOUNDARIES\n{world_foundation}\n\n"

        return (
            "You are the Game Master, Rules Arbiter, and World Simulator for a Choice-driven RPG engine.\n\n"
            "# 1. GLOBAL SYSTEM CONSTRAINTS (AUTHORITATIVE & IMMUTABLE)\n"
            f"{global_rules}\n\n"
            "# 2. ACTIVE CAMPAIGN GAMEPLAY & STATE\n"
            f"{campaign_gameplay}\n\n"
            f"{directives_section}"
            f"{config_section}"
            f"{ontology_section}"
            f"{foundation_section}"
            "# 4. WORLD BIBLE & RELEVANT LORE\n"
            f"{world_lore}\n\n"
            "# 5. STORY STEERING & NARRATIVE SEEDS\n"
            f"{narrative_ideas}"
            f"{turns_text}\n"
        )


def assemble_prompt(
    campaign_name: str,
    root_dir: str = ".",
    query: str = None,
    retrieval_enabled: bool = None
) -> str:
    assembler = PromptAssembler(root_dir)
    return assembler.build_system_prompt(
        campaign_name,
        query=query,
        retrieval_enabled=retrieval_enabled
    )
