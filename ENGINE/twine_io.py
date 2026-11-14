#!/usr/bin/env python3
"""
ENGINE/twine_io.py
==================
Twine-compatible story graph archive import, export, and model mapping.

Parses and emits Twine 2 HTML story archives containing <tw-storydata>
and <tw-passagedata> elements, maintaining story-format neutrality (Harlowe,
SugarCube, Chapbook, Snowman).

Implements Issue #15:
- R1: Twine Archive Import & Export
- R2: Model Mapping & Story-Format Neutrality
- R4: Round-trip Guarantee
- R7: Export driven from campaign's own files
"""

from dataclasses import dataclass, field, asdict
import html
from html.parser import HTMLParser
import json
import os
import re
import sys
import uuid
import glob
from typing import Any, Dict, List, Optional, Tuple, Union


# ==============================================================================
# DATA MODELS
# ==============================================================================

@dataclass
class StoryLink:
    """Represents an outgoing link / choice in a passage."""
    text: str
    target: str
    raw: str = ""

    def to_dict(self) -> Dict[str, Any]:
        d = {"text": self.text, "target": self.target}
        if self.raw:
            d["raw"] = self.raw
        return d

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "StoryLink":
        return cls(
            text=str(data.get("text", "")),
            target=str(data.get("target", "")),
            raw=str(data.get("raw", ""))
        )


@dataclass
class PassageNode:
    """Represents a single scene node / passage in the story graph."""
    pid: int
    name: str
    text: str
    tags: List[str] = field(default_factory=list)
    links: List[StoryLink] = field(default_factory=list)
    variables: Dict[str, Any] = field(default_factory=dict)
    metadata: Dict[str, Any] = field(default_factory=dict)
    position: Dict[str, float] = field(default_factory=lambda: {"x": 100.0, "y": 100.0})
    size: Dict[str, float] = field(default_factory=lambda: {"width": 100.0, "height": 100.0})
    warnings: List[str] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "pid": self.pid,
            "name": self.name,
            "text": self.text,
            "tags": list(self.tags),
            "links": [link.to_dict() for link in self.links],
            "variables": dict(self.variables),
            "metadata": dict(self.metadata),
            "position": dict(self.position),
            "size": dict(self.size),
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "PassageNode":
        links = [StoryLink.from_dict(lk) for lk in data.get("links", [])]
        pos = data.get("position", {"x": 100.0, "y": 100.0})
        sz = data.get("size", {"width": 100.0, "height": 100.0})
        return cls(
            pid=int(data.get("pid", 1)),
            name=str(data.get("name", "")),
            text=str(data.get("text", "")),
            tags=list(data.get("tags", [])),
            links=links,
            variables=dict(data.get("variables", {})),
            metadata=dict(data.get("metadata", {})),
            position={"x": float(pos.get("x", 100.0)), "y": float(pos.get("y", 100.0))},
            size={"width": float(sz.get("width", 100.0)), "height": float(sz.get("height", 100.0))},
            warnings=list(data.get("warnings", []))
        )


@dataclass
class StoryGraph:
    """Complete story graph containing passages and story-level metadata."""
    name: str
    startnode: str
    passages: Dict[str, PassageNode] = field(default_factory=dict)
    metadata: Dict[str, Any] = field(default_factory=dict)
    warnings: List[str] = field(default_factory=list)

    def add_passage(self, passage: PassageNode):
        self.passages[passage.name] = passage

    def get_passage(self, name_or_pid: Union[str, int]) -> Optional[PassageNode]:
        if str(name_or_pid) in self.passages:
            return self.passages[str(name_or_pid)]
        for p in self.passages.values():
            if str(p.pid) == str(name_or_pid) or p.name == str(name_or_pid):
                return p
        return None

    def get_start_passage(self) -> Optional[PassageNode]:
        return self.get_passage(self.startnode)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "schema_version": 1,
            "name": self.name,
            "startnode": str(self.startnode),
            "metadata": dict(self.metadata),
            "passages": [p.to_dict() for p in self.passages.values()]
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "StoryGraph":
        sg = cls(
            name=str(data.get("name", "Untitled Story")),
            startnode=str(data.get("startnode", "1")),
            metadata=dict(data.get("metadata", {}))
        )
        for pdata in data.get("passages", []):
            p = PassageNode.from_dict(pdata)
            sg.add_passage(p)
        return sg

    def to_json(self, indent: int = 2) -> str:
        return json.dumps(self.to_dict(), indent=indent, ensure_ascii=False)

    @classmethod
    def from_json(cls, json_str: str) -> "StoryGraph":
        return cls.from_dict(json.loads(json_str))


# ==============================================================================
# LINK, VARIABLE, AND METADATA EXTRACTORS
# ==============================================================================

def parse_passage_links(text: str) -> List[StoryLink]:
    """
    Extracts outgoing choices/links from passage text across Twine syntaxes:
    1. [[label->target]]
    2. [[target<-label]]
    3. [[label|target]]
    4. [[target]]
    5. <<link "label" "target">>
    6. <<link 'label' 'target'>>
    7. <<link "label" [[target]]>>
    8. <<link "target">>
    """
    links: List[StoryLink] = []
    seen = set()

    # SugarCube <<link ...>> patterns
    # <<link "label" "target">> or <<link 'label' 'target'>>
    sugarcube_two_arg = re.compile(
        r'<<link\s+["\']([^"\']+)["\']\s+["\']([^"\']+)["\']\s*>>',
        re.IGNORECASE
    )
    for m in sugarcube_two_arg.finditer(text):
        label = m.group(1).strip()
        target = m.group(2).strip()
        key = (label, target)
        if key not in seen:
            seen.add(key)
            links.append(StoryLink(text=label, target=target, raw=m.group(0)))

    # <<link "label" [[target]]>>
    sugarcube_bracket_arg = re.compile(
        r'<<link\s+["\']([^"\']+)["\']\s+\[\[(.*?)\]\]\s*>>',
        re.IGNORECASE
    )
    for m in sugarcube_bracket_arg.finditer(text):
        label = m.group(1).strip()
        target = m.group(2).strip()
        key = (label, target)
        if key not in seen:
            seen.add(key)
            links.append(StoryLink(text=label, target=target, raw=m.group(0)))

    # <<link "target">>
    sugarcube_one_arg = re.compile(
        r'<<link\s+["\']([^"\']+)["\']\s*>>',
        re.IGNORECASE
    )
    for m in sugarcube_one_arg.finditer(text):
        # Check if already matched by two-arg
        full_match = m.group(0)
        if any(full_match in lk.raw for lk in links):
            continue
        target = m.group(1).strip()
        key = (target, target)
        if key not in seen:
            seen.add(key)
            links.append(StoryLink(text=target, target=target, raw=m.group(0)))

    # Standard [[...]] wiki-link patterns
    wiki_link_pat = re.compile(r'\[\[(.*?)\]\]')
    for m in wiki_link_pat.finditer(text):
        inner = m.group(1).strip()
        raw = m.group(0)

        # Check if this [[...]] was part of a <<link ... [[...]]>>
        if any(raw in lk.raw for lk in links):
            continue

        if '->' in inner:
            parts = inner.split('->', 1)
            label = parts[0].strip()
            target = parts[1].strip()
        elif '<-' in inner:
            parts = inner.split('<-', 1)
            target = parts[0].strip()
            label = parts[1].strip()
        elif '|' in inner:
            parts = inner.split('|', 1)
            label = parts[0].strip()
            target = parts[1].strip()
        else:
            label = inner
            target = inner

        if target:
            key = (label, target)
            if key not in seen:
                seen.add(key)
                links.append(StoryLink(text=label, target=target, raw=raw))

    return links


def _parse_value(val_str: str) -> Any:
    """Parses a value string into a typed Python value."""
    s = val_str.strip()
    # String literal with quotes
    if (s.startswith('"') and s.endswith('"')) or (s.startswith("'") and s.endswith("'")):
        return s[1:-1]
    low = s.lower()
    if low == "true":
        return True
    if low == "false":
        return False
    if low == "null" or low == "none":
        return None
    # Integer
    if re.match(r'^-?\d+$', s):
        try:
            return int(s)
        except ValueError:
            pass
    # Float
    if re.match(r'^-?\d+\.\d+$', s):
        try:
            return float(s)
        except ValueError:
            pass
    return s


def parse_passage_variables(text: str) -> Dict[str, Any]:
    """
    Extracts variable modifications from passage text:
    - Harlowe: (set: $var to value)
    - SugarCube: <<set $var = value>> or <<set $var to value>>
    """
    variables: Dict[str, Any] = {}

    # SugarCube <<set $var = value>> / <<set $var to value>>
    sugarcube_set = re.compile(
        r'<<set\s+\$([a-zA-Z0-9_]+)\s*(?:=|to)\s*([^>]+?)>>',
        re.IGNORECASE
    )
    for m in sugarcube_set.finditer(text):
        var_name = m.group(1).strip()
        raw_val = m.group(2).strip()
        variables[var_name] = _parse_value(raw_val)

    # Harlowe (set: $var to value)
    harlowe_set = re.compile(
        r'\(set:\s*\$([a-zA-Z0-9_]+)\s+to\s+([^)]+?)\)',
        re.IGNORECASE
    )
    for m in harlowe_set.finditer(text):
        var_name = m.group(1).strip()
        raw_val = m.group(2).strip()
        variables[var_name] = _parse_value(raw_val)

    return variables


def parse_tags_metadata(tags: Union[str, List[str]]) -> Tuple[List[str], Dict[str, Any]]:
    """
    Parses a space-separated tag string or list of tags into a normalized
    tags list and a structured metadata dictionary.

    Mapping:
    - terminal, end -> metadata["terminal"] = True
    - mode:<mode> -> metadata["mode"] = mode
    - location:<loc> -> metadata["location"] = loc
    - faction:<fac> -> metadata["faction"] = fac
    - intensity:<num> -> metadata["intensity"] = int(num)
    - clock:<id> -> metadata["clocks"].append(id)
    """
    if isinstance(tags, str):
        tag_list = [t.strip() for t in tags.split() if t.strip()]
    else:
        tag_list = [str(t).strip() for t in tags if str(t).strip()]

    metadata: Dict[str, Any] = {}
    clocks: List[str] = []

    for tag in tag_list:
        low = tag.lower()
        if low in ("terminal", "end"):
            metadata["terminal"] = True
        elif ":" in tag:
            key, val = tag.split(":", 1)
            key = key.strip().lower()
            val = val.strip()
            if key == "location":
                metadata["location"] = val
            elif key == "faction":
                metadata["faction"] = val
            elif key == "mode":
                metadata["mode"] = val
            elif key == "intensity":
                try:
                    metadata["intensity"] = int(val)
                except ValueError:
                    metadata["intensity"] = val
            elif key in ("clock", "clock_id"):
                if val not in clocks:
                    clocks.append(val)
            else:
                metadata[key] = val
        else:
            # Other tag flags
            metadata.setdefault("flags", []).append(tag)

    if clocks:
        metadata["clocks"] = clocks

    return tag_list, metadata


def format_metadata_tags(metadata: Dict[str, Any], existing_tags: List[str] = None) -> List[str]:
    """Formats metadata dictionary back into a standardized list of Twine tags."""
    tags: List[str] = []
    seen = set()

    def add_tag(t: str):
        if t and t not in seen:
            seen.add(t)
            tags.append(t)

    # 1. Operational Mode
    if "mode" in metadata:
        add_tag(f"mode:{metadata['mode']}")

    # 2. Location
    if "location" in metadata:
        add_tag(f"location:{metadata['location']}")

    # 3. Faction
    if "faction" in metadata:
        add_tag(f"faction:{metadata['faction']}")

    # 4. Intensity
    if "intensity" in metadata:
        add_tag(f"intensity:{metadata['intensity']}")

    # 5. Clocks
    for clk in metadata.get("clocks", []):
        add_tag(f"clock:{clk}")

    # 6. Terminal tag
    if metadata.get("terminal"):
        add_tag("terminal")

    # 7. Preserve existing extra tags
    if existing_tags:
        for t in existing_tags:
            add_tag(t)

    return tags


def extract_unsupported_macro_warnings(text: str, passage_name: str) -> List[str]:
    """
    Detects macros that belong to specific formats (Harlowe, SugarCube) outside
    the portable subset (links and variable assignments).
    Returns descriptive warnings without modifying or dropping the macros.
    """
    warnings: List[str] = []

    # Supported SugarCube macros: link, /link, set, goto
    supported_sugarcube = {"link", "/link", "set", "goto"}
    sc_pattern = re.compile(r'<<(/?[a-zA-Z0-9_-]+)\b([^>]*)>>')
    for m in sc_pattern.finditer(text):
        macro_name = m.group(1).lower()
        if macro_name not in supported_sugarcube:
            warnings.append(
                f"Unsupported SugarCube macro '<<{m.group(1)}...>>' in passage '{passage_name}' preserved as narrative text."
            )

    # Supported Harlowe macros: set, link, link-reveal, link-goto
    supported_harlowe = {"set", "link", "link-reveal", "link-goto"}
    hl_pattern = re.compile(r'\(([a-zA-Z0-9_-]+):\s*([^)]*)\)')
    for m in hl_pattern.finditer(text):
        macro_name = m.group(1).lower()
        if macro_name not in supported_harlowe:
            warnings.append(
                f"Unsupported Harlowe macro '({m.group(1)}:...)' in passage '{passage_name}' preserved as narrative text."
            )

    return warnings


# ==============================================================================
# HTML PARSER & EMITTER
# ==============================================================================

def _parse_attributes(attr_str: str) -> Dict[str, str]:
    """Extracts key-value attributes from an HTML element attribute string."""
    attrs = {}
    pattern = re.compile(r'([a-zA-Z0-9_-]+)\s*=\s*(?:"([^"]*)"|\'([^\']*)\'|([^\s>]+))')
    for m in pattern.finditer(attr_str):
        key = m.group(1).lower()
        val = m.group(2) if m.group(2) is not None else (m.group(3) if m.group(3) is not None else m.group(4))
        attrs[key] = html.unescape(val or "")
    return attrs


def parse_twine_html(html_content: str) -> StoryGraph:
    """
    Parses a Twine 2 HTML archive string into a StoryGraph instance.
    Extracts <tw-storydata> and all <tw-passagedata> elements cleanly.
    """
    story_match = re.search(r'<tw-storydata\b([^>]*?)>', html_content, re.IGNORECASE)
    story_attrs = _parse_attributes(story_match.group(1)) if story_match else {}

    story_name = story_attrs.get("name", "Untitled Campaign")
    startnode = story_attrs.get("startnode", "1")
    metadata = {
        "creator": story_attrs.get("creator", "Whimsy"),
        "creator_version": story_attrs.get("creator-version", "1.0.0"),
        "format": story_attrs.get("format", "Harlowe"),
        "format_version": story_attrs.get("format-version", "3.3.9"),
        "ifid": story_attrs.get("ifid", str(uuid.uuid4()).upper()),
        "zoom": story_attrs.get("zoom", "1"),
        "options": story_attrs.get("options", "")
    }

    graph = StoryGraph(name=story_name, startnode=startnode, metadata=metadata)
    all_warnings: List[str] = []

    passage_pat = re.compile(r'<tw-passagedata\b([^>]*?)>(.*?)</tw-passagedata>', re.DOTALL | re.IGNORECASE)
    matches = list(passage_pat.finditer(html_content))

    for idx, match in enumerate(matches, start=1):
        pdata = _parse_attributes(match.group(1))
        pid = int(pdata.get("pid", idx))
        name = pdata.get("name", f"Passage {pid}")
        raw_tags = pdata.get("tags", "")
        tags_list, meta = parse_tags_metadata(raw_tags)
        raw_text = html.unescape(match.group(2))

        # Extract links, variables, warnings
        links = parse_passage_links(raw_text)
        variables = parse_passage_variables(raw_text)
        warnings = extract_unsupported_macro_warnings(raw_text, name)
        if warnings:
            all_warnings.extend(warnings)

        # Parse position and size
        pos_str = pdata.get("position", "100,100")
        try:
            px, py = [float(x.strip()) for x in pos_str.split(",")]
        except Exception:
            px, py = 100.0, 100.0

        size_str = pdata.get("size", "100,100")
        try:
            sw, sh = [float(x.strip()) for x in size_str.split(",")]
        except Exception:
            sw, sh = 100.0, 100.0

        node = PassageNode(
            pid=pid,
            name=name,
            text=raw_text,
            tags=tags_list,
            links=links,
            variables=variables,
            metadata=meta,
            position={"x": px, "y": py},
            size={"width": sw, "height": sh},
            warnings=warnings
        )
        graph.add_passage(node)

    graph.warnings = all_warnings
    return graph


def _compute_auto_layout(graph: StoryGraph) -> Dict[str, Tuple[float, float]]:
    """
    Computes a clean layered topological layout for passages without positions
    or when exporting a graph with default positions.
    """
    positions: Dict[str, Tuple[float, float]] = {}
    start_p = graph.get_start_passage()
    start_name = start_p.name if start_p else (list(graph.passages.keys())[0] if graph.passages else "")

    if not start_name:
        return positions

    # BFS layer assignment
    layers: Dict[str, int] = {start_name: 0}
    queue = [start_name]
    visited = {start_name}

    while queue:
        curr = queue.pop(0)
        curr_layer = layers[curr]
        node = graph.get_passage(curr)
        if node:
            for lk in node.links:
                target = lk.target
                if target in graph.passages and target not in visited:
                    visited.add(target)
                    layers[target] = curr_layer + 1
                    queue.append(target)

    # Any unreached passages placed in the last layer
    max_layer = max(layers.values()) if layers else 0
    for name in graph.passages:
        if name not in layers:
            max_layer += 1
            layers[name] = max_layer

    # Group by layer
    layer_groups: Dict[int, List[str]] = {}
    for name, lvl in layers.items():
        layer_groups.setdefault(lvl, []).append(name)

    # Compute coordinates (X = 100 + layer * 260, Y = 100 + idx * 160)
    for lvl in sorted(layer_groups.keys()):
        group = layer_groups[lvl]
        for idx, name in enumerate(group):
            x = 100.0 + lvl * 260.0
            y = 100.0 + idx * 160.0
            positions[name] = (x, y)

    return positions


def emit_twine_html(graph: StoryGraph) -> str:
    """
    Emits a standard Twine 2 HTML story archive document containing
    <tw-storydata> and <tw-passagedata> elements.
    """
    meta = graph.metadata or {}
    creator = meta.get("creator", "Whimsy")
    creator_ver = meta.get("creator_version", "1.0.0")
    s_format = meta.get("format", "Harlowe")
    format_ver = meta.get("format_version", "3.3.9")
    ifid = meta.get("ifid", str(uuid.uuid4()).upper())
    zoom = meta.get("zoom", "1")
    options = meta.get("options", "")

    # Resolve startnode
    start_p = graph.get_start_passage()
    startnode = str(start_p.pid if start_p else graph.startnode or "1")

    # Compute auto layout if positions are default
    has_custom_pos = any(
        p.position.get("x", 100) != 100 or p.position.get("y", 100) != 100
        for p in graph.passages.values()
    )
    auto_layout = {}
    if not has_custom_pos and len(graph.passages) > 1:
        auto_layout = _compute_auto_layout(graph)

    # Sort passages by pid
    passages_sorted = sorted(graph.passages.values(), key=lambda p: p.pid)

    passage_elements: List[str] = []
    for p in passages_sorted:
        # Determine position
        if p.name in auto_layout:
            pos_x, pos_y = auto_layout[p.name]
        else:
            pos_x = p.position.get("x", 100.0)
            pos_y = p.position.get("y", 100.0)

        pos_str = f"{int(pos_x)},{int(pos_y)}"
        size_str = f"{int(p.size.get('width', 100))},{int(p.size.get('height', 100))}"
        tags_str = " ".join(format_metadata_tags(p.metadata, p.tags))

        # Ensure text is properly escaped for HTML embedding
        escaped_text = html.escape(p.text, quote=False)
        escaped_name = html.escape(p.name, quote=True)
        escaped_tags = html.escape(tags_str, quote=True)

        elem = (
            f'<tw-passagedata pid="{p.pid}" name="{escaped_name}" '
            f'tags="{escaped_tags}" position="{pos_str}" size="{size_str}">'
            f'{escaped_text}</tw-passagedata>'
        )
        passage_elements.append(elem)

    passages_block = "\n".join(passage_elements)
    escaped_story_name = html.escape(graph.name, quote=True)

    html_doc = f"""<!DOCTYPE html>
<html>
<head>
<meta charset="utf-8">
<title>{escaped_story_name}</title>
</head>
<body>
<tw-storydata name="{escaped_story_name}" startnode="{startnode}" creator="{creator}" creator-version="{creator_ver}" format="{s_format}" format-version="{format_ver}" ifid="{ifid}" zoom="{zoom}" options="{options}" hidden>
<style role="stylesheet" id="twine-user-stylesheet" type="text/twine-css"></style>
<script role="script" id="twine-user-script" type="text/twine-javascript"></script>
{passages_block}
</tw-storydata>
</body>
</html>
"""
    return html_doc


# ==============================================================================
# CAMPAIGN EXPORT & IMPORT (R1 & R7)
# ==============================================================================

def _get_workspace_root(root_dir: str = None) -> str:
    if root_dir:
        return os.path.abspath(root_dir)
    current = os.path.dirname(os.path.abspath(__file__))
    return os.path.abspath(os.path.join(current, ".."))


def export_campaign_to_graph(campaign_id: str, root_dir: str = None) -> StoryGraph:
    """
    Constructs a StoryGraph from a campaign's existing files:
    - CAMPAIGNS/<campaign_id>/campaign_config.json
    - CAMPAIGNS/<campaign_id>/GAMEPLAY/status.json
    - CAMPAIGNS/<campaign_id>/GAMEPLAY/story_graph.json (if previously authored/imported)
    - CAMPAIGNS/<campaign_id>/TURNS/ACTIVE/ and TURNS/ARCHIVE/
    - CAMPAIGNS/<campaign_id>/WORLD_BIBLE/
    """
    root = _get_workspace_root(root_dir)
    campaign_dir = os.path.join(root, "CAMPAIGNS", campaign_id)
    if not os.path.isdir(campaign_dir):
        raise FileNotFoundError(f"Campaign directory not found: {campaign_dir}")

    # 1. Check if an authored story graph already exists
    story_graph_file = os.path.join(campaign_dir, "GAMEPLAY", "story_graph.json")
    if os.path.isfile(story_graph_file):
        try:
            with open(story_graph_file, "r", encoding="utf-8") as f:
                data = json.load(f)
            return StoryGraph.from_dict(data)
        except Exception as e:
            pass

    # 2. Reconstruct graph from campaign files
    config_file = os.path.join(campaign_dir, "campaign_config.json")
    story_name = campaign_id
    operational_mode = "classic_cyoa"
    if os.path.isfile(config_file):
        try:
            with open(config_file, "r", encoding="utf-8") as f:
                cfg = json.load(f)
                story_name = cfg.get("title", campaign_id)
                operational_mode = cfg.get("operational_mode", "classic_cyoa")
        except Exception:
            pass

    status_file = os.path.join(campaign_dir, "GAMEPLAY", "status.json")
    status_data = {}
    if os.path.isfile(status_file):
        try:
            with open(status_file, "r", encoding="utf-8") as f:
                status_data = json.load(f)
        except Exception:
            pass

    # Collect all turn markdown files
    def get_turn_num(fpath: str) -> int:
        m = re.search(r'turn_(\d+)', os.path.basename(fpath))
        return int(m.group(1)) if m else -1

    active_dir = os.path.join(campaign_dir, "TURNS", "ACTIVE")
    archive_dir = os.path.join(campaign_dir, "TURNS", "ARCHIVE")
    active_files = glob.glob(os.path.join(active_dir, "turn_*.md")) if os.path.isdir(active_dir) else []
    archive_files = glob.glob(os.path.join(archive_dir, "turn_*.md")) if os.path.isdir(archive_dir) else []
    all_turn_files = sorted(set(archive_files + active_files), key=get_turn_num)

    graph = StoryGraph(
        name=story_name,
        startnode="1",
        metadata={
            "creator": "Whimsy",
            "creator_version": "1.0.0",
            "format": "Harlowe",
            "format_version": "3.3.9",
            "ifid": str(uuid.uuid4()).upper()
        }
    )

    if not all_turn_files:
        # Minimal initial passage if campaign has no turns yet
        init_meta = {
            "mode": operational_mode,
            "terminal": True
        }
        p = PassageNode(
            pid=1,
            name="Turn 1",
            text="Initial campaign staging point.",
            tags=format_metadata_tags(init_meta),
            links=[],
            metadata=init_meta
        )
        graph.add_passage(p)
        return graph

    # Parse each turn file into a PassageNode
    turn_nodes: Dict[int, PassageNode] = {}
    for idx, fpath in enumerate(all_turn_files, start=1):
        turn_num = get_turn_num(fpath)
        pid = turn_num if turn_num > 0 else idx
        passage_name = f"Turn {pid}"

        with open(fpath, "r", encoding="utf-8") as f:
            content = f.read()

        links = parse_passage_links(content)
        variables = parse_passage_variables(content)

        # Scene metadata extraction from status or file
        node_meta = {"mode": operational_mode}
        if status_data:
            loc = status_data.get("scene_anchor", {}).get("location")
            if loc:
                node_meta["location"] = loc
            for clk in status_data.get("clocks", []):
                if isinstance(clk, dict) and "id" in clk:
                    node_meta.setdefault("clocks", []).append(clk["id"])

        # Extract options block choices if no Twine links exist
        if not links:
            from ENGINE.mode_validator import extract_options_from_text
            extracted = extract_options_from_text(content)
            for opt in extracted:
                opt_text = opt.get("text", "")
                # If target not embedded, create target
                target = f"Turn {pid + 1}"
                links.append(StoryLink(text=opt_text, target=target, raw=f"[[{opt_text}->{target}]]"))

        node = PassageNode(
            pid=pid,
            name=passage_name,
            text=content,
            tags=format_metadata_tags(node_meta),
            links=links,
            variables=variables,
            metadata=node_meta
        )
        turn_nodes[pid] = node

    # For any passage pointing to a target that isn't yet created, create terminal stub or link
    all_targets = set()
    for node in turn_nodes.values():
        for lk in node.links:
            all_targets.add(lk.target)

    for p in turn_nodes.values():
        graph.add_passage(p)

    # Check if targets exist; if missing, create terminal stubs
    max_pid = max(turn_nodes.keys()) if turn_nodes else 1
    for tgt in all_targets:
        if not graph.get_passage(tgt):
            max_pid += 1
            stub_meta = {"mode": operational_mode, "terminal": True}
            stub = PassageNode(
                pid=max_pid,
                name=tgt,
                text=f"Resolution for {tgt}.",
                tags=format_metadata_tags(stub_meta),
                links=[],
                metadata=stub_meta
            )
            graph.add_passage(stub)

    # If the last turn has no links, tag as terminal
    if max(turn_nodes.keys()) in turn_nodes:
        last_turn = turn_nodes[max(turn_nodes.keys())]
        if not last_turn.links:
            last_turn.metadata["terminal"] = True
            last_turn.tags = format_metadata_tags(last_turn.metadata, last_turn.tags)

    return graph


def export_campaign_to_archive(campaign_id: str, out_path: str, root_dir: str = None) -> str:
    """
    Exports a campaign to a standalone Twine 2 HTML story archive.
    """
    graph = export_campaign_to_graph(campaign_id, root_dir)
    html_content = emit_twine_html(graph)
    out_dir = os.path.dirname(os.path.abspath(out_path))
    if out_dir:
        os.makedirs(out_dir, exist_ok=True)
    with open(out_path, "w", encoding="utf-8") as f:
        f.write(html_content)
    return out_path


def import_archive_to_campaign(archive_path: str, campaign_id: str, root_dir: str = None) -> StoryGraph:
    """
    Imports a Twine 2 HTML story archive into a campaign:
    - Writes CAMPAIGNS/<campaign_id>/GAMEPLAY/story_graph.json
    - Writes campaign_config.json
    - Writes GAMEPLAY/status.json
    - Generates TURNS/ACTIVE/turn_*.md files for passages
    - Generates GAMEPLAY/upcoming_hooks.md
    """
    if not os.path.isfile(archive_path):
        raise FileNotFoundError(f"Twine archive file not found: {archive_path}")

    with open(archive_path, "r", encoding="utf-8") as f:
        html_content = f.read()

    graph = parse_twine_html(html_content)

    root = _get_workspace_root(root_dir)
    campaign_dir = os.path.join(root, "CAMPAIGNS", campaign_id)
    active_dir = os.path.join(campaign_dir, "TURNS", "ACTIVE")
    archive_dir = os.path.join(campaign_dir, "TURNS", "ARCHIVE")
    gameplay_dir = os.path.join(campaign_dir, "GAMEPLAY")
    world_bible_dir = os.path.join(campaign_dir, "WORLD_BIBLE")

    os.makedirs(active_dir, exist_ok=True)
    os.makedirs(archive_dir, exist_ok=True)
    os.makedirs(gameplay_dir, exist_ok=True)
    os.makedirs(os.path.join(world_bible_dir, "CORE"), exist_ok=True)
    os.makedirs(os.path.join(world_bible_dir, "PLACES"), exist_ok=True)
    os.makedirs(os.path.join(world_bible_dir, "FACTIONS"), exist_ok=True)
    os.makedirs(os.path.join(world_bible_dir, "PEOPLE"), exist_ok=True)

    # 1. Save story_graph.json in GAMEPLAY/
    story_graph_path = os.path.join(gameplay_dir, "story_graph.json")
    with open(story_graph_path, "w", encoding="utf-8") as f:
        f.write(graph.to_json(indent=2))

    # 2. Determine operational mode from graph tags
    mode = "classic_cyoa"
    for p in graph.passages.values():
        if p.metadata.get("mode"):
            mode = p.metadata["mode"]
            break

    # 3. Create campaign_config.json
    config_data = {
        "id": campaign_id,
        "title": graph.name,
        "operational_mode": mode,
        "genre": "Interactive Fiction",
        "theme": {
            "bg_dark": "#0d1117",
            "bg_slate": "#161b22",
            "bg_card": "#21262d",
            "gold_primary": "#58a6ff",
            "gold_dim": "#1f6feb",
            "accent_glow": "rgba(88, 166, 255, 0.2)",
            "text_ivory": "#f0f6fc",
            "font_family": "system-ui, -apple-system, sans-serif"
        }
    }
    with open(os.path.join(campaign_dir, "campaign_config.json"), "w", encoding="utf-8") as f:
        json.dump(config_data, f, indent=2)

    # 4. Resolve starting passage
    start_p = graph.get_start_passage() or (list(graph.passages.values())[0] if graph.passages else None)

    # 5. Create GAMEPLAY/status.json
    start_loc = start_p.metadata.get("location", "Nexus") if start_p else "Nexus"
    clocks_list = []
    if start_p and start_p.metadata.get("clocks"):
        for clk_id in start_p.metadata["clocks"]:
            clocks_list.append({
                "id": clk_id,
                "label": clk_id.replace("_", " ").title(),
                "current": 0,
                "max": 4,
                "visibility": "known"
            })

    status_data = {
        "schema_version": 2,
        "campaign_id": campaign_id,
        "turn": 1,
        "timeline": "Beginning",
        "character": {
            "name": "Protagonist",
            "archetype": "Adventurer"
        },
        "progression": {
            "energy": start_p.variables.get("energy", 100) if start_p else 100,
            "energy_max": 100,
            "stress": 0,
            "stress_max": 100,
            "checkpoint_tokens": 5,
            "checkpoint_max": 5
        },
        "purse": {
            "credits": start_p.variables.get("funds", 0) if start_p else 0,
            "display": f"{start_p.variables.get('funds', 0) if start_p else 0} ₡"
        },
        "public_state": {
            "flags": dict(start_p.variables) if start_p else {},
            "conditions": [],
            "open_threads": []
        },
        "clocks": clocks_list,
        "scene_anchor": {
            "location": start_loc,
            "context": f"Active scene: {start_p.name if start_p else 'Start'}",
            "time": "08:00 Cycle"
        }
    }
    with open(os.path.join(gameplay_dir, "status.json"), "w", encoding="utf-8") as f:
        json.dump(status_data, f, indent=2)

    # 6. Generate TURNS/ACTIVE/turn_*.md files for each passage
    for p in graph.passages.values():
        turn_file = os.path.join(active_dir, f"turn_{p.pid:04d}.md")
        lines = [
            f"# Turn {p.pid}: {p.name}\n",
            "## Situation & Scene Description",
            p.text.strip(),
            "\n---"
        ]

        if p.links:
            lines.append("\n[OPTIONS & TYPABLE REFERENCE]")
            for idx, lk in enumerate(p.links, start=1):
                lines.append(f"{idx}. {lk.text} [[{lk.text}->{lk.target}]]")

        tags_str = " ".join(format_metadata_tags(p.metadata, p.tags))
        vars_str = ", ".join(f"{k}={v}" for k, v in p.variables.items())
        lines.append(f"\n[SYS: Turn {p.pid} | Tags: {tags_str} | Variables: {vars_str}]")

        with open(turn_file, "w", encoding="utf-8") as f:
            f.write("\n".join(lines))

    # 7. Generate GAMEPLAY/upcoming_hooks.md from start choices
    hooks_file = os.path.join(gameplay_dir, "upcoming_hooks.md")
    hook_lines = ["# IMMEDIATE PUBLIC HOOKS\n"]
    if start_p and start_p.links:
        for idx, lk in enumerate(start_p.links, start=1):
            hook_lines.append(f"{idx}. {lk.text} (Target: {lk.target})")
    else:
        hook_lines.append("1. Advance story narrative.")
    with open(hooks_file, "w", encoding="utf-8") as f:
        f.write("\n".join(hook_lines))

    return graph


# ==============================================================================
# CLI
# ==============================================================================

def main():
    import argparse
    parser = argparse.ArgumentParser(
        description="Twine-compatible story graph archive import, export, and validator."
    )
    subparsers = parser.add_subparsers(dest="command", required=True)

    # Export command
    export_parser = subparsers.add_parser("export", help="Export a campaign to a Twine HTML story archive.")
    export_parser.add_argument("--campaign", required=True, help="Campaign identifier.")
    export_parser.add_argument("--out", required=True, help="Output .html archive path.")
    export_parser.add_argument("--root", default=None, help="Optional workspace root directory.")
    export_parser.add_argument("--validate", action="store_true", help="Run graph validator on export.")

    # Import command
    import_parser = subparsers.add_parser("import", help="Import a Twine HTML story archive into a campaign.")
    import_parser.add_argument("--archive", required=True, help="Path to Twine .html archive.")
    import_parser.add_argument("--campaign", required=True, help="Target campaign identifier.")
    import_parser.add_argument("--root", default=None, help="Optional workspace root directory.")
    import_parser.add_argument("--validate", action="store_true", help="Run graph validator on import.")

    args = parser.parse_args()

    if args.command == "export":
        print(f"Exporting campaign '{args.campaign}' to '{args.out}'...")
        export_campaign_to_archive(args.campaign, args.out, root_dir=args.root)
        print(f"Successfully exported story archive to {args.out}")

        if args.validate:
            from ENGINE.graph_validator import validate_campaign
            res = validate_campaign(args.campaign, root_dir=args.root)
            if not res.valid:
                print(f"Validation warnings/errors found: {len(res.errors)} errors, {len(res.warnings)} warnings.")
                for d in res.diagnostics:
                    print(f"  [{d.severity.upper()}] {d.message}")
            else:
                print("Graph validation passed with 0 errors.")

    elif args.command == "import":
        print(f"Importing archive '{args.archive}' into campaign '{args.campaign}'...")
        graph = import_archive_to_campaign(args.archive, args.campaign, root_dir=args.root)
        print(f"Successfully imported {len(graph.passages)} passages into CAMPAIGNS/{args.campaign}")

        if args.validate:
            from ENGINE.graph_validator import validate_graph
            res = validate_graph(graph)
            if not res.valid:
                print(f"Validation warnings/errors found: {len(res.errors)} errors, {len(res.warnings)} warnings.")
                for d in res.diagnostics:
                    print(f"  [{d.severity.upper()}] {d.message}")
            else:
                print("Graph validation passed with 0 errors.")


if __name__ == "__main__":
    main()
