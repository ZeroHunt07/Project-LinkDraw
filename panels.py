"""
Unified Sidebar Panel Architecture (Canva, LibreOffice Draw, and Maltego).
Provides collapsible decks and context-sensitive tabs.
"""
import tkinter as tk
from tkinter import ttk, messagebox, colorchooser, filedialog, simpledialog
import os
import re
import webbrowser
from urllib.parse import quote_plus
import algorithms
import layouts
import linkdraw_investigation
import notes_store
from drawing_tools import BrandKit, LayerManager, PageManager, EXTENDED_SHAPES, ARROW_STYLES
from graph_model import FONT_FAMILIES, FONT_STYLES, FSIZES, LINE_STYLES


class UnifiedSidebar(ttk.Frame):
    def __init__(self, parent, app):
        super().__init__(parent, width=320)
        self.app = parent if app is None else app
        self.brand_kit = BrandKit()
        saved_colors = self.app.model.settings.get("brand_colors")
        if isinstance(saved_colors, list) and saved_colors:
            self.brand_kit.colors = list(saved_colors)
        self.layer_manager = LayerManager(self.app.model)
        self.page_manager = PageManager(self.app.model)
        try:
            self.standalone_notes = notes_store.load_notes()
        except (OSError, ValueError) as exc:
            self.standalone_notes = []
            messagebox.showerror(
                "Could not load notes",
                f"Standalone notes could not be loaded:\n{exc}",
                parent=self,
            )
        self.active_standalone_note_id = None
        self.standalone_save_after = None
        self.loaded_node_note_id = None
        self.node_note_save_after = None
        self.loading_standalone_note = False
        self.loading_node_note = False
        self.osint_window = None

        self.pack_propagate(False)

        # Header with Collapse / Close button
        header = ttk.Frame(self, padding=(6, 4))
        header.pack(fill="x")
        ttk.Label(header, text="Toolbox & Inspector", font=("Helvetica", 10, "bold")).pack(side="left")
        ttk.Button(header, text="✕", width=3, command=self.app.toggle_sidebar).pack(side="right")

        # Notebook with Primary Tabs:
        # 1. Elements (Canva)
        # 2. Properties (LibreOffice Draw - Contextual)
        # 3. OSINT research opens in its own workspace window.
        self.nb = ttk.Notebook(self)
        self.nb.pack(fill="both", expand=True)

        self.tab_elements = ttk.Frame(self.nb)
        self.tab_props = ttk.Frame(self.nb)

        self.nb.add(self.tab_elements, text="Elements")
        self.nb.add(self.tab_props, text="Inspector")

        self.build_elements_tab()
        self.build_properties_tab()

    def open_osint_window(self):
        if self.osint_window is not None and self.osint_window.winfo_exists():
            self.osint_window.deiconify()
            self.osint_window.lift()
            self.osint_window.focus_force()
            self.update_transforms_deck()
            return self.osint_window

        window = tk.Toplevel(self.app.root)
        window.title("LinkDraw Pro — OSINT Research")
        window.geometry("460x760")
        window.minsize(400, 520)
        window.transient(self.app.root)
        self.osint_window = window

        self.build_investigation_tab(window)
        self.update_transforms_deck()

        def close_window():
            self.save_osint_workbench_state()
            self.osint_window = None
            window.destroy()

        window.protocol("WM_DELETE_WINDOW", close_window)
        return window

    @staticmethod
    def _scrollable_content(parent):
        canvas = tk.Canvas(parent, highlightthickness=0)
        scrollbar = ttk.Scrollbar(parent, orient="vertical", command=canvas.yview)
        content = ttk.Frame(canvas)
        window_id = canvas.create_window((0, 0), window=content, anchor="nw")

        content.bind(
            "<Configure>",
            lambda _event: canvas.configure(scrollregion=canvas.bbox("all")),
        )
        canvas.bind(
            "<Configure>",
            lambda event: canvas.itemconfigure(window_id, width=event.width),
        )
        canvas.configure(yscrollcommand=scrollbar.set)
        canvas.pack(side="left", fill="both", expand=True)
        scrollbar.pack(side="right", fill="y")
        return canvas, content

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
        canvas, deck_frame = self._scrollable_content(f)
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
        ttk.Button(
            deck_brand, text="Color Connections", command=self.apply_brand_to_connections
        ).pack(fill="x", pady=(3, 0))

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
        self.app.model.nodes[nid]["layer"] = self.active_layer_var.get()
        self.app.select(nodes={nid})
        self.app.redraw()

    def set_selected_layer(self, layer_name):
        if layer_name not in self.layer_manager.layers:
            raise ValueError(f"Unknown layer: {layer_name}")
        targets = [
            node for nid, node in self.app.model.nodes.items()
            if nid in self.app.sel_nodes
        ]
        if not targets or all(node.get("layer", "Data") == layer_name for node in targets):
            return
        self.app.model.push_undo()
        for node in targets:
            node["layer"] = layer_name
        self.app.dirty = True
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
            self.app.model.settings["brand_colors"] = list(self.brand_kit.colors)
            self.app.model.dirty = True
            self.app.dirty = True
            self.refresh_brand_swatches()
            self.refresh_inspector_palette()
            self.app.update_color_swatches()

    def recolor_selection(self, col):
        if self.app.sel_nodes:
            self.app.model.push_undo()
            for nid in self.app.sel_nodes:
                self.app.model.nodes[nid]["color"] = col
            self.app.dirty = True
            self.app.redraw()
        elif self.app.sel_conn and self.app.sel_conn in self.app.model.conns:
            self.app.model.push_undo()
            self.app.model.conns[self.app.sel_conn]["color"] = col
            self.app.dirty = True
            self.app.redraw()

    def apply_brand_theme(self):
        self.brand_kit.apply_to_model(self.app.model)
        if self.app.model.nodes:
            self.app.dirty = True
        self.app.redraw()

    def apply_brand_to_connections(self):
        if not self.app.model.conns:
            self.app.status.set("Add a connection before applying the brand palette.")
            return
        self.app.model.push_undo()
        self.app.dirty = True
        palette = self.brand_kit.colors
        for index, cid in enumerate(sorted(self.app.model.conns)):
            self.app.model.conns[cid]["color"] = palette[index % len(palette)]
        if self.app.sel_conn in self.app.model.conns:
            self.app.line_color_var.set(self.app.model.conns[self.app.sel_conn]["color"])
        self.app.redraw()
        self.app.status.set("Applied the brand palette to connections.")

    # =========================================================================
    # TAB 2: LibreOffice Draw-Inspired Diagramming & Properties Tab
    # =========================================================================
    def build_properties_tab(self):
        f = ttk.Frame(self.tab_props, padding=8)
        f.pack(fill="both", expand=True)

        _canvas, content = self._scrollable_content(f)
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
                                     command=lambda name=l_name: self.toggle_layer_visibility(name))
            cb_vis.pack(side="left")
            locked_var = tk.BooleanVar(value=self.layer_manager.is_locked(l_name))
            ttk.Checkbutton(
                row, text="Lock", variable=locked_var,
                command=lambda name=l_name: self.toggle_layer_lock(name),
            ).pack(side="right")

        layer_row = ttk.Frame(deck_layers)
        layer_row.pack(fill="x", pady=(3, 0))
        ttk.Label(layer_row, text="New elements").pack(side="left")
        self.active_layer_var = tk.StringVar(value=self.layer_manager.active_layer)
        ttk.Combobox(
            layer_row, textvariable=self.active_layer_var,
            values=list(self.layer_manager.layers), state="readonly", width=14,
        ).pack(side="right")

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
        ttk.Checkbutton(
            deck_grid, text="Snap to Grid", variable=self.app.snap_var,
            command=self.app.on_view_setting_change,
        ).pack(anchor="w")
        ttk.Checkbutton(
            deck_grid, text="Show Grid", variable=self.app.grid_var,
            command=self.app.on_view_setting_change,
        ).pack(anchor="w")
        self.constrain_var = tk.BooleanVar(value=False)
        ttk.Checkbutton(deck_grid, text="Constrain Axis (H / V only)", variable=self.constrain_var).pack(anchor="w")

        self.update_inspector_deck()

    def toggle_layer_visibility(self, name):
        self.layer_manager.toggle_visible(name)
        self.app.dirty = True
        self.app.redraw()

    def toggle_layer_lock(self, name):
        self.layer_manager.toggle_locked(name)
        self.app.dirty = True
        self.app.redraw()

    def update_inspector_deck(self):
        """Context-sensitive inspector update."""
        for w in self.deck_inspector.winfo_children():
            w.destroy()

        if self.app.sel_nodes:
            selected_ids = sorted(self.app.sel_nodes)
            nid = selected_ids[0]
            node = self.app.model.nodes.get(nid)
            if not node:
                return
            selection_text = (
                f"{len(selected_ids)} nodes selected"
                if len(selected_ids) > 1
                else f"Node #{nid} ({node.get('shape', 'node').title()})"
            )
            ttk.Label(
                self.deck_inspector, text=selection_text,
                font=("Helvetica", 9, "bold"),
            ).pack(anchor="w")
            layer_row = ttk.Frame(self.deck_inspector)
            layer_row.pack(fill="x", pady=(4, 2))
            ttk.Label(layer_row, text="Layer").pack(side="left")
            layer_var = tk.StringVar(value=node.get("layer", "Data"))
            layer_combo = ttk.Combobox(
                layer_row, textvariable=layer_var,
                values=list(self.layer_manager.layers), state="readonly", width=16,
            )
            layer_combo.pack(side="right")
            layer_combo.bind(
                "<<ComboboxSelected>>",
                lambda _event: self.set_selected_layer(layer_var.get()),
            )

            palette_row = ttk.Frame(self.deck_inspector)
            palette_row.pack(fill="x", pady=(4, 2))
            ttk.Label(palette_row, text="Fill").pack(side="left", padx=(0, 4))
            self.inspector_palette = ttk.Frame(palette_row)
            self.inspector_palette.pack(side="left", fill="x", expand=True)
            self.refresh_inspector_palette()
            ttk.Button(
                palette_row, text="Pick…", width=6,
                command=self.app.pick_custom_node_color,
            ).pack(side="right", padx=(4, 0))

            size_row = ttk.Frame(self.deck_inspector)
            size_row.pack(fill="x", pady=2)
            ttk.Label(size_row, text="Width").pack(side="left")
            w_sp = ttk.Spinbox(size_row, from_=40, to=400, increment=10, width=5)
            w_sp.set(int(node["w"]))
            w_sp.pack(side="left", padx=(3, 8))
            w_sp.bind("<Return>", lambda e: self.set_node_size(nid, w_sp.get(), None))

            ttk.Label(size_row, text="Height").pack(side="left")
            h_sp = ttk.Spinbox(size_row, from_=30, to=300, increment=10, width=5)
            h_sp.set(int(node["h"]))
            h_sp.pack(side="left", padx=3)
            h_sp.bind("<Return>", lambda e: self.set_node_size(nid, None, h_sp.get()))

            typography = ttk.LabelFrame(self.deck_inspector, text="Typography", padding=4)
            typography.pack(fill="x", pady=(4, 2))
            font_row = ttk.Frame(typography)
            font_row.pack(fill="x", pady=2)
            ttk.Label(font_row, text="Font").pack(side="left")
            font_var = tk.StringVar(value=node.get("font_family", "Helvetica"))
            font_combo = ttk.Combobox(
                font_row, textvariable=font_var, values=FONT_FAMILIES,
                state="readonly", width=14,
            )
            font_combo.pack(side="left", fill="x", expand=True, padx=4)
            font_combo.bind(
                "<<ComboboxSelected>>",
                lambda e: self.set_selected_node_property("font_family", font_var.get()),
            )

            type_row = ttk.Frame(typography)
            type_row.pack(fill="x", pady=2)
            ttk.Label(type_row, text="Size").pack(side="left")
            size_var = tk.StringVar(value=str(node.get("fs", 11)))
            size_combo = ttk.Combobox(
                type_row, textvariable=size_var, values=FSIZES,
                state="readonly", width=5,
            )
            size_combo.pack(side="left", padx=4)
            size_combo.bind(
                "<<ComboboxSelected>>",
                lambda e: self.set_selected_node_property("fs", int(size_var.get())),
            )
            ttk.Label(type_row, text="Style").pack(side="left", padx=(6, 2))
            font_style_var = tk.StringVar(value=node.get("font_style", "normal"))
            font_style_combo = ttk.Combobox(
                type_row, textvariable=font_style_var, values=FONT_STYLES,
                state="readonly", width=12,
            )
            font_style_combo.pack(side="left", fill="x", expand=True)
            font_style_combo.bind(
                "<<ComboboxSelected>>",
                lambda e: self.set_selected_node_property("font_style", font_style_var.get()),
            )

            text_color_row = ttk.Frame(typography)
            text_color_row.pack(fill="x", pady=(3, 1))
            text_color = node.get("text_color") or "Automatic"
            ttk.Label(text_color_row, text=f"Text color: {text_color}").pack(side="left")
            ttk.Button(
                text_color_row, text="Pick…",
                command=self.app.pick_node_text_color,
            ).pack(side="right")
            ttk.Button(
                text_color_row, text="Automatic",
                command=self.app.reset_node_text_color,
            ).pack(side="right", padx=3)

            ttk.Button(
                self.deck_inspector, text="Edit Label…",
                command=self.app.edit_selected_inline,
            ).pack(fill="x", pady=4)

        elif self.app.sel_conn and self.app.sel_conn in self.app.model.conns:
            cid = self.app.sel_conn
            cn = self.app.model.conns[cid]
            ttk.Label(self.deck_inspector, text=f"Connection #{cid} ({cn['a']} → {cn['b']})", font=("Helvetica", 9, "bold")).pack(anchor="w")
            ttk.Label(
                self.deck_inspector,
                text="Drag the orange midpoint handle on the canvas to bend this line.",
                wraplength=265,
            ).pack(anchor="w", pady=(2, 4))

            r1 = ttk.Frame(self.deck_inspector)
            r1.pack(fill="x", pady=2)
            ttk.Label(r1, text="Width:").pack(side="left")
            sp = ttk.Spinbox(r1, from_=1, to=10, width=4)
            sp.set(cn.get("width", 2))
            sp.pack(side="left", padx=4)
            sp.bind("<Return>", lambda e: self.set_conn_width(cid, sp.get()))

            ttk.Label(r1, text="Pattern:").pack(side="left", padx=(4, 2))
            line_style_var = tk.StringVar(
                value=cn.get("line_style", "dashed" if cn.get("dash") else "solid")
            )
            line_style_combo = ttk.Combobox(
                r1, textvariable=line_style_var, values=LINE_STYLES,
                width=9, state="readonly",
            )
            line_style_combo.pack(side="left", padx=2)
            line_style_combo.bind(
                "<<ComboboxSelected>>",
                lambda e: self.set_conn_line_style(cid, line_style_var.get()),
            )

            r2 = ttk.Frame(self.deck_inspector)
            r2.pack(fill="x", pady=2)
            ttk.Label(r2, text="Weight:").pack(side="left")
            w_sp = ttk.Spinbox(r2, from_=0.1, to=100.0, increment=1.0, width=6)
            w_sp.set(cn.get("weight", 1.0))
            w_sp.pack(side="left", padx=4)
            w_sp.bind("<Return>", lambda e: self.set_conn_weight(cid, w_sp.get()))
            ttk.Button(r2, text="Line Color…", command=self.app.pick_conn_color).pack(side="right")

            label_var = tk.StringVar(value=cn.get("label", ""))
            ttk.Label(self.deck_inspector, text="Label").pack(anchor="w")
            label_entry = ttk.Entry(self.deck_inspector, textvariable=label_var)
            label_entry.pack(fill="x", pady=(0, 3))
            label_entry.bind("<Return>", lambda e: self.set_conn_label(cid, label_var.get()))
            label_entry.bind("<FocusOut>", lambda e: self.set_conn_label(cid, label_var.get()))

            actions = ttk.Frame(self.deck_inspector)
            actions.pack(fill="x", pady=2)
            ttk.Button(
                actions, text="Reverse Direction", command=self.app.reverse_selected_conn
            ).pack(side="left", fill="x", expand=True, padx=(0, 2))
            ttk.Button(
                actions, text="Apply Style to New Lines", command=self.use_conn_as_default
            ).pack(side="left", fill="x", expand=True, padx=(2, 0))

        else:
            ttk.Label(self.deck_inspector, text="Canvas Inspector", font=("Helvetica", 9, "bold")).pack(anchor="w")
            ttk.Label(self.deck_inspector, text=f"Total Nodes: {len(self.app.model.nodes)}", font=("Helvetica", 8)).pack(anchor="w")
            ttk.Label(self.deck_inspector, text=f"Total Edges: {len(self.app.model.conns)}", font=("Helvetica", 8)).pack(anchor="w")
            ttk.Button(self.deck_inspector, text="Fit All in Window", command=self.app.fit).pack(fill="x", pady=4)

    def set_node_size(self, nid, w, h):
        selected_ids = [item for item in self.app.sel_nodes if item in self.app.model.nodes]
        if not selected_ids and nid in self.app.model.nodes:
            selected_ids = [nid]
        if not selected_ids:
            return
        width = float(w) if w else None
        height = float(h) if h else None
        if all(
            (width is None or self.app.model.nodes[item]["w"] == width)
            and (height is None or self.app.model.nodes[item]["h"] == height)
            for item in selected_ids
        ):
            return
        self.app.model.push_undo()
        self.app.dirty = True
        for item in selected_ids:
            node = self.app.model.nodes[item]
            if width is not None:
                node["w"] = width
            if height is not None:
                node["h"] = height
            self.app.model.update_spatial_node(item)
        self.app.redraw()

    def refresh_inspector_palette(self):
        if not hasattr(self, "inspector_palette"):
            return
        for widget in self.inspector_palette.winfo_children():
            widget.destroy()
        colors = self.brand_kit.colors[:8]
        for color in colors:
            swatch = tk.Label(
                self.inspector_palette, bg=color, width=2, height=1,
                relief="solid", bd=1, cursor="hand2",
            )
            swatch.pack(side="left", padx=1)
            swatch.bind(
                "<Button-1>",
                lambda _event, selected_color=color: self.app.set_selected_node_color(selected_color),
            )

    def set_selected_node_property(self, property_name, value):
        allowed_properties = {"font_family", "font_style", "text_color", "fs"}
        if property_name not in allowed_properties:
            raise ValueError(f"Unsupported node style property: {property_name}")
        targets = [
            self.app.model.nodes[nid]
            for nid in self.app.sel_nodes
            if nid in self.app.model.nodes
        ]
        if not targets or all(node.get(property_name) == value for node in targets):
            return
        self.app.model.push_undo()
        for node in targets:
            node[property_name] = value
        self.app.dirty = True
        if property_name == "fs":
            self.app.fs_var.set(str(value))
        elif property_name == "font_family":
            self.app.node_font_var.set(value)
        elif property_name == "font_style":
            self.app.node_font_style_var.set(value)
        self.app.redraw()

    def set_conn_width(self, cid, val):
        value = int(val)
        if cid not in self.app.model.conns or self.app.model.conns[cid].get("width") == value:
            return
        self.app.model.push_undo()
        self.app.dirty = True
        self.app.model.conns[cid]["width"] = value
        self.app.redraw()

    def set_conn_weight(self, cid, val):
        value = float(val)
        if cid not in self.app.model.conns or self.app.model.conns[cid].get("weight") == value:
            return
        self.app.model.push_undo()
        self.app.dirty = True
        self.app.model.conns[cid]["weight"] = value
        self.app.redraw()

    def set_conn_line_style(self, cid, line_style):
        if cid not in self.app.model.conns:
            return
        connection = self.app.model.conns[cid]
        if connection.get("line_style", "dashed" if connection.get("dash") else "solid") == line_style:
            return
        self.app.model.push_undo()
        self.app.dirty = True
        connection["line_style"] = line_style
        connection["dash"] = line_style != "solid"
        self.app.line_style_var.set(line_style)
        self.app.dash_var.set(line_style != "solid")
        self.app.redraw()

    def set_conn_label(self, cid, label):
        if cid not in self.app.model.conns:
            return
        label = label.strip()
        if self.app.model.conns[cid].get("label", "") == label:
            return
        self.app.model.push_undo()
        self.app.dirty = True
        self.app.model.conns[cid]["label"] = label
        self.app.redraw()

    def use_conn_as_default(self):
        connection = self.app.model.conns.get(self.app.sel_conn)
        if connection is None:
            return
        line_style = connection.get(
            "line_style", "dashed" if connection.get("dash") else "solid"
        )
        self.app.line_var.set(connection.get("type", "curved"))
        self.app.arrow_var.set(connection.get("arrow", "forward"))
        self.app.width_var.set(str(connection.get("width", 2)))
        self.app.line_style_var.set(line_style)
        self.app.line_color_var.set(connection.get("color", "#374151"))
        self.app.model.settings.update({
            "default_line_type": self.app.line_var.get(),
            "default_arrow": self.app.arrow_var.get(),
            "default_line_width": int(self.app.width_var.get()),
            "default_line_style": line_style,
            "default_line_color": self.app.line_color_var.get(),
        })
        self.app.model.dirty = True
        self.app.dirty = True
        self.app.dash_var.set(line_style != "solid")
        self.app.status.set("Selected connection style will be used for new lines.")

    def set_connector_routing(self, routing_type):
        if self.app.sel_conn in self.app.model.conns:
            self.app.model.push_undo()
            self.app.dirty = True
            self.app.model.conns[self.app.sel_conn]["type"] = routing_type
            self.app.line_var.set(routing_type)
            self.app.redraw()
        else:
            self.app.line_var.set(routing_type)
            self.app.model.settings["default_line_type"] = routing_type
            self.app.model.dirty = True
            self.app.dirty = True

    def set_arrow_style(self, arr):
        if self.app.sel_conn in self.app.model.conns:
            self.app.model.push_undo()
            self.app.dirty = True
            self.app.model.conns[self.app.sel_conn]["arrow"] = arr
            self.app.arrow_var.set(arr)
            self.app.redraw()
        else:
            self.app.arrow_var.set(arr)
            self.app.model.settings["default_arrow"] = arr
            self.app.model.dirty = True
            self.app.dirty = True

    def switch_document_page(self):
        pg = self.page_var.get()
        self.page_manager.switch_page(pg)
        self.app.dirty = True
        self.app.select()
        self.app.redraw()
        self.app.fit()

    def add_document_page(self):
        new_name = self.page_manager.add_page()
        self.page_combo.configure(values=list(self.page_manager.pages.keys()))
        self.page_var.set(new_name)
        self.app.dirty = True
        self.app.select()
        self.app.redraw()

    # =========================================================================
    # TAB 3: Maltego-Inspired Investigation & Analysis Tab
    # =========================================================================
    def build_investigation_tab(self, parent):
        f = ttk.Frame(parent, padding=8)
        f.pack(fill="both", expand=True)

        self.osint_canvas, content = self._scrollable_content(f)
        self.osint_content = content

        # 1. Entities Palette Deck
        deck_ent = ttk.LabelFrame(content, text="Entities Palette", padding=6)
        deck_ent.pack(fill="x", pady=4)
        ttk.Label(deck_ent, text="Click to Spawn Entity:", font=("Helvetica", 8)).pack(anchor="w")

        ent_grid = ttk.Frame(deck_ent)
        ent_grid.pack(fill="x", pady=2)
        col_idx, row_idx = 0, 0
        for name, cfg in linkdraw_investigation.ENTITY_TYPES.items():
            txt = f"{cfg['icon']} {name}"
            btn = ttk.Button(ent_grid, text=txt, width=13,
                             command=lambda ent=name, c=cfg: self.spawn_entity(ent, c))
            btn.grid(row=row_idx, column=col_idx, padx=2, pady=2, sticky="ew")
            col_idx += 1
            if col_idx >= 2:
                col_idx = 0
                row_idx += 1
        ttk.Button(
            deck_ent, text="Auto-detect selected entities",
            command=self.app.auto_detect_selected_entities,
        ).pack(fill="x", pady=(4, 0))

        self.build_osint_research_deck(content)

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

    def build_osint_research_deck(self, parent):
        state = self.app.model.settings.setdefault("osint_workbench", {})
        deck = ttk.LabelFrame(parent, text="Research Capture → Diagram", padding=6)
        deck.pack(fill="x", pady=6)

        self.osint_search_var = tk.StringVar(value=state.get("search", ""))
        search_row = ttk.Frame(deck)
        search_row.pack(fill="x")
        ttk.Entry(search_row, textvariable=self.osint_search_var).pack(
            side="left", fill="x", expand=True,
        )
        ttk.Button(search_row, text="Search web", command=self.open_osint_search).pack(
            side="left", padx=(4, 0),
        )

        self.osint_source_title_var = tk.StringVar(value=state.get("source_title", ""))
        ttk.Label(deck, text="Source title").pack(anchor="w", pady=(4, 0))
        ttk.Entry(deck, textvariable=self.osint_source_title_var).pack(fill="x")

        self.osint_source_url_var = tk.StringVar(value=state.get("source_url", ""))
        ttk.Label(deck, text="Source URL").pack(anchor="w", pady=(4, 0))
        ttk.Entry(deck, textvariable=self.osint_source_url_var).pack(fill="x")

        ttk.Label(
            deck, text="Paste information from the source (analysis stays local).",
            wraplength=275,
        ).pack(anchor="w", pady=(5, 2))
        evidence_frame = ttk.Frame(deck)
        evidence_frame.pack(fill="x")
        self.osint_evidence_text = tk.Text(evidence_frame, height=5, wrap="word")
        evidence_scroll = ttk.Scrollbar(
            evidence_frame, orient="vertical", command=self.osint_evidence_text.yview,
        )
        self.osint_evidence_text.configure(yscrollcommand=evidence_scroll.set)
        self.osint_evidence_text.pack(side="left", fill="both", expand=True)
        evidence_scroll.pack(side="right", fill="y")
        self.osint_evidence_text.insert("1.0", state.get("evidence_text", ""))

        ttk.Button(
            deck, text="Extract entities from pasted text",
            command=self.extract_osint_entities,
        ).pack(fill="x", pady=(4, 3))

        manual_row = ttk.Frame(deck)
        manual_row.pack(fill="x", pady=2)
        self.osint_manual_value = tk.StringVar()
        ttk.Entry(manual_row, textvariable=self.osint_manual_value).pack(
            side="left", fill="x", expand=True,
        )
        self.osint_manual_type = tk.StringVar(value="Auto-detect")
        ttk.Combobox(
            manual_row, textvariable=self.osint_manual_type,
            values=("Auto-detect", *linkdraw_investigation.ENTITY_TYPES.keys()),
            state="readonly", width=13,
        ).pack(side="left", padx=(4, 0))
        ttk.Button(
            deck, text="Add typed entity to preview",
            command=self.add_manual_osint_entity,
        ).pack(fill="x", pady=(2, 4))

        ttk.Label(deck, text="Entities to add").pack(anchor="w")
        candidates_frame = ttk.Frame(deck)
        candidates_frame.pack(fill="x")
        self.osint_candidate_list = tk.Listbox(
            candidates_frame, height=6, selectmode="extended", exportselection=False,
        )
        candidates_scroll = ttk.Scrollbar(
            candidates_frame, orient="vertical", command=self.osint_candidate_list.yview,
        )
        self.osint_candidate_list.configure(yscrollcommand=candidates_scroll.set)
        self.osint_candidate_list.pack(side="left", fill="both", expand=True)
        candidates_scroll.pack(side="right", fill="y")
        self.osint_candidates = [
            item for item in state.get("candidates", [])
            if isinstance(item, dict) and item.get("value") and item.get("type")
        ]
        self.refresh_osint_candidate_list()
        ttk.Button(
            deck, text="Remove selected preview entities",
            command=self.remove_selected_osint_candidates,
        ).pack(fill="x", pady=(3, 0))

        ttk.Label(deck, text="Optional relationship to selected graph element").pack(
            anchor="w", pady=(4, 0),
        )
        self.osint_relation_var = tk.StringVar(value="observed with")
        ttk.Entry(deck, textvariable=self.osint_relation_var).pack(fill="x")
        ttk.Button(
            deck, text="Add selected findings to diagram",
            command=self.add_osint_candidates_to_graph,
        ).pack(fill="x", pady=(4, 0))

        for variable in (
            self.osint_search_var,
            self.osint_source_title_var,
            self.osint_source_url_var,
            self.osint_manual_value,
        ):
            variable.trace_add("write", self.save_osint_workbench_state)
        self.osint_evidence_text.bind(
            "<KeyRelease>", self.save_osint_workbench_state,
        )

    def save_osint_workbench_state(self, *_):
        state = self.app.model.settings.setdefault("osint_workbench", {})
        state.update({
            "search": self.osint_search_var.get(),
            "source_title": self.osint_source_title_var.get(),
            "source_url": self.osint_source_url_var.get(),
            "evidence_text": self.osint_evidence_text.get("1.0", "end-1c"),
            "candidates": list(self.osint_candidates),
        })
        self.app.model.dirty = True
        self.app.dirty = True

    def open_osint_search(self):
        query = self.osint_search_var.get().strip()
        if not query:
            self.app.status.set("Enter a search phrase first.")
            return
        webbrowser.open(f"https://www.google.com/search?q={quote_plus(query)}")

    def refresh_osint_candidate_list(self):
        self.osint_candidate_list.delete(0, "end")
        for item in self.osint_candidates:
            self.osint_candidate_list.insert("end", f"{item['type']}: {item['value']}")
        self.save_osint_workbench_state()

    def remove_selected_osint_candidates(self):
        selected = set(self.osint_candidate_list.curselection())
        if not selected:
            return
        self.osint_candidates = [
            item for index, item in enumerate(self.osint_candidates)
            if index not in selected
        ]
        self.refresh_osint_candidate_list()

    def add_osint_candidate(self, entity_type, value):
        value = value.strip().strip(".,;:!?)]}\"'")
        if not value or entity_type not in linkdraw_investigation.ENTITY_TYPES:
            return False
        key = (entity_type.casefold(), value.casefold())
        if any((item["type"].casefold(), item["value"].casefold()) == key for item in self.osint_candidates):
            return False
        self.osint_candidates.append({"type": entity_type, "value": value})
        return True

    def extract_osint_entities(self):
        text = self.osint_evidence_text.get("1.0", "end-1c")
        patterns = (
            r"https?://[^\s<>\"']+|www\.[^\s<>\"']+",
            r"[\w.+-]+@[\w.-]+\.[A-Za-z]{2,}",
            r"(?<![\w.])(?:\d{1,3}\.){3}\d{1,3}(?![\w.])",
            r"(?<![@\w.-])(?:[A-Za-z0-9](?:[A-Za-z0-9-]{0,61}[A-Za-z0-9])?\.)+[A-Za-z]{2,63}(?![\w-])",
        )
        matches = []
        for pattern in patterns:
            matches.extend((match.start(), match.group(0)) for match in re.finditer(pattern, text))
        added = 0
        for _, raw_value in sorted(matches):
            value = raw_value.strip(".,;:!?)]}\"'")
            entity_type = linkdraw_investigation.detect_entity_type(value)
            if entity_type and self.add_osint_candidate(entity_type, value):
                added += 1
        self.refresh_osint_candidate_list()
        self.app.status.set(f"Extracted {added} new entities from pasted source text.")

    def add_manual_osint_entity(self):
        value = self.osint_manual_value.get().strip()
        entity_type = self.osint_manual_type.get()
        if entity_type == "Auto-detect":
            entity_type = linkdraw_investigation.detect_entity_type(value)
        if not entity_type:
            self.app.status.set("Could not identify that entity. Choose its type or enter a domain, URL, IP, email, or hash.")
            return
        if not self.add_osint_candidate(entity_type, value):
            self.app.status.set("That entity is already in the preview.")
            return
        self.refresh_osint_candidate_list()
        self.osint_manual_value.set("")

    def add_osint_candidates_to_graph(self):
        selected = self.osint_candidate_list.curselection()
        if not selected:
            self.app.status.set("Select one or more findings to add to the diagram.")
            return

        source_title = self.osint_source_title_var.get().strip()
        source_url = self.osint_source_url_var.get().strip()
        evidence = self.osint_evidence_text.get("1.0", "end-1c").strip()
        relation = self.osint_relation_var.get().strip()
        anchor_id = next(iter(sorted(self.app.sel_nodes)), None)
        anchor = self.app.model.nodes.get(anchor_id)
        if anchor is None:
            center_x, center_y = self.app.to_world(
                self.app.canvas.winfo_width() / 2,
                self.app.canvas.winfo_height() / 2,
            )
        else:
            center_x, center_y = anchor["x"] + 240, anchor["y"]

        self.app.model.push_undo()
        added_ids = []
        reused_ids = []
        selected_candidates = [self.osint_candidates[index] for index in selected]
        for index, candidate in enumerate(selected_candidates):
            entity_type = candidate["type"]
            value = candidate["value"]
            existing_id = next(
                (
                    nid for nid, node in self.app.model.nodes.items()
                    if node.get("entity_type") == entity_type
                    and node.get("text", "").casefold() == value.casefold()
                ),
                None,
            )
            config = linkdraw_investigation.ENTITY_TYPES[entity_type]
            if existing_id is None:
                row, column = divmod(index, 2)
                nid = self.app.model.make_node(
                    center_x + column * 220,
                    center_y + (row - (len(selected_candidates) - 1) / 4) * 120,
                    text=value,
                    shape=config["shape"],
                    color=config["color"],
                    icon=config["icon"],
                    tags=["osint", entity_type.casefold()],
                )
                node = self.app.model.nodes[nid]
                node["entity_type"] = entity_type
                node["layer"] = self.active_layer_var.get()
                added_ids.append(nid)
            else:
                nid = existing_id
                node = self.app.model.nodes[nid]
                reused_ids.append(nid)

            source = {"title": source_title, "url": source_url}
            sources = node.setdefault("metadata", {}).setdefault("osint_sources", [])
            if source_url or source_title:
                if source not in sources:
                    sources.append(source)
            if evidence:
                citation = f"Source: {source_title or 'User-supplied source'}"
                if source_url:
                    citation += f"\nURL: {source_url}"
                excerpt = evidence[:1000]
                rich_notes = node.setdefault("rich_notes", {"text": "", "image_path": "", "checklist": []})
                previous = rich_notes.get("text", "").strip()
                if citation not in previous:
                    rich_notes["text"] = f"{previous}\n\n{citation}\n{excerpt}".strip()

            if anchor is not None and nid != anchor_id and relation:
                connected = any(
                    conn["a"] == anchor_id and conn["b"] == nid
                    and conn.get("label") == relation
                    for conn in self.app.model.conns.values()
                )
                if not connected:
                    self.app.model.make_conn(anchor_id, nid, label=relation)

        self.app.dirty = True
        self.app.select(nodes=set(added_ids or reused_ids))
        self.app.redraw()
        self.app.fit()
        self.app.status.set(
            f"Added {len(added_ids)} new entities; reused {len(set(reused_ids))} existing entities."
        )

    def spawn_entity(self, ent_name, cfg):
        value = simpledialog.askstring(
            f"Add {ent_name}",
            f"Enter the actual {ent_name} value or name:",
            parent=self.osint_window,
        )
        if value is None:
            return
        value = value.strip()
        if not value:
            self.app.status.set(f"Enter a name or value for the {ent_name} entity.")
            return

        existing_id = next(
            (
                nid for nid, node in self.app.model.nodes.items()
                if node.get("entity_type") == ent_name
                and node.get("text", "").casefold() == value.casefold()
            ),
            None,
        )
        if existing_id is not None:
            self.app.select(nodes={existing_id})
            self.app.status.set(f"{ent_name} already exists in the diagram; selected it.")
            return

        W = self.app.canvas.winfo_width() / 2.0
        H = self.app.canvas.winfo_height() / 2.0
        wx, wy = self.app.to_world(W, H)
        self.app.model.push_undo()
        nid = self.app.model.make_node(
            wx, wy,
            text=value,
            shape=cfg.get("shape", "rounded"),
            color=cfg.get("color", "#dbeafe"),
            icon=cfg.get("icon", "🏷️"),
            tags=["osint", ent_name.casefold()],
            metadata={"indicator": value},
        )
        self.app.model.nodes[nid]["entity_type"] = ent_name
        self.app.model.nodes[nid]["layer"] = self.active_layer_var.get()
        self.app.select(nodes={nid})
        self.app.redraw()
        self.app.status.set(f"Added {ent_name}: {value}")

    def update_transforms_deck(self):
        if not hasattr(self, "deck_transforms") or not self.deck_transforms.winfo_exists():
            return
        for w in self.deck_transforms.winfo_children():
            w.destroy()

        if len(self.app.sel_nodes) == 1:
            nid = next(iter(self.app.sel_nodes))
            node = self.app.model.nodes.get(nid)
            if not node:
                return
            ent_type = node.get("entity_type") or "Domain"
            ttk.Label(self.deck_transforms, text=f"Transforms for [{ent_type}]:", font=("Helvetica", 8, "bold")).pack(anchor="w", pady=(0, 4))
            tf_list = linkdraw_investigation.InvestigationEngine.get_available_transforms(ent_type)
            for title, key in tf_list:
                ttk.Button(self.deck_transforms, text=f"⚡ {title}",
                           command=lambda k=key, n=node: self.execute_transform(k, n)).pack(fill="x", pady=2)
        else:
            ttk.Label(self.deck_transforms, text="Select a single node to run OSINT transforms.", font=("Helvetica", 8), foreground="#6b7280").pack(anchor="w")

    def execute_transform(self, transform_key, node):
        spawned = linkdraw_investigation.InvestigationEngine.run_transform(transform_key, node, self.app.model)
        self.app.status.set(f"Transform executed: spawned {len(spawned)} entities.")
        self.app.redraw()
        self.app.fit()

    def run_metric(self, metric, mode):
        linkdraw_investigation.apply_metric_view(self.app.model, metric=metric, mode=mode)
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
        f = ttk.Frame(self.tab_notes, padding=6)
        f.pack(fill="both", expand=True)

        self.notes_nb = ttk.Notebook(f)
        self.notes_nb.pack(fill="both", expand=True)
        self.tab_my_notes = ttk.Frame(self.notes_nb, padding=6)
        self.tab_node_notes = ttk.Frame(self.notes_nb, padding=6)
        self.notes_nb.add(self.tab_my_notes, text="My Notes")
        self.notes_nb.add(self.tab_node_notes, text="Selected Node")

        search_row = ttk.Frame(self.tab_my_notes)
        search_row.pack(fill="x", pady=(0, 5))
        ttk.Label(search_row, text="Search").pack(side="left")
        self.standalone_search_var = tk.StringVar()
        search_entry = ttk.Entry(search_row, textvariable=self.standalone_search_var)
        search_entry.pack(side="left", fill="x", expand=True, padx=(5, 0))
        self.standalone_search_var.trace_add("write", self.refresh_standalone_note_list)

        list_frame = ttk.Frame(self.tab_my_notes)
        list_frame.pack(fill="x", expand=False)
        self.standalone_note_list = tk.Listbox(
            list_frame,
            height=5,
            exportselection=False,
            activestyle="none",
            relief="solid",
            borderwidth=1,
        )
        list_scroll = ttk.Scrollbar(
            list_frame, orient="vertical", command=self.standalone_note_list.yview
        )
        self.standalone_note_list.configure(yscrollcommand=list_scroll.set)
        self.standalone_note_list.pack(side="left", fill="both", expand=True)
        list_scroll.pack(side="right", fill="y")
        self.standalone_note_list.bind("<<ListboxSelect>>", self.select_standalone_note)

        note_actions = ttk.Frame(self.tab_my_notes)
        note_actions.pack(fill="x", pady=(5, 4))
        ttk.Button(note_actions, text="New", command=self.add_standalone_note).pack(
            side="left", fill="x", expand=True
        )
        ttk.Button(note_actions, text="Delete", command=self.delete_standalone_note).pack(
            side="left", fill="x", expand=True, padx=(4, 0)
        )
        ttk.Button(note_actions, text="Duplicate", command=self.duplicate_standalone_note).pack(
            side="left", fill="x", expand=True, padx=(4, 0)
        )
        ttk.Button(note_actions, text="Export", command=self.export_standalone_note).pack(
            side="left", fill="x", expand=True, padx=(4, 0)
        )
        ttk.Button(note_actions, text="Save", command=self.save_standalone_note).pack(
            side="left", fill="x", expand=True, padx=(4, 0)
        )

        self.standalone_title_var = tk.StringVar()
        self.standalone_title_var.trace_add("write", self.schedule_standalone_note_save)
        self.standalone_title = ttk.Entry(
            self.tab_my_notes, textvariable=self.standalone_title_var, font=("Helvetica", 11, "bold")
        )
        self.standalone_title.pack(fill="x", pady=(2, 4))
        self.standalone_title.bind("<KeyRelease>", self.schedule_standalone_note_save)

        details = ttk.LabelFrame(self.tab_my_notes, text="Investigation details", padding=5)
        details.pack(fill="x", pady=(0, 4))
        self.note_type_var = tk.StringVar(value="Observation")
        self.note_type_var.trace_add("write", self.schedule_standalone_note_save)
        type_row = ttk.Frame(details)
        type_row.pack(fill="x", pady=1)
        ttk.Label(type_row, text="Type").pack(side="left")
        ttk.Combobox(
            type_row, textvariable=self.note_type_var,
            values=("Observation", "Source", "Lead", "Analysis", "Question", "Action"),
            state="readonly", width=16,
        ).pack(side="right", fill="x", expand=True, padx=(4, 0))

        self.note_source_var = tk.StringVar()
        self.note_source_var.trace_add("write", self.schedule_standalone_note_save)
        ttk.Label(details, text="Source URL").pack(anchor="w", pady=(3, 0))
        ttk.Entry(details, textvariable=self.note_source_var).pack(fill="x")

        self.note_tags_var = tk.StringVar()
        self.note_tags_var.trace_add("write", self.schedule_standalone_note_save)
        ttk.Label(details, text="Tags (comma-separated)").pack(anchor="w", pady=(3, 0))
        ttk.Entry(details, textvariable=self.note_tags_var).pack(fill="x")

        self.note_link_var = tk.StringVar(value="No linked element")
        self.note_link_combo = ttk.Combobox(
            details, textvariable=self.note_link_var, state="readonly",
        )
        self.note_link_combo.pack(fill="x", pady=(4, 2))
        self.note_link_combo.bind("<<ComboboxSelected>>", self.schedule_standalone_note_save)
        link_actions = ttk.Frame(details)
        link_actions.pack(fill="x")
        ttk.Button(
            link_actions, text="Link selected element",
            command=self.link_note_to_selected_node,
        ).pack(side="left", fill="x", expand=True)
        ttk.Button(
            link_actions, text="Go to element",
            command=self.open_note_linked_node,
        ).pack(side="left", fill="x", expand=True, padx=(4, 0))

        body_frame = ttk.Frame(self.tab_my_notes)
        body_frame.pack(fill="both", expand=True)
        self.standalone_body = tk.Text(
            body_frame, wrap="word", font=("Helvetica", 9), undo=True, padx=6, pady=5
        )
        body_scroll = ttk.Scrollbar(body_frame, orient="vertical", command=self.standalone_body.yview)
        self.standalone_body.configure(yscrollcommand=body_scroll.set)
        self.standalone_body.pack(side="left", fill="both", expand=True)
        body_scroll.pack(side="right", fill="y")
        self.standalone_body.bind("<KeyRelease>", self.schedule_standalone_note_save)

        editor_actions = ttk.Frame(self.tab_my_notes)
        editor_actions.pack(fill="x", pady=(4, 0))
        ttk.Button(
            editor_actions, text="Insert checklist item", command=self.insert_checklist_item
        ).pack(side="left")
        templates = ttk.Frame(self.tab_my_notes)
        templates.pack(fill="x", pady=(4, 0))
        for label, heading in (
            ("Source", "Source details"),
            ("Observation", "Observation"),
            ("Analysis", "Analysis"),
            ("Next steps", "Next steps"),
        ):
            ttk.Button(
                templates, text=label,
                command=lambda title=heading: self.insert_investigation_template(title),
            ).pack(side="left", fill="x", expand=True, padx=1)
        self.standalone_note_status = ttk.Label(editor_actions, text="No note selected")
        self.standalone_note_status.pack(side="right")

        self.deck_node_notes = ttk.LabelFrame(self.tab_node_notes, text="Node notes", padding=6)
        self.deck_node_notes.pack(fill="both", expand=True, pady=(0, 6))
        self.node_note_heading = ttk.Label(
            self.deck_node_notes, text="Select a node to view or edit its notes."
        )
        self.node_note_heading.pack(anchor="w", pady=(0, 4))
        self.note_text = tk.Text(
            self.deck_node_notes, height=8, wrap="word", font=("Helvetica", 9), undo=True
        )
        self.note_text.pack(fill="both", expand=True, pady=4)
        self.note_text.bind("<KeyRelease>", self.schedule_node_note_save)

        img_row = ttk.Frame(self.deck_node_notes)
        img_row.pack(fill="x", pady=2)
        self.note_img_var = tk.StringVar()
        ttk.Label(img_row, text="Attachment").pack(side="left")
        ttk.Entry(img_row, textvariable=self.note_img_var).pack(side="left", fill="x", expand=True, padx=4)
        ttk.Button(img_row, text="Browse...", command=self.attach_note_image).pack(side="left")
        self.note_img_var.trace_add("write", self.schedule_node_note_save)

        ttk.Button(
            self.deck_node_notes, text="Save Node Notes", command=self.save_current_node_notes
        ).pack(fill="x", pady=4)

        deck_bkm = ttk.LabelFrame(self.tab_node_notes, text="Canvas bookmarks", padding=6)
        deck_bkm.pack(fill="x", pady=6)
        self.bookmarks = {}
        self.bkm_combo = ttk.Combobox(deck_bkm, values=[], state="readonly")
        self.bkm_combo.pack(fill="x", pady=2)
        self.bkm_combo.bind("<<ComboboxSelected>>", lambda e: self.restore_bookmark())

        bkm_btn_row = ttk.Frame(deck_bkm)
        bkm_btn_row.pack(fill="x", pady=2)
        ttk.Button(
            bkm_btn_row, text="Add Bookmark", command=self.add_bookmark
        ).pack(side="left", fill="x", expand=True, padx=1)

        self.refresh_standalone_note_list()
        self.refresh_note_link_options()
        self.update_notes_tab()

    def update_notes_tab(self):
        if not hasattr(self, "note_text"):
            return
        self._commit_node_notes()
        self.loading_node_note = True
        self.note_text.delete("1.0", "end")
        self.note_img_var.set("")
        self.loaded_node_note_id = None
        if len(self.app.sel_nodes) == 1:
            nid = next(iter(self.app.sel_nodes))
            node = self.app.model.nodes.get(nid)
            if node:
                self.loaded_node_note_id = nid
                self.node_note_heading.configure(text=f"Notes for: {node.get('text', 'Node')}")
                notes_data = node.get("rich_notes", {})
                self.note_text.insert("1.0", notes_data.get("text", ""))
                self.note_img_var.set(notes_data.get("image_path", ""))
        else:
            self.node_note_heading.configure(text="Select a single node to edit its notes.")
        self.loading_node_note = False

    def attach_note_image(self):
        p = filedialog.askopenfilename(filetypes=[("Image Files", "*.png;*.jpg;*.jpeg;*.gif"), ("All Files", "*.*")])
        if p:
            self.note_img_var.set(p)

    def schedule_node_note_save(self, *_):
        if self.loading_node_note or self.loaded_node_note_id is None:
            return
        if self.node_note_save_after is not None:
            self.after_cancel(self.node_note_save_after)
        self.node_note_save_after = self.after(500, self._commit_node_notes)

    def _commit_node_notes(self):
        if self.node_note_save_after is not None:
            self.after_cancel(self.node_note_save_after)
            self.node_note_save_after = None
        nid = self.loaded_node_note_id
        if nid is None or nid not in self.app.model.nodes or self.loading_node_note:
            return
        new_notes = {
            "text": self.note_text.get("1.0", "end-1c"),
            "image_path": self.note_img_var.get(),
        }
        node = self.app.model.nodes[nid]
        old_notes = node.get("rich_notes", {})
        if old_notes.get("text", "") == new_notes["text"] and old_notes.get(
            "image_path", ""
        ) == new_notes["image_path"]:
            return
        self.app.model.push_undo()
        node["rich_notes"] = {**old_notes, **new_notes}
        self.app.dirty = True
        self.app.status.set(f"Saved notes for Node #{nid}.")

    def save_current_node_notes(self):
        if self.loaded_node_note_id is None:
            self.app.status.set("Select a single node before adding node notes.")
            return
        self._commit_node_notes()

    def refresh_standalone_note_list(self, *_):
        if not hasattr(self, "standalone_note_list"):
            return
        query = self.standalone_search_var.get().strip().casefold()
        active_id = self.active_standalone_note_id
        self.visible_standalone_note_ids = []
        self.standalone_note_list.delete(0, "end")
        for note in sorted(
            self.standalone_notes, key=lambda item: item.get("updated_at", ""), reverse=True
        ):
            title = note.get("title", "Untitled note")
            body = note.get("body", "")
            searchable = " ".join((
                title,
                body,
                note.get("note_type", ""),
                note.get("source_url", ""),
                " ".join(note.get("tags", [])),
                note.get("linked_node_name", ""),
            )).casefold()
            if query and query not in searchable:
                continue
            self.visible_standalone_note_ids.append(note["id"])
            self.standalone_note_list.insert(
                "end", f"[{note.get('note_type', 'Observation')}] {title or 'Untitled note'}"
            )
        if active_id in self.visible_standalone_note_ids:
            index = self.visible_standalone_note_ids.index(active_id)
            self.standalone_note_list.selection_set(index)
            self.standalone_note_list.activate(index)

    def _get_standalone_note(self, note_id):
        return next((note for note in self.standalone_notes if note["id"] == note_id), None)

    def select_standalone_note(self, _event=None):
        selection = self.standalone_note_list.curselection()
        if not selection:
            return
        note_id = self.visible_standalone_note_ids[selection[0]]
        if note_id == self.active_standalone_note_id:
            return
        self._save_standalone_note()
        self.active_standalone_note_id = note_id
        self._load_standalone_note(self._get_standalone_note(note_id))
        self.refresh_standalone_note_list()

    def _load_standalone_note(self, note):
        self.loading_standalone_note = True
        self.standalone_title_var.set(note.get("title", "") if note else "")
        self.note_type_var.set(note.get("note_type", "Observation") if note else "Observation")
        self.note_source_var.set(note.get("source_url", "") if note else "")
        tags = note.get("tags", []) if note else []
        self.note_tags_var.set(", ".join(tags) if isinstance(tags, list) else str(tags))
        self.standalone_body.delete("1.0", "end")
        if note:
            self.standalone_body.insert("1.0", note.get("body", ""))
            self.standalone_note_status.configure(text="Saved")
        else:
            self.standalone_note_status.configure(text="Create a note to get started.")
        self.refresh_note_link_options(note)
        self.loading_standalone_note = False
        self._update_note_word_count()

    def refresh_note_link_options(self, note=None):
        labels = ["No linked element"]
        self.note_link_ids = {labels[0]: None}
        for nid, node in self.app.model.nodes.items():
            label = f"{node.get('text', 'Element')} (#{nid})"
            labels.append(label)
            self.note_link_ids[label] = nid
        self.note_link_combo.configure(values=labels)
        linked_id = note.get("linked_node_id") if note else None
        linked_label = next(
            (label for label, nid in self.note_link_ids.items() if nid == linked_id),
            labels[0],
        )
        if linked_id is not None and linked_label == labels[0] and note.get("linked_node_name"):
            linked_label = f"{note['linked_node_name']} (#{linked_id}) — unavailable"
        self.note_link_var.set(linked_label)

    def link_note_to_selected_node(self):
        note = self._get_standalone_note(self.active_standalone_note_id)
        selected = next(iter(self.app.sel_nodes), None)
        if note is None:
            self.app.status.set("Create or select a note before linking an element.")
            return
        if selected not in self.app.model.nodes:
            self.app.status.set("Select an element on the canvas first.")
            return
        if not self._save_standalone_note(show_errors=True):
            return
        node = self.app.model.nodes[selected]
        note["linked_node_id"] = selected
        note["linked_node_name"] = node.get("text", "Element")
        self.refresh_note_link_options(note)
        self._persist_standalone_notes(show_errors=True)
        self.app.status.set(f"Linked note to {node.get('text', 'Element')}.")

    def open_note_linked_node(self):
        note = self._get_standalone_note(self.active_standalone_note_id)
        if note is None:
            self.app.status.set("Select a note first.")
            return
        node_id = note.get("linked_node_id")
        node = self.app.model.nodes.get(node_id)
        if node is None or (
            note.get("linked_node_name")
            and note["linked_node_name"] != node.get("text", "")
        ):
            self.app.status.set("The linked element is not available in the current graph.")
            return
        width, height = self.app.canvas.winfo_width(), self.app.canvas.winfo_height()
        self.app.select(nodes={node_id})
        self.app.ox = width / 2 - node["x"] * self.app.scale
        self.app.oy = height / 2 - node["y"] * self.app.scale
        self.app.redraw()
        self.app.status.set(f"Focused linked element: {node.get('text', 'Element')}.")

    def insert_investigation_template(self, heading):
        if self.active_standalone_note_id is None:
            self.add_standalone_note()
        if self.active_standalone_note_id is None:
            return
        prompts = {
            "Source details": "URL:\nAuthor / account:\nPublished:\nAccessed:\n\n",
            "Observation": "What was observed?\n\n",
            "Analysis": "Assessment:\nConfidence (low / medium / high):\nAlternative explanations:\n\n",
            "Next steps": "- [ ] Verify:\n- [ ] Follow up:\n\n",
        }
        self.standalone_body.insert("insert", f"{heading}\n{prompts[heading]}")
        self.standalone_body.focus_set()
        self.schedule_standalone_note_save()

    def add_standalone_note(self):
        self._save_standalone_note()
        note = notes_store.create_note()
        if len(self.app.sel_nodes) == 1:
            nid = next(iter(self.app.sel_nodes))
            node = self.app.model.nodes.get(nid)
            if node:
                note["linked_node_id"] = nid
                note["linked_node_name"] = node.get("text", "Element")
        self.standalone_notes.append(note)
        self.active_standalone_note_id = note["id"]
        self._load_standalone_note(note)
        self.refresh_standalone_note_list()
        if not self._persist_standalone_notes(show_errors=True):
            self.standalone_notes.remove(note)
            self.active_standalone_note_id = None
            self._load_standalone_note(None)
            self.refresh_standalone_note_list()
            return
        self.standalone_title.focus_set()
        self.standalone_title.selection_range(0, "end")

    def delete_standalone_note(self):
        note = self._get_standalone_note(self.active_standalone_note_id)
        if note is None:
            return
        if not messagebox.askyesno(
            "Delete note", f"Delete “{note.get('title') or 'Untitled note'}”?",
            parent=self,
        ):
            return
        index = self.standalone_notes.index(note)
        self.standalone_notes.remove(note)
        self.active_standalone_note_id = None
        self._load_standalone_note(None)
        self.refresh_standalone_note_list()
        if not self._persist_standalone_notes(show_errors=True):
            self.standalone_notes.insert(index, note)
            self.active_standalone_note_id = note["id"]
            self._load_standalone_note(note)
            self.refresh_standalone_note_list()

    def duplicate_standalone_note(self):
        source = self._get_standalone_note(self.active_standalone_note_id)
        if source is None:
            self.app.status.set("Select a note before duplicating it.")
            return
        self._save_standalone_note()
        duplicate = notes_store.create_note()
        duplicate["title"] = f"{source.get('title') or 'Untitled note'} copy"
        duplicate["body"] = source.get("body", "")
        for field in ("note_type", "source_url", "tags", "linked_node_id", "linked_node_name"):
            duplicate[field] = source.get(field, duplicate.get(field))
        self.standalone_notes.append(duplicate)
        self.active_standalone_note_id = duplicate["id"]
        self._load_standalone_note(duplicate)
        self.refresh_standalone_note_list()
        if not self._persist_standalone_notes(show_errors=True):
            self.standalone_notes.remove(duplicate)
            self.active_standalone_note_id = source["id"]
            self._load_standalone_note(source)
            self.refresh_standalone_note_list()

    def export_standalone_note(self):
        note = self._get_standalone_note(self.active_standalone_note_id)
        if note is None:
            self.app.status.set("Select a note before exporting it.")
            return
        self._save_standalone_note()
        path = filedialog.asksaveasfilename(
            parent=self,
            title="Export Note",
            defaultextension=".md",
            initialfile=f"{note['title'] or 'Untitled note'}.md",
            filetypes=[("Markdown", "*.md"), ("Text", "*.txt"), ("All files", "*.*")],
        )
        if not path:
            return
        try:
            with open(path, "w", encoding="utf-8") as note_file:
                note_file.write(f"# {note['title'] or 'Untitled note'}\n\n")
                note_file.write(f"- Type: {note.get('note_type', 'Observation')}\n")
                if note.get("source_url"):
                    note_file.write(f"- Source: {note['source_url']}\n")
                if note.get("tags"):
                    note_file.write(f"- Tags: {', '.join(note['tags'])}\n")
                if note.get("linked_node_name"):
                    note_file.write(
                        f"- Linked element: {note['linked_node_name']} "
                        f"(#{note.get('linked_node_id')})\n"
                    )
                note_file.write(f"- Updated: {note.get('updated_at', '')}\n\n")
                note_file.write(note.get("body", ""))
                note_file.write("\n")
        except OSError as exc:
            messagebox.showerror("Could not export note", str(exc), parent=self)
            return
        self.app.status.set(f"Exported note to {path}.")

    def schedule_standalone_note_save(self, *_):
        if self.loading_standalone_note or self.active_standalone_note_id is None:
            return
        self._update_note_word_count("Unsaved")
        if self.standalone_save_after is not None:
            self.after_cancel(self.standalone_save_after)
        self.standalone_save_after = self.after(650, self._save_standalone_note)

    def _save_standalone_note(self, show_errors=False):
        if self.standalone_save_after is not None:
            self.after_cancel(self.standalone_save_after)
            self.standalone_save_after = None
        note = self._get_standalone_note(self.active_standalone_note_id)
        if note is None or self.loading_standalone_note:
            return True
        title = self.standalone_title_var.get().strip() or "Untitled note"
        note["title"] = title
        note["note_type"] = self.note_type_var.get()
        note["source_url"] = self.note_source_var.get().strip()
        note["tags"] = [tag.strip() for tag in self.note_tags_var.get().split(",") if tag.strip()]
        linked_id = self.note_link_ids.get(self.note_link_var.get())
        if linked_id is not None:
            node = self.app.model.nodes.get(linked_id)
            if node is not None:
                note["linked_node_id"] = linked_id
                note["linked_node_name"] = node.get("text", "Element")
        elif self.note_link_var.get() == "No linked element":
            note["linked_node_id"] = None
            note["linked_node_name"] = ""
        note["body"] = self.standalone_body.get("1.0", "end-1c")
        note["updated_at"] = notes_store.timestamp_now()
        self.refresh_standalone_note_list()
        return self._persist_standalone_notes(show_errors=show_errors)

    def _persist_standalone_notes(self, show_errors=False):
        try:
            notes_store.save_notes(self.standalone_notes)
        except OSError as exc:
            self.standalone_note_status.configure(text=f"Save failed: {exc}")
            self.app.status.set("Could not save standalone notes.")
            if show_errors:
                messagebox.showerror("Could not save notes", str(exc), parent=self)
            return False
        self._update_note_word_count("Saved")
        return True

    def save_standalone_note(self, show_errors=True):
        if self.active_standalone_note_id is None:
            self.app.status.set("Create or select a note before saving.")
            return
        if self._save_standalone_note(show_errors=show_errors):
            self.app.status.set("Standalone note saved.")

    def insert_checklist_item(self):
        if self.active_standalone_note_id is None:
            self.add_standalone_note()
        if self.active_standalone_note_id is None:
            return
        self.standalone_body.insert("insert", "- [ ] ")
        self.standalone_body.focus_set()
        self.schedule_standalone_note_save()

    def _update_note_word_count(self, state=""):
        if not hasattr(self, "standalone_body"):
            return
        text = self.standalone_body.get("1.0", "end-1c")
        words = len(text.split())
        status = f"{words} words"
        if state:
            status = f"{state} · {status}"
        self.standalone_note_status.configure(text=status)

    def flush_pending_notes(self):
        if hasattr(self, "note_text"):
            self._commit_node_notes()
        if getattr(self, "active_standalone_note_id", None) is not None:
            return self._save_standalone_note(show_errors=True)
        return True

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
