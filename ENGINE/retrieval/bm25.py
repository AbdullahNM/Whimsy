#!/usr/bin/env python3
"""
Pure Python BM25 indexer for Whimsy campaign retrieval.
Indexes WORLD_BIBLE markdown files, WORLD_FOUNDATION JSON, and turn history.
Standard library only: zero heavy external dependencies.
"""

import os
import re
import glob
import json
import math
from dataclasses import dataclass, field
from collections import Counter
from typing import Optional, List, Dict, Tuple, Any

# Simple English stopword list for cleaner lexical matching
STOPWORDS = {
    "a", "about", "above", "after", "again", "against", "all", "am", "an",
    "and", "any", "are", "aren't", "as", "at", "be", "because", "been",
    "before", "being", "below", "between", "both", "but", "by", "can",
    "cannot", "could", "did", "do", "does", "doing", "down", "during",
    "each", "few", "for", "from", "further", "had", "has", "have",
    "having", "he", "her", "here", "hers", "herself", "him", "himself",
    "his", "how", "i", "if", "in", "into", "is", "it", "its", "itself",
    "me", "more", "most", "my", "myself", "no", "nor", "not", "of", "off",
    "on", "once", "only", "or", "other", "ought", "our", "ours", "ourselves",
    "out", "over", "own", "same", "she", "should", "so", "some", "such",
    "than", "that", "the", "their", "theirs", "them", "themselves", "then",
    "there", "these", "they", "this", "those", "through", "to", "too",
    "under", "until", "up", "very", "was", "we", "were", "what", "when",
    "where", "which", "while", "who", "whom", "why", "with", "would",
    "you", "your", "yours", "yourself", "yourselves"
}

def tokenize(text: str, remove_stopwords: bool = False) -> List[str]:
    """
    Tokenizes text into normalized lowercase alphanumeric words.
    Strips markdown artifacts and extracts clean terms.
    """
    if not text:
        return []
    # Strip markdown syntax symbols like `#`, `*`, `_`, `[`, `]`, `(`, `)`
    cleaned = re.sub(r"[#*_`\[\]()\"']", " ", text.lower())
    tokens = re.findall(r"\b[a-z0-9_-]+\b", cleaned)
    if remove_stopwords:
        tokens = [t for t in tokens if t not in STOPWORDS and len(t) > 1]
    return tokens


@dataclass
class Document:
    """Represents a retrievable passage or document."""
    doc_id: str
    title: str
    category: str
    content: str
    metadata: Dict[str, Any] = field(default_factory=dict)
    tokens: List[str] = field(default_factory=list)

    def __post_init__(self):
        if not self.tokens and self.content:
            # We tokenize title and content combined for BM25 term matching
            full_text = f"{self.title} {self.content}"
            self.tokens = tokenize(full_text)


class BM25Indexer:
    """
    Pure Python Okapi BM25 Indexer.
    Calculates TF-IDF and BM25 relevance scores over arbitrary document sets.
    """
    def __init__(self, k1: float = 1.5, b: float = 0.75):
        self.k1 = k1
        self.b = b
        self.documents: List[Document] = []
        self.doc_lengths: List[int] = []
        self.avgdl: float = 0.0
        self.doc_freqs: Dict[str, int] = {}
        self.term_freqs: List[Dict[str, int]] = []
        self.inverted_index: Dict[str, List[int]] = {}
        self.idf_cache: Dict[str, float] = {}
        self._doc_id_to_idx: Dict[str, int] = {}

    def add_document(self, doc: Document) -> int:
        idx = len(self.documents)
        self.documents.append(doc)
        self._doc_id_to_idx[doc.doc_id] = idx

        length = len(doc.tokens)
        self.doc_lengths.append(length)

        tf = Counter(doc.tokens)
        self.term_freqs.append(tf)

        for term in tf.keys():
            self.doc_freqs[term] = self.doc_freqs.get(term, 0) + 1
            if term not in self.inverted_index:
                self.inverted_index[term] = []
            self.inverted_index[term].append(idx)

        return idx

    def add_documents(self, docs: List[Document]) -> None:
        for doc in docs:
            self.add_document(doc)
        self.build_index()

    def build_index(self) -> None:
        """Computes average document length and IDF for all indexed terms."""
        num_docs = len(self.documents)
        if num_docs == 0:
            self.avgdl = 0.0
            self.idf_cache.clear()
            return

        self.avgdl = sum(self.doc_lengths) / num_docs

        self.idf_cache.clear()
        for term, df in self.doc_freqs.items():
            # Robertson-Spärck Jones IDF variation guaranteed >= 0
            # idf = ln(1 + (N - n + 0.5) / (n + 0.5))
            self.idf_cache[term] = math.log(1.0 + (num_docs - df + 0.5) / (df + 0.5))

    def get_document(self, doc_id: str) -> Optional[Document]:
        idx = self._doc_id_to_idx.get(doc_id)
        if idx is not None and idx < len(self.documents):
            return self.documents[idx]
        return None

    def score(self, query_tokens: List[str], doc_idx: int) -> float:
        """Calculates BM25 score for a document index against query tokens."""
        if doc_idx >= len(self.documents):
            return 0.0

        doc_len = self.doc_lengths[doc_idx]
        if self.avgdl == 0.0:
            return 0.0

        len_norm = 1.0 - self.b + self.b * (doc_len / self.avgdl)
        tf_dict = self.term_freqs[doc_idx]
        score = 0.0

        for q in query_tokens:
            tf = tf_dict.get(q, 0)
            if tf == 0:
                continue
            idf = self.idf_cache.get(q, 0.0)
            num = tf * (self.k1 + 1.0)
            denom = tf + self.k1 * len_norm
            score += idf * (num / denom)

        return score

    def search(
        self,
        query: str,
        top_k: int = 10,
        category_filter: Optional[List[str]] = None,
        min_score: float = 0.0
    ) -> List[Tuple[Document, float]]:
        """
        Executes BM25 search over the corpus.
        Returns sorted list of (Document, score).
        """
        if not self.documents:
            return []

        if not self.idf_cache:
            self.build_index()

        q_tokens = tokenize(query)
        if not q_tokens:
            return []

        # Find candidate documents containing at least one query term
        candidate_indices = set()
        for token in q_tokens:
            for idx in self.inverted_index.get(token, []):
                candidate_indices.add(idx)

        if not candidate_indices:
            return []

        allowed_cats = {c.upper() for c in category_filter} if category_filter else None

        scored: List[Tuple[Document, float]] = []
        for idx in candidate_indices:
            doc = self.documents[idx]
            if allowed_cats and doc.category.upper() not in allowed_cats:
                continue
            doc_score = self.score(q_tokens, idx)
            if doc_score > min_score:
                scored.append((doc, doc_score))

        scored.sort(key=lambda x: x[1], reverse=True)
        return scored[:top_k]

    # --- Campaign File Indexers ---

    def index_world_bible(self, bible_dir: str) -> List[Document]:
        """Indexes all markdown files in WORLD_BIBLE directory."""
        if not os.path.exists(bible_dir):
            return []

        docs = []
        # Support both category subfolders and root overview
        categories = ["CORE", "PLACES", "PEOPLE", "FACTIONS", "LORE", "GUIDES"]

        for cat in categories:
            cat_dir = os.path.join(bible_dir, cat)
            if os.path.isdir(cat_dir):
                for mpath in sorted(glob.glob(os.path.join(cat_dir, "*.md"))):
                    doc = self._parse_markdown_file(mpath, category=cat)
                    if doc:
                        docs.append(doc)

        overview_path = os.path.join(bible_dir, "overview.md")
        if os.path.exists(overview_path):
            doc = self._parse_markdown_file(overview_path, category="OVERVIEW")
            if doc:
                docs.append(doc)

        # Catch any additional root or miscellaneous markdown files
        for root_md in glob.glob(os.path.join(bible_dir, "*.md")):
            if os.path.basename(root_md) != "overview.md":
                doc = self._parse_markdown_file(root_md, category="LORE")
                if doc:
                    docs.append(doc)

        return docs

    def _parse_markdown_file(self, file_path: str, category: str) -> Optional[Document]:
        """Parses a markdown file into a retrievable Document."""
        try:
            with open(file_path, "r", encoding="utf-8") as f:
                content = f.read().strip()
        except Exception:
            return None

        if not content:
            return None

        base_name = os.path.splitext(os.path.basename(file_path))[0]
        title = base_name.replace("_", " ").title()

        # Check if first line has a markdown header
        lines = content.splitlines()
        for line in lines:
            if line.startswith("# "):
                title = line.lstrip("# ").strip()
                break

        doc_id = f"world_bible:{category.lower()}:{base_name.lower()}"
        return Document(
            doc_id=doc_id,
            title=title,
            category=category,
            content=content,
            metadata={"file_path": file_path, "base_name": base_name}
        )

    def index_world_foundation(self, foundation_path_or_dir: str) -> List[Document]:
        """Indexes facts, factions, tensions, NPC knowledge, and rumors from WORLD_FOUNDATION."""
        wf_path = foundation_path_or_dir
        if os.path.isdir(wf_path):
            candidates = [
                os.path.join(wf_path, "world_foundation.json"),
                os.path.join(wf_path, "WORLD_FOUNDATION", "world_foundation.json")
            ]
            wf_path = None
            for cand in candidates:
                if os.path.exists(cand):
                    wf_path = cand
                    break
            if not wf_path:
                jsons = sorted(glob.glob(os.path.join(foundation_path_or_dir, "*.json")))
                if jsons:
                    wf_path = jsons[0]

        if not wf_path or not os.path.exists(wf_path):
            return []

        try:
            with open(wf_path, "r", encoding="utf-8") as f:
                data = json.load(f)
        except Exception:
            return []

        docs = []

        # 1. Immutable Facts
        facts = data.get("immutable_facts", [])
        for idx, fact in enumerate(facts):
            if isinstance(fact, dict):
                f_id = fact.get("id", f"FACT-{idx+1}")
                cat = fact.get("category", "General")
                stmt = fact.get("statement") or fact.get("fact") or fact.get("description", "")
                notes = fact.get("notes", "")
                text = f"{stmt} {notes}".strip()
                docs.append(Document(
                    doc_id=f"wf:fact:{f_id.lower()}",
                    title=f"Immutable Fact [{cat.upper()}]: {f_id}",
                    category="WORLD_FOUNDATION",
                    content=text,
                    metadata={"fact_id": f_id, "type": "immutable_fact", "category": cat}
                ))
            else:
                docs.append(Document(
                    doc_id=f"wf:fact:fact_{idx+1}",
                    title=f"Immutable Fact #{idx+1}",
                    category="WORLD_FOUNDATION",
                    content=str(fact),
                    metadata={"type": "immutable_fact"}
                ))

        # 2. Mutable World State
        mutable = data.get("mutable_world_state", {})
        if mutable:
            mut_lines = []
            if isinstance(mutable, dict):
                for k, v in mutable.items():
                    mut_lines.append(f"{k}: {v}")
            else:
                mut_lines.append(str(mutable))
            docs.append(Document(
                doc_id="wf:mutable_state",
                title="Mutable World State & Geopolitics",
                category="WORLD_FOUNDATION",
                content="\n".join(mut_lines),
                metadata={"type": "mutable_state"}
            ))

        # 3. Factions & Tensions
        factions = data.get("factions_and_tensions", [])
        for idx, fac in enumerate(factions):
            if isinstance(fac, dict):
                f_id = fac.get("id", f"fac_{idx+1}")
                name = fac.get("name", f_id)
                agenda = fac.get("agenda", "")
                objs = "; ".join(fac.get("objectives", []))
                tensions = []
                for t in fac.get("tensions", []):
                    if isinstance(t, dict):
                        target = t.get("target_entity") or t.get("target_faction_or_entity", "Unknown")
                        fric = t.get("source_of_friction", "")
                        intens = t.get("intensity", "")
                        tensions.append(f"Tension with {target} ({intens}): {fric}")
                    else:
                        tensions.append(str(t))
                tens_str = "\n".join(tensions)
                content = f"Faction: {name}\nAgenda: {agenda}\nObjectives: {objs}\nTensions:\n{tens_str}"
                docs.append(Document(
                    doc_id=f"wf:faction:{f_id.lower()}",
                    title=f"Faction: {name}",
                    category="WORLD_FOUNDATION",
                    content=content,
                    metadata={"faction_id": f_id, "faction_name": name, "type": "faction"}
                ))

        # 4. NPC Epistemic Knowledge Map
        npc_kn = data.get("npc_knowledge", {})
        if isinstance(npc_kn, dict):
            for npc_id, kn in npc_kn.items():
                if isinstance(kn, dict):
                    knows = ", ".join(kn.get("knows", []))
                    not_knows = ", ".join(kn.get("does_not_know", []))
                    false_bel = ", ".join(kn.get("falsely_believes", []))
                    content = (
                        f"NPC: {npc_id}\n"
                        f"Known Truths: {knows}\n"
                        f"Ignorant Of: {not_knows}\n"
                        f"False Beliefs: {false_bel}"
                    )
                else:
                    content = f"NPC: {npc_id}\nKnowledge: {kn}"
                docs.append(Document(
                    doc_id=f"wf:npc_knowledge:{npc_id.lower()}",
                    title=f"NPC Epistemic Knowledge: {npc_id}",
                    category="WORLD_FOUNDATION",
                    content=content,
                    metadata={"npc_id": npc_id, "type": "npc_knowledge"}
                ))

        # 5. Rumors & Beliefs
        rumors = data.get("rumors_and_beliefs", [])
        for idx, rum in enumerate(rumors):
            if isinstance(rum, dict):
                r_id = rum.get("id", f"RUMOR-{idx+1}")
                claim = rum.get("claim", "")
                believed_by = rum.get("believed_by", "")
                veracity = rum.get("veracity", "")
                content = f"Rumor: {claim}\nBelieved by: {believed_by}\nVeracity: {veracity}"
                docs.append(Document(
                    doc_id=f"wf:rumor:{r_id.lower()}",
                    title=f"Rumor [{veracity}]: {r_id}",
                    category="WORLD_FOUNDATION",
                    content=content,
                    metadata={"rumor_id": r_id, "type": "rumor", "veracity": veracity}
                ))

        # 6. Unresolved Mysteries (Canon secrets)
        mysteries = data.get("unresolved_mysteries", [])
        for idx, myst in enumerate(mysteries):
            if isinstance(myst, dict):
                m_id = myst.get("id", f"MYSTERY-{idx+1}")
                m_title = myst.get("title", m_id)
                m_truth = myst.get("secret_truth") or myst.get("truth") or myst.get("description", "")
                discovered = bool(myst.get("discovered", False))
                cond = myst.get("discovery_conditions", "")
                status_label = "DISCOVERED" if discovered else "HIDDEN FROM PROTAGONIST VIEW - CANON SECRET"
                content = f"[{status_label}] {m_title}: {m_truth}\nDiscovery Condition: {cond}"
                docs.append(Document(
                    doc_id=f"wf:mystery:{m_id.lower()}",
                    title=f"Mystery: {m_title}",
                    category="WORLD_FOUNDATION",
                    content=content,
                    metadata={
                        "mystery_id": m_id,
                        "type": "unresolved_mystery",
                        "is_secret": True,
                        "discovered": discovered
                    }
                ))

        return docs

    def index_turns(self, turns_dir: str) -> List[Document]:
        """Indexes active and archive turn files from TURNS directory."""
        if not os.path.exists(turns_dir):
            return []

        docs = []
        for subdir in ["ACTIVE", "ARCHIVE"]:
            target_dir = os.path.join(turns_dir, subdir)
            if os.path.isdir(target_dir):
                for tfile in sorted(glob.glob(os.path.join(target_dir, "turn_*.md"))):
                    base_name = os.path.splitext(os.path.basename(tfile))[0]
                    try:
                        with open(tfile, "r", encoding="utf-8") as f:
                            content = f.read().strip()
                        if content:
                            docs.append(Document(
                                doc_id=f"turns:{subdir.lower()}:{base_name}",
                                title=f"Turn History: {base_name}",
                                category="TURNS",
                                content=content,
                                metadata={"turn_file": tfile, "turn_status": subdir.lower()}
                            ))
                    except Exception:
                        continue

        return docs

    def index_campaign(self, campaign_dir: str) -> List[Document]:
        """Indexes all retrievable sources in a campaign directory."""
        bible_dir = os.path.join(campaign_dir, "WORLD_BIBLE")
        foundation_dir = os.path.join(campaign_dir, "WORLD_FOUNDATION")
        turns_dir = os.path.join(campaign_dir, "TURNS")

        all_docs = []
        all_docs.extend(self.index_world_bible(bible_dir))
        all_docs.extend(self.index_world_foundation(foundation_dir))
        all_docs.extend(self.index_turns(turns_dir))

        self.add_documents(all_docs)
        return all_docs
