#!/usr/bin/env python3
"""
World Bible & Entity Graph for Whimsy campaign retrieval.
Extracts entities, wikilinks, cross-references, ontology relations, and gameplay status.
Supports k-hop graph traversal from active scene anchors.
Standard library only: zero heavy external dependencies.
"""

import os
import re
import glob
import json
from collections import deque
from dataclasses import dataclass, field
from typing import Optional, List, Dict, Set, Tuple, Any

from .bm25 import Document, tokenize


def normalize_id(text: str) -> str:
    """Normalizes an entity name into a clean unique identifier."""
    if not text:
        return ""
    # Lowercase, replace non-alphanumeric with underscore, collapse underscores
    cleaned = re.sub(r"[^a-z0-9]+", "_", text.strip().lower())
    return cleaned.strip("_")


@dataclass
class EntityNode:
    """Represents an entity, location, character, faction, or passage in the campaign graph."""
    id: str
    name: str
    type: str  # "location", "character", "faction", "item", "concept", "fact", "document"
    category: str  # "PLACES", "PEOPLE", "FACTIONS", "GAMEPLAY", "ONTOLOGY", "WORLD_FOUNDATION", etc.
    doc_ids: List[str] = field(default_factory=list)
    metadata: Dict[str, Any] = field(default_factory=dict)


@dataclass
class EntityEdge:
    """Represents a directional or bidirectional relationship between two nodes."""
    source: str
    target: str
    edge_type: str  # "wikilink", "mentions", "located_in", "allied_with", "tension_with", "member_of", "contact_of", etc.
    weight: float = 1.0
    metadata: Dict[str, Any] = field(default_factory=dict)


class EntityGraph:
    """
    World Bible & Entity Graph.
    Constructs and maintains knowledge graph of all campaign entities and relations.
    """
    def __init__(self):
        self.nodes: Dict[str, EntityNode] = {}
        self.edges: Dict[str, List[EntityEdge]] = {}
        self.incoming_edges: Dict[str, List[EntityEdge]] = {}
        self._name_to_id: Dict[str, str] = {}

    def add_node(self, node: EntityNode) -> EntityNode:
        if node.id in self.nodes:
            existing = self.nodes[node.id]
            # Merge doc_ids and metadata
            for did in node.doc_ids:
                if did not in existing.doc_ids:
                    existing.doc_ids.append(did)
            existing.metadata.update(node.metadata)
            if not existing.category and node.category:
                existing.category = node.category
            return existing

        self.nodes[node.id] = node
        self.edges[node.id] = []
        self.incoming_edges[node.id] = []
        self._name_to_id[node.name.lower()] = node.id
        return node

    def add_edge(self, edge: EntityEdge, bidirectional: bool = True) -> None:
        if edge.source not in self.nodes or edge.target not in self.nodes:
            return

        # Check for duplicate or stronger existing edge
        for existing in self.edges[edge.source]:
            if existing.target == edge.target:
                if existing.edge_type == edge.edge_type:
                    return
                # If existing is a wikilink (stronger), don't overwrite with mentions
                if existing.edge_type == "wikilink" and edge.edge_type == "mentions":
                    return

        self.edges[edge.source].append(edge)
        self.incoming_edges[edge.target].append(edge)

        if bidirectional:
            reverse_edge = EntityEdge(
                source=edge.target,
                target=edge.source,
                edge_type=edge.edge_type,
                weight=edge.weight,
                metadata=edge.metadata
            )
            for existing in self.edges[edge.target]:
                if existing.target == edge.source:
                    if existing.edge_type == edge.edge_type:
                        return
                    if existing.edge_type == "wikilink" and edge.edge_type == "mentions":
                        return
            self.edges[edge.target].append(reverse_edge)
            self.incoming_edges[edge.source].append(reverse_edge)

    def get_node(self, node_id: str) -> Optional[EntityNode]:
        return self.nodes.get(node_id)

    def find_node(self, query: str) -> Optional[EntityNode]:
        """Resolves node by normalized id, exact name, or partial match."""
        if not query:
            return None

        # 1. Exact normalized id
        nid = normalize_id(query)
        if nid in self.nodes:
            return self.nodes[nid]

        # 2. Exact lowercase name
        q_lower = query.strip().lower()
        if q_lower in self._name_to_id:
            return self.nodes[self._name_to_id[q_lower]]

        # 3. Check aliases in metadata
        for node in self.nodes.values():
            aliases = [a.lower() for a in node.metadata.get("aliases", [])]
            if q_lower in aliases:
                return node

        # 4. Substring match against names
        for node in self.nodes.values():
            if q_lower in node.name.lower() or node.name.lower() in q_lower:
                return node

        return None

    def find_nodes_by_type(self, node_type: str) -> List[EntityNode]:
        return [n for n in self.nodes.values() if n.type == node_type]

    def find_nodes_by_category(self, category: str) -> List[EntityNode]:
        return [n for n in self.nodes.values() if n.category.upper() == category.upper()]

    # --- Campaign Construction ---

    def build_from_campaign(self, campaign_dir: str, documents: Optional[List[Document]] = None) -> None:
        """Constructs graph from ontology, world foundation, gameplay state, and world bible."""
        # 1. Active Campaign Ontology (ontology.json)
        self._load_ontology(campaign_dir)

        # 2. World Foundation (world_foundation.json)
        self._load_world_foundation(campaign_dir)

        # 3. Gameplay State & Relations (GAMEPLAY/)
        self._load_gameplay_state(campaign_dir)

        # 4. World Bible Entities & Documents
        self._load_world_bible(campaign_dir, documents)

        # 5. Wikilinks & Cross-reference Extraction
        self._extract_wikilinks_and_cross_references(campaign_dir, documents)

    def _load_ontology(self, campaign_dir: str) -> None:
        ont_path = os.path.join(campaign_dir, "ontology.json")
        if not os.path.exists(ont_path):
            return

        try:
            with open(ont_path, "r", encoding="utf-8") as f:
                data = json.load(f)
        except Exception:
            return

        chars = data.get("characters", {})
        for cid, char in chars.items():
            name = char.get("name", cid)
            node = EntityNode(
                id=normalize_id(cid),
                name=name,
                type="character",
                category="ONTOLOGY",
                metadata={"archetype": char.get("archetype"), "origin": char.get("origin")}
            )
            self.add_node(node)

        cohorts = data.get("cohort_rosters", {})
        for coh_id, coh in cohorts.items():
            coh_name = coh.get("cohort_name", coh_id)
            c_node = EntityNode(
                id=normalize_id(coh_id),
                name=coh_name,
                type="cohort",
                category="ONTOLOGY",
                metadata={"tactical_doctrine": coh.get("tactical_doctrine")}
            )
            self.add_node(c_node)
            for m_id in coh.get("members", []):
                m_node_id = normalize_id(m_id)
                if m_node_id in self.nodes:
                    self.add_edge(EntityEdge(
                        source=m_node_id,
                        target=c_node.id,
                        edge_type="member_of",
                        weight=1.0
                    ))

        # Relational Graph Edges
        for edge_data in data.get("relational_graph_edges", []):
            src = normalize_id(edge_data.get("source", ""))
            tgt = normalize_id(edge_data.get("target", ""))
            etype = edge_data.get("type", "related_to")
            desc = edge_data.get("description", "")
            if src in self.nodes and tgt in self.nodes:
                self.add_edge(EntityEdge(
                    source=src,
                    target=tgt,
                    edge_type=etype,
                    weight=1.0,
                    metadata={"description": desc}
                ))

    def _load_world_foundation(self, campaign_dir: str) -> None:
        candidates = [
            os.path.join(campaign_dir, "WORLD_FOUNDATION", "world_foundation.json"),
            os.path.join(campaign_dir, "world_foundation.json")
        ]
        wf_path = next((c for c in candidates if os.path.exists(c)), None)
        if not wf_path:
            return

        try:
            with open(wf_path, "r", encoding="utf-8") as f:
                data = json.load(f)
        except Exception:
            return

        # Factions
        for fac in data.get("factions_and_tensions", []):
            if isinstance(fac, dict):
                f_id = normalize_id(fac.get("id", fac.get("name", "")))
                name = fac.get("name", f_id)
                f_node = EntityNode(
                    id=f_id,
                    name=name,
                    type="faction",
                    category="FACTIONS",
                    metadata={"agenda": fac.get("agenda", "")}
                )
                self.add_node(f_node)

                for t in fac.get("tensions", []):
                    if isinstance(t, dict):
                        tgt_name = t.get("target_entity") or t.get("target_faction_or_entity", "")
                        tgt_id = normalize_id(tgt_name)
                        if tgt_id in self.nodes:
                            self.add_edge(EntityEdge(
                                source=f_id,
                                target=tgt_id,
                                edge_type="tension_with",
                                weight=0.9,
                                metadata={"intensity": t.get("intensity", "")}
                            ))

        # NPC Knowledge
        npc_kn = data.get("npc_knowledge", {})
        if isinstance(npc_kn, dict):
            for npc_id in npc_kn.keys():
                n_id = normalize_id(npc_id)
                if n_id not in self.nodes:
                    self.add_node(EntityNode(
                        id=n_id,
                        name=npc_id.replace("_", " ").title(),
                        type="character",
                        category="PEOPLE"
                    ))

    def _load_gameplay_state(self, campaign_dir: str) -> None:
        status_path = os.path.join(campaign_dir, "GAMEPLAY", "status.json")
        protagonist_node = None
        if os.path.exists(status_path):
            try:
                with open(status_path, "r", encoding="utf-8") as f:
                    status_data = json.load(f)

                # Protagonist character
                char_info = status_data.get("character", {})
                c_name = char_info.get("name", "Protagonist")
                c_id = normalize_id(c_name)
                protagonist_node = self.add_node(EntityNode(
                    id=c_id,
                    name=c_name,
                    type="character",
                    category="GAMEPLAY",
                    metadata={"archetype": char_info.get("archetype")}
                ))

                # Scene Anchor Location
                scene_anchor = status_data.get("scene_anchor", {})
                loc_name = scene_anchor.get("location")
                if loc_name:
                    loc_id = normalize_id(loc_name)
                    loc_node = self.add_node(EntityNode(
                        id=loc_id,
                        name=loc_name,
                        type="location",
                        category="PLACES"
                    ))
                    self.add_edge(EntityEdge(
                        source=protagonist_node.id,
                        target=loc_node.id,
                        edge_type="located_in",
                        weight=1.0
                    ))

            except Exception:
                pass

        # Relations
        relations_path = os.path.join(campaign_dir, "GAMEPLAY", "relations.json")
        if os.path.exists(relations_path):
            try:
                with open(relations_path, "r", encoding="utf-8") as f:
                    rel_data = json.load(f)
                contacts = rel_data.get("contacts", [])
                for ct in contacts:
                    cname = ct.get("name")
                    if cname:
                        cid = normalize_id(cname)
                        cnode = self.add_node(EntityNode(
                            id=cid,
                            name=cname,
                            type="character",
                            category="PEOPLE",
                            metadata={"role": ct.get("role", "")}
                        ))
                        if protagonist_node:
                            self.add_edge(EntityEdge(
                                source=protagonist_node.id,
                                target=cnode.id,
                                edge_type="contact_of",
                                weight=0.8
                            ))
            except Exception:
                pass
        else:
            # Markdown fallback for relations.md
            rel_md = os.path.join(campaign_dir, "GAMEPLAY", "relations.md")
            if os.path.exists(rel_md):
                try:
                    with open(rel_md, "r", encoding="utf-8") as f:
                        text = f.read()
                    # Look for `- **Name** — Role...`
                    matches = re.findall(r"-\s+\*\*([^*]+)\*\*", text)
                    for match in matches:
                        cid = normalize_id(match)
                        cnode = self.add_node(EntityNode(
                            id=cid,
                            name=match,
                            type="character",
                            category="PEOPLE"
                        ))
                        if protagonist_node:
                            self.add_edge(EntityEdge(
                                source=protagonist_node.id,
                                target=cnode.id,
                                edge_type="contact_of",
                                weight=0.8
                            ))
                except Exception:
                    pass

    def _load_world_bible(self, campaign_dir: str, documents: Optional[List[Document]] = None) -> None:
        bible_dir = os.path.join(campaign_dir, "WORLD_BIBLE")
        if not os.path.exists(bible_dir):
            return

        cat_type_map = {
            "PLACES": "location",
            "PEOPLE": "character",
            "FACTIONS": "faction",
            "CORE": "concept",
            "LORE": "lore",
            "GUIDES": "guide"
        }

        # If documents were passed, associate them directly
        doc_map = {d.doc_id: d for d in (documents or [])}

        for cat, ntype in cat_type_map.items():
            cat_dir = os.path.join(bible_dir, cat)
            if not os.path.isdir(cat_dir):
                continue
            for fpath in glob.glob(os.path.join(cat_dir, "*.md")):
                bname = os.path.splitext(os.path.basename(fpath))[0]
                doc_id = f"world_bible:{cat.lower()}:{bname.lower()}"

                # Extract title from markdown
                title = bname.replace("_", " ").title()
                content = ""
                try:
                    with open(fpath, "r", encoding="utf-8") as f:
                        content = f.read()
                    for line in content.splitlines():
                        if line.startswith("# "):
                            title = line.lstrip("# ").strip()
                            break
                except Exception:
                    pass

                node = self.add_node(EntityNode(
                    id=normalize_id(bname),
                    name=title,
                    type=ntype,
                    category=cat,
                    doc_ids=[doc_id]
                ))

                # Also extract inline bullet entities like `- **Terminal Bay A:** ...`
                inline_entities = re.findall(r"-\s+\*\*([^*:]+)(?::|\*\*)\s*(.*)", content)
                for ent_name, ent_desc in inline_entities:
                    ent_id = normalize_id(ent_name)
                    ent_node = self.add_node(EntityNode(
                        id=ent_id,
                        name=ent_name.strip(),
                        type=ntype,
                        category=cat,
                        doc_ids=[doc_id],
                        metadata={"description": ent_desc.strip()}
                    ))
                    # Edge between parent doc node and sub-entity
                    self.add_edge(EntityEdge(
                        source=node.id,
                        target=ent_node.id,
                        edge_type="contains",
                        weight=1.0
                    ))

    def _extract_wikilinks_and_cross_references(
        self,
        campaign_dir: str,
        documents: Optional[List[Document]] = None
    ) -> None:
        """Parses wikilinks [[Target]] and mentions of known entities across all text."""
        # Collect all text sources (documents if provided, else scan WORLD_BIBLE and GAMEPLAY)
        sources: List[Tuple[str, str, str]] = []  # (doc_node_id, title, content)

        if documents:
            for doc in documents:
                node = self.find_node(doc.title) or self.get_node(normalize_id(doc.title))
                node_id = node.id if node else normalize_id(doc.title)
                sources.append((node_id, doc.title, doc.content))
        else:
            bible_dir = os.path.join(campaign_dir, "WORLD_BIBLE")
            for mpath in glob.glob(os.path.join(bible_dir, "**", "*.md"), recursive=True):
                bname = os.path.splitext(os.path.basename(mpath))[0]
                try:
                    with open(mpath, "r", encoding="utf-8") as f:
                        text = f.read()
                    sources.append((normalize_id(bname), bname, text))
                except Exception:
                    continue

        # Build list of targetable entity names for mention detection
        known_entities = [
            (node.id, node.name, re.compile(rf"\b{re.escape(node.name)}\b", re.IGNORECASE))
            for node in self.nodes.values()
            if len(node.name) >= 3 and node.name.lower() not in {"overview", "status", "primer"}
        ]

        for src_node_id, title, content in sources:
            src_node = self.get_node(src_node_id)
            if not src_node:
                src_node = self.add_node(EntityNode(
                    id=src_node_id,
                    name=title,
                    type="document",
                    category="LORE"
                ))

            # 1. Wikilinks [[Target]] or [[Target|Alias]]
            wikilinks = re.findall(r"\[\[([^\]|]+)(?:\|[^\]]+)?\]\]", content)
            wikilink_targets: Set[str] = set()
            for target_name in wikilinks:
                target_name = target_name.strip()
                target_node = self.find_node(target_name)
                if not target_node:
                    target_id = normalize_id(target_name)
                    target_node = self.add_node(EntityNode(
                        id=target_id,
                        name=target_name,
                        type="concept",
                        category="WIKILINK"
                    ))
                wikilink_targets.add(target_node.id)
                self.add_edge(EntityEdge(
                    source=src_node.id,
                    target=target_node.id,
                    edge_type="wikilink",
                    weight=1.0
                ))

            # 2. Entity Mentions (skip if already connected via wikilink)
            for ent_id, ent_name, pattern in known_entities:
                if ent_id == src_node.id or ent_id in wikilink_targets:
                    continue
                if pattern.search(content):
                    self.add_edge(EntityEdge(
                        source=src_node.id,
                        target=ent_id,
                        edge_type="mentions",
                        weight=0.8
                    ))

    # --- Graph Traversal & Scoring ---

    def traverse_k_hop(
        self,
        start_nodes: List[str],
        max_hops: int = 2,
        decay: float = 0.75
    ) -> Dict[str, float]:
        """
        Executes k-hop breadth-first traversal from a list of anchor node names/ids.
        Returns mapping of node_id -> proximity_score, sorted descending.
        """
        resolved_starts: List[str] = []
        for s in start_nodes:
            n = self.find_node(s)
            if n:
                resolved_starts.append(n.id)

        if not resolved_starts:
            return {}

        visited: Dict[str, float] = {}
        queue: deque = deque()

        for s_id in resolved_starts:
            visited[s_id] = 1.0
            queue.append((s_id, 0, 1.0))

        while queue:
            curr_id, hop, score = queue.popleft()
            if hop >= max_hops:
                continue

            for edge in self.edges.get(curr_id, []):
                neighbor = edge.target
                edge_weight = edge.weight
                neighbor_score = score * decay * edge_weight

                if neighbor not in visited or neighbor_score > visited[neighbor]:
                    visited[neighbor] = neighbor_score
                    queue.append((neighbor, hop + 1, neighbor_score))

        # Sort descending by proximity score
        return dict(sorted(visited.items(), key=lambda x: x[1], reverse=True))

    def resolve_anchors_from_status(self, status_data: Dict[str, Any]) -> List[str]:
        """Extracts candidate anchor entity names from status.json structure."""
        anchors: List[str] = []

        # 1. Location
        scene_anchor = status_data.get("scene_anchor", {})
        loc = scene_anchor.get("location")
        if loc:
            anchors.append(loc)
            # If compound location e.g. "Sub-Level 4 Staging Room, Terminal Bay A", split parts
            for part in loc.split(","):
                part_clean = part.strip()
                if part_clean and part_clean != loc:
                    anchors.append(part_clean)

        # 2. Protagonist character
        char = status_data.get("character", {})
        if char.get("name"):
            anchors.append(char["name"])

        # 3. Pacing state current location / objective
        pacing = status_data.get("pacing_state", {})
        if pacing.get("current_location") and pacing["current_location"] not in anchors:
            anchors.append(pacing["current_location"])

        # 4. Context mentions
        context = scene_anchor.get("context", "")
        if context:
            for node in self.nodes.values():
                if len(node.name) >= 4 and node.name.lower() in context.lower():
                    if node.name not in anchors:
                        anchors.append(node.name)

        return anchors

    def get_passage_scores_from_nodes(
        self,
        node_scores: Dict[str, float],
        documents: List[Document]
    ) -> Dict[str, float]:
        """
        Maps graph node proximity scores to document IDs for hybrid ranking.
        """
        passage_scores: Dict[str, float] = {}

        for node_id, proximity in node_scores.items():
            node = self.nodes.get(node_id)
            if not node:
                continue

            # 1. Direct doc_ids assigned to node
            for did in node.doc_ids:
                passage_scores[did] = max(passage_scores.get(did, 0.0), proximity)

            # 2. Check documents by title or id match
            for doc in documents:
                norm_doc_title = normalize_id(doc.title)
                norm_doc_id = normalize_id(doc.doc_id)
                if node_id in norm_doc_id or node_id == norm_doc_title or node.name.lower() == doc.title.lower():
                    passage_scores[doc.doc_id] = max(passage_scores.get(doc.doc_id, 0.0), proximity)

        return dict(sorted(passage_scores.items(), key=lambda x: x[1], reverse=True))
