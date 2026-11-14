#!/usr/bin/env python3
"""
Comprehensive test suite for Issue 16: Hybrid + Graph Grounded Retrieval (RAG) Pipeline.
Tests BM25 indexer, World Bible & Entity Graph, Reciprocal Rank Fusion,
epistemic certainty filtering, budget clamping, and PromptAssembler integration.
"""

import os
import sys
import unittest
import tempfile
import json
import shutil

ROOT_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if ROOT_DIR not in sys.path:
    sys.path.insert(0, ROOT_DIR)

from ENGINE.retrieval import (
    BM25Indexer,
    Document,
    tokenize,
    EntityGraph,
    EntityNode,
    EntityEdge,
    normalize_id,
    HybridRetriever,
    RetrievedPassage,
    reciprocal_rank_fusion
)
from ENGINE.prompt_assembler import PromptAssembler, assemble_prompt


class TestBM25Indexer(unittest.TestCase):
    """Tests R1: Pure Python BM25 indexer."""

    def test_tokenize(self):
        text = "Hello, [[Terminal Bay A]]! It's #1 (awesome)."
        tokens = tokenize(text)
        self.assertIn("hello", tokens)
        self.assertIn("terminal", tokens)
        self.assertIn("bay", tokens)
        self.assertIn("a", tokens)
        self.assertIn("1", tokens)
        self.assertIn("awesome", tokens)

        tokens_no_stop = tokenize("this is a test of the emergency system", remove_stopwords=True)
        self.assertIn("emergency", tokens_no_stop)
        self.assertIn("system", tokens_no_stop)
        self.assertNotIn("this", tokens_no_stop)
        self.assertNotIn("is", tokens_no_stop)

    def test_bm25_scoring_and_ranking(self):
        indexer = BM25Indexer()
        doc1 = Document(
            doc_id="doc1",
            title="Reactor Room",
            category="PLACES",
            content="The geothermal reactor powers the entire subterranean metro grid."
        )
        doc2 = Document(
            doc_id="doc2",
            title="Archival Vault",
            category="PLACES",
            content="Ancient historical manuscripts stored behind secure containment doors."
        )
        doc3 = Document(
            doc_id="doc3",
            title="Grid Maintenance",
            category="CORE",
            content="Protocols for repairing the electrical grid and geothermal conduits."
        )
        indexer.add_documents([doc1, doc2, doc3])

        # Query for "geothermal reactor"
        results = indexer.search("geothermal reactor", top_k=2)
        self.assertEqual(len(results), 2)
        # Doc 1 has both "geothermal" and "reactor", Doc 3 has only "geothermal"
        self.assertEqual(results[0][0].doc_id, "doc1")
        self.assertGreater(results[0][1], results[1][1])

    def test_bm25_empty_and_unknown_terms(self):
        indexer = BM25Indexer()
        # Empty index search
        self.assertEqual(indexer.search("anything"), [])

        doc = Document(doc_id="d1", title="Alpha", category="CORE", content="Simple text here")
        indexer.add_document(doc)
        indexer.build_index()

        # Empty query
        self.assertEqual(indexer.search(""), [])
        # Unknown terms
        self.assertEqual(indexer.search("nonexistentxyz"), [])

    def test_bm25_category_filter(self):
        indexer = BM25Indexer()
        doc1 = Document(doc_id="d1", title="Station Bay", category="PLACES", content="Transit hub")
        doc2 = Document(doc_id="d2", title="Station Rules", category="CORE", content="Transit hub regulations")
        indexer.add_documents([doc1, doc2])

        results = indexer.search("transit hub", category_filter=["CORE"])
        self.assertEqual(len(results), 1)
        self.assertEqual(results[0][0].doc_id, "d2")

    def test_campaign_indexing(self):
        campaign_dir = os.path.join(ROOT_DIR, "CAMPAIGNS", "template_campaign")
        indexer = BM25Indexer()
        docs = indexer.index_campaign(campaign_dir)
        self.assertGreater(len(docs), 5)

        # Check that WORLD_BIBLE, WORLD_FOUNDATION, and TURNS were indexed
        categories = {d.category for d in docs}
        self.assertIn("WORLD_FOUNDATION", categories)
        self.assertIn("TURNS", categories)

        # Search for Metro Core
        hits = indexer.search("Metro Core", top_k=3)
        self.assertTrue(any("overview" in h[0].doc_id or "primer" in h[0].doc_id for h in hits))


class TestEntityGraph(unittest.TestCase):
    """Tests R2: World Bible & Entity Graph construction and k-hop traversal."""

    def test_normalize_id(self):
        self.assertEqual(normalize_id("Terminal Bay A"), "terminal_bay_a")
        self.assertEqual(normalize_id("  Sub-Level 4: Staging!  "), "sub_level_4_staging")

    def test_node_and_edge_management(self):
        graph = EntityGraph()
        n1 = EntityNode(id="station_a", name="Station A", type="location", category="PLACES")
        n2 = EntityNode(id="alex", name="Alex Mercer", type="character", category="PEOPLE")
        graph.add_node(n1)
        graph.add_node(n2)

        edge = EntityEdge(source="alex", target="station_a", edge_type="located_in")
        graph.add_edge(edge, bidirectional=True)

        self.assertEqual(len(graph.edges["alex"]), 1)
        self.assertEqual(graph.edges["alex"][0].target, "station_a")
        # Bidirectional edge exists on station_a
        self.assertEqual(len(graph.edges["station_a"]), 1)
        self.assertEqual(graph.edges["station_a"][0].target, "alex")

        # Resolving node
        self.assertEqual(graph.find_node("Station A").id, "station_a")
        self.assertEqual(graph.find_node("alex mercer").id, "alex")

    def test_k_hop_traversal_decay(self):
        graph = EntityGraph()
        # Linear graph: A <-> B <-> C <-> D
        for name in ["A", "B", "C", "D"]:
            graph.add_node(EntityNode(id=name.lower(), name=name, type="concept", category="TEST"))

        graph.add_edge(EntityEdge(source="a", target="b", edge_type="link", weight=1.0))
        graph.add_edge(EntityEdge(source="b", target="c", edge_type="link", weight=1.0))
        graph.add_edge(EntityEdge(source="c", target="d", edge_type="link", weight=1.0))

        # 2-hop traversal from A with decay 0.5
        scores = graph.traverse_k_hop(["A"], max_hops=2, decay=0.5)

        self.assertIn("a", scores)
        self.assertIn("b", scores)
        self.assertIn("c", scores)
        self.assertNotIn("d", scores)  # D is 3 hops away

        self.assertEqual(scores["a"], 1.0)
        self.assertAlmostEqual(scores["b"], 0.5)
        self.assertAlmostEqual(scores["c"], 0.25)

    def test_wikilinks_and_mentions_parsing(self):
        graph = EntityGraph()
        loc_node = EntityNode(id="sector_7", name="Sector 7", type="location", category="PLACES")
        char_node = EntityNode(id="commander_vane", name="Commander Vane", type="character", category="PEOPLE")
        graph.add_node(loc_node)
        graph.add_node(char_node)

        doc = Document(
            doc_id="mission_brief",
            title="Mission Briefing",
            category="CORE",
            content="Report to [[Sector 7]] immediately. Commander Vane will oversee your squad."
        )
        graph._extract_wikilinks_and_cross_references(campaign_dir="", documents=[doc])

        # Briefing doc node should link to Sector 7 via wikilink and Commander Vane via mentions
        doc_node = graph.find_node("Mission Briefing")
        self.assertIsNotNone(doc_node)

        connected_targets = {edge.target: edge.edge_type for edge in graph.edges[doc_node.id]}
        self.assertIn("sector_7", connected_targets)
        self.assertEqual(connected_targets["sector_7"], "wikilink")
        self.assertIn("commander_vane", connected_targets)
        self.assertEqual(connected_targets["commander_vane"], "mentions")

    def test_campaign_graph_construction(self):
        campaign_dir = os.path.join(ROOT_DIR, "CAMPAIGNS", "template_campaign")
        graph = EntityGraph()
        graph.build_from_campaign(campaign_dir)

        # Check key nodes exist
        self.assertIsNotNone(graph.find_node("Alex Mercer"))
        self.assertIsNotNone(graph.find_node("Terminal Bay A"))
        self.assertIsNotNone(graph.find_node("Central Transit Directorate"))

        # Check anchor resolution
        status_path = os.path.join(campaign_dir, "GAMEPLAY", "status.json")
        with open(status_path, "r", encoding="utf-8") as f:
            status_data = json.load(f)

        anchors = graph.resolve_anchors_from_status(status_data)
        self.assertTrue(any("Terminal Bay A" in a for a in anchors))

        # Check traversal from Terminal Bay A
        traversal = graph.traverse_k_hop(["Terminal Bay A"], max_hops=2)
        self.assertIn("terminal_bay_a", traversal)
        self.assertEqual(traversal["terminal_bay_a"], 1.0)


class TestHybridRetrieverPipeline(unittest.TestCase):
    """Tests R3: Hybrid Retriever, RRF, Epistemic Filtering, and Budget Clamping."""

    def test_reciprocal_rank_fusion(self):
        # Ranking 1: docA (rank 1), docB (rank 2), docC (rank 3)
        # Ranking 2: docB (rank 1), docD (rank 2), docA (rank 3)
        r1 = ["docA", "docB", "docC"]
        r2 = ["docB", "docD", "docA"]

        scores = reciprocal_rank_fusion([r1, r2], k=60)

        # docB rank 2 in r1, rank 1 in r2 -> 1/62 + 1/61
        # docA rank 1 in r1, rank 3 in r2 -> 1/61 + 1/63
        # docB score should be higher than docA
        self.assertGreater(scores["docB"], scores["docA"])
        # docC and docD only appear in one list
        self.assertLess(scores["docC"], scores["docA"])
        self.assertLess(scores["docD"], scores["docA"])

    def test_epistemic_filtering_unrevealed_secrets(self):
        campaign_dir = os.path.join(ROOT_DIR, "CAMPAIGNS", "template_campaign")
        retriever = HybridRetriever(campaign_dir)
        retriever.ensure_indexed()

        # Query specifically targeted at canon secret
        passages = retriever.retrieve(
            query="Container Sigma-9 prototype neural transceiver Sub-Level 8 ancient reactor"
        )

        for p in passages:
            # Confirm no unrevealed secrets leak into retrieved output
            self.assertFalse(p.metadata.get("is_secret") and not p.metadata.get("discovered", False))
            self.assertNotIn("[HIDDEN FROM PROTAGONIST VIEW - CANON SECRET]", p.content)
            self.assertNotEqual(p.metadata.get("mystery_id"), "MYSTERY-01")
            self.assertNotEqual(p.metadata.get("mystery_id"), "MYSTERY-02")

    def test_discovered_secrets_are_accessible(self):
        # Create a mock campaign where a secret was discovered
        with tempfile.TemporaryDirectory() as temp_dir:
            camp_dir = os.path.join(temp_dir, "test_camp")
            os.makedirs(os.path.join(camp_dir, "WORLD_BIBLE", "CORE"))
            os.makedirs(os.path.join(camp_dir, "WORLD_FOUNDATION"))
            os.makedirs(os.path.join(camp_dir, "GAMEPLAY"))

            wf = {
                "campaign_id": "test_camp",
                "unresolved_mysteries": [
                    {
                        "id": "MYSTERY-DISCOVERED",
                        "title": "Decoded Transmission",
                        "secret_truth": "The transmission reveals secret rebel coordinates.",
                        "discovered": True
                    },
                    {
                        "id": "MYSTERY-UNDISCOVERED",
                        "title": "Hidden Vault",
                        "secret_truth": "The vault holds the weapon of doom.",
                        "discovered": False
                    }
                ]
            }
            with open(os.path.join(camp_dir, "WORLD_FOUNDATION", "world_foundation.json"), "w") as f:
                json.dump(wf, f)

            with open(os.path.join(camp_dir, "WORLD_BIBLE", "CORE", "primer.md"), "w") as f:
                f.write("# World Primer\nA mysterious land.")

            retriever = HybridRetriever(camp_dir)
            passages = retriever.retrieve("transmission coordinates vault weapon")

            titles = [p.title for p in passages]
            self.assertIn("Mystery: Decoded Transmission", titles)
            self.assertNotIn("Mystery: Hidden Vault", titles)

    def test_budget_clamping_prevents_context_overflow(self):
        campaign_dir = os.path.join(ROOT_DIR, "CAMPAIGNS", "template_campaign")

        # Test passage count limit
        retriever = HybridRetriever(campaign_dir, max_passages=2)
        passages = retriever.retrieve("Terminal Bay Metro Core Transit", max_passages=2)
        self.assertLessEqual(len(passages), 2)

        # Test strict character budget limit
        strict_budget = 350
        passages_capped = retriever.retrieve("Terminal Bay Metro Core Transit", char_budget=strict_budget)
        total_chars = sum(len(p.content) for p in passages_capped)
        self.assertLessEqual(total_chars, strict_budget)

    def test_retrieve_formatted(self):
        campaign_dir = os.path.join(ROOT_DIR, "CAMPAIGNS", "template_campaign")
        retriever = HybridRetriever(campaign_dir)
        formatted = retriever.retrieve_formatted("Terminal Bay A", max_passages=3)
        self.assertIn("=== WORLD BIBLE [", formatted)
        self.assertTrue(len(formatted) > 100)


class TestPromptAssemblerIntegration(unittest.TestCase):
    """Tests R4: Prompt Assembler Integration with Hybrid Retrieval."""

    def setUp(self):
        self.assembler = PromptAssembler(ROOT_DIR)

    def test_prompt_assembler_with_retrieval_toggle(self):
        # Retrieval explicitly enabled
        prompt_rag = self.assembler.build_system_prompt(
            "template_campaign",
            query="Terminal Bay A",
            retrieval_enabled=True
        )
        self.assertIn("# 4. WORLD BIBLE & RELEVANT LORE", prompt_rag)
        self.assertIn("=== WORLD BIBLE [", prompt_rag)

        # Retrieval explicitly disabled (falls back to load_world_bible)
        prompt_monolithic = self.assembler.build_system_prompt(
            "template_campaign",
            retrieval_enabled=False
        )
        self.assertIn("# 4. WORLD BIBLE & RELEVANT LORE", prompt_monolithic)
        self.assertIn("=== WORLD BIBLE [CORE]: SETTING_PRIMER ===", prompt_monolithic)

    def test_prompt_assembler_retrieval_from_config(self):
        # template_campaign has retrieval: { enabled: true } in campaign_config.json
        prompt = self.assembler.build_system_prompt("template_campaign")
        self.assertIn("# 4. WORLD BIBLE & RELEVANT LORE", prompt)
        self.assertIn("Metro Core", prompt)

    def test_assemble_prompt_convenience_function(self):
        prompt = assemble_prompt("template_campaign", ROOT_DIR, query="staging bay")
        self.assertIn("GLOBAL SYSTEM CONSTRAINTS", prompt)
        self.assertIn("ACTIVE CAMPAIGN GAMEPLAY & STATE", prompt)
        self.assertIn("WORLD BIBLE & RELEVANT LORE", prompt)


if __name__ == "__main__":
    unittest.main()
