"""
Graph data model, nodes, edges, sticky notes, undo/redo manager, and serialization.
"""
import copy
import json
from spatial_index import SpatialGrid

NODE_COLORS_LIGHT = ["#ffffff", "#dbeafe", "#dcfce7", "#fef9c3", "#fee2e2", "#ede9fe", "#fed7aa", "#ccfbf1"]
NODE_COLORS_DARK = ["#334155", "#1e3a8a", "#064e3b", "#713f12", "#881337", "#581c87", "#7c2d12", "#134e4a"]
NODE_COLORS_HC = ["#ffffff", "#ffff00", "#00ffff", "#ff00ff", "#00ff00", "#ff8800", "#ffffff", "#00ffff"]

LINE_COLORS_LIGHT = ["#374151", "#2563eb", "#16a34a", "#d97706", "#dc2626", "#7c3aed", "#0891b2", "#be185d"]
LINE_COLORS_DARK = ["#cbd5e1", "#60a5fa", "#4ade80", "#fbbf24", "#f87171", "#c084fc", "#22d3ee", "#f472b6"]
LINE_COLORS_HC = ["#ffffff", "#ffff00", "#00ffff", "#ff00ff", "#00ff00", "#ff8800", "#00e5ff", "#ff3366"]

SHAPES = ["rounded", "rectangle", "square", "circle", "diamond", "hexagon", "triangle", "star", "text", "cloud", "callout", "cylinder", "parallelogram"]
LINE_TYPES = ["straight", "curved", "elbow", "orthogonal"]
ARROWS = ["none", "forward", "backward", "both", "diamond", "circle", "crowfoot"]
WIDTHS = ["1", "2", "3", "4", "6"]
FSIZES = ["9", "11", "13", "16", "20", "28"]


class GraphModel:
    def __init__(self):
        self.nodes = {}  # nid -> dict
        self.conns = {}  # cid -> dict
        self.sticky_notes = {}  # sid -> dict
        self.freehand_strokes = []  # list of {"points": [...], "color": hex, "width": int}
        self.next_id = 1
        self.spatial = SpatialGrid(cell_size=120)

        # Document settings
        self.settings = {
            "theme": "light",
            "bg": None,
            "grid": True,
            "grid_style": "lines",
            "grid_size": 20,
            "snap": True,
            "drag_pan": "box",
            "minimap": True,
            "animated_flow": False,
            "show_legend": False,
            "show_tooltips": True,
            "lazy_edges": True,
            "viewport_culling": True,
            "default_node_color": NODE_COLORS_LIGHT[1],
            "default_shape": "rounded",
            "default_font_size": 11,
            "default_node_w": 130,
            "default_node_h": 60,
        }

        # Undo / redo
        self.undo_stack = []
        self.redo_stack = []
        self.dirty = False

    def new_id(self):
        i = self.next_id
        self.next_id += 1
        return i

    # ---- Node operations
    def make_node(self, x, y, text="Node", shape=None, color=None, w=None, h=None, fs=None, tags=None, metadata=None, icon=""):
        nid = self.new_id()
        w = w or self.settings["default_node_w"]
        h = h or self.settings["default_node_h"]
        shape = shape or self.settings["default_shape"]
        color = color or self.settings["default_node_color"]
        fs = fs or self.settings["default_font_size"]
        node = {
            "id": nid,
            "x": float(x),
            "y": float(y),
            "w": float(w),
            "h": float(h),
            "text": str(text),
            "shape": shape,
            "color": color,
            "fs": int(fs),
            "tags": list(tags) if tags else [],
            "metadata": dict(metadata) if metadata else {},
            "icon": icon or "",
            "badge": "",
            "highlight": None,
            "entity_type": "",
            "rich_notes": {"text": "", "image_path": "", "checklist": []},
        }
        self.nodes[nid] = node
        self.update_spatial_node(nid)
        return nid

    def update_spatial_node(self, nid):
        if nid in self.nodes:
            n = self.nodes[nid]
            hw, hh = n["w"] / 2, n["h"] / 2
            self.spatial.insert("node", nid, n["x"] - hw, n["y"] - hh, n["x"] + hw, n["y"] + hh)

    def remove_node(self, nid):
        if nid in self.nodes:
            self.spatial.remove("node", nid)
            del self.nodes[nid]
            # remove adjacent connections
            dead_conns = [cid for cid, c in self.conns.items() if c["a"] == nid or c["b"] == nid]
            for cid in dead_conns:
                self.remove_conn(cid)

    # ---- Edge operations
    def make_conn(self, a, b, label="", type_=None, arrow="forward", color=None, width=2, weight=1.0, dash=False):
        cid = self.new_id()
        color = color or LINE_COLORS_LIGHT[0]
        conn = {
            "id": cid,
            "a": a,
            "b": b,
            "type": type_ or "curved",
            "arrow": arrow,
            "dash": bool(dash),
            "color": color,
            "label": str(label),
            "width": int(width),
            "weight": float(weight),
            "highlight": None,
            "flow": None,
        }
        self.conns[cid] = conn
        self.update_spatial_conn(cid)
        return cid

    def update_spatial_conn(self, cid):
        if cid in self.conns:
            c = self.conns[cid]
            if c["a"] in self.nodes and c["b"] in self.nodes:
                na, nb = self.nodes[c["a"]], self.nodes[c["b"]]
                x0, y0 = min(na["x"], nb["x"]) - 20, min(na["y"], nb["y"]) - 20
                x1, y1 = max(na["x"], nb["x"]) + 20, max(na["y"], nb["y"]) + 20
                if c["a"] == c["b"]:  # self-loop
                    x0 -= 40
                    y0 -= 60
                    x1 += 40
                self.spatial.insert("conn", cid, x0, y0, x1, y1)

    def remove_conn(self, cid):
        if cid in self.conns:
            self.spatial.remove("conn", cid)
            del self.conns[cid]

    # ---- Sticky note operations
    def make_sticky_note(self, x, y, text="Note", w=140, h=100, color="#fef08a"):
        sid = self.new_id()
        note = {
            "id": sid,
            "x": float(x),
            "y": float(y),
            "w": float(w),
            "h": float(h),
            "text": str(text),
            "color": color,
        }
        self.sticky_notes[sid] = note
        self.update_spatial_sticky(sid)
        return sid

    def update_spatial_sticky(self, sid):
        if sid in self.sticky_notes:
            n = self.sticky_notes[sid]
            hw, hh = n["w"] / 2, n["h"] / 2
            self.spatial.insert("sticky", sid, n["x"] - hw, n["y"] - hh, n["x"] + hw, n["y"] + hh)

    def remove_sticky_note(self, sid):
        if sid in self.sticky_notes:
            self.spatial.remove("sticky", sid)
            del self.sticky_notes[sid]

    def rebuild_spatial_index(self):
        self.spatial.clear()
        for nid in self.nodes:
            self.update_spatial_node(nid)
        for cid in self.conns:
            self.update_spatial_conn(cid)
        for sid in self.sticky_notes:
            self.update_spatial_sticky(sid)

    # ---- Geometry & bounds
    def bounds(self, margin=60):
        if not self.nodes and not self.sticky_notes:
            return -200, -150, 400, 300
        xs, ys = [], []
        for n in self.nodes.values():
            xs.extend([n["x"] - n["w"] / 2, n["x"] + n["w"] / 2])
            ys.extend([n["y"] - n["h"] / 2, n["y"] + n["h"] / 2])
        for s in self.sticky_notes.values():
            xs.extend([s["x"] - s["w"] / 2, s["x"] + s["w"] / 2])
            ys.extend([s["y"] - s["h"] / 2, s["y"] + s["h"] / 2])
        x0, y0 = min(xs) - margin, min(ys) - margin
        x1, y1 = max(xs) + margin, max(ys) + margin
        return x0, y0, max(100.0, x1 - x0), max(100.0, y1 - y0)

    # ---- Undo / Redo snapshots
    def snapshot(self):
        return json.dumps({
            "nodes": list(self.nodes.values()),
            "conns": list(self.conns.values()),
            "sticky_notes": list(self.sticky_notes.values()),
            "freehand_strokes": list(self.freehand_strokes),
            "next_id": self.next_id,
        })

    def push_undo(self):
        self.undo_stack.append(self.snapshot())
        if len(self.undo_stack) > 150:
            del self.undo_stack[0]
        self.redo_stack.clear()
        self.dirty = True

    def undo(self):
        if self.undo_stack:
            self.redo_stack.append(self.snapshot())
            snap = self.undo_stack.pop()
            self.load_snapshot(snap)
            self.dirty = True
            return True
        return False

    def redo(self):
        if self.redo_stack:
            self.undo_stack.append(self.snapshot())
            snap = self.redo_stack.pop()
            self.load_snapshot(snap)
            self.dirty = True
            return True
        return False

    def load_snapshot(self, snap_json):
        d = json.loads(snap_json)
        self.load_dict(d)

    def load_dict(self, d):
        self.nodes.clear()
        self.conns.clear()
        self.sticky_notes.clear()
        self.freehand_strokes = list(d.get("freehand_strokes", []))

        for n in d.get("nodes", []):
            n.setdefault("w", 130)
            n.setdefault("h", 60)
            n.setdefault("shape", "rounded")
            n.setdefault("color", NODE_COLORS_LIGHT[1])
            n.setdefault("text", "")
            n.setdefault("fs", 11)
            n.setdefault("tags", [])
            n.setdefault("metadata", {})
            n.setdefault("icon", "")
            n.setdefault("badge", "")
            n.setdefault("highlight", None)
            n.setdefault("entity_type", "")
            n.setdefault("rich_notes", {"text": "", "image_path": "", "checklist": []})
            self.nodes[n["id"]] = n

        for c in d.get("conns", []):
            c.setdefault("type", "curved")
            c.setdefault("arrow", "forward")
            c.setdefault("dash", False)
            c.setdefault("color", LINE_COLORS_LIGHT[0])
            c.setdefault("label", "")
            c.setdefault("width", 2)
            c.setdefault("weight", 1.0)
            c.setdefault("highlight", None)
            c.setdefault("flow", None)
            self.conns[c["id"]] = c

        for s in d.get("sticky_notes", []):
            s.setdefault("w", 140)
            s.setdefault("h", 100)
            s.setdefault("text", "Note")
            s.setdefault("color", "#fef08a")
            self.sticky_notes[s["id"]] = s

        used_ids = list(self.nodes) + list(self.conns) + list(self.sticky_notes)
        self.next_id = max([d.get("next_id", 1)] + [i + 1 for i in used_ids])
        self.rebuild_spatial_index()

    def to_dict(self):
        return {
            "nodes": list(self.nodes.values()),
            "conns": list(self.conns.values()),
            "sticky_notes": list(self.sticky_notes.values()),
            "freehand_strokes": list(self.freehand_strokes),
            "next_id": self.next_id,
            "settings": dict(self.settings),
        }

    def clone_subgraph(self, node_ids, offset=40):
        """Clone selected nodes and edges connecting them."""
        node_ids = set(node_ids)
        id_map = {}
        new_nodes = []
        for nid in sorted(node_ids):
            if nid in self.nodes:
                old = self.nodes[nid]
                n2 = copy.deepcopy(old)
                n2["id"] = self.new_id()
                n2["x"] += offset
                n2["y"] += offset
                self.nodes[n2["id"]] = n2
                self.update_spatial_node(n2["id"])
                id_map[nid] = n2["id"]
                new_nodes.append(n2["id"])

        for cid, cn in list(self.conns.items()):
            if cn["a"] in id_map and cn["b"] in id_map:
                c2 = copy.deepcopy(cn)
                c2["id"] = self.new_id()
                c2["a"] = id_map[cn["a"]]
                c2["b"] = id_map[cn["b"]]
                self.conns[c2["id"]] = c2
                self.update_spatial_conn(c2["id"])

        return set(new_nodes)

    def clear_highlights(self):
        for n in self.nodes.values():
            n["highlight"] = None
            n["badge"] = ""
        for c in self.conns.values():
            c["highlight"] = None
            c["flow"] = None

