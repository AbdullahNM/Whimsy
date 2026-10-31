import re
from typing import Optional, Dict, Any

class StateParser:
    """
    Authoritative parser for GM Turn Resolutions:
    - [XP RESOLUTION: ...]
    - [CURRENCY RESOLUTION: ...]
    - [SYS: Turn X | ...]
    """

    @staticmethod
    def parse_xp_resolution(text: str) -> Optional[Dict[str, Any]]:
        # Pattern: [XP RESOLUTION: Previous: 295 | Delta: +20 (...) | New Total: 315 / 500]
        pattern = r'\[XP RESOLUTION:\s*Previous:\s*(\d+)\s*\|\s*Delta:\s*([+\-]?\d+)(?:\s*\((.*?)\))?\s*\|\s*New Total:\s*(\d+)\s*\/\s*(\d+)\]'
        match = re.search(pattern, text, re.IGNORECASE)
        if match:
            return {
                "previous": int(match.group(1)),
                "delta": int(match.group(2)),
                "reason": match.group(3).strip() if match.group(3) else None,
                "current": int(match.group(4)),
                "threshold": int(match.group(5))
            }
        # Fallback simpler regex
        fallback = re.search(r'\[XP RESOLUTION:.*?New Total:\s*(\d+)\s*\/\s*(\d+)\]', text, re.IGNORECASE)
        if fallback:
            return {
                "current": int(fallback.group(1)),
                "threshold": int(fallback.group(2))
            }
        return None

    @staticmethod
    def parse_currency_resolution(text: str) -> Optional[Dict[str, Any]]:
        # Pattern: [CURRENCY RESOLUTION: Previous: X | Delta: ±Y (Reason) | New Purse: Z]
        pattern = r'\[CURRENCY RESOLUTION:\s*Previous:\s*([^\|]+)\|\s*Delta:\s*([^\|]+)\|\s*New Purse:\s*([^\]]+)\]'
        match = re.search(pattern, text, re.IGNORECASE)
        if match:
            return {
                "previous": match.group(1).strip(),
                "delta": match.group(2).strip(),
                "new_purse": match.group(3).strip()
            }
        # Fallback simpler regex
        fallback = re.search(r'\[CURRENCY RESOLUTION:.*?New Purse:\s*([^\]]+)\]', text, re.IGNORECASE)
        if fallback:
            return {"new_purse": fallback.group(1).strip()}
        return None

    @staticmethod
    def parse_system_block(text: str) -> Optional[Dict[str, Any]]:
        # Pattern: [SYS: Turn X | Lvl Y | XP Z/Threshold | Purse: ... | Strain ... | ...]
        pattern = r'\[SYS:\s*(.*?)\]'
        match = re.search(pattern, text, re.IGNORECASE)
        if match:
            raw_block = match.group(1)
            parts = [p.strip() for p in raw_block.split('|')]
            data = {"raw": raw_block}
            for p in parts:
                if p.lower().startswith("turn"):
                    num = re.search(r'\d+', p)
                    if num: data["turn"] = int(num.group(0))
                elif p.lower().startswith("lvl") or p.lower().startswith("level"):
                    num = re.search(r'\d+', p)
                    if num: data["level"] = int(num.group(0))
                elif p.lower().startswith("strain"):
                    s = re.search(r'([0-9\/]+)', p)
                    if s: data["strain"] = s.group(1)
            return data
        return None

    @classmethod
    def apply_state_mutations(cls, text: str, status_md: str, items_md: str) -> tuple[str, str, bool]:
        """
        Parses deltas from GM output and mutates status.md and items.md text.
        Returns (new_status_md, new_items_md, was_modified).
        """
        modified = False
        new_status = status_md
        new_items = items_md

        xp_data = cls.parse_xp_resolution(text)
        if xp_data and "current" in xp_data:
            # Update XP in status.md: handles "XP: ...", "**XP**: ...", or "**XP: ...**"
            new_xp_str = f"{xp_data['current']} / {xp_data['threshold']}"
            new_status = re.sub(
                r'(\bXP\*{0,2}:\s*)\d+\s*\/\s*\d+',
                rf'\g<1>{new_xp_str}',
                new_status,
                flags=re.IGNORECASE
            )
            modified = True

        curr_data = cls.parse_currency_resolution(text)
        if curr_data and "new_purse" in curr_data:
            new_purse = curr_data["new_purse"]
            # Update Purse in items.md
            new_items = re.sub(
                r'(\*\*Current Coin\*\*:\s*`)[^`]+(`)',
                rf'\g<1>{new_purse}\g<2>',
                new_items,
                flags=re.IGNORECASE
            )
            modified = True

        sys_data = cls.parse_system_block(text)
        if sys_data and "strain" in sys_data:
            new_strain = sys_data["strain"]
            new_status = re.sub(
                r'(\bStrain(?:\s*Buffer)?\*{0,2}:\s*)[0-9\/\s]+',
                rf'\g<1>{new_strain}',
                new_status,
                flags=re.IGNORECASE
            )
            modified = True

        return new_status, new_items, modified

    @classmethod
    def apply_state_mutations_json(cls, text: str, status_data: Dict[str, Any]) -> tuple[Dict[str, Any], bool]:
        """
        Parses deltas from GM output and mutates status.json dictionary.
        Returns (updated_status_data, was_modified).
        """
        import copy
        modified = False
        data = copy.deepcopy(status_data)

        xp_data = cls.parse_xp_resolution(text)
        if xp_data:
            if "progression" in data:
                if "current" in xp_data:
                    data["progression"]["xp"] = xp_data["current"]
                    modified = True
                if "threshold" in xp_data:
                    data["progression"]["xp_threshold"] = xp_data["threshold"]
                    modified = True

        curr_data = cls.parse_currency_resolution(text)
        if curr_data and "new_purse" in curr_data:
            new_purse = curr_data["new_purse"]
            if "purse" in data:
                data["purse"]["display"] = new_purse
                # Attempt to parse breakdown if campaign currency format (e.g. "3G 6S 20C") or credits
                gold_match = re.search(r'(\d+)\s*(?:G|Gold|Crown)', new_purse, re.I)
                silver_match = re.search(r'(\d+)\s*(?:S|Silver|Mark)', new_purse, re.I)
                copper_match = re.search(r'(\d+)\s*(?:C|Copper|Cog)', new_purse, re.I)
                credits_match = re.search(r'(\d+)\s*(?:₡|Credits?)\b|^\s*(\d+)\s*₡', new_purse, re.I)
                if gold_match: data["purse"]["gold"] = int(gold_match.group(1))
                if silver_match: data["purse"]["silver"] = int(silver_match.group(1))
                if copper_match: data["purse"]["copper"] = int(copper_match.group(1))
                if credits_match:
                    cred_val = credits_match.group(1) or credits_match.group(2)
                    data["purse"]["credits"] = int(cred_val)
                modified = True

        sys_data = cls.parse_system_block(text)
        if sys_data:
            if "turn" in sys_data:
                data["turn"] = sys_data["turn"]
                modified = True
            if "level" in sys_data and "progression" in data:
                data["progression"]["level"] = sys_data["level"]
                modified = True
            if "strain" in sys_data and "progression" in data:
                strain_parts = str(sys_data["strain"]).split('/')
                try:
                    val = int(strain_parts[0])
                    # Dynamically detect active strain key (ocular_strain, mana_strain, stress, etc.)
                    strain_key = None
                    for candidate in ["ocular_strain", "mana_strain", "stress", "strain"]:
                        if candidate in data["progression"]:
                            strain_key = candidate
                            break
                    if not strain_key:
                        strain_key = "mana_strain"
                    data["progression"][strain_key] = val
                    if len(strain_parts) > 1:
                        data["progression"]["strain_max"] = int(strain_parts[1])
                    modified = True
                except ValueError:
                    pass

        return data, modified

