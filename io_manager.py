"""
Data Import/Export, Formats, Vector & Raster Rendering, Clipboard, and Autosave.
Covers features 10, 41–43, 47–50.
"""
import csv
import base64
import io
import json
import math
import mimetypes
import os
import pickle
import subprocess
import sys
from xml.sax.saxutils import escape
import networkx as nx
from PIL import Image, ImageDraw, ImageFont
from graph_model import LINE_DASH_PATTERNS

AUTOSAVE_PATH = os.path.join(os.path.expanduser("~"), ".linkdraw_autosave.json")
RECENT_PATH = os.path.join(os.path.expanduser("~"), ".linkdraw_recent.json")


# ---- 50. Recent Files
def get_recent_files():
    try:
        if os.path.exists(RECENT_PATH):
            with open(RECENT_PATH, "r", encoding="utf-8") as f:
                files = json.load(f)
                return [p for p in files if os.path.exists(p)][:10]
    except Exception:
        pass
    return []


def _layer_is_visible(model, layer_name):
    return model.settings.get("layers", {}).get(layer_name, {}).get("visible", True)


def _connection_is_visible(model, connection):
    a = model.nodes.get(connection.get("a"))
    b = model.nodes.get(connection.get("b"))
    return (
        _layer_is_visible(model, connection.get("layer", "Data"))
        and a is not None and b is not None
        and _layer_is_visible(model, a.get("layer", "Data"))
        and _layer_is_visible(model, b.get("layer", "Data"))
    )


def add_recent_file(path):
    if not path or not os.path.exists(path):
        return
    files = get_recent_files()
    if path in files:
        files.remove(path)
    files.insert(0, os.path.abspath(path))
    try:
        with open(RECENT_PATH, "w", encoding="utf-8") as f:
            json.dump(files[:10], f)
    except Exception:
        pass


# ---- 49. Autosave & Recovery
def save_autosave(model):
    try:
        with open(AUTOSAVE_PATH, "w", encoding="utf-8") as f:
            json.dump(model.to_dict(), f)
    except Exception:
        pass


def check_recovery_available():
    try:
        if os.path.exists(AUTOSAVE_PATH) and os.path.getsize(AUTOSAVE_PATH) > 20:
            return True
    except Exception:
        pass
    return False


def load_autosave(model):
    try:
        if os.path.exists(AUTOSAVE_PATH):
            with open(AUTOSAVE_PATH, "r", encoding="utf-8") as f:
                d = json.load(f)
            model.load_dict(d)
            if "settings" in d:
                model.settings.update(d["settings"])
            return True
    except Exception:
        pass
    return False


# ---- 41. CSV Import / Export
def export_csv(model, node_csv_path, edge_csv_path):
    with open(node_csv_path, "w", newline="", encoding="utf-8") as f:
        writer = csv.writer(f)
        writer.writerow(["id", "text", "x", "y", "w", "h", "shape", "color", "fs", "tags", "icon", "metadata"])
        for n in model.nodes.values():
            writer.writerow([
                n["id"], n["text"], n["x"], n["y"], n["w"], n["h"],
                n["shape"], n["color"], n.get("fs", 11),
                ";".join(n.get("tags", [])), n.get("icon", ""),
                json.dumps(n.get("metadata", {}))
            ])

    with open(edge_csv_path, "w", newline="", encoding="utf-8") as f:
        writer = csv.writer(f)
        writer.writerow([
            "id", "source", "target", "weight", "label", "type", "arrow",
            "color", "width", "dash", "line_style",
        ])
        for c in model.conns.values():
            writer.writerow([
                c["id"], c["a"], c["b"], c.get("weight", 1.0),
                c.get("label", ""), c.get("type", "curved"), c.get("arrow", "forward"),
                c.get("color", "#374151"), c.get("width", 2), c.get("dash", False),
                c.get("line_style", "dashed" if c.get("dash") else "solid"),
            ])


def import_csv(model, node_csv_path=None, edge_csv_path=None):
    model.push_undo()
    id_map = {}
    if node_csv_path and os.path.exists(node_csv_path):
        with open(node_csv_path, "r", encoding="utf-8") as f:
            reader = csv.DictReader(f)
            for row in reader:
                try:
                    orig_id = int(row.get("id", 0))
                    tags = [t.strip() for t in row.get("tags", "").split(";") if t.strip()]
                    meta_str = row.get("metadata", "{}")
                    try:
                        meta = json.loads(meta_str) if meta_str else {}
                    except Exception:
                        meta = {}
                    nid = model.make_node(
                        x=float(row.get("x", 0)),
                        y=float(row.get("y", 0)),
                        text=row.get("text", "Node"),
                        shape=row.get("shape", "rounded"),
                        color=row.get("color", "#dbeafe"),
                        w=float(row.get("w", 130)),
                        h=float(row.get("h", 60)),
                        fs=int(row.get("fs", 11)),
                        tags=tags,
                        metadata=meta,
                        icon=row.get("icon", ""),
                    )
                    id_map[orig_id] = nid
                except Exception as e:
                    print("Error importing node row:", e)

    if edge_csv_path and os.path.exists(edge_csv_path):
        with open(edge_csv_path, "r", encoding="utf-8") as f:
            reader = csv.DictReader(f)
            for row in reader:
                try:
                    src = int(row.get("source", 0))
                    tgt = int(row.get("target", 0))
                    a = id_map.get(src, src if src in model.nodes else None)
                    b = id_map.get(tgt, tgt if tgt in model.nodes else None)
                    if a and b:
                        model.make_conn(
                            a=a, b=b,
                            label=row.get("label", ""),
                            type_=row.get("type", "curved"),
                            arrow=row.get("arrow", "forward"),
                            color=row.get("color", "#374151"),
                            width=int(row.get("width", 2)),
                            weight=float(row.get("weight", 1.0)),
                            dash=row.get("dash", "false").lower() in ("true", "1"),
                            line_style=row.get("line_style") or None,
                        )
                except Exception as e:
                    print("Error importing edge row:", e)


# ---- 42. GraphML / GEXF Import & Export
def export_graphml(model, filepath):
    G = nx.DiGraph()
    for nid, n in model.nodes.items():
        G.add_node(str(nid), label=str(n["text"]), x=float(n["x"]), y=float(n["y"]),
                   shape=str(n["shape"]), color=str(n["color"]), tags=",".join(n.get("tags", [])))
    for cid, c in model.conns.items():
        G.add_edge(str(c["a"]), str(c["b"]), id=str(cid), weight=float(c.get("weight", 1.0)),
                   label=str(c.get("label", "")), type=str(c.get("type", "curved")),
                   arrow=str(c.get("arrow", "forward")), color=str(c.get("color", "#374151")),
                   width=int(c.get("width", 2)), line_style=str(c.get("line_style", "dashed" if c.get("dash") else "solid")))
    nx.write_graphml(G, filepath)


def import_graphml(model, filepath):
    G = nx.read_graphml(filepath)
    model.push_undo()
    model.nodes.clear()
    model.conns.clear()
    id_map = {}
    for node, data in G.nodes(data=True):
        nid = model.make_node(
            x=float(data.get("x", 0)),
            y=float(data.get("y", 0)),
            text=str(data.get("label", data.get("text", node))),
            shape=str(data.get("shape", "rounded")),
            color=str(data.get("color", "#dbeafe")),
            tags=[t.strip() for t in str(data.get("tags", "")).split(",") if t.strip()]
        )
        id_map[node] = nid

    for u, v, data in G.edges(data=True):
        if u in id_map and v in id_map:
            model.make_conn(
                a=id_map[u],
                b=id_map[v],
                label=str(data.get("label", "")),
                type_=str(data.get("type", "curved")),
                arrow=str(data.get("arrow", "forward")),
                color=str(data.get("color", "#374151")),
                width=int(data.get("width", 2)),
                weight=float(data.get("weight", 1.0)),
                line_style=str(data.get("line_style", "dashed" if data.get("dash") else "solid")),
            )


def export_gexf(model, filepath):
    G = nx.DiGraph()
    for nid, n in model.nodes.items():
        G.add_node(str(nid), label=str(n["text"]), x=float(n["x"]), y=float(n["y"]))
    for cid, c in model.conns.items():
        G.add_edge(str(c["a"]), str(c["b"]), id=str(cid), weight=float(c.get("weight", 1.0)),
                   label=str(c.get("label", "")), type=str(c.get("type", "curved")),
                   arrow=str(c.get("arrow", "forward")), color=str(c.get("color", "#374151")),
                   width=int(c.get("width", 2)),
                   line_style=str(c.get("line_style", "dashed" if c.get("dash") else "solid")))
    nx.write_gexf(G, filepath)


def import_gexf(model, filepath):
    G = nx.read_gexf(filepath)
    model.push_undo()
    model.nodes.clear()
    model.conns.clear()
    id_map = {}
    for node, data in G.nodes(data=True):
        nid = model.make_node(
            x=float(data.get("x", 0)),
            y=float(data.get("y", 0)),
            text=str(data.get("label", node))
        )
        id_map[node] = nid

    for u, v, data in G.edges(data=True):
        if u in id_map and v in id_map:
            model.make_conn(
                a=id_map[u],
                b=id_map[v],
                label=str(data.get("label", "")),
                type_=str(data.get("type", "curved")),
                arrow=str(data.get("arrow", "forward")),
                color=str(data.get("color", "#374151")),
                width=int(data.get("width", 2)),
                weight=float(data.get("weight", 1.0)),
                line_style=str(data.get("line_style", "solid")),
            )


# ---- 43. DOT / Graphviz Import & Export
def export_dot(model, filepath):
    lines = ["digraph LinkDraw {", '  rankdir="LR";', '  node [style="filled", fontname="Helvetica"];']
    for nid, n in model.nodes.items():
        lbl = n["text"].replace('"', '\\"').replace("\n", "\\n")
        lines.append(f'  "{nid}" [label="{lbl}", fillcolor="{n["color"]}", shape="{n["shape"]}"];')
    for cid, c in model.conns.items():
        lbl = c.get("label", "").replace('"', '\\"')
        line_style = c.get("line_style", "dashed" if c.get("dash") else "solid")
        dot_style = {
            "dashed": "dashed",
            "dotted": "dotted",
            "dash-dot": "dashed",
            "long-dash": "dashed",
            "dash-dot-dot": "dotted",
        }.get(line_style, "solid")
        lines.append(
            f'  "{c["a"]}" -> "{c["b"]}" [label="{lbl}", color="{c["color"]}", '
            f'penwidth="{c.get("width", 2)}", style="{dot_style}"];'
        )
    lines.append("}")
    with open(filepath, "w", encoding="utf-8") as f:
        f.write("\n".join(lines))


def import_dot(model, filepath):
    """Import DOT graph using pydot or regex fallback."""
    model.push_undo()
    try:
        import pydot
        graphs = pydot.graph_from_dot_file(filepath)
        if graphs:
            g = graphs[0]
            id_map = {}
            for node in g.get_nodes():
                name = node.get_name().strip('"')
                if name in ("node", "edge", "graph"):
                    continue
                lbl = node.get_label() or name
                lbl = lbl.strip('"').replace("\\n", "\n")
                color = (node.get_fillcolor() or "#dbeafe").strip('"')
                nid = model.make_node(0, 0, text=lbl, color=color)
                id_map[name] = nid
            for edge in g.get_edges():
                src = edge.get_source().strip('"')
                tgt = edge.get_destination().strip('"')
                if src in id_map and tgt in id_map:
                    lbl = (edge.get_label() or "").strip('"')
                    line_style = (edge.get_style() or "solid").strip('"')
                    line_style = {"dashed": "dashed", "dotted": "dotted"}.get(
                        line_style, "solid"
                    )
                    model.make_conn(
                        id_map[src],
                        id_map[tgt],
                        label=lbl,
                        color=(edge.get_color() or "#374151").strip('"'),
                        width=int(float((edge.get_penwidth() or 2))),
                        line_style=line_style,
                    )
            # Apply auto layout
            from layouts import compute_fruchterman_reingold
            pos = compute_fruchterman_reingold(model, list(model.nodes.keys()))
            for nid, (px, py) in pos.items():
                model.nodes[nid]["x"] = round(px)
                model.nodes[nid]["y"] = round(py)
                model.update_spatial_node(nid)
            return True
    except Exception as e:
        print("DOT import error:", e)
    return False


# ---- 47. Export to NetworkX pickle
def export_pickle(model, filepath):
    G = nx.DiGraph()
    for nid, n in model.nodes.items():
        G.add_node(nid, **n)
    for cid, c in model.conns.items():
        G.add_edge(c["a"], c["b"], **c)
    with open(filepath, "wb") as f:
        pickle.dump(G, f)


# ---- Helper: Border point calculation for any shape
def get_shape_border_point(node, tx, ty):
    cx, cy = node["x"], node["y"]
    dx, dy = tx - cx, ty - cy
    if dx == 0 and dy == 0:
        return cx, cy
    hw, hh = node["w"] / 2.0, node["h"] / 2.0
    shape = node.get("shape", "rounded")

    if shape == "circle":
        t = 1.0 / math.sqrt((dx / hw) ** 2 + (dy / hh) ** 2)
        return cx + dx * t, cy + dy * t
    elif shape == "square":
        side = max(hw, hh)
        t = min(side / abs(dx) if dx else math.inf, side / abs(dy) if dy else math.inf)
        return cx + dx * t, cy + dy * t
    elif shape == "diamond":
        t = 1.0 / (abs(dx) / hw + abs(dy) / hh)
        return cx + dx * t, cy + dy * t
    elif shape == "triangle":
        # isosceles triangle vertices: (cx, cy - hh), (cx + hw, cy + hh), (cx - hw, cy + hh)
        # approximate with bounding polygon ray
        t = min(hw / abs(dx) if dx else math.inf, hh / abs(dy) if dy else math.inf)
        return cx + dx * t, cy + dy * t
    elif shape == "hexagon":
        t = min(hw / abs(dx) if dx else math.inf, hh / abs(dy) if dy else math.inf) * 0.9
        return cx + dx * t, cy + dy * t
    elif shape == "star":
        t = min(hw / abs(dx) if dx else math.inf, hh / abs(dy) if dy else math.inf) * 0.85
        return cx + dx * t, cy + dy * t
    elif shape in ("cylinder", "parallelogram", "cloud", "callout"):
        t = min(hw / abs(dx) if dx else math.inf, hh / abs(dy) if dy else math.inf) * 0.95
        return cx + dx * t, cy + dy * t
    else:  # rounded, rectangle, text
        t = min(hw / abs(dx) if dx else math.inf, hh / abs(dy) if dy else math.inf)
        return cx + dx * t, cy + dy * t


# ---- Helper: Connection geometry with Self-Loops & Parallel Bundling
def get_conn_geom(model, cn, parallel_index=0, parallel_total=1):
    """
    Returns (kind, raw_points, label_pos).
    Supports:
    - 4. Self-loops: circle/horseshoe arc on top of node
    - 5. Edge bundling / parallel edge curvature separation
    - 2. Quadratic Bezier arcs
    - 28. Orthogonal right-angle routing
    """
    a_id, b_id = cn["a"], cn["b"]
    a, b = model.nodes[a_id], model.nodes[b_id]

    # Self-loop
    if a_id == b_id:
        cx, cy = a["x"], a["y"] - a["h"] / 2.0
        r = 28.0
        # loop points forming an arc above node
        s = (cx - 16.0, cy)
        c1 = (cx - 36.0, cy - r * 2.2)
        c2 = (cx + 36.0, cy - r * 2.2)
        e = (cx + 16.0, cy)
        lab_pos = (cx, cy - r * 2.4 - 10.0)
        return "self_loop", [s, c1, c2, e], lab_pos

    ax, ay, bx, by = a["x"], a["y"], b["x"], b["y"]
    t = cn.get("type", "curved")

    if t == "orthogonal" or t == "elbow":
        dx, dy = bx - ax, by - ay
        if abs(dx) >= abs(dy):
            sg = 1 if dx >= 0 else -1
            s = (ax + sg * a["w"] / 2.0, ay)
            e = (bx - sg * b["w"] / 2.0, by)
            mx = (s[0] + e[0]) / 2.0
            return "line", [s, (mx, s[1]), (mx, e[1]), e], (mx, (s[1] + e[1]) / 2.0)
        else:
            sg = 1 if dy >= 0 else -1
            s = (ax, ay + sg * a["h"] / 2.0)
            e = (bx, by - sg * b["h"] / 2.0)
            my = (s[1] + e[1]) / 2.0
            return "line", [s, (s[0], my), (e[0], my), e], ((s[0] + e[0]) / 2.0, my)

    # Parallel edge curvature offset (Bundling / separation)
    offset_mag = 0.0
    custom_bend = float(cn.get("bend", 0.0))
    if abs(custom_bend) > 0.5:
        t = "curved"
        offset_mag = custom_bend
    elif parallel_total > 1:
        # alternating offsets: +35, -35, +70, -70...
        step = (parallel_index - (parallel_total - 1) / 2.0) * 36.0
        offset_mag = step
    elif t == "curved":
        dx, dy = bx - ax, by - ay
        d = math.hypot(dx, dy) or 1.0
        offset_mag = min(0.25 * d, 60.0)

    if abs(offset_mag) > 0.5:
        dx, dy = bx - ax, by - ay
        d = math.hypot(dx, dy) or 1.0
        mx, my = (ax + bx) / 2.0, (ay + by) / 2.0
        ctrl = (mx - dy / d * offset_mag, my + dx / d * offset_mag)
        s = get_shape_border_point(a, *ctrl)
        e = get_shape_border_point(b, *ctrl)
        # Bezier midpoint formula at t=0.5: (s + 2*ctrl + e) / 4
        lab_pos = ((s[0] + 2 * ctrl[0] + e[0]) / 4.0, (s[1] + 2 * ctrl[1] + e[1]) / 4.0)
        return "curve", [s, ctrl, e], lab_pos

    # Straight line
    s = get_shape_border_point(a, bx, by)
    e = get_shape_border_point(b, ax, ay)
    return "line", [s, e], ((s[0] + e[0]) / 2.0, (s[1] + e[1]) / 2.0)


def sample_curve(kind, pts, steps=24):
    if kind == "line":
        return pts
    if kind == "curve":
        (x0, y0), (x1, y1), (x2, y2) = pts
        res = []
        for i in range(steps + 1):
            t = i / steps
            u = 1.0 - t
            res.append((u * u * x0 + 2 * u * t * x1 + t * t * x2,
                        u * u * y0 + 2 * u * t * y1 + t * t * y2))
        return res
    if kind == "self_loop":
        # Cubic bezier for self-loop
        (x0, y0), (x1, y1), (x2, y2), (x3, y3) = pts
        res = []
        for i in range(steps + 1):
            t = i / steps
            u = 1.0 - t
            x = u**3 * x0 + 3 * u**2 * t * x1 + 3 * u * t**2 * x2 + t**3 * x3
            y = u**3 * y0 + 3 * u**2 * t * y1 + 3 * u * t**2 * y2 + t**3 * y3
            res.append((x, y))
        return res
    return pts


# ---- 10. Export to SVG
def export_svg(model, filepath):
    x0, y0, W, H = model.bounds(80)
    out = [
        f'<svg xmlns="http://www.w3.org/2000/svg" width="{W:.0f}" height="{H:.0f}" '
        f'viewBox="{x0:.1f} {y0:.1f} {W:.1f} {H:.1f}" font-family="Helvetica, Arial, sans-serif">',
        f'<rect x="{x0:.1f}" y="{y0:.1f}" width="{W:.1f}" height="{H:.1f}" fill="#fafafa"/>',
        "<defs>"
    ]
    # Arrow markers
    for col in sorted({c.get("color", "#374151") for c in model.conns.values()}):
        c_clean = col.lstrip("#")
        out.append(f'<marker id="m{c_clean}" viewBox="0 0 10 10" refX="9" refY="5" '
                   f'markerWidth="6" markerHeight="6" orient="auto-start-reverse">'
                   f'<path d="M0 1L10 5L0 9z" fill="{col}"/></marker>')
    out.append("</defs>")

    # Freehand Strokes (Draw & Brush)
    for st in getattr(model, "freehand_strokes", []):
        if not _layer_is_visible(model, st.get("layer", "Data")):
            continue
        pts = st.get("points", [])
        if len(pts) >= 2:
            d = "M" + " L".join(f"{px:.1f} {py:.1f}" for px, py in pts)
            out.append(f'<path d="{d}" fill="none" stroke="{st.get("color", "#ef4444")}" '
                       f'stroke-width="{st.get("width", 3)}" stroke-linecap="round" stroke-linejoin="round"/>')

    # Sticky Notes
    for s in model.sticky_notes.values():
        if not _layer_is_visible(model, s.get("layer", "Annotations")):
            continue
        sx, sy, sw, sh = s["x"], s["y"], s["w"], s["h"]
        out.append(f'<rect x="{sx - sw/2:.1f}" y="{sy - sh/2:.1f}" width="{sw:.1f}" height="{sh:.1f}" '
                   f'fill="{s["color"]}" stroke="#eab308" stroke-width="1.5" rx="4"/>')
        out.append(f'<text x="{sx:.1f}" y="{sy + 4:.1f}" text-anchor="middle" font-size="11" fill="#713f12">'
                   f'{escape(s["text"])}</text>')

    # Group parallel edges
    edge_pairs = {}
    for cid, c in model.conns.items():
        if _connection_is_visible(model, c):
            pair = tuple(sorted([c["a"], c["b"]]))
            edge_pairs.setdefault(pair, []).append(cid)

    # Connections
    for pair, cids in edge_pairs.items():
        total = len(cids)
        for idx, cid in enumerate(cids):
            cn = model.conns[cid]
            kind, raw, lab = get_conn_geom(model, cn, idx, total)
            pts = sample_curve(kind, raw)
            d = "M" + " L".join(f"{px:.1f} {py:.1f}" for px, py in pts)
            c_clean = cn.get("color", "#374151").lstrip("#")
            mk = ""
            if cn.get("arrow") in ("forward", "both"):
                mk += f' marker-end="url(#m{c_clean})"'
            if cn.get("arrow") in ("backward", "both"):
                mk += f' marker-start="url(#m{c_clean})"'
            line_style = cn.get("line_style", "dashed" if cn.get("dash") else "solid")
            dash_pattern = LINE_DASH_PATTERNS.get(line_style)
            dash = f' stroke-dasharray="{" ".join(map(str, dash_pattern))}"' if dash_pattern else ""
            out.append(f'<path d="{d}" fill="none" stroke="{cn.get("color", "#374151")}" '
                       f'stroke-width="{cn.get("width", 2)}"{dash}{mk}/>')

            lbl = cn.get("label", "")
            if cn.get("weight") and cn.get("weight") != 1.0:
                lbl = f"{lbl} (w:{cn['weight']})" if lbl else f"w:{cn['weight']}"
            if lbl:
                out.append(f'<rect x="{lab[0] - 25:.1f}" y="{lab[1] - 8:.1f}" width="50" height="16" '
                           f'fill="#ffffff" stroke="#e5e7eb" rx="3"/>')
                out.append(f'<text x="{lab[0]:.1f}" y="{lab[1] + 4:.1f}" text-anchor="middle" '
                           f'font-size="10" fill="#374151">{escape(lbl)}</text>')

    # Nodes
    for n in model.nodes.values():
        if not _layer_is_visible(model, n.get("layer", "Data")):
            continue
        x, y, w, h = n["x"], n["y"], n["w"], n["h"]
        hw, hh = w / 2.0, h / 2.0
        sh = n.get("shape", "rounded")
        col = n.get("color", "#dbeafe")
        st = f'fill="{col}" stroke="#4b5563" stroke-width="1.5"'

        if sh == "circle":
            out.append(f'<ellipse cx="{x:.1f}" cy="{y:.1f}" rx="{hw:.1f}" ry="{hh:.1f}" {st}/>')
        elif sh == "square":
            side = max(w, h)
            out.append(f'<rect x="{x - side/2:.1f}" y="{y - side/2:.1f}" width="{side:.1f}" height="{side:.1f}" {st}/>')
        elif sh == "diamond":
            pts = f"{x:.1f},{y - hh:.1f} {x + hw:.1f},{y:.1f} {x:.1f},{y + hh:.1f} {x - hw:.1f},{y:.1f}"
            out.append(f'<polygon points="{pts}" {st}/>')
        elif sh == "triangle":
            pts = f"{x:.1f},{y - hh:.1f} {x + hw:.1f},{y + hh:.1f} {x - hw:.1f},{y + hh:.1f}"
            out.append(f'<polygon points="{pts}" {st}/>')
        elif sh == "hexagon":
            r_x, r_y = hw, hh
            h_pts = []
            for k in range(6):
                ang = math.pi / 6 + k * math.pi / 3
                h_pts.append(f"{x + r_x * math.cos(ang):.1f},{y + r_y * math.sin(ang):.1f}")
            out.append(f'<polygon points="{" ".join(h_pts)}" {st}/>')
        elif sh == "star":
            s_pts = []
            for k in range(10):
                ang = -math.pi / 2 + k * math.pi / 5
                r = hw if k % 2 == 0 else hw * 0.45
                s_pts.append(f"{x + r * math.cos(ang):.1f},{y + r * math.sin(ang):.1f}")
            out.append(f'<polygon points="{" ".join(s_pts)}" {st}/>')
        elif sh == "parallelogram":
            off = hw * 0.3
            pts = f"{x - hw + off:.1f},{y - hh:.1f} {x + hw:.1f},{y - hh:.1f} {x + hw - off:.1f},{y + hh:.1f} {x - hw:.1f},{y + hh:.1f}"
            out.append(f'<polygon points="{pts}" {st}/>')
        elif sh in ("cylinder", "cloud", "callout"):
            out.append(f'<rect x="{x - hw:.1f}" y="{y - hh:.1f}" width="{w:.1f}" height="{h:.1f}" rx="18" {st}/>')
        elif sh == "rounded":
            out.append(f'<rect x="{x - hw:.1f}" y="{y - hh:.1f}" width="{w:.1f}" height="{h:.1f}" rx="12" {st}/>')
        elif sh == "rectangle":
            out.append(f'<rect x="{x - hw:.1f}" y="{y - hh:.1f}" width="{w:.1f}" height="{h:.1f}" {st}/>')

        # Icon / Emoji & Text
        txt = n.get("text", "")
        if n.get("icon"):
            txt = f"{n['icon']} {txt}"
        fs = n.get("fs", 11)
        image_path = n.get("image_path")
        text_y = y + (hh * 0.65 if image_path and os.path.isfile(image_path) else 4)
        if image_path and os.path.isfile(image_path):
            mime_type = mimetypes.guess_type(image_path)[0] or "application/octet-stream"
            with open(image_path, "rb") as image_file:
                encoded_image = base64.b64encode(image_file.read()).decode("ascii")
            out.append(
                f'<image x="{x - hw + 6:.1f}" y="{y - hh + 6:.1f}" '
                f'width="{max(1, w - 12):.1f}" height="{max(1, h * 0.55):.1f}" '
                f'preserveAspectRatio="xMidYMid meet" '
                f'href="data:{mime_type};base64,{encoded_image}"/>'
            )
        font_family = escape(n.get("font_family", "Helvetica"), {'"': "&quot;"})
        font_style = n.get("font_style", "normal")
        font_weight = "bold" if "bold" in font_style else "normal"
        font_slant = "italic" if "italic" in font_style else "normal"
        text_color = n.get("text_color") or "#111827"
        out.append(
            f'<text x="{x:.1f}" y="{text_y:.1f}" text-anchor="middle" font-size="{fs}" '
            f'font-family="{font_family}" font-weight="{font_weight}" '
            f'font-style="{font_slant}" fill="{text_color}">{escape(txt)}</text>'
        )

    out.append("</svg>")
    with open(filepath, "w", encoding="utf-8") as f:
        f.write("\n".join(out))


# ---- 10. Export to Raster (PNG / PDF via Pillow)
def export_raster(model, filepath, kind="png"):
    S = 2  # 2x supersampling for crisp high-dpi render
    x0, y0, W, H = model.bounds(80)
    img = Image.new("RGB", (int(W * S), int(H * S)), "#fafafa")
    draw = ImageDraw.Draw(img)

    def P(x, y):
        return ((x - x0) * S, (y - y0) * S)

    def draw_styled_line(points, fill, width, line_style):
        pattern = LINE_DASH_PATTERNS.get(line_style)
        if not pattern:
            draw.line(points, fill=fill, width=width, joint="curve")
            return
        pattern = [max(1, round(length * S)) for length in pattern]
        for start, end in zip(points, points[1:]):
            dx, dy = end[0] - start[0], end[1] - start[1]
            length = math.hypot(dx, dy)
            if length == 0:
                continue
            cursor = 0.0
            pattern_index = 0
            while cursor < length:
                segment_end = min(length, cursor + pattern[pattern_index])
                if pattern_index % 2 == 0:
                    p1 = (start[0] + dx * cursor / length, start[1] + dy * cursor / length)
                    p2 = (start[0] + dx * segment_end / length, start[1] + dy * segment_end / length)
                    draw.line((p1, p2), fill=fill, width=width)
                cursor = segment_end
                pattern_index = (pattern_index + 1) % len(pattern)

    def get_font(size, family="Helvetica", style="normal"):
        family_key = family.casefold()
        if family_key == "courier new":
            regular = ("Courier New.ttf", "LiberationMono-Regular.ttf", "DejaVuSansMono.ttf")
            bold = ("Courier New Bold.ttf", "LiberationMono-Bold.ttf", "DejaVuSansMono-Bold.ttf")
            italic = ("Courier New Italic.ttf", "LiberationMono-Italic.ttf", "DejaVuSansMono-Oblique.ttf")
            bold_italic = (
                "Courier New Bold Italic.ttf",
                "LiberationMono-BoldItalic.ttf",
                "DejaVuSansMono-BoldOblique.ttf",
            )
        elif family_key == "times new roman":
            regular = ("Times New Roman.ttf", "LiberationSerif-Regular.ttf", "DejaVuSerif.ttf")
            bold = ("Times New Roman Bold.ttf", "LiberationSerif-Bold.ttf", "DejaVuSerif-Bold.ttf")
            italic = ("Times New Roman Italic.ttf", "LiberationSerif-Italic.ttf", "DejaVuSerif-Italic.ttf")
            bold_italic = (
                "Times New Roman Bold Italic.ttf",
                "LiberationSerif-BoldItalic.ttf",
                "DejaVuSerif-BoldItalic.ttf",
            )
        else:
            regular = ("Helvetica.ttf", "Arial.ttf", "LiberationSans-Regular.ttf", "DejaVuSans.ttf")
            bold = ("Arial_Bold.ttf", "arialbd.ttf", "LiberationSans-Bold.ttf", "DejaVuSans-Bold.ttf")
            italic = ("Arial_Italic.ttf", "ariali.ttf", "LiberationSans-Italic.ttf", "DejaVuSans-Oblique.ttf")
            bold_italic = (
                "Arial_BoldItalic.ttf",
                "arialbi.ttf",
                "LiberationSans-BoldItalic.ttf",
                "DejaVuSans-BoldOblique.ttf",
            )
        candidates = {
            "normal": regular,
            "bold": bold,
            "italic": italic,
            "bold italic": bold_italic,
        }.get(style, regular)
        if sys.platform == "win32":
            font_directories = [os.path.join(os.environ.get("WINDIR", "C:\\Windows"), "Fonts")]
        elif sys.platform == "darwin":
            font_directories = ["/System/Library/Fonts", "/Library/Fonts"]
        else:
            font_directories = [
                "/usr/share/fonts/truetype/liberation2",
                "/usr/share/fonts/truetype/liberation",
                "/usr/share/fonts/truetype/dejavu",
                "/usr/share/fonts/truetype/msttcorefonts",
                "/usr/share/fonts",
            ]
        font_paths = [
            os.path.join(directory, name)
            for directory in font_directories
            for name in candidates
        ]
        for name in (*font_paths, *candidates):
            try:
                return ImageFont.truetype(name, int(size * S))
            except OSError:
                pass
        return ImageFont.load_default()

    # Freehand Strokes (Draw & Brush)
    for st in getattr(model, "freehand_strokes", []):
        if not _layer_is_visible(model, st.get("layer", "Data")):
            continue
        pts = [P(px, py) for px, py in st.get("points", [])]
        if len(pts) >= 2:
            draw.line(pts, fill=st.get("color", "#ef4444"), width=max(1, round(st.get("width", 3) * S)), joint="curve")

    # Sticky Notes
    for s in model.sticky_notes.values():
        if not _layer_is_visible(model, s.get("layer", "Annotations")):
            continue
        sx, sy, sw, sh = s["x"], s["y"], s["w"], s["h"]
        p1 = P(sx - sw / 2, sy - sh / 2)
        p2 = P(sx + sw / 2, sy + sh / 2)
        draw.rounded_rectangle([p1, p2], radius=6 * S, fill=s["color"], outline="#eab308", width=max(1, S))
        draw.text(P(sx, sy), s["text"], fill="#713f12", font=get_font(11), anchor="mm")

    # Group parallel edges
    edge_pairs = {}
    for cid, c in model.conns.items():
        if _connection_is_visible(model, c):
            pair = tuple(sorted([c["a"], c["b"]]))
            edge_pairs.setdefault(pair, []).append(cid)

    # Connections
    for pair, cids in edge_pairs.items():
        total = len(cids)
        for idx, cid in enumerate(cids):
            cn = model.conns[cid]
            kind_g, raw, lab = get_conn_geom(model, cn, idx, total)
            pts = [P(px, py) for px, py in sample_curve(kind_g, raw)]
            col = cn.get("color", "#374151")
            wd = max(1, round(cn.get("width", 2) * S))
            draw_styled_line(
                pts, col, wd,
                cn.get("line_style", "dashed" if cn.get("dash") else "solid"),
            )

            # Arrowhead at end
            if cn.get("arrow") in ("forward", "both") and len(pts) >= 2:
                tip = pts[-1]
                prev = pts[-2]
                ang = math.atan2(tip[1] - prev[1], tip[0] - prev[0])
                L, B = 10 * S, 5 * S
                b1 = (tip[0] - L * math.cos(ang) + B * math.sin(ang), tip[1] - L * math.sin(ang) - B * math.cos(ang))
                b2 = (tip[0] - L * math.cos(ang) - B * math.sin(ang), tip[1] - L * math.sin(ang) + B * math.cos(ang))
                draw.polygon([tip, b1, b2], fill=col)

            lbl = cn.get("label", "")
            if cn.get("weight") and cn.get("weight") != 1.0:
                lbl = f"{lbl} (w:{cn['weight']})" if lbl else f"w:{cn['weight']}"
            if lbl:
                cx, cy = P(*lab)
                fnt = get_font(10)
                bb = draw.textbbox((cx, cy), lbl, font=fnt, anchor="mm")
                draw.rectangle((bb[0] - 4, bb[1] - 2, bb[2] + 4, bb[3] + 2), fill="#ffffff", outline="#e5e7eb")
                draw.text((cx, cy), lbl, fill="#374151", font=fnt, anchor="mm")

    # Nodes
    for n in model.nodes.values():
        if not _layer_is_visible(model, n.get("layer", "Data")):
            continue
        x, y, w, h = n["x"], n["y"], n["w"], n["h"]
        hw, hh = w / 2.0, h / 2.0
        sh = n.get("shape", "rounded")
        col = n.get("color", "#dbeafe")
        p1, p2 = P(x - hw, y - hh), P(x + hw, y + hh)
        kw = dict(fill=col, outline="#4b5563", width=max(1, round(1.5 * S)))

        if sh == "circle":
            draw.ellipse([p1, p2], **kw)
        elif sh == "square":
            side = max(w, h)
            sp1, sp2 = P(x - side / 2, y - side / 2), P(x + side / 2, y + side / 2)
            draw.rectangle([sp1, sp2], **kw)
        elif sh == "diamond":
            pts = [P(x, y - hh), P(x + hw, y), P(x, y + hh), P(x - hw, y)]
            draw.polygon(pts, **kw)
        elif sh == "triangle":
            pts = [P(x, y - hh), P(x + hw, y + hh), P(x - hw, y + hh)]
            draw.polygon(pts, **kw)
        elif sh == "hexagon":
            pts = []
            for k in range(6):
                ang = math.pi / 6 + k * math.pi / 3
                pts.append(P(x + hw * math.cos(ang), y + hh * math.sin(ang)))
            draw.polygon(pts, **kw)
        elif sh == "star":
            pts = []
            for k in range(10):
                ang = -math.pi / 2 + k * math.pi / 5
                r = hw if k % 2 == 0 else hw * 0.45
                pts.append(P(x + r * math.cos(ang), y + r * math.sin(ang)))
            draw.polygon(pts, **kw)
        elif sh == "parallelogram":
            off = hw * 0.3
            pts = [P(x - hw + off, y - hh), P(x + hw, y - hh), P(x + hw - off, y + hh), P(x - hw, y + hh)]
            draw.polygon(pts, **kw)
        elif sh in ("cylinder", "cloud", "callout"):
            draw.rounded_rectangle([p1, p2], radius=18 * S, **kw)
        elif sh == "rounded":
            draw.rounded_rectangle([p1, p2], radius=12 * S, **kw)
        elif sh == "rectangle":
            draw.rectangle([p1, p2], **kw)

        image_path = n.get("image_path")
        if image_path and os.path.isfile(image_path):
            with Image.open(image_path) as source:
                source = source.convert("RGBA")
                source.thumbnail(
                    (max(1, round((w - 14) * S)), max(1, round((h * 0.55) * S))),
                    Image.Resampling.LANCZOS,
                )
                ix, iy = P(x, y - hh * 0.18)
                img.paste(source, (round(ix - source.width / 2), round(iy - source.height / 2)), source)

        txt = n.get("text", "")
        if n.get("icon"):
            txt = f"{n['icon']} {txt}"
        fs = n.get("fs", 11)
        font = get_font(
            fs,
            n.get("font_family", "Helvetica"),
            n.get("font_style", "normal"),
        )
        text_y = y + (hh * 0.65 if image_path and os.path.isfile(image_path) else 0)
        draw.text(
            P(x, text_y),
            txt,
            fill=n.get("text_color") or "#111827",
            font=font,
            anchor="mm",
        )

    if kind == "pdf":
        img.save(filepath, "PDF", resolution=72 * S)
    else:
        img.save(filepath, "PNG")


# ---- 48. Screenshot to Clipboard
def copy_screenshot_to_clipboard(model, root):
    """Render image and copy to system clipboard using xclip or tkinter fallback."""
    try:
        buffer = io.BytesIO()
        export_raster(model, buffer, kind="png")
        data = buffer.getvalue()
        # Try xclip on Linux
        p = subprocess.Popen(["xclip", "-selection", "clipboard", "-t", "image/png"], stdin=subprocess.PIPE)
        p.communicate(input=data)
        if p.returncode == 0:
            return True
    except Exception as e:
        print("Clipboard copy error:", e)
    return False
