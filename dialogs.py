"""
Dialogs, Views, Overlays, and UI panels.
Covers features 17–20, 44–46, 51–55, 56–57, 60, 66.
"""
import json
import tkinter as tk
from tkinter import ttk, simpledialog, messagebox, colorchooser
from graph_model import SHAPES, LINE_TYPES, ARROWS, NODE_COLORS_LIGHT, LINE_COLORS_LIGHT
import algorithms


# ---- 17. Inline Label Editor on Canvas
class InlineTextEditor:
    def __init__(self, app, node_id, on_commit=None):
        self.app = app
        self.node_id = node_id
        self.on_commit = on_commit
        self.node = app.model.nodes.get(node_id)
        if not self.node:
            return

        sx, sy = app.to_screen(self.node["x"], self.node["y"])
        w = max(100, int(self.node["w"] * app.scale))
        h = max(36, int(self.node["h"] * app.scale))

        self.frame = tk.Frame(app.canvas, bg="#ffffff", bd=2, relief="solid")
        self.text_widget = tk.Text(self.frame, font=("Helvetica", max(9, int(self.node.get("fs", 11) * app.scale))),
                                   wrap="word", width=12, height=3, bd=0, highlightthickness=0)
        self.text_widget.pack(fill="both", expand=True, padx=2, pady=2)
        self.text_widget.insert("1.0", self.node["text"])
        self.text_widget.focus_set()
        self.text_widget.tag_add("sel", "1.0", "end")

        self.win = app.canvas.create_window(sx, sy, window=self.frame, width=w, height=h)

        self.text_widget.bind("<Return>", self._on_return)
        self.text_widget.bind("<Shift-Return>", lambda e: None)
        self.text_widget.bind("<Escape>", self._on_cancel)
        self.text_widget.bind("<FocusOut>", self._on_focus_out)

    def _on_return(self, event):
        if not (event.state & 0x1):  # Plain return commits
            self.commit()
            return "break"

    def _on_cancel(self, event=None):
        self.destroy()

    def _on_focus_out(self, event=None):
        self.commit()

    def commit(self):
        new_text = self.text_widget.get("1.0", "end-1c").strip()
        if new_text and self.node_id in self.app.model.nodes:
            self.app.model.push_undo()
            self.app.model.nodes[self.node_id]["text"] = new_text
            self.app.model.update_spatial_node(self.node_id)
            if self.on_commit:
                self.on_commit()
        self.destroy()

    def destroy(self):
        try:
            self.app.canvas.delete(self.win)
            self.frame.destroy()
        except Exception:
            pass
        self.app.canvas.focus_set()
        self.app.redraw()


# ---- 20. Right-Click Edge Context Menu
class EdgeContextMenu:
    def __init__(self, app, conn_id, x, y):
        self.app = app
        self.conn_id = conn_id
        cn = app.model.conns.get(conn_id)
        if not cn:
            return

        menu = tk.Menu(app.root, tearoff=0)

        # 18. Weight & Label editing
        menu.add_command(label=f"Edit Weight ({cn.get('weight', 1.0)})...", command=self.edit_weight)
        menu.add_command(label=f"Edit Label ('{cn.get('label', '')}')...", command=self.edit_label)
        menu.add_separator()

        # Type submenu
        t_menu = tk.Menu(menu, tearoff=0)
        for t in LINE_TYPES:
            t_menu.add_command(label=t.title(), command=lambda typ=t: self.set_type(typ))
        menu.add_cascade(label=f"Line Type: {cn.get('type', 'curved').title()}", menu=t_menu)

        # Arrow submenu
        a_menu = tk.Menu(menu, tearoff=0)
        for arr in ARROWS:
            a_menu.add_command(label=arr.title(), command=lambda a=arr: self.set_arrow(a))
        menu.add_cascade(label=f"Arrow: {cn.get('arrow', 'forward').title()}", menu=a_menu)

        # Reverse direction
        menu.add_command(label="Reverse Direction", command=self.reverse)
        menu.add_separator()

        # Color
        menu.add_command(label="Change Color...", command=self.pick_color)
        menu.add_command(label="Delete Connection", command=self.delete_conn)

        menu.tk_popup(x, y)

    def edit_weight(self):
        cn = self.app.model.conns.get(self.conn_id)
        if not cn:
            return
        w_val = simpledialog.askfloat("Edge Weight", "Enter edge weight (cost/capacity):",
                                      initialvalue=cn.get("weight", 1.0), parent=self.app.root)
        if w_val is not None:
            self.app.model.push_undo()
            cn["weight"] = max(0.01, float(w_val))
            self.app.redraw()

    def edit_label(self):
        cn = self.app.model.conns.get(self.conn_id)
        if not cn:
            return
        lbl = simpledialog.askstring("Connection Label", "Enter connection label:",
                                     initialvalue=cn.get("label", ""), parent=self.app.root)
        if lbl is not None:
            self.app.model.push_undo()
            cn["label"] = lbl
            self.app.redraw()

    def set_type(self, typ):
        cn = self.app.model.conns.get(self.conn_id)
        if cn:
            self.app.model.push_undo()
            cn["type"] = typ
            self.app.redraw()

    def set_arrow(self, arr):
        cn = self.app.model.conns.get(self.conn_id)
        if cn:
            self.app.model.push_undo()
            cn["arrow"] = arr
            self.app.redraw()

    def reverse(self):
        cn = self.app.model.conns.get(self.conn_id)
        if cn:
            self.app.model.push_undo()
            cn["a"], cn["b"] = cn["b"], cn["a"]
            self.app.redraw()

    def pick_color(self):
        cn = self.app.model.conns.get(self.conn_id)
        if not cn:
            return
        col = colorchooser.askcolor(cn.get("color", "#374151"), parent=self.app.root)[1]
        if col:
            self.app.model.push_undo()
            cn["color"] = col
            self.app.redraw()

    def delete_conn(self):
        self.app.model.push_undo()
        self.app.model.remove_conn(self.conn_id)
        self.app.sel_conn = None
        self.app.redraw()


# ---- 19. Keyboard Shortcuts Panel (?)
def show_shortcuts_panel(parent):
    w = tk.Toplevel(parent)
    w.title("Keyboard Shortcuts Cheat-Sheet")
    w.geometry("640x520")
    w.transient(parent)

    f = ttk.Frame(w, padding=16)
    f.pack(fill="both", expand=True)

    ttk.Label(f, text="Keyboard & Mouse Shortcuts", font=("Helvetica", 14, "bold")).pack(anchor="w", pady=(0, 10))

    tree = ttk.Treeview(f, columns=("Key", "Action"), show="headings", height=16)
    tree.heading("Key", text="Key / Shortcut")
    tree.heading("Action", text="Description")
    tree.column("Key", width=180)
    tree.column("Action", width=420)
    tree.pack(fill="both", expand=True)

    shortcuts = [
        ("V", "Select tool (click, shift-click, drag box, move)"),
        ("N", "Add Node tool (click canvas to create node)"),
        ("C / E", "Connect tool (drag node -> node)"),
        ("H", "Hand tool (drag to pan canvas)"),
        ("Delete / Backspace", "Delete selected node(s) or connection"),
        ("Enter / Double-Click", "Inline label editing on node"),
        ("Ctrl+Z", "Undo last mutation"),
        ("Ctrl+Y", "Redo last undone mutation"),
        ("Ctrl+C / Ctrl+X", "Copy / Cut selected subgraph"),
        ("Ctrl+V", "Paste subgraph with offset"),
        ("Ctrl+D", "Duplicate selected subgraph"),
        ("Ctrl+A", "Select all nodes"),
        ("Ctrl+F", "Find / Search nodes by label or tag"),
        ("F", "Fit graph to screen"),
        ("Space + Drag", "Pan the canvas smoothly"),
        ("Middle / Right Drag", "Pan the canvas"),
        ("Mouse Wheel", "Zoom in / Zoom out"),
        ("Shift + Wheel", "Pan sideways horizontally"),
        ("Ctrl + Wheel", "Pan vertically"),
        ("Arrow Keys", "Nudge selected nodes (Shift = 1px)"),
        ("?", "Open this Keyboard Shortcuts cheat-sheet"),
    ]

    for k, a in shortcuts:
        tree.insert("", "end", values=(k, a))

    ttk.Button(f, text="Close", command=w.destroy).pack(pady=(10, 0))


# ---- 46. Node-List View
class NodeListView(tk.Toplevel):
    def __init__(self, app):
        super().__init__(app.root)
        self.app = app
        self.title("Node List View")
        self.geometry("700x400")

        f = ttk.Frame(self, padding=10)
        f.pack(fill="both", expand=True)

        cols = ("ID", "Label", "Shape", "In-Deg", "Out-Deg", "Tags", "Position")
        self.tree = ttk.Treeview(f, columns=cols, show="headings", selectmode="browse")
        for col in cols:
            self.tree.heading(col, text=col, command=lambda c=col: self._sort_by(c))
            self.tree.column(col, width=90)
        self.tree.column("Label", width=180)

        sb = ttk.Scrollbar(f, orient="vertical", command=self.tree.yview)
        self.tree.configure(yscrollcommand=sb.set)
        self.tree.pack(side="left", fill="both", expand=True)
        sb.pack(side="right", fill="y")

        self.tree.bind("<Double-1>", self._on_double_click)
        self.populate()

    def populate(self):
        for item in self.tree.get_children():
            self.tree.delete(item)

        G = algorithms.to_networkx(self.app.model, directed=True)
        for nid, n in sorted(self.app.model.nodes.items()):
            in_d = G.in_degree(nid) if nid in G else 0
            out_d = G.out_degree(nid) if nid in G else 0
            pos = f"({int(n['x'])}, {int(n['y'])})"
            tags = ", ".join(n.get("tags", []))
            self.tree.insert("", "end", iid=str(nid),
                             values=(nid, n["text"], n["shape"], in_d, out_d, tags, pos))

    def _sort_by(self, col):
        pass

    def _on_double_click(self, event):
        sel = self.tree.selection()
        if sel:
            nid = int(sel[0])
            self.app.select(nodes={nid})
            # Center on node
            n = self.app.model.nodes[nid]
            W = self.app.canvas.winfo_width()
            H = self.app.canvas.winfo_height()
            self.app.ox = W / 2.0 - n["x"] * self.app.scale
            self.app.oy = H / 2.0 - n["y"] * self.app.scale
            self.app.redraw()


# ---- 45. Edge-List View
class EdgeListView(tk.Toplevel):
    def __init__(self, app):
        super().__init__(app.root)
        self.app = app
        self.title("Edge List View")
        self.geometry("700x400")

        f = ttk.Frame(self, padding=10)
        f.pack(fill="both", expand=True)

        cols = ("ID", "Source", "Target", "Weight", "Label", "Type", "Arrow")
        self.tree = ttk.Treeview(f, columns=cols, show="headings", selectmode="browse")
        for col in cols:
            self.tree.heading(col, text=col)
            self.tree.column(col, width=90)
        self.tree.column("Label", width=140)

        sb = ttk.Scrollbar(f, orient="vertical", command=self.tree.yview)
        self.tree.configure(yscrollcommand=sb.set)
        self.tree.pack(side="left", fill="both", expand=True)
        sb.pack(side="right", fill="y")

        self.tree.bind("<Double-1>", self._on_double_click)
        self.populate()

    def populate(self):
        for item in self.tree.get_children():
            self.tree.delete(item)

        for cid, c in sorted(self.app.model.conns.items()):
            src_lbl = self.app.model.nodes[c["a"]]["text"] if c["a"] in self.app.model.nodes else str(c["a"])
            tgt_lbl = self.app.model.nodes[c["b"]]["text"] if c["b"] in self.app.model.nodes else str(c["b"])
            self.tree.insert("", "end", iid=str(cid),
                             values=(cid, f"{c['a']} ({src_lbl})", f"{c['b']} ({tgt_lbl})",
                                     c.get("weight", 1.0), c.get("label", ""), c.get("type", "curved"), c.get("arrow", "forward")))

    def _on_double_click(self, event):
        sel = self.tree.selection()
        if sel:
            cid = int(sel[0])
            self.app.select(conn=cid)


# ---- 44. Adjacency-Matrix View
class AdjacencyMatrixView(tk.Toplevel):
    def __init__(self, app):
        super().__init__(app.root)
        self.app = app
        self.title("Adjacency Matrix")
        self.geometry("720x500")

        f = ttk.Frame(self, padding=10)
        f.pack(fill="both", expand=True)

        node_ids = sorted(app.model.nodes.keys())
        cols = ["Node"] + [f"{nid}" for nid in node_ids]

        tree = ttk.Treeview(f, columns=cols, show="headings")
        for col in cols:
            tree.heading(col, text=col)
            tree.column(col, width=50, anchor="center")
        tree.column("Node", width=120, anchor="w")

        # compute weights
        weights = {}
        for c in app.model.conns.values():
            weights[(c["a"], c["b"])] = c.get("weight", 1.0)

        for u in node_ids:
            lbl = f"{u}: {app.model.nodes[u]['text'][:12]}"
            row = [lbl]
            for v in node_ids:
                if (u, v) in weights:
                    row.append(str(weights[(u, v)]))
                else:
                    row.append("·")
            tree.insert("", "end", values=row)

        hsb = ttk.Scrollbar(f, orient="horizontal", command=tree.xview)
        vsb = ttk.Scrollbar(f, orient="vertical", command=tree.yview)
        tree.configure(xscrollcommand=hsb.set, yscrollcommand=vsb.set)
        tree.grid(row=0, column=0, sticky="nsew")
        vsb.grid(row=0, column=1, sticky="ns")
        hsb.grid(row=1, column=0, sticky="ew")
        f.grid_rowconfigure(0, weight=1)
        f.grid_columnconfigure(0, weight=1)


# ---- 51–55. Graph Properties Panel with Degree Histogram Mini-Chart
class GraphPropertiesDialog(tk.Toplevel):
    def __init__(self, app):
        super().__init__(app.root)
        self.app = app
        self.title("Graph Properties & Analysis")
        self.geometry("560x600")

        props = algorithms.compute_graph_properties(app.model)

        main = ttk.Frame(self, padding=16)
        main.pack(fill="both", expand=True)

        ttk.Label(main, text="Graph Metrics & Statistics", font=("Helvetica", 13, "bold")).pack(anchor="w", pady=(0, 8))

        info_frame = ttk.LabelFrame(main, text="Network Properties", padding=10)
        info_frame.pack(fill="x", pady=4)

        items = [
            ("Nodes Count", props["nodes"]),
            ("Edges Count", props["edges"]),
            ("Graph Density", f"{props['density']:.4f}"),
            ("Is DAG (Acyclic)?", "Yes" if props["is_dag"] else "No"),
            ("Is Connected?", "Yes" if props["is_connected"] else "No"),
            ("Clustering Coefficient", f"{props['avg_clustering']:.4f}"),
            ("Diameter", props["diameter"] if props["diameter"] is not None else "N/A"),
            ("Radius", props["radius"] if props["radius"] is not None else "N/A"),
            ("Avg Shortest Path Length", props["avg_path_length"] if props["avg_path_length"] is not None else "N/A"),
        ]

        for i, (k, v) in enumerate(items):
            row = i // 2
            col = (i % 2) * 2
            ttk.Label(info_frame, text=f"{k}:", font=("Helvetica", 9, "bold")).grid(row=row, column=col, sticky="w", padx=4, pady=2)
            ttk.Label(info_frame, text=str(v)).grid(row=row, column=col + 1, sticky="w", padx=(0, 16), pady=2)

        # 51. Mini Degree Histogram
        hist_frame = ttk.LabelFrame(main, text="Degree Distribution Histogram", padding=10)
        hist_frame.pack(fill="both", expand=True, pady=8)

        canvas = tk.Canvas(hist_frame, bg="#ffffff", height=180, highlightthickness=1, highlightbackground="#d1d5db")
        canvas.pack(fill="both", expand=True)

        deg_hist = props["degree_hist"]
        if deg_hist:
            max_deg = max(deg_hist.keys()) if deg_hist else 1
            max_count = max(deg_hist.values()) if deg_hist else 1
            w = 480
            h = 150
            bar_w = max(14, w // (max_deg + 2))

            canvas.create_line(40, h - 25, w - 10, h - 25, fill="#9ca3af")
            canvas.create_line(40, 15, 40, h - 25, fill="#9ca3af")

            for deg in range(max_deg + 1):
                count = deg_hist.get(deg, 0)
                bx = 50 + deg * bar_w
                bh = (count / max_count) * (h - 50) if max_count else 0
                canvas.create_rectangle(bx, h - 25 - bh, bx + bar_w - 4, h - 25, fill="#3b82f6", outline="#1d4ed8")
                canvas.create_text(bx + bar_w / 2 - 2, h - 14, text=str(deg), font=("Helvetica", 8), fill="#4b5563")
                if count > 0:
                    canvas.create_text(bx + bar_w / 2 - 2, h - 32 - bh, text=str(count), font=("Helvetica", 8, "bold"), fill="#1e3a8a")

        ttk.Button(main, text="Close", command=self.destroy).pack(pady=(6, 0))


# ---- 57. Rich Node Metadata Editor
class NodeMetadataEditor(tk.Toplevel):
    def __init__(self, app, node_id):
        super().__init__(app.root)
        self.app = app
        self.node_id = node_id
        self.node = app.model.nodes.get(node_id)
        self.title(f"Node Metadata - ID {node_id}")
        self.geometry("450x360")

        f = ttk.Frame(self, padding=12)
        f.pack(fill="both", expand=True)

        ttk.Label(f, text=f"Metadata for Node: {self.node['text']}", font=("Helvetica", 11, "bold")).pack(anchor="w", pady=(0, 6))

        self.tree = ttk.Treeview(f, columns=("Key", "Value"), show="headings", height=8)
        self.tree.heading("Key", text="Attribute Key")
        self.tree.heading("Value", text="Value")
        self.tree.pack(fill="both", expand=True)

        for k, v in self.node.get("metadata", {}).items():
            self.tree.insert("", "end", values=(k, v))

        btn_bar = ttk.Frame(f)
        btn_bar.pack(fill="x", pady=6)
        ttk.Button(btn_bar, text="Add Attribute", command=self.add_attr).pack(side="left", padx=2)
        ttk.Button(btn_bar, text="Delete Attribute", command=self.del_attr).pack(side="left", padx=2)
        ttk.Button(btn_bar, text="Close", command=self.destroy).pack(side="right")

    def add_attr(self):
        k = simpledialog.askstring("Add Attribute", "Enter property name (key):", parent=self)
        if k:
            v = simpledialog.askstring("Add Attribute", f"Enter value for '{k}':", parent=self)
            if v is not None:
                self.app.model.push_undo()
                self.node.setdefault("metadata", {})[k] = v
                self.tree.insert("", "end", values=(k, v))

    def del_attr(self):
        sel = self.tree.selection()
        if sel:
            item = sel[0]
            k = self.tree.item(item, "values")[0]
            if k in self.node.get("metadata", {}):
                self.app.model.push_undo()
                del self.node["metadata"][k]
            self.tree.delete(item)


# ---- 56. Node Tags / Categories Dialog
class TagsManagerDialog(tk.Toplevel):
    def __init__(self, app):
        super().__init__(app.root)
        self.app = app
        self.title("Tags & Categories Manager")
        self.geometry("420x360")

        f = ttk.Frame(self, padding=12)
        f.pack(fill="both", expand=True)

        ttk.Label(f, text="Node Tags / Categories", font=("Helvetica", 11, "bold")).pack(anchor="w", pady=(0, 6))

        all_tags = set()
        for n in app.model.nodes.values():
            all_tags.update(n.get("tags", []))

        self.listbox = tk.Listbox(f, height=8)
        self.listbox.pack(fill="both", expand=True)
        for t in sorted(all_tags):
            self.listbox.insert("end", t)

        btn_bar = ttk.Frame(f)
        btn_bar.pack(fill="x", pady=8)
        ttk.Button(btn_bar, text="Filter / Select Tag", command=self.filter_tag).pack(side="left", padx=2)
        ttk.Button(btn_bar, text="Color by Tags", command=self.color_by_tags).pack(side="left", padx=2)
        ttk.Button(btn_bar, text="Add Tag to Selected", command=self.add_tag_to_selected).pack(side="left", padx=2)

    def filter_tag(self):
        sel = self.listbox.curselection()
        if sel:
            tag = self.listbox.get(sel[0])
            matched = [nid for nid, n in self.app.model.nodes.items() if tag in n.get("tags", [])]
            self.app.select(nodes=set(matched))
            self.app.status.set(f"Selected {len(matched)} node(s) with tag '{tag}'.")
            self.destroy()

    def color_by_tags(self):
        self.app.model.push_undo()
        tag_colors = {}
        idx = 0
        palette = algorithms.DISTINCT_COLORS
        for n in self.app.model.nodes.values():
            if n.get("tags"):
                first_tag = n["tags"][0]
                if first_tag not in tag_colors:
                    tag_colors[first_tag] = palette[idx % len(palette)]
                    idx += 1
                n["color"] = tag_colors[first_tag]
        self.app.redraw()
        self.destroy()

    def add_tag_to_selected(self):
        tag = simpledialog.askstring("Add Tag", "Enter tag name:", parent=self)
        if tag and self.app.sel_nodes:
            self.app.model.push_undo()
            for nid in self.app.sel_nodes:
                tags = self.app.model.nodes[nid].setdefault("tags", [])
                if tag not in tags:
                    tags.append(tag)
            self.destroy()


# ---- 66. Preferences Dialog
class PreferencesDialog(tk.Toplevel):
    def __init__(self, app):
        super().__init__(app.root)
        self.app = app
        self.title("Preferences")
        self.geometry("480x420")
        self.resizable(False, False)

        f = ttk.Frame(self, padding=16)
        f.pack(fill="both", expand=True)

        pad = dict(sticky="w", pady=4)
        ttk.Label(f, text="Preferences & Defaults", font=("Helvetica", 12, "bold")).grid(row=0, column=0, columnspan=2, pady=(0, 10))

        # Default Node Color
        ttk.Label(f, text="Default Node Color:").grid(row=1, column=0, **pad)
        fr_col = ttk.Frame(f)
        fr_col.grid(row=1, column=1, **pad)
        self.col_lbl = tk.Label(fr_col, bg=app.model.settings["default_node_color"], width=4, relief="solid", bd=1)
        self.col_lbl.pack(side="left", padx=4)
        ttk.Button(fr_col, text="Choose...", command=self.pick_default_col).pack(side="left")

        # Default Shape
        ttk.Label(f, text="Default Shape:").grid(row=2, column=0, **pad)
        self.shape_var = tk.StringVar(value=app.model.settings["default_shape"])
        cb_shape = ttk.Combobox(f, textvariable=self.shape_var, values=SHAPES, state="readonly", width=12)
        cb_shape.grid(row=2, column=1, **pad)

        # Default Font Size
        ttk.Label(f, text="Default Font Size:").grid(row=3, column=0, **pad)
        self.fs_var = tk.IntVar(value=app.model.settings["default_font_size"])
        sp_fs = ttk.Spinbox(f, from_=8, to=32, textvariable=self.fs_var, width=6)
        sp_fs.grid(row=3, column=1, **pad)

        # Theme
        ttk.Label(f, text="Theme:").grid(row=4, column=0, **pad)
        self.theme_var = tk.StringVar(value=app.model.settings["theme"])
        fr_th = ttk.Frame(f)
        fr_th.grid(row=4, column=1, **pad)
        for t in ("light", "dark", "high_contrast"):
            ttk.Radiobutton(fr_th, text=t.replace("_", "-").title(), value=t, variable=self.theme_var).pack(side="left", padx=3)

        # Viewport Culling & Lazy Rendering
        ttk.Label(f, text="Performance:").grid(row=5, column=0, **pad)
        fr_perf = ttk.Frame(f)
        fr_perf.grid(row=5, column=1, **pad)
        self.cull_var = tk.BooleanVar(value=app.model.settings.get("viewport_culling", True))
        self.lazy_var = tk.BooleanVar(value=app.model.settings.get("lazy_edges", True))
        ttk.Checkbutton(fr_perf, text="Viewport Culling", variable=self.cull_var).pack(anchor="w")
        ttk.Checkbutton(fr_perf, text="Lazy Edge Details on Zoom", variable=self.lazy_var).pack(anchor="w")

        # Grid
        ttk.Label(f, text="Grid Settings:").grid(row=6, column=0, **pad)
        fr_grid = ttk.Frame(f)
        fr_grid.grid(row=6, column=1, **pad)
        self.grid_var = tk.BooleanVar(value=app.model.settings["grid"])
        self.snap_var = tk.BooleanVar(value=app.model.settings["snap"])
        ttk.Checkbutton(fr_grid, text="Show Grid", variable=self.grid_var).pack(side="left", padx=2)
        ttk.Checkbutton(fr_grid, text="Snap to Grid", variable=self.snap_var).pack(side="left", padx=4)

        ttk.Button(f, text="Save Preferences", command=self.save).grid(row=7, column=0, columnspan=2, pady=(16, 0))

    def pick_default_col(self):
        c = colorchooser.askcolor(self.app.model.settings["default_node_color"], parent=self)[1]
        if c:
            self.col_lbl.config(bg=c)

    def save(self):
        s = self.app.model.settings
        s["default_node_color"] = self.col_lbl.cget("bg")
        s["default_shape"] = self.shape_var.get()
        s["default_font_size"] = self.fs_var.get()
        s["theme"] = self.theme_var.get()
        s["viewport_culling"] = self.cull_var.get()
        s["lazy_edges"] = self.lazy_var.get()
        s["grid"] = self.grid_var.get()
        s["snap"] = self.snap_var.get()
        self.app.theme.set(s["theme"])
        self.app.grid_var.set(s["grid"])
        self.app.snap_var.set(s["snap"])
        self.app.redraw()
        self.destroy()

