#!/usr/bin/env python3
"""
ENGINE/evaluator.py
===================
Automated Evaluation Engine for Whimsy CYOA.
Implements direct scoring across 5 calibrated dimensions:
1. world_grounding
2. tactical_continuity
3. pacing_alignment
4. style_contract_adherence
5. shadow_gm_steering

Mitigates length bias (penalizes excessive verbosity without substance)
and position bias (order-invariance, option balance checks).
Produces structured EvaluationReport with per-dimension scores (1-5),
evidence citations, and specific critique/remedy.
"""

import os
import re
import json
from typing import Dict, Any, List, Optional, Tuple

try:
    from ENGINE.style_contract import StyleContractValidator
except ImportError:
    from style_contract import StyleContractValidator


class EvaluationReport:
    """Structured report produced by Evaluator evaluating a turn."""
    def __init__(
        self,
        turn_num: int,
        campaign_id: str,
        overall_score: float,
        dimension_scores: Dict[str, float],
        evidence: Dict[str, List[str]],
        critique: Dict[str, str],
        remedy: Dict[str, str],
        bias_adjustments: Dict[str, Any],
        raw_scores: Optional[Dict[str, float]] = None,
        rubric_id: str = "narrator_turn_evaluation_v1"
    ):
        self.turn_num = turn_num
        self.campaign_id = campaign_id
        self.overall_score = round(float(overall_score), 2)
        self.dimension_scores = {k: round(float(v), 2) for k, v in dimension_scores.items()}
        self.evidence = evidence
        self.critique = critique
        self.remedy = remedy
        self.bias_adjustments = bias_adjustments
        self.raw_scores = {k: round(float(v), 2) for k, v in (raw_scores or dimension_scores).items()}
        self.rubric_id = rubric_id

    def to_dict(self) -> Dict[str, Any]:
        return {
            "turn_num": self.turn_num,
            "campaign_id": self.campaign_id,
            "overall_score": self.overall_score,
            "dimension_scores": self.dimension_scores,
            "raw_scores": self.raw_scores,
            "evidence": self.evidence,
            "critique": self.critique,
            "remedy": self.remedy,
            "bias_adjustments": self.bias_adjustments,
            "rubric_id": self.rubric_id
        }

    def to_json(self, indent: int = 2) -> str:
        return json.dumps(self.to_dict(), indent=indent, ensure_ascii=False)


class Evaluator:
    """Evaluates narrative turns against the standardized evaluation rubric."""

    def __init__(self, root_dir: str):
        self.root_dir = root_dir
        self.rubric_path = os.path.join(root_dir, "GLOBAL", "RUBRICS", "narrator_evaluation_rubric.json")
        self.schema_path = os.path.join(root_dir, "GLOBAL", "SCHEMAS", "evaluation_rubric.schema.json")
        self.rubric = self._load_rubric()
        self.style_validator = StyleContractValidator()

    def _load_rubric(self) -> Dict[str, Any]:
        if os.path.exists(self.rubric_path):
            try:
                with open(self.rubric_path, "r", encoding="utf-8") as f:
                    return json.load(f)
            except Exception:
                pass
        return self._default_rubric()

    @staticmethod
    def _default_rubric() -> Dict[str, Any]:
        return {
            "rubric_id": "narrator_turn_evaluation_v1",
            "name": "Narrator Quality & Agent Calibration Rubric",
            "dimensions": [
                {"id": "world_grounding", "name": "World Grounding", "weight": 0.25},
                {"id": "tactical_continuity", "name": "Tactical Continuity", "weight": 0.25},
                {"id": "pacing_alignment", "name": "Pacing Alignment", "weight": 0.15},
                {"id": "style_contract_adherence", "name": "Style Contract Adherence", "weight": 0.20},
                {"id": "shadow_gm_steering", "name": "Shadow GM Steering", "weight": 0.15}
            ]
        }

    def _get_dimension_weights(self) -> Dict[str, float]:
        weights = {}
        for d in self.rubric.get("dimensions", []):
            weights[d["id"]] = float(d.get("weight", 0.2))
        total = sum(weights.values())
        if total > 0:
            return {k: v / total for k, v in weights.items()}
        return {k: 0.2 for k in ["world_grounding", "tactical_continuity", "pacing_alignment", "style_contract_adherence", "shadow_gm_steering"]}

    def _load_campaign_context(self, campaign_id: str) -> Dict[str, Any]:
        """Loads campaign files to supply context for evaluation."""
        context = {
            "known_entities": set(),
            "canon_secrets": [],
            "operational_mode": "classic_cyoa",
            "zoom_level": "detailed_scene",
            "narrative_intensity": 1,
            "scene_anchor": {},
            "upcoming_hooks": []
        }
        campaign_dir = os.path.join(self.root_dir, "CAMPAIGNS", campaign_id)
        if not os.path.isdir(campaign_dir) and os.path.isdir(campaign_id):
            campaign_dir = campaign_id

        if not os.path.isdir(campaign_dir):
            return context

        # 1. status.json
        status_path = os.path.join(campaign_dir, "GAMEPLAY", "status.json")
        if os.path.exists(status_path):
            try:
                with open(status_path, "r", encoding="utf-8") as f:
                    sdata = json.load(f)
                    context["operational_mode"] = sdata.get("operational_mode", "classic_cyoa")
                    pacing = sdata.get("pacing_state", {})
                    context["zoom_level"] = pacing.get("zoom_level", "detailed_scene")
                    context["narrative_intensity"] = pacing.get("narrative_intensity", 1)
                    context["scene_anchor"] = sdata.get("scene_anchor", {})
            except Exception:
                pass

        # 2. world_foundation.json
        wf_candidates = [
            os.path.join(campaign_dir, "WORLD_FOUNDATION", "world_foundation.json"),
            os.path.join(campaign_dir, "world_foundation.json")
        ]
        for wfc in wf_candidates:
            if os.path.exists(wfc):
                try:
                    with open(wfc, "r", encoding="utf-8") as f:
                        wfdata = json.load(f)
                        for fact in wfdata.get("immutable_facts", []):
                            if isinstance(fact, dict):
                                context["known_entities"].add(fact.get("subject", "").lower())
                        for faction in wfdata.get("factions", []):
                            if isinstance(faction, dict):
                                context["known_entities"].add(faction.get("name", "").lower())
                        for loc in wfdata.get("spatial_graph", {}).get("nodes", []):
                            if isinstance(loc, dict):
                                context["known_entities"].add(loc.get("name", "").lower())
                        for npc in wfdata.get("npc_knowledge_horizons", []):
                            if isinstance(npc, dict):
                                context["known_entities"].add(npc.get("npc_name", "").lower())
                        for sec in wfdata.get("canon_secrets", []):
                            if isinstance(sec, dict):
                                context["canon_secrets"].append(sec.get("truth", sec.get("title", "")))
                            elif isinstance(sec, str):
                                context["canon_secrets"].append(sec)
                except Exception:
                    pass
                break

        # 3. upcoming_hooks.md
        hooks_path = os.path.join(campaign_dir, "GAMEPLAY", "upcoming_hooks.md")
        if os.path.exists(hooks_path):
            try:
                with open(hooks_path, "r", encoding="utf-8") as f:
                    context["upcoming_hooks"] = [line.strip("- *").strip() for line in f if line.strip().startswith(("-", "*"))]
            except Exception:
                pass

        return context

    def _evaluate_world_grounding(
        self, response: str, context: Dict[str, Any]
    ) -> Tuple[float, List[str], str, str]:
        """Evaluates world grounding (adherence to facts, no leaked canon secrets)."""
        evidence = []
        score = 4.0
        critique = "Prose demonstrates grounded consistency with campaign setting."
        remedy = "Maintain strict NPC knowledge limits and consistent faction staging."

        # Check for leaked canon secrets
        secrets = context.get("canon_secrets", [])
        leaked = []
        for sec in secrets:
            if sec and len(sec) > 10 and sec.lower() in response.lower():
                leaked.append(sec)

        if leaked:
            score = 1.0
            evidence.append(f"Canon secret exposed unearned: '{leaked[0]}'")
            critique = "Critical lore leak: unearned exposure of hidden canon secret."
            remedy = "Redact canon secret from narrative; protagonist has not discovered discovery condition."
            return score, evidence, critique, remedy

        # Check references to known entities or setting anchors
        known = context.get("known_entities", set())
        found_entities = [e for e in known if e and e in response.lower()]
        if found_entities:
            evidence.append(f"Referenced established world entities: {', '.join(found_entities[:3])}")
            score = 5.0
            critique = "Vivid, seamless integration of campaign lore and entities."
            remedy = "Preserve consistent epistemic boundaries."
        else:
            # Check if generic or out of context
            anchor_loc = context.get("scene_anchor", {}).get("location")
            if anchor_loc and anchor_loc.lower() in response.lower():
                evidence.append(f"Maintained scene location anchor: '{anchor_loc}'")
                score = 4.0
            else:
                evidence.append("No explicit world entity citations found in response.")
                score = 3.0
                critique = "Adequately consistent, but setting details are somewhat generic."
                remedy = "Anchor sensory details explicitly to known factions, locations, or NPC perspectives."

        return score, evidence, critique, remedy

    def _evaluate_tactical_continuity(
        self, action: str, response: str
    ) -> Tuple[float, List[str], str, str]:
        """Evaluates causal outcome fidelity based on player's chosen action."""
        evidence = []
        clean_action = action.strip()
        if not clean_action:
            return 3.0, ["Empty player action supplied."], "No player action to evaluate continuity against.", "Supply explicit player intent."

        # Extract primary action keywords (nouns, verbs, ignoring common stopwords)
        stopwords = {"the", "a", "an", "and", "or", "to", "in", "on", "at", "with", "my", "your", "i", "of", "for", "into"}
        words = [w.lower().strip(".,!?:;'\"()") for w in clean_action.split() if len(w) > 2]
        action_keywords = [w for w in words if w not in stopwords]

        # Check occurrence in first 2-3 sentences of response
        sentences = re.split(r"(?<=[.!?])\s+", response)
        first_chunk = " ".join(sentences[:3]).lower() if sentences else response.lower()

        matched_keywords = [kw for kw in action_keywords if kw in first_chunk]
        full_response_matches = [kw for kw in action_keywords if kw in response.lower()]

        if len(matched_keywords) >= max(1, len(action_keywords) // 2):
            matched_sentence = next((s for s in sentences if any(kw in s.lower() for kw in action_keywords)), sentences[0] if sentences else response)
            evidence.append(f"Immediate causal reaction: '{matched_sentence.strip()}'")
            score = 5.0
            critique = "Direct, instantaneous causal resolution of player action."
            remedy = "Continue immediate causal anchoring."
        elif full_response_matches:
            matched_sentence = next((s for s in sentences if any(kw in s.lower() for kw in full_response_matches)), response[:100])
            evidence.append(f"Action resolved with delay: '{matched_sentence.strip()}'")
            score = 3.5
            critique = "Action is acknowledged but delayed in narrative sequence."
            remedy = "Resolve the physical outcome of the player's choice in the opening sentence."
        else:
            evidence.append(f"Action '{action}' lacked explicit causal echoes in response.")
            score = 1.5
            critique = "Disjointed narrative leap; player's stated action has negligible causal impact."
            remedy = "Directly reflect the outcome of the player's action before introducing new complications."

        return score, evidence, critique, remedy

    def _evaluate_pacing_alignment(
        self, response: str, context: Dict[str, Any]
    ) -> Tuple[float, List[str], str, str]:
        """Evaluates compliance with Adaptive Narrative Focus Controller zoom and intensity."""
        evidence = []
        target_zoom = context.get("zoom_level", "detailed_scene")
        target_intensity = context.get("narrative_intensity", 1)

        word_count = len(response.split())
        score = 4.0
        critique = f"Pacing aligns with {target_zoom} focus."
        remedy = "Maintain appropriate scene compression."

        # Zoom level checks
        if target_zoom == "detailed_scene":
            if word_count < 40:
                score = 2.0
                evidence.append(f"Detailed scene too brief ({word_count} words).")
                critique = "Scene lacks moment-to-moment sensory texture required for detailed focus."
                remedy = "Expand sensory details, dialogue, or micro-tactical actions."
            elif word_count > 600:
                score = 3.0
                evidence.append(f"Detailed scene is bloated ({word_count} words).")
                critique = "Scene drags without advancing state."
                remedy = "Prune repetitive descriptions and accelerate toward the decision point."
            else:
                score = 5.0
                evidence.append(f"Well-proportioned detailed scene ({word_count} words).")
        elif target_zoom in ["short_summary", "montage"]:
            if word_count > 300:
                score = 2.5
                evidence.append(f"{target_zoom} overly dilated ({word_count} words).")
                critique = f"{target_zoom} should compress time rather than provide exhaustive moment-to-moment play."
                remedy = f"Summarize intermediate actions and transitions briskly."
            else:
                score = 4.8
                evidence.append(f"Concise summary ({word_count} words) fitting {target_zoom}.")
        elif target_zoom == "time_skip":
            if word_count > 200:
                score = 2.0
                evidence.append(f"Time skip exceeds expected brevity ({word_count} words).")
                critique = "Time skip must jump forward cleanly without blow-by-blow narrative."
                remedy = "State the elapsed duration and transition directly to the next active focal beat."
            else:
                score = 5.0
                evidence.append(f"Crisp temporal jump ({word_count} words).")

        return score, evidence, critique, remedy

    def _evaluate_style_contract_adherence(
        self, response: str
    ) -> Tuple[float, List[str], str, str]:
        """Evaluates clean, grounded prose without purple prose, STEM jargon, or narrator praise."""
        evidence = []
        is_valid, violations, raw_score = self.style_validator.validate_prose(response)

        # Scale raw_score (0.0 to 1.0) to 1.0 to 5.0
        score = 1.0 + (raw_score * 4.0)

        if violations:
            evidence.extend(violations[:3])
            critique = f"Detected {len(violations)} style contract violation(s)."
            remedy = f"Eliminate violations: {violations[0]}."
        else:
            evidence.append("Prose strictly satisfies style contract with zero detected violations.")
            score = 5.0
            critique = "Grounded, atmospheric prose free of purple prose, jargon, and narrator praise."
            remedy = "Maintain natural, everyday sensory language."

        return round(score, 2), evidence, critique, remedy

    def _evaluate_shadow_gm_steering(
        self, response: str, context: Dict[str, Any]
    ) -> Tuple[float, List[str], str, str]:
        """Evaluates alignment with narrative trajectory without railroading."""
        evidence = []
        score = 4.0
        critique = "Presents balanced choices and respects player agency."
        remedy = "Keep offering meaningful, non-railroaded tactical alternatives."

        # Check for options presentation (numbered choices 1., 2., 3., 4.)
        options_found = re.findall(r"^\s*([1-4])\.\s+(.+)$", response, flags=re.MULTILINE)
        if options_found:
            count = len(options_found)
            evidence.append(f"Provided {count} structured choices for player agency.")
            if count >= 3:
                score = 5.0
            else:
                score = 3.5
                critique = "Limited choice diversity offered."
                remedy = "Present 3 to 4 distinct tactical alternatives."
        else:
            if "### [OPTIONS" in response or "OPTIONS" in response:
                score = 4.0
                evidence.append("Choice block present.")
            else:
                score = 2.5
                evidence.append("No explicit choice options found.")
                critique = "Turn does not clearly yield agency back to player with tactical options."
                remedy = "Include a clear, typable choices block with distinct courses of action."

        return score, evidence, critique, remedy

    def _mitigate_length_bias(
        self, response: str, raw_scores: Dict[str, float]
    ) -> Tuple[Dict[str, float], Dict[str, Any]]:
        """
        Mitigates length bias (penalizing excessive verbosity without substance).
        Rewards concise, high-substance prose; penalizes bloated fluff.
        """
        words = response.split()
        word_count = len(words)

        # Count substantive elements: concrete nouns, numbers, tactical verbs
        substance_markers = re.findall(
            r"\b(?:door|room|lock|key|terminal|blade|guard|hallway|datapad|corridor|crate|vault|alarm|step|turn|clock|strike|press|move|search|open|take|draw|fire|\d+)\b",
            response,
            flags=re.IGNORECASE
        )
        substance_density = len(substance_markers) / max(word_count, 1)

        adjusted_scores = dict(raw_scores)
        penalty = 0.0
        explanation = "Response length and substance density are within calibrated bounds."
        length_bias_detected = False

        # If excessively verbose with low substance density
        if word_count > 450 and substance_density < 0.04:
            length_bias_detected = True
            penalty = min(1.2, 0.4 + ((word_count - 450) / 300) * 0.5)
            explanation = f"Verbosity penalty applied: {word_count} words with low substance density ({substance_density:.3f})."
            for dim in ["pacing_alignment", "style_contract_adherence"]:
                if dim in adjusted_scores:
                    adjusted_scores[dim] = max(1.0, adjusted_scores[dim] - penalty)
        elif word_count <= 250 and substance_density >= 0.08:
            # Reward concise, tight substance
            explanation = f"Concise substance bonus: {word_count} words with high substance density ({substance_density:.3f})."
            if "pacing_alignment" in adjusted_scores:
                adjusted_scores["pacing_alignment"] = min(5.0, adjusted_scores["pacing_alignment"] + 0.2)

        adjustments = {
            "length_bias_detected": length_bias_detected,
            "word_count": word_count,
            "substance_density": round(substance_density, 4),
            "length_penalty": round(penalty, 2),
            "explanation": explanation
        }
        return adjusted_scores, adjustments

    def _mitigate_position_bias(
        self, response: str, adjusted_scores: Dict[str, float]
    ) -> Tuple[Dict[str, float], Dict[str, Any]]:
        """
        Mitigates position bias by verifying option balance across choices
        and ensuring order-invariant direct scoring.
        """
        options_found = re.findall(r"^\s*([1-4])\.\s+(.+)$", response, flags=re.MULTILINE)
        choice_balance = 1.0
        explanation = "Direct scoring is order-invariant across all evaluation dimensions."

        if len(options_found) >= 2:
            lengths = [len(opt[1].split()) for opt in options_found]
            avg_len = sum(lengths) / len(lengths)
            # If Option 1 is 3x longer than all other options combined, flag option 1 position skew
            if lengths[0] > (avg_len * 2.2) and lengths[0] > 20:
                choice_balance = 0.7
                explanation = "Position skew detected: Option 1 dominates choice length over alternative branches."
                if "shadow_gm_steering" in adjusted_scores:
                    adjusted_scores["shadow_gm_steering"] = max(1.0, adjusted_scores["shadow_gm_steering"] - 0.5)

        adjustments = {
            "order_invariant": True,
            "choice_balance_score": choice_balance,
            "explanation": explanation
        }
        return adjusted_scores, adjustments

    def evaluate_turn(
        self,
        campaign_id: str,
        turn_num: int,
        action: str,
        response: str,
        context: Optional[Dict[str, Any]] = None
    ) -> EvaluationReport:
        """
        Executes complete multi-dimensional turn evaluation with bias mitigation.
        """
        if context is None:
            context = self._load_campaign_context(campaign_id)

        # 1. Evaluate individual dimensions
        ev_wg, cite_wg, crit_wg, rem_wg = self._evaluate_world_grounding(response, context)
        ev_tc, cite_tc, crit_tc, rem_tc = self._evaluate_tactical_continuity(action, response)
        ev_pa, cite_pa, crit_pa, rem_pa = self._evaluate_pacing_alignment(response, context)
        ev_sc, cite_sc, crit_sc, rem_sc = self._evaluate_style_contract_adherence(response)
        ev_sg, cite_sg, crit_sg, rem_sg = self._evaluate_shadow_gm_steering(response, context)

        raw_scores = {
            "world_grounding": ev_wg,
            "tactical_continuity": ev_tc,
            "pacing_alignment": ev_pa,
            "style_contract_adherence": ev_sc,
            "shadow_gm_steering": ev_sg
        }

        evidence = {
            "world_grounding": cite_wg,
            "tactical_continuity": cite_tc,
            "pacing_alignment": cite_pa,
            "style_contract_adherence": cite_sc,
            "shadow_gm_steering": cite_sg
        }

        critique = {
            "world_grounding": crit_wg,
            "tactical_continuity": crit_tc,
            "pacing_alignment": crit_pa,
            "style_contract_adherence": crit_sc,
            "shadow_gm_steering": crit_sg
        }

        remedy = {
            "world_grounding": rem_wg,
            "tactical_continuity": rem_tc,
            "pacing_alignment": rem_pa,
            "style_contract_adherence": rem_sc,
            "shadow_gm_steering": rem_sg
        }

        # 2. Bias mitigation
        length_adjusted, length_bias_info = self._mitigate_length_bias(response, raw_scores)
        final_scores, position_bias_info = self._mitigate_position_bias(response, length_adjusted)

        bias_adjustments = {
            "length_bias": length_bias_info,
            "position_bias": position_bias_info
        }

        # 3. Compute weighted overall score
        weights = self._get_dimension_weights()
        overall_score = sum(final_scores.get(dim, 3.0) * weights.get(dim, 0.2) for dim in weights)

        return EvaluationReport(
            turn_num=turn_num,
            campaign_id=campaign_id,
            overall_score=overall_score,
            dimension_scores=final_scores,
            evidence=evidence,
            critique=critique,
            remedy=remedy,
            bias_adjustments=bias_adjustments,
            raw_scores=raw_scores,
            rubric_id=self.rubric.get("rubric_id", "narrator_turn_evaluation_v1")
        )
