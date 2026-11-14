#!/usr/bin/env python3
"""
ENGINE/graph_export.py
======================
Story graph visualization and export.

Provides:
- to_dot(graph): Emits Graphviz DOT format for graphviz/dot visualization.
- export_to_dot(graph, path): Writes DOT file to disk.
- to_html_view(graph): Emits self-contained standalone interactive HTML view.
- export_to_html_view(graph, path): Writes HTML view to disk.

Offline-capable, dependency-free interactive HTML viewer with SVG pan/zoom,
node inspection sidebar, search filtering, and topological graph layout.
"""

import html
import json
import os
from typing import Any, Dict, List, Optional, Set, Tuple

from ENGINE.twine_io import StoryGraph, PassageNode


def _escape_dot(text: str) -> str:
    """Escapes strings for Graphviz DOT format."""
    return (
        text.replace('\\', '\\\\')
        .replace('"', '\\"')
        .replace('\r', '')
        .replace('\n', '\\n')
    )


def to_dot(graph: StoryGraph) -> str:
    """
    Renders a StoryGraph into Graphviz DOT format.
    Distinguishes start nodes, terminal nodes, and normal nodes with distinct styling.
    """
    lines: List[str] = [
        'digraph StoryGraph {',
        '  graph [rankdir=LR, bgcolor="#0d1117", pad="0.5", nodesep="0.6", ranksep="1.0"];',
        '  node [fontname="system-ui, -apple-system, sans-serif", fontsize=11, shape=box, style="filled,rounded", penwidth=1.5];',
        '  edge [fontname="system-ui, -apple-system, sans-serif", fontsize=9, color="#58a6ff", fontcolor="#8b949e", arrowsize=0.8];',
        ''
    ]

    start_p = graph.get_start_passage()
    start_pid = str(start_p.pid if start_p else graph.startnode)

    for p in graph.passages.values():
        p_id = f"node_{p.pid}"
        is_start = (str(p.pid) == start_pid or p.name == str(graph.startnode))
        is_terminal = p.metadata.get("terminal") or any(t.lower() in ("terminal", "end") for t in p.tags)

        # Style resolution
        if is_start:
            fill = "#1f6feb"
            stroke = "#58a6ff"
            font_color = "#f0f6fc"
            penwidth = 2.5
        elif is_terminal:
            fill = "#238636"
            stroke = "#3fb950"
            font_color = "#f0f6fc"
            penwidth = 2.0
        else:
            fill = "#161b22"
            stroke = "#30363d"
            font_color = "#c9d1d9"
            penwidth = 1.5

        # Format label
        label_parts = [p.name]
        loc = p.metadata.get("location")
        if loc:
            label_parts.append(f"[{loc}]")
        if p.variables:
            vars_str = ", ".join(f"${k}" for k in list(p.variables.keys())[:3])
            label_parts.append(f"({vars_str})")

        label_escaped = _escape_dot("\\n".join(label_parts))
        lines.append(
            f'  {p_id} [label="{label_escaped}", fillcolor="{fill}", color="{stroke}", fontcolor="{font_color}", penwidth={penwidth}];'
        )

    lines.append('')

    # Edges
    for p in graph.passages.values():
        src_id = f"node_{p.pid}"
        for lk in p.links:
            target_node = graph.get_passage(lk.target)
            if target_node:
                tgt_id = f"node_{target_node.pid}"
                # Truncate choice text for clean edge labels
                choice_label = lk.text
                if len(choice_label) > 32:
                    choice_label = choice_label[:29] + "..."
                choice_escaped = _escape_dot(choice_label)
                lines.append(f'  {src_id} -> {tgt_id} [label="{choice_escaped}"];')

    lines.append('}')
    return "\n".join(lines)


def export_to_dot(graph: StoryGraph, out_path: str) -> str:
    """Exports a StoryGraph to a .dot file on disk."""
    dot_str = to_dot(graph)
    os.makedirs(os.path.dirname(os.path.abspath(out_path)), exist_ok=True)
    with open(out_path, "w", encoding="utf-8") as f:
        f.write(dot_str)
    return out_path


# ==============================================================================
# STANDALONE HTML INTERACTIVE GRAPH VIEW
# ==============================================================================

def _compute_graph_layout(graph: StoryGraph) -> Dict[str, Any]:
    """
    Computes node positions and SVG dimensions for interactive visualization.
    Uses layered BFS/topological placement from start node.
    """
    start_p = graph.get_start_passage()
    start_name = start_p.name if start_p else (list(graph.passages.keys())[0] if graph.passages else "")

    layers: Dict[str, int] = {}
    if start_name:
        layers[start_name] = 0
        queue = [start_name]
        visited = {start_name}

        while queue:
            curr = queue.pop(0)
            curr_layer = layers[curr]
            node = graph.get_passage(curr)
            if node:
                for lk in node.links:
                    tgt = lk.target
                    if tgt in graph.passages and tgt not in visited:
                        visited.add(tgt)
                        layers[tgt] = curr_layer + 1
                        queue.append(tgt)

    # Any unreached nodes
    max_layer = max(layers.values()) if layers else 0
    for name in graph.passages:
        if name not in layers:
            max_layer += 1
            layers[name] = max_layer

    # Group nodes by layer
    layer_groups: Dict[int, List[str]] = {}
    for name, lvl in layers.items():
        layer_groups.setdefault(lvl, []).append(name)

    card_width = 200
    card_height = 80
    layer_spacing = 320
    vertical_spacing = 130
    margin_x = 100
    margin_y = 100

    nodes_data = []
    positions: Dict[str, Tuple[float, float]] = {}

    max_x = 800
    max_y = 600

    for lvl in sorted(layer_groups.keys()):
        group = layer_groups[lvl]
        total_group_h = (len(group) - 1) * vertical_spacing
        start_y = margin_y

        for idx, name in enumerate(group):
            p = graph.get_passage(name)
            if not p:
                continue

            x = margin_x + lvl * layer_spacing
            y = start_y + idx * vertical_spacing
            positions[name] = (x, y)

            if x + card_width + margin_x > max_x:
                max_x = x + card_width + margin_x
            if y + card_height + margin_y > max_y:
                max_y = y + card_height + margin_y

            is_start = (name == start_name)
            is_terminal = p.metadata.get("terminal") or any(t.lower() in ("terminal", "end") for t in p.tags)

            nodes_data.append({
                "pid": p.pid,
                "name": p.name,
                "text": p.text,
                "tags": p.tags,
                "metadata": p.metadata,
                "variables": p.variables,
                "is_start": is_start,
                "is_terminal": is_terminal,
                "x": x,
                "y": y,
                "width": card_width,
                "height": card_height,
                "outgoing_count": len(p.links)
            })

    # Prepare links data
    links_data = []
    for p in graph.passages.values():
        src_pos = positions.get(p.name)
        if not src_pos:
            continue
        for lk in p.links:
            tgt_node = graph.get_passage(lk.target)
            if not tgt_node:
                continue
            tgt_pos = positions.get(tgt_node.name)
            if not tgt_pos:
                continue

            x1 = src_pos[0] + card_width
            y1 = src_pos[1] + (card_height / 2.0)
            x2 = tgt_pos[0]
            y2 = tgt_pos[1] + (card_height / 2.0)

            # Curved control points
            dx = max(40.0, abs(x2 - x1) * 0.5)
            cx1 = x1 + dx
            cy1 = y1
            cx2 = x2 - dx
            cy2 = y2
            path_d = f"M {x1:.1f} {y1:.1f} C {cx1:.1f} {cy1:.1f}, {cx2:.1f} {cy2:.1f}, {x2:.1f} {y2:.1f}"

            links_data.append({
                "source": p.name,
                "target": tgt_node.name,
                "text": lk.text,
                "path_d": path_d,
                "mid_x": (x1 + x2) / 2.0,
                "mid_y": (y1 + y2) / 2.0
            })

    return {
        "nodes": nodes_data,
        "links": links_data,
        "width": max_x,
        "height": max_y
    }


def to_html_view(graph: StoryGraph) -> str:
    """
    Renders the story graph into a self-contained, standalone interactive HTML view.
    Zero external CDN dependencies. Features SVG pan/zoom, node inspector, and search filter.
    """
    layout = _compute_graph_layout(graph)
    graph_json = json.dumps(graph.to_dict(), ensure_ascii=False)
    layout_json = json.dumps(layout, ensure_ascii=False)

    escaped_title = html.escape(graph.name)
    total_passages = len(graph.passages)
    total_links = sum(len(p.links) for p in graph.passages.values())
    terminal_count = sum(1 for p in graph.passages.values() if p.metadata.get("terminal") or any(t.lower() in ("terminal", "end") for t in p.tags))

    # Pre-render static SVG elements for instant rendering and offline accessibility
    edges_svg_list = []
    for idx, lk in enumerate(layout["links"]):
        s_esc = html.escape(lk["source"], quote=True)
        t_esc = html.escape(lk["target"], quote=True)
        edges_svg_list.append(
            f'<path d="{lk["path_d"]}" class="edge" marker-end="url(#arrow-dim)" id="edge-{idx}" data-source="{s_esc}" data-target="{t_esc}" />'
        )
    edges_svg = "\n        ".join(edges_svg_list)

    nodes_svg_list = []
    for node in layout["nodes"]:
        name_esc = html.escape(node["name"], quote=True)
        title_text = node["name"][:20] + "..." if len(node["name"]) > 22 else node["name"]
        loc = node["metadata"].get("location") or ("Ending" if node["is_terminal"] else f"{node['outgoing_count']} choices")
        loc_text = loc[:24] + "..." if len(loc) > 26 else loc
        cls_parts = ["node-card"]
        if node["is_start"]:
            cls_parts.append("start")
        if node["is_terminal"]:
            cls_parts.append("terminal")
        card_cls = " ".join(cls_parts)

        nodes_svg_list.append(
            f'<g class="node-group" transform="translate({node["x"]}, {node["y"]})" data-name="{name_esc}" id="node-{node["pid"]}">'
            f'<rect class="{card_cls}" width="{node["width"]}" height="{node["height"]}" />'
            f'<text class="node-title" x="12" y="28">{html.escape(title_text)}</text>'
            f'<text class="node-sub" x="12" y="52">{html.escape(loc_text)}</text>'
            f'</g>'
        )
    nodes_svg = "\n        ".join(nodes_svg_list)

    html_content = f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>{escaped_title} — Whimsy Story Graph</title>
<style>
  :root {{
    --bg-dark: #0d1117;
    --bg-panel: #161b22;
    --bg-card: #21262d;
    --border: #30363d;
    --border-hover: #58a6ff;
    --text-primary: #f0f6fc;
    --text-secondary: #8b949e;
    --accent: #58a6ff;
    --accent-glow: rgba(88, 166, 255, 0.25);
    --start-node: #1f6feb;
    --terminal-node: #238636;
    --danger: #f85149;
  }}

  * {{ box-sizing: border-box; margin: 0; padding: 0; }}
  body {{
    font-family: system-ui, -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif;
    background-color: var(--bg-dark);
    color: var(--text-primary);
    overflow: hidden;
    height: 100vh;
    display: flex;
    flex-direction: column;
  }}

  header {{
    height: 52px;
    background-color: var(--bg-panel);
    border-bottom: 1px solid var(--border);
    display: flex;
    align-items: center;
    justify-content: space-between;
    padding: 0 16px;
    z-index: 10;
  }}

  .header-left {{
    display: flex;
    align-items: center;
    gap: 12px;
  }}

  .title {{
    font-size: 16px;
    font-weight: 600;
    color: var(--text-primary);
  }}

  .badge {{
    font-size: 11px;
    padding: 3px 8px;
    border-radius: 12px;
    background-color: var(--bg-card);
    border: 1px solid var(--border);
    color: var(--text-secondary);
  }}

  .header-right {{
    display: flex;
    align-items: center;
    gap: 10px;
  }}

  .search-input {{
    background-color: var(--bg-card);
    border: 1px solid var(--border);
    color: var(--text-primary);
    border-radius: 6px;
    padding: 6px 12px;
    font-size: 12px;
    width: 220px;
    outline: none;
    transition: border-color 0.15s ease;
  }}
  .search-input:focus {{
    border-color: var(--accent);
  }}

  .btn {{
    background-color: var(--bg-card);
    border: 1px solid var(--border);
    color: var(--text-primary);
    padding: 5px 10px;
    border-radius: 6px;
    cursor: pointer;
    font-size: 12px;
    transition: all 0.15s ease;
  }}
  .btn:hover {{
    background-color: var(--border);
    border-color: var(--accent);
  }}

  #workspace {{
    flex: 1;
    display: flex;
    position: relative;
    overflow: hidden;
  }}

  #canvas-container {{
    flex: 1;
    height: 100%;
    cursor: grab;
    position: relative;
    background-image: radial-gradient(circle, #21262d 1px, transparent 1px);
    background-size: 24px 24px;
  }}
  #canvas-container:active {{
    cursor: grabbing;
  }}

  #graph-svg {{
    width: 100%;
    height: 100%;
    display: block;
  }}

  /* SVG Elements */
  .edge {{
    fill: none;
    stroke: #38444d;
    stroke-width: 2;
    transition: stroke 0.2s ease, stroke-width 0.2s ease;
  }}
  .edge.highlighted {{
    stroke: var(--accent);
    stroke-width: 3.5;
  }}

  .edge-label {{
    font-size: 9px;
    fill: var(--text-secondary);
    text-anchor: middle;
    pointer-events: none;
  }}

  .node-group {{
    cursor: pointer;
    transition: transform 0.15s ease, opacity 0.2s ease;
  }}
  .node-group:hover rect.node-card {{
    stroke: var(--accent);
    stroke-width: 2.5;
  }}
  .node-group.dimmed {{
    opacity: 0.2;
  }}
  .node-group.active rect.node-card {{
    stroke: var(--accent);
    stroke-width: 3;
    filter: drop-shadow(0 0 10px var(--accent-glow));
  }}

  rect.node-card {{
    fill: var(--bg-card);
    stroke: var(--border);
    stroke-width: 1.5;
    rx: 8;
    ry: 8;
  }}
  rect.node-card.start {{
    stroke: var(--start-node);
    stroke-width: 2.5;
  }}
  rect.node-card.terminal {{
    stroke: var(--terminal-node);
    stroke-width: 2.5;
  }}

  text.node-title {{
    fill: var(--text-primary);
    font-size: 13px;
    font-weight: 600;
  }}
  text.node-sub {{
    fill: var(--text-secondary);
    font-size: 10px;
  }}

  /* Sidebar Inspector */
  #inspector {{
    width: 360px;
    height: 100%;
    background-color: var(--bg-panel);
    border-left: 1px solid var(--border);
    display: flex;
    flex-direction: column;
    overflow-y: auto;
    transition: transform 0.2s ease;
  }}
  #inspector.collapsed {{
    transform: translateX(100%);
    position: absolute;
    right: 0;
  }}

  .inspector-header {{
    padding: 16px;
    border-bottom: 1px solid var(--border);
    display: flex;
    justify-content: space-between;
    align-items: center;
  }}
  .inspector-title {{
    font-size: 15px;
    font-weight: 600;
  }}

  .inspector-body {{
    padding: 16px;
    flex: 1;
    display: flex;
    flex-direction: column;
    gap: 16px;
  }}

  .prop-section {{
    display: flex;
    flex-direction: column;
    gap: 6px;
  }}
  .prop-label {{
    font-size: 11px;
    text-transform: uppercase;
    letter-spacing: 0.05em;
    color: var(--text-secondary);
    font-weight: 600;
  }}

  .tag-pill {{
    display: inline-block;
    font-size: 11px;
    padding: 2px 8px;
    border-radius: 4px;
    background-color: rgba(88, 166, 255, 0.15);
    color: var(--accent);
    border: 1px solid rgba(88, 166, 255, 0.3);
    margin-right: 4px;
    margin-bottom: 4px;
  }}
  .tag-pill.terminal {{
    background-color: rgba(35, 134, 54, 0.2);
    color: #3fb950;
    border-color: rgba(63, 185, 80, 0.3);
  }}

  .choice-item {{
    background-color: var(--bg-card);
    border: 1px solid var(--border);
    border-radius: 6px;
    padding: 8px 10px;
    cursor: pointer;
    font-size: 12px;
    display: flex;
    justify-content: space-between;
    align-items: center;
    transition: border-color 0.15s ease;
  }}
  .choice-item:hover {{
    border-color: var(--accent);
  }}
  .choice-arrow {{
    color: var(--accent);
    font-weight: bold;
  }}

  .text-box {{
    background-color: var(--bg-card);
    border: 1px solid var(--border);
    border-radius: 6px;
    padding: 10px;
    font-size: 12px;
    line-height: 1.5;
    max-height: 220px;
    overflow-y: auto;
    color: var(--text-primary);
    white-space: pre-wrap;
  }}

  /* Controls Overlay */
  .controls-overlay {{
    position: absolute;
    bottom: 20px;
    left: 20px;
    display: flex;
    flex-direction: column;
    gap: 6px;
    z-index: 5;
  }}
  .ctrl-btn {{
    width: 32px;
    height: 32px;
    background-color: var(--bg-panel);
    border: 1px solid var(--border);
    color: var(--text-primary);
    border-radius: 6px;
    display: flex;
    align-items: center;
    justify-content: center;
    cursor: pointer;
    font-size: 16px;
    box-shadow: 0 4px 12px rgba(0,0,0,0.4);
  }}
  .ctrl-btn:hover {{
    border-color: var(--accent);
    color: var(--accent);
  }}
</style>
</head>
<body>

<header>
  <div class="header-left">
    <div class="title">{escaped_title}</div>
    <div class="badge">{total_passages} Passages</div>
    <div class="badge">{total_links} Links</div>
    <div class="badge">{terminal_count} Endings</div>
  </div>
  <div class="header-right">
    <input type="text" id="search-box" class="search-input" placeholder="Search passages or tags...">
    <button class="btn" id="btn-reset-view">Reset View</button>
  </div>
</header>

<div id="workspace">
  <div id="canvas-container">
    <svg id="graph-svg">
      <defs>
        <marker id="arrow" viewBox="0 0 10 10" refX="10" refY="5" markerWidth="6" markerHeight="6" orient="auto-start-reverse">
          <path d="M 0 1.5 L 8 5 L 0 8.5 z" fill="#58a6ff" />
        </marker>
        <marker id="arrow-dim" viewBox="0 0 10 10" refX="10" refY="5" markerWidth="6" markerHeight="6" orient="auto-start-reverse">
          <path d="M 0 1.5 L 8 5 L 0 8.5 z" fill="#38444d" />
        </marker>
      </defs>
      <g id="viewport">
        <g id="edges-layer">
        {edges_svg}
        </g>
        <g id="nodes-layer">
        {nodes_svg}
        </g>
      </g>
    </svg>

    <div class="controls-overlay">
      <div class="ctrl-btn" id="btn-zoom-in" title="Zoom In">+</div>
      <div class="ctrl-btn" id="btn-zoom-out" title="Zoom Out">-</div>
      <div class="ctrl-btn" id="btn-center" title="Center Graph">⊙</div>
    </div>
  </div>

  <div id="inspector">
    <div class="inspector-header">
      <div class="inspector-title" id="insp-title">Passage Inspector</div>
      <button class="btn" id="insp-close">✕</button>
    </div>
    <div class="inspector-body">
      <div class="prop-section">
        <div class="prop-label">Passage Name & ID</div>
        <div id="insp-name" style="font-weight:600; font-size:14px;">-</div>
      </div>

      <div class="prop-section">
        <div class="prop-label">Tags & Attributes</div>
        <div id="insp-tags">-</div>
      </div>

      <div class="prop-section">
        <div class="prop-label">Variables / State Effects</div>
        <div id="insp-vars" style="font-size:12px; font-family:monospace; color:var(--text-secondary);">-</div>
      </div>

      <div class="prop-section">
        <div class="prop-label">Outgoing Choices (<span id="insp-choice-count">0</span>)</div>
        <div id="insp-choices" style="display:flex; flex-direction:column; gap:6px;">-</div>
      </div>

      <div class="prop-section">
        <div class="prop-label">Passage Prose</div>
        <div class="text-box" id="insp-text">-</div>
      </div>
    </div>
  </div>
</div>

<script>
  const storyGraph = {graph_json};
  const layoutData = {layout_json};

  let scale = 1.0;
  let panX = 40.0;
  let panY = 40.0;
  let isDragging = false;
  let startX = 0;
  let startY = 0;
  let selectedNode = null;

  const viewport = document.getElementById("viewport");
  const edgesLayer = document.getElementById("edges-layer");
  const nodesLayer = document.getElementById("nodes-layer");
  const canvasContainer = document.getElementById("canvas-container");
  const searchBox = document.getElementById("search-box");

  function updateTransform() {{
    viewport.setAttribute("transform", `translate(${{panX}}, ${{panY}}) scale(${{scale}})`);
  }}

  function renderGraph() {{
    // Bind click handlers to existing static node elements
    document.querySelectorAll(".node-group").forEach(el => {{
      const name = el.dataset.name;
      const node = layoutData.nodes.find(n => n.name === name);
      if (node) {{
        el.addEventListener("click", (e) => {{
          e.stopPropagation();
          selectNode(node);
        }});
      }}
    }});
  }}

  function selectNode(node) {{
    selectedNode = node;
    document.querySelectorAll(".node-group").forEach(el => {{
      el.classList.toggle("active", el.dataset.name === node.name);
    }});

    // Highlight incident edges
    document.querySelectorAll(".edge").forEach(el => {{
      const isOut = el.dataset.source === node.name;
      const isIn = el.dataset.target === node.name;
      el.classList.toggle("highlighted", isOut || isIn);
      el.setAttribute("marker-end", (isOut || isIn) ? "url(#arrow)" : "url(#arrow-dim)");
    }});

    // Update inspector panel
    document.getElementById("insp-name").textContent = `${{node.name}} (PID: ${{node.pid}})`;
    
    // Tags
    const tagsDiv = document.getElementById("insp-tags");
    tagsDiv.innerHTML = "";
    if (node.tags && node.tags.length > 0) {{
      node.tags.forEach(t => {{
        const pill = document.createElement("span");
        pill.className = `tag-pill ${{t.toLowerCase().includes('terminal') ? 'terminal' : ''}}`;
        pill.textContent = t;
        tagsDiv.appendChild(pill);
      }});
    }} else {{
      tagsDiv.textContent = "No tags";
    }}

    // Variables
    const varsDiv = document.getElementById("insp-vars");
    if (node.variables && Object.keys(node.variables).length > 0) {{
      varsDiv.innerHTML = Object.entries(node.variables)
        .map(([k, v]) => `<div>$${{k}} = ${{JSON.stringify(v)}}</div>`)
        .join("");
    }} else {{
      varsDiv.textContent = "None";
    }}

    // Choices
    const passageObj = storyGraph.passages.find(p => p.name === node.name);
    const choicesDiv = document.getElementById("insp-choices");
    choicesDiv.innerHTML = "";
    if (passageObj && passageObj.links && passageObj.links.length > 0) {{
      document.getElementById("insp-choice-count").textContent = passageObj.links.length;
      passageObj.links.forEach(lk => {{
        const item = document.createElement("div");
        item.className = "choice-item";
        item.innerHTML = `<span>${{lk.text}}</span><span class="choice-arrow">→ ${{lk.target}}</span>`;
        item.addEventListener("click", () => {{
          const tgtNode = layoutData.nodes.find(n => n.name === lk.target);
          if (tgtNode) focusNode(tgtNode);
        }});
        choicesDiv.appendChild(item);
      }});
    }} else {{
      document.getElementById("insp-choice-count").textContent = "0";
      choicesDiv.innerHTML = "<div style='color:var(--text-secondary); font-size:12px;'>Terminal scene (no outgoing choices)</div>";
    }}

    // Text
    document.getElementById("insp-text").textContent = node.text || "No narrative content.";
  }}

  function focusNode(node) {{
    selectNode(node);
    const containerW = canvasContainer.clientWidth;
    const containerH = canvasContainer.clientHeight;
    panX = (containerW / 2) - (node.x + node.width / 2) * scale;
    panY = (containerH / 2) - (node.y + node.height / 2) * scale;
    updateTransform();
  }}

  // Pan & Zoom
  canvasContainer.addEventListener("mousedown", (e) => {{
    isDragging = true;
    startX = e.clientX - panX;
    startY = e.clientY - panY;
  }});

  window.addEventListener("mousemove", (e) => {{
    if (!isDragging) return;
    panX = e.clientX - startX;
    panY = e.clientY - startY;
    updateTransform();
  }});

  window.addEventListener("mouseup", () => {{
    isDragging = false;
  }});

  canvasContainer.addEventListener("wheel", (e) => {{
    e.preventDefault();
    const zoomFactor = e.deltaY < 0 ? 1.15 : 0.85;
    const rect = canvasContainer.getBoundingClientRect();
    const mouseX = e.clientX - rect.left;
    const mouseY = e.clientY - rect.top;

    const newScale = Math.min(Math.max(scale * zoomFactor, 0.2), 3.0);
    panX = mouseX - (mouseX - panX) * (newScale / scale);
    panY = mouseY - (mouseY - panY) * (newScale / scale);
    scale = newScale;
    updateTransform();
  }}, {{ passive: false }});

  // Buttons
  document.getElementById("btn-zoom-in").addEventListener("click", () => {{
    scale = Math.min(scale * 1.25, 3.0);
    updateTransform();
  }});
  document.getElementById("btn-zoom-out").addEventListener("click", () => {{
    scale = Math.max(scale / 1.25, 0.2);
    updateTransform();
  }});
  document.getElementById("btn-center").addEventListener("click", resetView);
  document.getElementById("btn-reset-view").addEventListener("click", resetView);

  function resetView() {{
    scale = 0.85;
    panX = 60;
    panY = 60;
    updateTransform();
  }}

  // Search
  searchBox.addEventListener("input", (e) => {{
    const query = e.target.value.toLowerCase().trim();
    if (!query) {{
      document.querySelectorAll(".node-group").forEach(el => el.classList.remove("dimmed"));
      return;
    }}
    document.querySelectorAll(".node-group").forEach(el => {{
      const nodeObj = layoutData.nodes.find(n => n.name === el.dataset.name);
      if (!nodeObj) return;
      const match = nodeObj.name.toLowerCase().includes(query) ||
                    (nodeObj.tags && nodeObj.tags.some(t => t.toLowerCase().includes(query))) ||
                    (nodeObj.text && nodeObj.text.toLowerCase().includes(query));
      el.classList.toggle("dimmed", !match);
    }});
  }});

  renderGraph();
  resetView();
  if (layoutData.nodes.length > 0) {{
    selectNode(layoutData.nodes[0]);
  }}
</script>
</body>
</html>
"""
    return html_content


def export_to_html_view(graph: StoryGraph, out_path: str) -> str:
    """Exports a StoryGraph to a self-contained interactive HTML file."""
    html_str = to_html_view(graph)
    os.makedirs(os.path.dirname(os.path.abspath(out_path)), exist_ok=True)
    with open(out_path, "w", encoding="utf-8") as f:
        f.write(html_str)
    return out_path
