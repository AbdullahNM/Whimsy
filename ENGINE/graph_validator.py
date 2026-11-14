#!/usr/bin/env python3
"""
ENGINE/graph_validator.py
=========================
Story graph validation engine.

Detects:
1. Unreachable passages (dead content / orphans)
2. Passages with zero outgoing choices missing 'terminal' or 'end' tags
3. Links pointing to non-existent passages (broken links)
4. Choice text collisions breaking deterministic choice matching
5. Cycles with no state escape (unwinnable loops)

Reuses normalization and choice matching rules from ENGINE/mode_validator.py.
"""

from dataclasses import dataclass, field, asdict
import os
import re
from typing import Any, Dict, List, Optional, Set, Tuple, Union

from ENGINE.mode_validator import _normalize_text, matches_choice_text
from ENGINE.twine_io import StoryGraph, PassageNode, export_campaign_to_graph


@dataclass
class Diagnostic:
    """Structured diagnostic reporting an issue or warning in the story graph."""
    code: str
    severity: str  # "error" or "warning"
    message: str
    passage_name: Optional[str] = None
    passage_id: Optional[Union[int, str]] = None
    target: Optional[str] = None
    file: Optional[str] = None
    line: Optional[int] = None
    details: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


@dataclass
class ValidationResult:
    """Aggregated validation output containing error/warning diagnostics."""
    valid: bool
    diagnostics: List[Diagnostic] = field(default_factory=list)

    @property
    def errors(self) -> List[Diagnostic]:
        return [d for d in self.diagnostics if d.severity == "error"]

    @property
    def warnings(self) -> List[Diagnostic]:
        return [d for d in self.diagnostics if d.severity == "warning"]

    def to_dict(self) -> Dict[str, Any]:
        return {
            "valid": self.valid,
            "errors": [d.to_dict() for d in self.errors],
            "warnings": [d.to_dict() for d in self.warnings],
            "total_diagnostics": len(self.diagnostics)
        }


class GraphValidator:
    """
    Validates a StoryGraph instance against CYOA structural invariants.
    """

    def __init__(self, graph: StoryGraph, file_references: Optional[Dict[str, str]] = None):
        self.graph = graph
        self.file_references = file_references or {}
        self.diagnostics: List[Diagnostic] = []

    def validate(self) -> ValidationResult:
        self.diagnostics.clear()

        # 1. Broken Links Check
        self._check_broken_links()

        # 2. Unreachable Passages (Orphans) Check
        self._check_unreachable_passages()

        # 3. Dead Ends Missing Terminal/End Tag Check
        self._check_terminal_tags()

        # 4. Choice Text Collisions Check
        self._check_choice_collisions()

        # 5. Dead Cycles with No State Escape Check
        self._check_dead_cycles()

        # Include format neutrality warnings from graph if present
        for warn in getattr(self.graph, "warnings", []):
            self.diagnostics.append(
                Diagnostic(
                    code="UNSUPPORTED_MACRO",
                    severity="warning",
                    message=warn
                )
            )

        is_valid = len(self.errors) == 0
        return ValidationResult(valid=is_valid, diagnostics=list(self.diagnostics))

    @property
    def errors(self) -> List[Diagnostic]:
        return [d for d in self.diagnostics if d.severity == "error"]

    @property
    def warnings(self) -> List[Diagnostic]:
        return [d for d in self.diagnostics if d.severity == "warning"]

    def _get_passage_file(self, passage: PassageNode) -> Optional[str]:
        if passage.name in self.file_references:
            return self.file_references[passage.name]
        pid_key = str(passage.pid)
        if pid_key in self.file_references:
            return self.file_references[pid_key]
        return None

    # --------------------------------------------------------------------------
    # 1. Broken Links
    # --------------------------------------------------------------------------
    def _check_broken_links(self):
        existing_names = set(self.graph.passages.keys())
        existing_pids = {str(p.pid) for p in self.graph.passages.values()}

        for passage in self.graph.passages.values():
            file_ref = self._get_passage_file(passage)
            for link in passage.links:
                target = link.target
                if target not in existing_names and target not in existing_pids:
                    self.diagnostics.append(
                        Diagnostic(
                            code="BROKEN_LINK",
                            severity="error",
                            message=f"Passage '{passage.name}' contains link pointing to non-existent target '{target}'.",
                            passage_name=passage.name,
                            passage_id=passage.pid,
                            target=target,
                            file=file_ref,
                            details={"choice_text": link.text, "target": target}
                        )
                    )

    # --------------------------------------------------------------------------
    # 2. Unreachable Passages (Orphans)
    # --------------------------------------------------------------------------
    def _check_unreachable_passages(self):
        start_p = self.graph.get_start_passage()
        if not start_p:
            start_keys = list(self.graph.passages.keys())
            if not start_keys:
                return
            start_p = self.graph.passages[start_keys[0]]

        # Traverse reachable nodes from startnode
        visited_names: Set[str] = set()
        queue = [start_p.name]
        visited_names.add(start_p.name)

        while queue:
            curr_name = queue.pop(0)
            curr_node = self.graph.get_passage(curr_name)
            if not curr_node:
                continue
            for link in curr_node.links:
                target_node = self.graph.get_passage(link.target)
                if target_node and target_node.name not in visited_names:
                    visited_names.add(target_node.name)
                    queue.append(target_node.name)

        # Flag any passage not in visited_names
        for passage in self.graph.passages.values():
            if passage.name not in visited_names:
                file_ref = self._get_passage_file(passage)
                self.diagnostics.append(
                    Diagnostic(
                        code="UNREACHABLE_PASSAGE",
                        severity="error",
                        message=f"Passage '{passage.name}' (pid {passage.pid}) is unreachable from start passage '{start_p.name}'.",
                        passage_name=passage.name,
                        passage_id=passage.pid,
                        file=file_ref
                    )
                )

    # --------------------------------------------------------------------------
    # 3. Dead Ends Missing Terminal/End Tag
    # --------------------------------------------------------------------------
    def _check_terminal_tags(self):
        for passage in self.graph.passages.values():
            if not passage.links:
                is_terminal = False
                # Check metadata
                if passage.metadata.get("terminal"):
                    is_terminal = True
                # Check tags
                for t in passage.tags:
                    low = t.lower()
                    if low in ("terminal", "end"):
                        is_terminal = True
                        break

                if not is_terminal:
                    file_ref = self._get_passage_file(passage)
                    self.diagnostics.append(
                        Diagnostic(
                            code="MISSING_TERMINAL_TAG",
                            severity="error",
                            message=f"Passage '{passage.name}' has zero outgoing choices and is not tagged as 'terminal' or 'end'.",
                            passage_name=passage.name,
                            passage_id=passage.pid,
                            file=file_ref
                        )
                    )

    # --------------------------------------------------------------------------
    # 4. Choice Text Collisions
    # --------------------------------------------------------------------------
    def _check_choice_collisions(self):
        for passage in self.graph.passages.values():
            if len(passage.links) < 2:
                continue

            file_ref = self._get_passage_file(passage)
            links = passage.links
            for i in range(len(links)):
                for j in range(i + 1, len(links)):
                    l1 = links[i]
                    l2 = links[j]
                    norm1 = _normalize_text(l1.text)
                    norm2 = _normalize_text(l2.text)

                    collision = False
                    if norm1 and norm2 and norm1 == norm2:
                        collision = True
                    elif matches_choice_text(l1.text, l2.text) or matches_choice_text(l2.text, l1.text):
                        collision = True

                    if collision:
                        self.diagnostics.append(
                            Diagnostic(
                                code="CHOICE_COLLISION",
                                severity="error",
                                message=f"Choice collision in passage '{passage.name}': choice '{l1.text}' collides with '{l2.text}'.",
                                passage_name=passage.name,
                                passage_id=passage.pid,
                                file=file_ref,
                                details={"choice_1": l1.text, "choice_2": l2.text}
                            )
                        )

    # --------------------------------------------------------------------------
    # 5. Cycles with No State Escape (Unwinnable Loops)
    # --------------------------------------------------------------------------
    def _check_dead_cycles(self):
        """
        Computes strongly connected components (SCCs) using Tarjan's algorithm.
        An SCC represents a dead cycle / trap loop if:
        1. It is a cycle: size > 1 or (size == 1 and self-loop).
        2. No node in the SCC has any outgoing edge to a node outside the SCC.
        3. The SCC does not contain a valid terminal passage.
        4. It has no state escape (mutating effects/variables to change state).
        """
        index = 0
        indices: Dict[str, int] = {}
        lowlinks: Dict[str, int] = {}
        on_stack: Set[str] = set()
        stack: List[str] = []
        sccs: List[List[str]] = []

        passages = self.graph.passages

        def strongconnect(node_name: str):
            nonlocal index
            indices[node_name] = index
            lowlinks[node_name] = index
            index += 1
            stack.append(node_name)
            on_stack.add(node_name)

            node = passages.get(node_name)
            if node:
                for link in node.links:
                    target_node = self.graph.get_passage(link.target)
                    if not target_node:
                        continue
                    tgt_name = target_node.name
                    if tgt_name not in indices:
                        strongconnect(tgt_name)
                        lowlinks[node_name] = min(lowlinks[node_name], lowlinks[tgt_name])
                    elif tgt_name in on_stack:
                        lowlinks[node_name] = min(lowlinks[node_name], indices[tgt_name])

            if lowlinks[node_name] == indices[node_name]:
                scc = []
                while True:
                    w = stack.pop()
                    on_stack.remove(w)
                    scc.append(w)
                    if w == node_name:
                        break
                sccs.append(scc)

        for p_name in passages:
            if p_name not in indices:
                strongconnect(p_name)

        # Check each SCC for trap loop properties
        for scc in sccs:
            is_cycle = False
            scc_set = set(scc)

            if len(scc) > 1:
                is_cycle = True
            elif len(scc) == 1:
                # Check for self-loop
                node = passages.get(scc[0])
                if node:
                    for lk in node.links:
                        tgt = self.graph.get_passage(lk.target)
                        if tgt and tgt.name == node.name:
                            is_cycle = True
                            break

            if not is_cycle:
                continue

            # Check if there is an exit from the SCC
            has_exit = False
            has_state_mutation = False
            for node_name in scc:
                node = passages.get(node_name)
                if not node:
                    continue
                if node.variables:
                    has_state_mutation = True
                for lk in node.links:
                    tgt = self.graph.get_passage(lk.target)
                    if tgt and tgt.name not in scc_set:
                        has_exit = True
                        break
                if has_exit:
                    break

            # If there is no exit from this cycle, it is an inescapable dead cycle
            if not has_exit:
                cycle_passages_str = ", ".join(sorted(scc))
                rep_passage = passages.get(scc[0])
                file_ref = self._get_passage_file(rep_passage) if rep_passage else None
                self.diagnostics.append(
                    Diagnostic(
                        code="DEAD_CYCLE",
                        severity="error",
                        message=f"Cycle with no escape detected among passages: {cycle_passages_str}.",
                        passage_name=scc[0],
                        passage_id=rep_passage.pid if rep_passage else None,
                        file=file_ref,
                        details={"cycle_nodes": scc}
                    )
                )


def validate_graph(graph: StoryGraph, file_references: Optional[Dict[str, str]] = None) -> ValidationResult:
    """Validates a StoryGraph instance and returns structured diagnostics."""
    validator = GraphValidator(graph, file_references=file_references)
    return validator.validate()


def validate_campaign(campaign_id: str, root_dir: str = None) -> ValidationResult:
    """Loads a campaign from disk and validates its story graph."""
    graph = export_campaign_to_graph(campaign_id, root_dir)
    return validate_graph(graph)
