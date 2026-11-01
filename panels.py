"""
Unified Sidebar Panel Architecture (Canva, LibreOffice Draw, and Maltego).
Provides collapsible decks and context-sensitive tabs.
"""
import tkinter as tk
from tkinter import ttk, messagebox, colorchooser, filedialog
import os
import algorithms
import layouts
import investigation
from drawing_tools import BrandKit, LayerManager, PageManager, EXTENDED_SHAPES, ARROW_STYLES


class UnifiedSidebar(ttk.Frame):
    def __init__(self, parent, app):
        super().__init__(parent, width=320)
        self.app = parent if app is None else app
        self.brand_kit = BrandKit()
        self.layer_manager = LayerManager()
        self.page_manager = PageManager(self.app.model)

        self.pack_propagate(False)

        # Header with Collapse / Close button
        header = ttk.Frame(self, padding=(6, 4))
        header.pack(fill="x")
        ttk.Label(header, text="Toolbox & Inspector", font=("Helvetica", 10, "bold")).pack(side="left")
        ttk.Button(header, text="✕", width=3, command=self.app.toggle_sidebar).pack(side="right")

        # Notebook with Primary Tabs:
        # 1. Elements (Canva)
        # 2. Properties (LibreOffice Draw - Contextual)
        # 3. Investigation (Maltego)
        # 4. Notes & Media
        self.nb = ttk.Notebook(self)
        self.nb.pack(fill="both", expand=True)

        self.tab_elements = ttk.Frame(self.nb)
        self.tab_props = ttk.Frame(self.nb)
        self.tab_osint = ttk.Frame(self.nb)
        self.tab_notes = ttk.Frame(self.nb)

        self.nb.add(self.tab_elements, text="Elements")
        self.nb.add(self.tab_props, text="Inspector")
        self.nb.add(self.tab_osint, text="OSINT")
        self.nb.add(self.tab_notes, text="Notes")

        self.build_elements_tab()
        self.build_properties_tab()
        self.build_investigation_tab()
        self.build_notes_tab()

    # =========================================================================
    # TAB 1: Canva-Inspired Elements & Media Tab
    # =========================================================================
    def build_elements_tab(self):
        f = ttk.Frame(self.tab_elements, padding=8)
        f.pack(fill="both", expand=True)

        # Search bar
        srch_frame = ttk.Frame(f)
        srch_frame.pack(fill="x", pady=(0, 6))
        ttk.Label(srch_frame, text="🔍").pack(side="left")
        self.elem_search_var = tk.StringVar()
        elem_entry = ttk.Entry(srch_frame, textvariable=self.elem_search_var)
        elem_entry.pack(side="left", fill="x", expand=True, padx=4)
        elem_entry.bind("<KeyRelease>", lambda e: self.filter_elements())

        # Scrollable container for decks
        canvas = tk.Canvas(f, highlightthickness=0)
        sb = ttk.Scrollbar(f, orient="vertical", command=canvas.yview)
        deck_frame = ttk.Frame(canvas)

        deck_frame.bind("<Configure>", lambda e: canvas.configure(scrollregion=canvas.bbox("all")))
        canvas.create_window((0, 0), window=deck_frame, anchor="nw", width=280)
        canvas.configure(yscrollcommand=sb.set)

        canvas.pack(side="left", fill="both", expand=True)
        sb.pack(side="right", fill="y")
        self.elem_deck_frame = deck_frame

        # 1. Shapes & Building Blocks Deck
        self.deck_shapes = ttk.LabelFrame(deck_frame, text="Shapes & Symbols", padding=6)
        self.deck_shapes.pack(fill="x", pady=4)
        self.populate_shape_buttons()

        # 2. Brand Kit Deck (Centralized Brand Styles)
        deck_brand = ttk.LabelFrame(deck_frame, text="Brand Kit (Styles)", padding=6)
        deck_brand.pack(fill="x", pady=6)
        ttk.Label(deck_brand, text="Brand Palette (Click to Recolor):", font=("Helvetica", 8)).pack(anchor="w")

        self.brand_swatches = ttk.Frame(deck_brand)
        self.brand_swatches.pack(fill="x", pady=4)
        self.refresh_brand_swatches()

        btn_row = ttk.Frame(deck_brand)
        btn_row.pack(fill="x", pady=2)
        ttk.Button(btn_row, text="Apply Brand Theme", command=self.apply_brand_theme).pack(side="left", fill="x", expand=True, padx=1)
        ttk.Button(btn_row, text="+ Color", width=6, command=self.add_brand_color).pack(side="left", padx=1)

        # 3. Pre-designed Templates Deck
        deck_tmpl = ttk.LabelFrame(deck_frame, text="Templates", padding=6)
        deck_tmpl.pack(fill="x", pady=6)
        templates = [
            ("Org Chart", "org"),
            ("Network Topology", "mesh"),
            ("Mind Map", "mind"),
            ("Flowchart", "flow"),
            ("Cyber Threat Map", "cyber"),
        ]
        for title, key in templates:
            ttk.Button(deck_tmpl, text=f"📋  {title}", command=lambda k=key: self.app.load_template(k)).pack(fill="x", pady=2)

    def populate_shape_buttons(self):
        for widget in self.deck_shapes.winfo_children():
            widget.destroy()

        q = self.elem_search_var.get().strip().lower() if hasattr(self, "elem_search_var") else ""
        grid = ttk.Frame(self.deck_shapes)
        grid.pack(fill="x")

        col_idx = 0
        row_idx = 0
        for sh_id, info in EXTENDED_SHAPES.items():
            if q and q not in info["name"].lower() and q not in info["cat"].lower():
                continue
            btn = ttk.Button(grid, text=info["name"][:14], width=14,
                             command=lambda s=sh_id: self.add_shape_node(s))
            btn.grid(row=row_idx, column=col_idx, padx=2, pady=2, sticky="ew")
            col_idx += 1
            if col_idx >= 2:
                col_idx = 0
                row_idx += 1

    def filter_elements(self):
        self.populate_shape_buttons()

    def add_shape_node(self, shape):
        W = self.app.canvas.winfo_width() / 2.0
        H = self.app.canvas.winfo_height() / 2.0
        wx, wy = self.app.to_world(W, H)
        self.app.model.push_undo()
        nid = self.app.model.make_node(wx, wy, text=shape.title(), shape=shape)
        self.app.select(nodes={nid})
        self.app.redraw()

    def refresh_brand_swatches(self):
        for w in self.brand_swatches.winfo_children():
            w.destroy()
        for col in self.brand_kit.colors:
            lbl = tk.Label(self.brand_swatches, bg=col, width=2, height=1, relief="solid", bd=1, cursor="hand2")
            lbl.pack(side="left", padx=1)
            lbl.bind("<Button-1>", lambda e, c=col: self.recolor_selection(c))

    def add_brand_color(self):
        c = colorchooser.askcolor(title="Add Brand Color")[1]
        if c:
            self.brand_kit.colors.append(c)
            self.refresh_brand_swatches()

    def recolor_selection(self, col):
        if self.app.sel_nodes:
            self.app.model.push_undo()
            for nid in self.app.sel_nodes:
                self.app.model.nodes[nid]["color"] = col
            self.app.redraw()
        elif self.app.sel_conn and self.app.sel_conn in self.app.model.conns:
            self.app.model.push_undo()
            self.app.model.conns[self.app.sel_conn]["color"] = col
            self.app.redraw()

    def apply_brand_theme(self):
        self.brand_kit.apply_to_model(self.app.model)
        self.app.redraw()

    # =========================================================================
    # TAB 2: LibreOffice Draw-Inspired Diagramming & Properties Tab
    # =========================================================================
    def build_properties_tab(self):
        f = ttk.Frame(self.tab_props, padding=8)
        f.pack(fill="both", expand=True)

        canvas = tk.Canvas(f, highlightthickness=0)
        sb = ttk.Scrollbar(f, orient="vertical", command=canvas.yview)
        content = ttk.Frame(canvas)

        content.bind("<Configure>", lambda e: canvas.configure(scrollregion=canvas.bbox("all")))
        canvas.create_window((0, 0), window=content, anchor="nw", width=280)
        canvas.configure(yscrollcommand=sb.set)

        canvas.pack(side="left", fill="both", expand=True)
        sb.pack(side="right", fill="y")
        self.props_content = content

        # 1. Contextual Inspector Deck (switches based on selection)
        self.deck_inspector = ttk.LabelFrame(content, text="Context Inspector", padding=6)
        self.deck_inspector.pack(fill="x", pady=4)

        # 2. Connector Routing Panel
        deck_routing = ttk.LabelFrame(content, text="Connector Routing", padding=6)
        deck_routing.pack(fill="x", pady=6)
        rout_row = ttk.Frame(deck_routing)
        rout_row.pack(fill="x")
        for typ in ("Straight", "Curved", "Elbow", "Orthogonal"):
            ttk.Button(rout_row, text=typ, width=8,
                       command=lambda t=typ.lower(): self.set_connector_routing(t)).pack(side="left", padx=1)

        # Arrowhead options
        ttk.Label(deck_routing, text="Arrowhead Style:", font=("Helvetica", 8)).pack(anchor="w", pady=(4, 2))
        arr_row = ttk.Frame(deck_routing)
        arr_row.pack(fill="x")
        for a_style in ("forward", "backward", "both", "diamond", "circle"):
            ttk.Button(arr_row, text=a_style[:4], width=5,
                       command=lambda a=a_style: self.set_arrow_style(a)).pack(side="left", padx=1)

        # 3. Layers & Page Management Deck
        deck_layers = ttk.LabelFrame(content, text="Layers & Pages", padding=6)
        deck_layers.pack(fill="x", pady=6)

        # Layer toggles
        ttk.Label(deck_layers, text="Layers (Visible / Lock):", font=("Helvetica", 8, "bold")).pack(anchor="w")
        for l_name in ("Background", "Data", "Annotations"):
            row = ttk.Frame(deck_layers)
            row.pack(fill="x", pady=1)
            v_var = tk.BooleanVar(value=self.layer_manager.is_visible(l_name))
            cb_vis = ttk.Checkbutton(row, text=l_name, variable=v_var,
                                     command=lambda name=l_name: (self.layer_manager.toggle_visible(name), self.app.redraw()))
            cb_vis.pack(side="left")

        # Multi-page controls
        ttk.Separator(deck_layers, orient="horizontal").pack(fill="x", pady=4)
        ttk.Label(deck_layers, text="Multi-Page Document:", font=("Helvetica", 8, "bold")).pack(anchor="w")
        page_row = ttk.Frame(deck_layers)
        page_row.pack(fill="x", pady=2)
        self.page_var = tk.StringVar(value="Page 1")
        self.page_combo = ttk.Combobox(page_row, textvariable=self.page_var, values=list(self.page_manager.pages.keys()), width=12, state="readonly")
        self.page_combo.pack(side="left", padx=2)
        self.page_combo.bind("<<ComboboxSelected>>", lambda e: self.switch_document_page())
        ttk.Button(page_row, text="+ Page", width=6, command=self.add_document_page).pack(side="left", padx=2)

        # 4. Grid, Snap & Constrain Objects Deck
        deck_grid = ttk.LabelFrame(content, text="Grid & Constrain Alignment", padding=6)
        deck_grid.pack(fill="x", pady=6)
        ttk.Checkbutton(deck_grid, text="Snap to Grid", variable=self.app.snap_var).pack(anchor="w")
        ttk.Checkbutton(deck_grid, text="Show Grid", variable=self.app.grid_var, command=self.app.redraw).pack(anchor="w")
        self.constrain_var = tk.BooleanVar(value=False)
        ttk.Checkbutton(deck_grid, text="Constrain Axis (H / V only)", variable=self.constrain_var).pack(anchor="w")

        self.update_inspector_deck()

    def update_inspector_deck(self):
        """Context-sensitive inspector update."""
        for w in self.deck_inspector.winfo_children():
            w.destroy()

        if self.app.sel_nodes:
            nid = next(iter(self.app.sel_nodes))
            node = self.app.model.nodes.get(nid)
            if not node:
                return
            ttk.Label(self.deck_inspector, text=f"Node #{nid} ({node.get('shape', 'node').title()})", font=("Helvetica", 9, "bold")).pack(anchor="w")

            # Area Fill & Color
            r1 = ttk.Frame(self.deck_inspector)
            r1.pack(fill="x", pady=2)
            ttk.Label(r1, text="Fill Color:").pack(side="left")
            c_lbl = tk.Label(r1, bg=node["color"], width=4, relief="solid", bd=1)
            c_lbl.pack(side="left", padx=4)
            ttk.Button(r1, text="Pick...", command=self.app.pick_custom_node_color).pack(side="left")

            # Size controls (Width x Height)
            r2 = ttk.Frame(self.deck_inspector)
            r2.pack(fill="x", pady=2)
            ttk.Label(r2, text="W:").pack(side="left")
            w_sp = ttk.Spinbox(r2, from_=40, to=400, increment=10, width=5)
            w_sp.set(int(node["w"]))
            w_sp.pack(side="left", padx=2)
            w_sp.bind("<Return>", lambda e: self.set_node_size(nid, w_sp.get(), None))

            ttk.Label(r2, text="H:").pack(side="left")
            h_sp = ttk.Spinbox(r2, from_=30, to=300, increment=10, width=5)
            h_sp.set(int(node["h"]))
            h_sp.pack(side="left", padx=2)
            h_sp.bind("<Return>", lambda e: self.set_node_size(nid, None, h_sp.get()))

            # Typography / Label
            ttk.Button(self.deck_inspector, text="Edit Label...", command=self.app.edit_selected_inline).pack(fill="x", pady=4)

        elif self.app.sel_conn and self.app.sel_conn in self.app.model.conns:
            cid = self.app.sel_conn
            cn = self.app.model.conns[cid]
            ttk.Label(self.deck_inspector, text=f"Connection #{cid} ({cn['a']} → {cn['b']})", font=("Helvetica", 9, "bold")).pack(anchor="w")

            r1 = ttk.Frame(self.deck_inspector)
            r1.pack(fill="x", pady=2)
            ttk.Label(r1, text="Width:").pack(side="left")
            sp = ttk.Spinbox(r1, from_=1, to=10, width=4)
            sp.set(cn.get("width", 2))
            sp.pack(side="left", padx=4)
            sp.bind("<Return>", lambda e: self.set_conn_width(cid, sp.get()))

            ttk.Label(r1, text="Weight:").pack(side="left", padx=(4, 2))
            w_sp = ttk.Spinbox(r1, from_=0.1, to=100.0, increment=1.0, width=5)
            w_sp.set(cn.get("weight", 1.0))
            w_sp.pack(side="left", padx=2)
            w_sp.bind("<Return>", lambda e: self.set_conn_weight(cid, w_sp.get()))

            ttk.Button(self.deck_inspector, text="Reverse Direction", command=self.app.reverse_selected_conn).pack(fill="x", pady=2)
            ttk.Button(self.deck_inspector, text="Line Color...", command=self.app.pick_conn_color).pack(fill="x", pady=2)

        else:
            ttk.Label(self.deck_inspector, text="Canvas Inspector", font=("Helvetica", 9, "bold")).pack(anchor="w")
            ttk.Label(self.deck_inspector, text=f"Total Nodes: {len(self.app.model.nodes)}", font=("Helvetica", 8)).pack(anchor="w")
            ttk.Label(self.deck_inspector, text=f"Total Edges: {len(self.app.model.conns)}", font=("Helvetica", 8)).pack(anchor="w")
            ttk.Button(self.deck_inspector, text="Fit All in Window", command=self.app.fit).pack(fill="x", pady=4)

    def set_node_size(self, nid, w, h):
        self.app.model.push_undo()
        n = self.app.model.nodes[nid]
        if w:
            n["w"] = float(w)
        if h:
            n["h"] = float(h)
        self.app.model.update_spatial_node(nid)
        self.app.redraw()

    def set_conn_width(self, cid, val):
        self.app.model.push_undo()
        self.app.model.conns[cid]["width"] = int(val)
        self.app.redraw()

    def set_conn_weight(self, cid, val):
        self.app.model.push_undo()
        self.app.model.conns[cid]["weight"] = float(val)
        self.app.redraw()

    def set_connector_routing(self, routing_type):
        if self.app.sel_conn in self.app.model.conns:
            self.app.model.push_undo()
            self.app.model.conns[self.app.sel_conn]["type"] = routing_type
            self.app.redraw()
        else:
            self.app.line_var.set(routing_type)

    def set_arrow_style(self, arr):
        if self.app.sel_conn in self.app.model.conns:
            self.app.model.push_undo()
            self.app.model.conns[self.app.sel_conn]["arrow"] = arr
            self.app.redraw()
        else:
            self.app.arrow_var.set(arr)

    def switch_document_page(self):
        pg = self.page_var.get()
        self.page_manager.switch_page(pg)
        self.app.redraw()
        self.app.fit()

    def add_document_page(self):
        new_name = self.page_manager.add_page()
        self.page_combo.configure(values=list(self.page_manager.pages.keys()))
        self.page_var.set(new_name)
        self.app.redraw()

    # =========================================================================
    # TAB 3: Maltego-Inspired Investigation & Analysis Tab
    # =========================================================================
    def build_investigation_tab(self):
        f = ttk.Frame(self.tab_osint, padding=8)
        f.pack(fill="both", expand=True)

        canvas = tk.Canvas(f, highlightthickness=0)
        sb = ttk.Scrollbar(f, orient="vertical", command=canvas.yview)
        content = ttk.Frame(canvas)

        content.bind("<Configure>", lambda e: canvas.configure(scrollregion=canvas.bbox("all")))
        canvas.create_window((0, 0), window=content, anchor="nw", width=280)
        canvas.configure(yscrollcommand=sb.set)

        canvas.pack(side="left", fill="both", expand=True)
        sb.pack(side="right", fill="y")
        self.osint_content = content

        # 1. Entities Palette Deck
        deck_ent = ttk.LabelFrame(content, text="Entities Palette", padding=6)
        deck_ent.pack(fill="x", pady=4)
        ttk.Label(deck_ent, text="Click to Spawn Entity:", font=("Helvetica", 8)).pack(anchor="w")

        ent_grid = ttk.Frame(deck_ent)
        ent_grid.pack(fill="x", pady=2)
        col_idx, row_idx = 0, 0
        for name, cfg in investigation.ENTITY_TYPES.items():
            txt = f"{cfg['icon']} {name}"
            btn = ttk.Button(ent_grid, text=txt, width=13,
                             command=lambda ent=name, c=cfg: self.spawn_entity(ent, c))
            btn.grid(row=row_idx, column=col_idx, padx=2, pady=2, sticky="ew")
            col_idx += 1
            if col_idx >= 2:
                col_idx = 0
                row_idx += 1

        # 2. Transforms Panel Deck
        self.deck_transforms = ttk.LabelFrame(content, text="Node Transforms", padding=6)
        self.deck_transforms.pack(fill="x", pady=6)
        self.update_transforms_deck()

        # 3. Views (Size / Color by Metric) Deck
        deck_metrics = ttk.LabelFrame(content, text="Views (Size / Color by Metric)", padding=6)
        deck_metrics.pack(fill="x", pady=6)

        m_row1 = ttk.Frame(deck_metrics)
        m_row1.pack(fill="x", pady=2)
        ttk.Button(m_row1, text="Degree Heatmap", command=lambda: self.run_metric("degree", "both")).pack(side="left", fill="x", expand=True, padx=1)
        ttk.Button(m_row1, text="PageRank Size", command=lambda: self.run_metric("pagerank", "size")).pack(side="left", fill="x", expand=True, padx=1)

        m_row2 = ttk.Frame(deck_metrics)
        m_row2.pack(fill="x", pady=2)
        ttk.Button(m_row2, text="Betweenness", command=lambda: self.run_metric("betweenness", "both")).pack(side="left", fill="x", expand=True, padx=1)
        ttk.Button(m_row2, text="Reset Sizes", command=self.reset_entity_sizes).pack(side="left", fill="x", expand=True, padx=1)

        # 4. Graph Controls Deck (Freeze / Lock Layout)
        deck_ctrl = ttk.LabelFrame(content, text="Graph Controls", padding=6)
        deck_ctrl.pack(fill="x", pady=6)
        self.freeze_var = tk.BooleanVar(value=False)
        ttk.Checkbutton(deck_ctrl, text="Freeze Node Positions", variable=self.freeze_var).pack(anchor="w")

    def spawn_entity(self, ent_name, cfg):
        W = self.app.canvas.winfo_width() / 2.0
        H = self.app.canvas.winfo_height() / 2.0
        wx, wy = self.app.to_world(W, H)
        self.app.model.push_undo()
        nid = self.app.model.make_node(
            wx, wy,
            text=f"New {ent_name}",
            shape=cfg.get("shape", "rounded"),
            color=cfg.get("color", "#dbeafe"),
            icon=cfg.get("icon", "🏷️"),
            tags=[ent_name.lower()]
        )
        self.app.model.nodes[nid]["entity_type"] = ent_name
        self.app.select(nodes={nid})
        self.app.redraw()

    def update_transforms_deck(self):
        for w in self.deck_transforms.winfo_children():
            w.destroy()

        if len(self.app.sel_nodes) == 1:
            nid = next(iter(self.app.sel_nodes))
            node = self.app.model.nodes.get(nid)
            if not node:
                return
            ent_type = node.get("entity_type") or "Domain"
            ttk.Label(self.deck_transforms, text=f"Transforms for [{ent_type}]:", font=("Helvetica", 8, "bold")).pack(anchor="w", pady=(0, 4))
            tf_list = investigation.InvestigationEngine.get_available_transforms(ent_type)
            for title, key in tf_list:
                ttk.Button(self.deck_transforms, text=f"⚡ {title}",
                           command=lambda k=key, n=node: self.execute_transform(k, n)).pack(fill="x", pady=2)
        else:
            ttk.Label(self.deck_transforms, text="Select a single node to run OSINT transforms.", font=("Helvetica", 8), foreground="#6b7280").pack(anchor="w")

    def execute_transform(self, transform_key, node):
        spawned = investigation.InvestigationEngine.run_transform(transform_key, node, self.app.model)
        self.app.status.set(f"Transform executed: spawned {len(spawned)} entities.")
        self.app.redraw()
        self.app.fit()

    def run_metric(self, metric, mode):
        investigation.apply_metric_view(self.app.model, metric=metric, mode=mode)
        self.app.redraw()
        self.app.status.set(f"Applied {metric.title()} visual metric mapping.")

    def reset_entity_sizes(self):
        self.app.model.push_undo()
        for n in self.app.model.nodes.values():
            n["w"] = 130.0
            n["h"] = 60.0
            self.app.model.update_spatial_node(n["id"])
        self.app.redraw()

    # =========================================================================
    # TAB 4: Rich Notes, Media & Graph Bookmarks
    # =========================================================================
    def build_notes_tab(self):
        f = ttk.Frame(self.tab_notes, padding=8)
        f.pack(fill="both", expand=True)

        self.deck_node_notes = ttk.LabelFrame(f, text="Node Rich Notes", padding=6)
        self.deck_node_notes.pack(fill="both", expand=True, pady=4)

        ttk.Label(self.deck_node_notes, text="Notes & Observations:", font=("Helvetica", 8, "bold")).pack(anchor="w")
        self.note_text = tk.Text(self.deck_node_notes, height=8, wrap="word", font=("Helvetica", 9))
        self.note_text.pack(fill="both", expand=True, pady=4)

        # Image Attachment
        img_row = ttk.Frame(self.deck_node_notes)
        img_row.pack(fill="x", pady=2)
        self.note_img_var = tk.StringVar()
        ttk.Label(img_row, text="Image:").pack(side="left")
        ttk.Entry(img_row, textvariable=self.note_img_var, width=16).pack(side="left", padx=2)
        ttk.Button(img_row, text="Browse...", command=self.attach_note_image).pack(side="left")

        ttk.Button(self.deck_node_notes, text="Save Node Notes", command=self.save_current_node_notes).pack(fill="x", pady=4)

        # Bookmarks deck
        deck_bkm = ttk.LabelFrame(f, text="Graph Camera Bookmarks", padding=6)
        deck_bkm.pack(fill="x", pady=6)
        self.bookmarks = {}
        self.bkm_combo = ttk.Combobox(deck_bkm, values=[], state="readonly")
        self.bkm_combo.pack(fill="x", pady=2)
        self.bkm_combo.bind("<<ComboboxSelected>>", lambda e: self.restore_bookmark())

        bkm_btn_row = ttk.Frame(deck_bkm)
        bkm_btn_row.pack(fill="x", pady=2)
        ttk.Button(bkm_btn_row, text="Add Bookmark", command=self.add_bookmark).pack(side="left", fill="x", expand=True, padx=1)

        self.update_notes_tab()

    def update_notes_tab(self):
        self.note_text.delete("1.0", "end")
        self.note_img_var.set("")
        if len(self.app.sel_nodes) == 1:
            nid = next(iter(self.app.sel_nodes))
            node = self.app.model.nodes.get(nid)
            if node and "rich_notes" in node:
                notes_data = node["rich_notes"]
                self.note_text.insert("1.0", notes_data.get("text", ""))
                self.note_img_var.set(notes_data.get("image_path", ""))

    def attach_note_image(self):
        p = filedialog.askopenfilename(filetypes=[("Image Files", "*.png;*.jpg;*.jpeg;*.gif"), ("All Files", "*.*")])
        if p:
            self.note_img_var.set(p)

    def save_current_node_notes(self):
        if len(self.app.sel_nodes) == 1:
            nid = next(iter(self.app.sel_nodes))
            self.app.model.push_undo()
            self.app.model.nodes[nid]["rich_notes"] = {
                "text": self.note_text.get("1.0", "end-1c"),
                "image_path": self.note_img_var.get(),
            }
            self.app.status.set(f"Saved rich notes for Node #{nid}.")

    def add_bookmark(self):
        import tkinter.simpledialog as sd
        name = sd.askstring("Add Bookmark", "Bookmark name:", parent=self)
        if name:
            self.bookmarks[name] = (self.app.scale, self.app.ox, self.app.oy)
            self.bkm_combo.configure(values=list(self.bookmarks.keys()))
            self.bkm_combo.set(name)

    def restore_bookmark(self):
        name = self.bkm_combo.get()
        if name in self.bookmarks:
            sc, ox, oy = self.bookmarks[name]
            self.app.scale, self.app.ox, self.app.oy = sc, ox, oy
            self.app.redraw()

    def on_selection_changed(self):
        """Called whenever selection changes to refresh contextual decks."""
        self.update_inspector_deck()
        self.update_transforms_deck()
        self.update_notes_tab()

