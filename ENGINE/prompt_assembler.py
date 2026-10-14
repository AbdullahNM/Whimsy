import os
import glob
import json
try:
    from ENGINE.turn_archiver import load_active_turns
except ImportError:
    from turn_archiver import load_active_turns

class PromptAssembler:
    def __init__(self, root_dir: str):
        self.root_dir = root_dir
        self.global_dir = os.path.join(root_dir, "GLOBAL")
        self.campaigns_dir = os.path.join(root_dir, "CAMPAIGNS")

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

    def build_system_prompt(self, campaign_name: str, active_topics: list[str] = None) -> str:
        global_rules = self.load_global_rules()
        campaign_gameplay = self.load_campaign_gameplay(campaign_name)
        campaign_ontology = self.load_campaign_ontology(campaign_name)
        world_lore = self.load_world_bible(campaign_name, active_topics)
        narrative_ideas = self.load_campaign_ideas(campaign_name)

        # Load active turns
        campaign_dir = os.path.join(self.campaigns_dir, campaign_name)
        active_turns = load_active_turns(campaign_dir)
        turns_text = ""
        if active_turns:
            turn_blocks = [f"=== RECENT TURN: {t['file']} ===\n{t['content']}" for t in active_turns]
            turns_text = "\n\n# 6. RECENT TURNS & IMMEDIATE HISTORY (ROLLING BUFFER)\n" + "\n\n".join(turn_blocks)

        ontology_section = ""
        if campaign_ontology:
            ontology_section = f"# 3. ONTOLOGY, KINSHIP & DISAMBIGUATION RULES\n{campaign_ontology}\n\n"

        return (
            "You are the Game Master, Rules Arbiter, and World Simulator for a Choice-driven RPG engine.\n\n"
            "# 1. GLOBAL SYSTEM CONSTRAINTS (AUTHORITATIVE & IMMUTABLE)\n"
            f"{global_rules}\n\n"
            "# 2. ACTIVE CAMPAIGN GAMEPLAY & STATE\n"
            f"{campaign_gameplay}\n\n"
            f"{ontology_section}"
            "# 4. WORLD BIBLE & RELEVANT LORE\n"
            f"{world_lore}\n\n"
            "# 5. STORY STEERING & NARRATIVE SEEDS\n"
            f"{narrative_ideas}"
            f"{turns_text}\n"
        )


def assemble_prompt(campaign_name: str, root_dir: str = ".") -> str:
    assembler = PromptAssembler(root_dir)
    return assembler.build_system_prompt(campaign_name)

