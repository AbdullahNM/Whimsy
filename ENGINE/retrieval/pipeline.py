#!/usr/bin/env python3
"""
Hybrid Retriever with Reciprocal Rank Fusion (RRF) for Whimsy.
Combines pure Python BM25 lexical search with Entity Graph proximity ranking.
Filters passages against epistemic certainty and enforces strict context budgets.
Standard library only: zero heavy external dependencies.
"""

import os
import json
from dataclasses import dataclass, field
from typing import Optional, List, Dict, Set, Tuple, Any

from .bm25 import BM25Indexer, Document
from .graph import EntityGraph


@dataclass
class RetrievedPassage:
    """Represents a budget-capped, epistemically verified retrieved passage."""
    id: str
    title: str
    category: str
    relevance_score: float
    content: str
    metadata: Dict[str, Any] = field(default_factory=dict)


def reciprocal_rank_fusion(
    rankings: List[List[str]],
    k: int = 60,
    weights: Optional[List[float]] = None
) -> Dict[str, float]:
    """
    Computes Reciprocal Rank Fusion (RRF) scores across multiple rankings.
    score(d) = sum_m [ weight_m / (k + rank_m(d)) ]
    where rank_m is 1-indexed.
    """
    scores: Dict[str, float] = {}
    if not weights:
        weights = [1.0] * len(rankings)

    for ranking, weight in zip(rankings, weights):
        for rank_idx, doc_id in enumerate(ranking, start=1):
            scores[doc_id] = scores.get(doc_id, 0.0) + (weight / (k + rank_idx))

    return dict(sorted(scores.items(), key=lambda x: x[1], reverse=True))


class HybridRetriever:
    """
    Orchestrates hybrid retrieval combining BM25 keyword rankings and
    Entity Graph proximity traversals, fused via Reciprocal Rank Fusion (RRF).
    Filters out unrevealed secrets (epistemic separation) and clamps to context budget.
    """
    def __init__(
        self,
        campaign_dir: str,
        char_budget: int = 16000,
        max_passages: int = 5,
        k_hops: int = 2,
        rrf_k: int = 60
    ):
        self.campaign_dir = campaign_dir
        self.char_budget = char_budget
        self.max_passages = max_passages
        self.k_hops = k_hops
        self.rrf_k = rrf_k

        self.bm25 = BM25Indexer()
        self.graph = EntityGraph()
        self.documents: List[Document] = []
        self._indexed: bool = False
        self._status_data: Optional[Dict[str, Any]] = None

    def ensure_indexed(self) -> None:
        """Indexes campaign files and constructs entity graph if not yet indexed."""
        if self._indexed:
            return

        self.documents = self.bm25.index_campaign(self.campaign_dir)
        self.graph.build_from_campaign(self.campaign_dir, self.documents)
        self._load_status()
        self._indexed = True

    def _load_status(self) -> Dict[str, Any]:
        if self._status_data is not None:
            return self._status_data

        status_path = os.path.join(self.campaign_dir, "GAMEPLAY", "status.json")
        if os.path.exists(status_path):
            try:
                with open(status_path, "r", encoding="utf-8") as f:
                    self._status_data = json.load(f)
                    return self._status_data
            except Exception:
                pass

        self._status_data = {}
        return self._status_data

    def filter_epistemic(self, doc: Document) -> bool:
        """
        Determines whether a document is epistemically accessible to the protagonist.
        Canon secrets and unresolved mysteries with discovered=False are excluded.
        """
        # 1. Metadata secret check
        if doc.metadata.get("is_secret") and not doc.metadata.get("discovered", False):
            return False

        # 2. Text marker check
        if "[HIDDEN FROM PROTAGONIST VIEW - CANON SECRET]" in doc.content:
            return False

        # 3. Dynamic mystery check from world_foundation.json
        if doc.metadata.get("type") == "unresolved_mystery":
            if not doc.metadata.get("discovered", False):
                return False

        return True

    def retrieve(
        self,
        query: str,
        active_anchors: Optional[List[str]] = None,
        max_passages: Optional[int] = None,
        char_budget: Optional[int] = None,
        category_filter: Optional[List[str]] = None
    ) -> List[RetrievedPassage]:
        """
        Performs hybrid retrieval:
        1. BM25 search over all campaign documents.
        2. k-hop graph expansion from active scene anchors.
        3. Reciprocal Rank Fusion (RRF) between lexical and graph rankings.
        4. Epistemic certainty filtering (blocks unrevealed secrets).
        5. Token/character budget clamping.
        """
        self.ensure_indexed()

        limit_passages = max_passages if max_passages is not None else self.max_passages
        limit_chars = char_budget if char_budget is not None else self.char_budget

        # 1. Lexical Retrieval (BM25)
        bm25_hits = self.bm25.search(
            query=query,
            top_k=50,
            category_filter=category_filter
        )
        bm25_ranked = [doc.doc_id for doc, score in bm25_hits]

        # 2. Graph Proximity Retrieval
        anchors = list(active_anchors) if active_anchors else []
        if not anchors:
            status = self._load_status()
            anchors = self.graph.resolve_anchors_from_status(status)

        # If still no anchors, use query to identify seed nodes
        if not anchors and query:
            for node in self.graph.nodes.values():
                if len(node.name) >= 4 and node.name.lower() in query.lower():
                    anchors.append(node.name)

        node_proximity = self.graph.traverse_k_hop(
            start_nodes=anchors,
            max_hops=self.k_hops
        )
        passage_proximity = self.graph.get_passage_scores_from_nodes(
            node_scores=node_proximity,
            documents=self.documents
        )
        graph_ranked = list(passage_proximity.keys())

        # If both are empty, return empty list
        if not bm25_ranked and not graph_ranked:
            return []

        # 3. Reciprocal Rank Fusion (RRF)
        # Combine BM25 ranking and Graph proximity ranking
        rankings = []
        weights = []
        if bm25_ranked:
            rankings.append(bm25_ranked)
            weights.append(1.0)
        if graph_ranked:
            rankings.append(graph_ranked)
            weights.append(1.0)

        fused_scores = reciprocal_rank_fusion(rankings, k=self.rrf_k, weights=weights)

        # 4. Epistemic Filtering & Budget Clamping
        retrieved: List[RetrievedPassage] = []
        current_chars = 0

        for doc_id, rrf_score in fused_scores.items():
            if len(retrieved) >= limit_passages:
                break

            doc = self.bm25.get_document(doc_id)
            if not doc:
                continue

            # Epistemic certainty check
            if not self.filter_epistemic(doc):
                continue

            content = doc.content
            content_len = len(content)

            # Check character budget
            if current_chars + content_len > limit_chars:
                if len(retrieved) == 0 and limit_chars > 0:
                    # Single passage exceeding entire budget: cleanly truncate
                    truncated = content[:limit_chars]
                    retrieved.append(RetrievedPassage(
                        id=doc.doc_id,
                        title=doc.title,
                        category=doc.category,
                        relevance_score=rrf_score,
                        content=truncated,
                        metadata=doc.metadata
                    ))
                    break
                else:
                    # Cannot fit entire passage without exceeding budget; stop
                    break

            retrieved.append(RetrievedPassage(
                id=doc.doc_id,
                title=doc.title,
                category=doc.category,
                relevance_score=rrf_score,
                content=content,
                metadata=doc.metadata
            ))
            current_chars += content_len

        return retrieved

    def retrieve_formatted(
        self,
        query: str,
        active_anchors: Optional[List[str]] = None,
        max_passages: Optional[int] = None,
        char_budget: Optional[int] = None,
        category_filter: Optional[List[str]] = None
    ) -> str:
        """
        Retrieves relevant passages and formats them into standard PromptAssembler
        world lore section blocks.
        """
        passages = self.retrieve(
            query=query,
            active_anchors=active_anchors,
            max_passages=max_passages,
            char_budget=char_budget,
            category_filter=category_filter
        )
        if not passages:
            return ""

        sections = []
        for p in passages:
            cat_label = p.category.upper()
            sections.append(f"=== WORLD BIBLE [{cat_label}]: {p.title.upper()} ===\n{p.content}")

        return "\n\n".join(sections)
