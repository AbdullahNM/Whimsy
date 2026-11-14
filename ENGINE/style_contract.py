#!/usr/bin/env python3
"""
ENGINE/style_contract.py
========================
Persistent Language & Style Contract Validator and Linter for CYOA Turns.
Ensures generated prose maintains natural, grounded everyday language without
narrative degradation, run-on sentences, modern STEM/calculus jargon, decorative
micro-SFX, narrator praise, or formulaic turn closings.
"""

import os
import re
import json
from typing import Any, Dict, List, Optional, Tuple


class StyleContractValidator:
    """
    Validates narrative prose against campaign style contracts and anti-degradation rules.
    """

    DEFAULT_CONFIG = {
        "mode": "natural_everyday_english",
        "max_sentence_words": 35,
        "max_avg_sentence_words": 28,
        "prohibited_patterns": [],
        "ban_stem_calculus_jargon": True,
        "ban_decorative_microsfx": True,
        "ban_forced_cliffhangers": True,
        "ban_narrator_praise": True,
        "ban_formulaic_closings": True,
    }

    # 1. Banned modern STEM / calculus / physics jargon
    STEM_JARGON_PATTERNS = [
        r"\breynolds\s+quotients?\b",
        r"\blambda\b",
        r"\bimpedance\b",
        r"\bshunt\s+tolerances?\b",
        r"\bsecond-order\s+terms?\b",
        r"\bsecond\s+order\s+terms?\b",
        r"\bdecay\s+constants?\b",
        r"\blatency\b",
        r"\btelemetry\b",
        r"\bcircuit\s+topolog(?:y|ies)\b",
        r"\bnetwork\s+throughput\b",
        r"\bfailure\s+domains?\b",
        r"\beigenvalues?\b",
        r"\beigenvectors?\b",
        r"\bdifferential\s+equations?\b",
        r"\bnavier-stokes\b",
        r"\bhamiltonian\b",
        r"\bquantum\s+decoherence\b",
        r"\bthermodynamic\s+efficiency\b",
        r"\bkinetic\s+vectors?\b",
        r"\bdeceleration\s+multipliers?\b",
        r"\b\d+\.\d+\s*(?:index|factor|multiplier)\b",
        r"\b(?:fifty|twenty|thirty|forty|sixty|seventy|eighty|ninety|\d+)\s+percent\s+harder\b",
    ]

    # 2. Banned decorative micro-SFX in mundane scenes
    DECORATIVE_MICRO_SFX_PATTERNS = [
        r"\bsparks?\s+(?:danced|dancing|crackled|flickered|leaped|jumped)\s+(?:on|across|from)\s+(?:the|your|his|her|their)\s+fork\b",
        r"\bsparks?\s+(?:danced|dancing|crackled|flickered|leaped|jumped)\b",
        r"\b(?:the\s+)?(?:room|walls?|ground|floor)\s+(?:trembled|shook|quivered|vibrated)\b",
        r"\bair\s+(?:grew\s+heavy|grew\s+thick|crackled|hummed|thrummed|thickened)\s+with\s+(?:unspoken\s+power|power|energy|raw\s+power|mana|tension)\b",
        r"\b(?:knuckles?|fingers?|eyes?|hands?)\s+(?:glowed|flared|crackled)\s+with\s+(?:power|energy|light|sparks)\b",
        r"\b(?:fist|hand)\s+slammed\s+(?:the\s+table|down),\s*(?:shaking|trembling|splintering)\b",
        r"\benergy\s+sparking\s+off\s+(?:the|your|his|her)\s+fork\b",
        r"\belemental\s+energy\s+sparking\b",
        r"\baura\s+(?:flared|flickered|pulsed)\s+(?:menacingly|dangerously|brightly)\b",
    ]

    # 3. Banned narrator praise / editorializing
    NARRATOR_PRAISE_PATTERNS = [
        r"\bwith\s+breathtaking\s+prowess\b",
        r"\bbreathtaking\s+prowess\b",
        r"\bbreathtaking\s+(?:skill|grace|speed|mastery)\b",
        r"\blike\s+a\s+true\s+prodigy\b",
        r"\btrue\s+prodigy\b",
        r"\bprodigious\s+talent\b",
        r"\bunbeknownst\s+to\s+(?:them|him|her|all|anyone)\b",
        r"\blittle\s+did\s+(?:they|he|she|anyone)\s+know\b",
        r"\ba\s+testament\s+to\s+(?:your|his|her|their)\s+(?:genius|prowess|might|greatness)\b",
        r"\bwith\s+(?:flawless|peerless|superhuman|unmatched|effortless)\s+(?:grace|skill|speed|precision|mastery|brilliance)\b",
        r"\bin\s+an\s+awe-inspiring\s+display\b",
        r"\byour\s+sheer\s+brilliance\b",
        r"\blike\s+a\s+seasoned\s+master\b",
        r"\bnone\s+could\s+(?:rival|match)\b",
    ]

    # 4. Banned repetitive formulaic turn closings
    FORMULAIC_CLOSINGS_PATTERNS = [
        r"\bthe\s+choice\s+is\s+yours(?:\.{2,3}|!|\?)?",
        r"\bwhat\s+will\s+you\s+do\b\??",
        r"\bwhat\s+do\s+you\s+do\b\??",
        r"\bthe\s+decision\s+is\s+yours\b",
        r"\bhow\s+will\s+you\s+proceed\b\??",
        r"\bhow\s+do\s+you\s+respond\b\??",
        r"\bwhat\s+(?:path|step|choice)\s+will\s+you\s+(?:take|choose|make)\b\??",
        r"\bwhere\s+will\s+your\s+journey\s+take\s+you\b\??",
        r"\bwhat\s+choice\s+will\s+you\s+make\b\??",
    ]

    # 5. Forced cliffhangers in non-climax scenes
    FORCED_CLIFFHANGER_PATTERNS = [
        r"\bsuddenly,\s*everything\s+went\s+(?:black|dark)(?:\.{2,3}|!|\?)?",
        r"\bjust\s+when\s+you\s+thought\s+it\s+was\s+safe\b",
        r"\bbefore\s+you\s+could\s+(?:react|breathe|move|speak),\s*(?:disaster\s+struck|a\s+sudden|an\s+explosion|the\s+floor|the\s+ceiling)\b",
        r"\bto\s+be\s+continued(?:\.{2,3}|!|\?)?",
        r"\ba\s+terrifying\s+roar\s+shook\s+the\s+building,\s*but\s+before\s+you\s+could\s+see\s+what\s+it\s+was\b",
        r"\blittle\s+did\s+you\s+know,\s*this\s+was\s+only\s+the\s+beginning\s+of\s+the\s+nightmare\b",
        r"\bjust\s+then,\s*an\s+unexpected\s+shadow\s+lunged\b",
        r"\bout\s+of\s+nowhere,\s*an\s+enemy\s+appeared\b",
    ]

    def __init__(self, config: Optional[dict] = None):
        self.config = dict(self.DEFAULT_CONFIG)
        if config:
            self.config.update(config)

    @classmethod
    def from_campaign(cls, campaign_name: str, root_dir: str = ".") -> "StyleContractValidator":
        """Load StyleContractValidator initialized with campaign_config.json's style_contract."""
        config_path = os.path.join(root_dir, "CAMPAIGNS", campaign_name, "campaign_config.json")
        if os.path.exists(config_path):
            try:
                with open(config_path, "r", encoding="utf-8") as f:
                    data = json.load(f)
                    style_cfg = data.get("style_contract")
                    if isinstance(style_cfg, dict):
                        return cls(style_cfg)
            except Exception:
                pass
        return cls()

    @classmethod
    def validate(cls, text: str, config: Optional[dict] = None, outcome: Optional[Any] = None) -> Tuple[bool, List[str], float]:
        """Convenience class method to validate prose with optional config and outcome."""
        return cls(config).validate_prose(text, outcome=outcome)

    def validate_prose(
        self,
        text: Any = None,
        config: Optional[dict] = None,
        outcome: Optional[Any] = None
    ) -> Tuple[bool, List[str], float]:
        """
        Validates prose text. Can be called either as an instance method:
            validator.validate_prose(text, config=None, outcome=None)
        or directly as:
            StyleContractValidator.validate_prose(text, config=None, outcome=None)
        Returns (is_compliant: bool, violations: list[str], score: float).
        """
        if not isinstance(self, StyleContractValidator):
            # Called directly on class without instantiation: StyleContractValidator.validate_prose(text, config, outcome)
            actual_text = self
            actual_config = text if isinstance(text, dict) else config
            validator = StyleContractValidator(actual_config)
            return validator.validate_prose(actual_text, outcome=outcome)

        effective_config = dict(self.config)
        if isinstance(config, dict):
            effective_config.update(config)

        return self._run_validation(str(text or ""), effective_config, outcome=outcome)

    def _extract_prose_sentences(self, text: str) -> List[str]:
        """
        Separates pure narrative prose from markdown headers, system receipts,
        and typable choice lists.
        """
        cleaned_lines = []
        for line in text.splitlines():
            trimmed = line.strip()
            if not trimmed:
                continue
            # Skip system status and resolution blocks
            if (
                trimmed.startswith("[SYS:")
                or trimmed.startswith("[XP RESOLUTION:")
                or trimmed.startswith("[CURRENCY RESOLUTION:")
                or (trimmed.startswith("[") and trimmed.endswith("]"))
            ):
                continue
            # Skip options headers and numbered choices
            if (
                trimmed.startswith("### [OPTIONS")
                or trimmed.startswith("### OPTIONS")
                or re.match(r"^\d+\.\s+", trimmed)
            ):
                continue
            # Skip markdown headers
            if re.match(r"^#{1,6}\s+", trimmed):
                continue
            cleaned_lines.append(trimmed)

        cleaned_text = " ".join(cleaned_lines)
        if not cleaned_text:
            return []

        # Split sentences by terminators (. ! ?)
        raw_sentences = re.split(r"(?<=[.!?])\s+", cleaned_text)
        sentences = [s.strip() for s in raw_sentences if s.strip()]
        return sentences

    @staticmethod
    def _find_non_overlapping_matches(patterns: List[str], text: str) -> List[str]:
        """Find matches from patterns, preferring longer and non-overlapping matches."""
        all_matches = []
        for pat in patterns:
            for m in re.finditer(pat, text, re.IGNORECASE):
                all_matches.append((m.start(), m.end(), m.group(0)))

        # Sort by start asc, then length desc
        all_matches.sort(key=lambda x: (x[0], -(x[1] - x[0])))

        selected = []
        last_end = -1
        for start, end, match_str in all_matches:
            if start >= last_end:
                selected.append(match_str)
                last_end = end
        return selected

    def _run_validation(self, text: str, config: dict, outcome: Optional[Any] = None) -> Tuple[bool, List[str], float]:
        violations: List[str] = []

        # 1. STEM / Calculus / Physics jargon check
        if config.get("ban_stem_calculus_jargon", True):
            matches = self._find_non_overlapping_matches(self.STEM_JARGON_PATTERNS, text)
            for m in matches:
                violations.append(f"Prohibited STEM/calculus jargon detected: '{m}'")

        # 2. Decorative micro-SFX check
        if config.get("ban_decorative_microsfx", True):
            matches = self._find_non_overlapping_matches(self.DECORATIVE_MICRO_SFX_PATTERNS, text)
            for m in matches:
                violations.append(f"Decorative micro-SFX detected: '{m}'")

        # 3. Narrator praise / editorializing check
        if config.get("ban_narrator_praise", True):
            matches = self._find_non_overlapping_matches(self.NARRATOR_PRAISE_PATTERNS, text)
            for m in matches:
                violations.append(f"Narrator praise/editorializing detected: '{m}'")

        # 4. Formulaic turn closings check
        if config.get("ban_formulaic_closings", True):
            matches = self._find_non_overlapping_matches(self.FORMULAIC_CLOSINGS_PATTERNS, text)
            for m in matches:
                violations.append(f"Formulaic turn closing detected: '{m}'")

        # 5. Forced cliffhangers check
        if config.get("ban_forced_cliffhangers", True):
            matches = self._find_non_overlapping_matches(self.FORCED_CLIFFHANGER_PATTERNS, text)
            for m in matches:
                violations.append(f"Forced cliffhanger detected: '{m}'")

        # 6. Prohibited custom patterns from config
        custom_patterns = config.get("prohibited_patterns", [])
        if isinstance(custom_patterns, list):
            for pat in custom_patterns:
                if not pat:
                    continue
                try:
                    matches = re.findall(pat, text, re.IGNORECASE)
                    for m in matches:
                        violations.append(f"Prohibited custom pattern detected: '{m}'")
                except re.error:
                    # Fallback to literal substring match
                    if pat.lower() in text.lower():
                        violations.append(f"Prohibited custom pattern detected: '{pat}'")

        # 7. Sentence length checks (prose sentences only)
        max_words = config.get("max_sentence_words", 35)
        max_avg_words = config.get("max_avg_sentence_words", 28)
        sentences = self._extract_prose_sentences(text)

        word_counts = []
        for s in sentences:
            words = [w for w in s.split() if w]
            wc = len(words)
            word_counts.append(wc)
            if max_words and wc > max_words:
                preview = s if len(s) <= 60 else s[:57] + "..."
                violations.append(
                    f"Sentence exceeds max word limit ({wc} > {max_words} words): '{preview}'"
                )

        if len(word_counts) >= 2 and max_avg_words:
            avg_words = sum(word_counts) / len(word_counts)
            if avg_words > max_avg_words:
                violations.append(
                    f"Average sentence length ({avg_words:.1f} words) exceeds limit ({max_avg_words} words per sentence)"
                )

        # 8. Fourth-Wall Seal: State change verification against Outcome (R6)
        if outcome is not None:
            outcome_vios = self._validate_outcome_alignment(text, outcome)
            violations.extend(outcome_vios)

        # Compliance determination & score calculation
        if not violations:
            is_compliant = True
            score = 1.0
        else:
            is_compliant = False
            # Deduct score per violation, bounded in [0.0, 1.0]
            penalty = min(1.0, len(violations) * 0.15)
            score = max(0.0, round(1.0 - penalty, 2))

        return is_compliant, violations, score

    def _validate_outcome_alignment(self, text: str, outcome: Any) -> List[str]:
        """
        Validates that generated prose and receipts do not assert unearned or
        uncontained state changes absent from the authoritative Outcome.
        """
        from ENGINE.state_parser import StateParser

        vios = []
        if hasattr(outcome, "to_dict"):
            out_data = outcome.to_dict()
        elif isinstance(outcome, dict):
            out_data = outcome
        else:
            out_data = {}

        prog_delta = out_data.get("progression_delta") or {}
        res_delta = out_data.get("resources_delta") or {}

        # 1. Progression receipt check
        prog_receipt = StateParser.parse_progression_resolution(text)
        if prog_receipt and "delta" in prog_receipt:
            claimed_delta = prog_receipt["delta"]
            # Check against progression deltas in outcome
            matching = any(v == claimed_delta for v in prog_delta.values() if isinstance(v, (int, float)))
            if not matching and claimed_delta != 0:
                vios.append(
                    f"Fourth-wall seal violation: Prose asserts progression delta ({claimed_delta}) not contained in outcome"
                )

        # 2. Currency receipt check
        curr_receipt = StateParser.parse_currency_resolution(text)
        if curr_receipt and "delta" in curr_receipt:
            claimed_delta_str = str(curr_receipt["delta"]).strip()
            # If outcome has no currency deltas but receipt asserts a non-zero delta
            if not res_delta and claimed_delta_str and claimed_delta_str != "0":
                vios.append(
                    f"Fourth-wall seal violation: Prose asserts currency delta ({claimed_delta_str}) not contained in outcome"
                )

        # 3. Diegetic prose assertions of state changes
        assertion_checks = [
            (r"\b(?:gained|earned|received)\s+(\d+)\s*(?:xp|experience)\b", "xp"),
            (r"\b(?:gained|earned|received)\s+(\d+)\s*(?:credits?|gold|coins?)\b", "currency"),
            (r"\bleveled\s+up\b", "level")
        ]
        for pat, kind in assertion_checks:
            for m in re.finditer(pat, text, re.IGNORECASE):
                if kind == "xp":
                    val = int(m.group(1))
                    if prog_delta.get("xp", 0) != val:
                        vios.append(f"Fourth-wall seal violation: Prose asserts XP gain ({val}) not contained in outcome")
                elif kind == "currency":
                    val = int(m.group(1))
                    awarded = res_delta.get("credits", res_delta.get("gold", 0))
                    if awarded != val:
                        vios.append(f"Fourth-wall seal violation: Prose asserts currency gain ({val}) not contained in outcome")
                elif kind == "level":
                    if prog_delta.get("level", 0) <= 0:
                        vios.append("Fourth-wall seal violation: Prose asserts level up not contained in outcome")

        return vios
