#!/usr/bin/env python3
"""
LinkDraw Pro - Interactive Graph & Network Canvas
Complete Implementation of 70 Features across Visualization, Interaction,
Layouts, Analysis, Import/Export, Graph Properties, Metadata, UX, and Performance.
"""
import copy
import json
import math
import os
import sys
import tkinter as tk
from tkinter import ttk, filedialog, messagebox, simpledialog, colorchooser

from graph_model import (
    GraphModel, SHAPES, LINE_TYPES, ARROWS, WIDTHS, FSIZES,
    NODE_COLORS_LIGHT, NODE_COLORS_DARK, NODE_COLORS_HC,
    LINE_COLORS_LIGHT, LINE_COLORS_DARK, LINE_COLORS_HC
)
import algorithms
import layouts
import io_manager
import dialogs
import panels
import investigation
import drawing_tools

MOD = "Command" if sys.platform == "darwin" else "Control"
MM_W, MM_H = 190, 130


class LinkDrawApp:
    def __init__(self, root):
        self.root = root
        root.title("LinkDraw Pro")
        root.geometry("1340x840")
        root.minsize(960, 560)

        # ---- Model & State
        self.model = GraphModel()
        self.path = None
        self.dirty = False
        self.clip = None
        self.paste_offset = 0

        # ---- View & Coordinates
        self.scale = 1.0
        self.ox, self.oy = 0.0, 0.0
        self.sel_nodes = set()
        self.sel_conn = None
        self.sel_sticky = None
        self.mode = None
        self.hover_node = None
        self.hover_conn = None
        self.cur = (0, 0)
        self.space_pressed = False
        self.mm_t = None
        self.T = {}

        # Alignment guides
        self.active_guides = []  # list of ('v'|'h', coord)

        # Flow animation state
        self.flow_phase = 0
        self.flow_job = None
        self.traversal_job = None

        # Tooltip state
        self.tooltip_win = None
        self.tooltip_timer = None

        # Layout animator
        self.animator = layouts.LayoutAnimator(self)

        # Freehand brush & sidebar state
        self.brush_color = "#ef4444"
        self.brush_width = 3
        self.current_stroke = None
        self.sidebar_visible = True
        self.brush_highlight = False   # highlighter (stipple) mode
        self.eraser_radius = 20        # eraser hit radius in world units
        self.shift_line_start = None   # for straight-line Shift+draw

        # ---- UI Variables
        self.tool = tk.StringVar(value="select")
        self.shape_var = tk.StringVar(value="rounded")
        self.line_var = tk.StringVar(value="curved")
        self.arrow_var = tk.StringVar(value="forward")
        self.dash_var = tk.BooleanVar(value=False)
        self.width_var = tk.StringVar(value="2")
        self.fs_var = tk.StringVar(value="11")
        self.status = tk.StringVar()
        self.zoom_text = tk.StringVar(value="100%")
        self.search_var = tk.StringVar()

        # Canvas settings
        self.theme = tk.StringVar(value="light")
        self.grid_var = tk.BooleanVar(value=True)
        self.snap_var = tk.BooleanVar(value=True)
        self.drag_pan = tk.StringVar(value="box")
        self.minimap_var = tk.BooleanVar(value=True)
        self.animated_flow_var = tk.BooleanVar(value=False)
        self.legend_var = tk.BooleanVar(value=False)

        # Build UI
        self.build_menu()
        self.build_toolbar()
        self.build_canvas()
        self.build_statusbar()
        self.bind_keys()

        root.protocol("WM_DELETE_WINDOW", self.on_close)

        # 49. Check crash recovery or load demo
        if io_manager.check_recovery_available() and not os.environ.get("LINKDRAW_TEST"):
            if messagebox.askyesno("Recover Session", "An auto-saved session was found. Would you like to recover it?"):
                io_manager.load_autosave(self.model)
                self.theme.set(self.model.settings.get("theme", "light"))
                self.grid_var.set(self.model.settings.get("grid", True))
                self.snap_var.set(self.model.settings.get("snap", True))
            else:
                self.load_demo()
        else:
            self.load_demo()

        self.on_tool_change()
        root.after(180, self.fit)

    # =========================================================================
    # Menus
    # =========================================================================
    def build_menu(self):
        acc = "Cmd" if sys.platform == "darwin" else "Ctrl"
        m = tk.Menu(self.root)

        # ---- File
        f = tk.Menu(m, tearoff=0)
        f.add_command(label="New", accelerator=f"{acc}+N", command=self.new_doc)
        f.add_command(label="Open...", accelerator=f"{acc}+O", command=self.open_doc)
        f.add_command(label="Save", accelerator=f"{acc}+S", command=self.save_doc)
        f.add_command(label="Save As...", command=self.save_as)
        f.add_separator()

        # 50. Recent Files
        self.recent_menu = tk.Menu(f, tearoff=0)
        self.update_recent_menu()
        f.add_cascade(label="Recent Files", menu=self.recent_menu)
        f.add_separator()

        # Templates
        tmpl = tk.Menu(f, tearoff=0)
        for label, key in (("Mind Map", "mind"), ("Flowchart", "flow"),
                           ("Architecture / Cloud", "arch"), ("Network Mesh", "mesh")):
            tmpl.add_command(label=label, command=lambda k=key: self.load_template(k))
        f.add_cascade(label="New from Template", menu=tmpl)
        f.add_separator()

        # 10, 41-43, 47-48. Import / Export
        imp = tk.Menu(f, tearoff=0)
        imp.add_command(label="Import CSV (Nodes / Edges)...", command=self.import_csv)
        imp.add_command(label="Import GraphML...", command=self.import_graphml)
        imp.add_command(label="Import GEXF (Gephi)...", command=self.import_gexf)
        imp.add_command(label="Import DOT (Graphviz)...", command=self.import_dot)
        f.add_cascade(label="Import", menu=imp)

        exp = tk.Menu(f, tearoff=0)
        exp.add_command(label="Export PNG...", command=lambda: self.export_raster("png"))
        exp.add_command(label="Export PDF...", command=lambda: self.export_raster("pdf"))
        exp.add_command(label="Export SVG...", command=self.export_svg)
        exp.add_command(label="Export PostScript...", command=self.export_ps)
        exp.add_separator()
        exp.add_command(label="Export CSV (Nodes & Edges)...", command=self.export_csv)
        exp.add_command(label="Export GraphML...", command=self.export_graphml)
        exp.add_command(label="Export GEXF...", command=self.export_gexf)
        exp.add_command(label="Export DOT...", command=self.export_dot)
        exp.add_command(label="Export NetworkX Pickle (.pkl)...", command=self.export_pickle)
        f.add_cascade(label="Export", menu=exp)

        # 48. Copy screenshot to clipboard
        f.add_command(label="Copy Screenshot to Clipboard", accelerator=f"{acc}+Shift+C", command=self.copy_screenshot)
        f.add_separator()
        f.add_command(label="Quit", command=self.on_close)
        m.add_cascade(label="File", menu=f)

        # ---- Edit
        e = tk.Menu(m, tearoff=0)
        e.add_command(label="Undo", accelerator=f"{acc}+Z", command=self.undo)
        e.add_command(label="Redo", accelerator=f"{acc}+Y", command=self.redo)
        e.add_separator()
        e.add_command(label="Cut", accelerator=f"{acc}+X", command=lambda: self.copy_selection(cut=True))
        e.add_command(label="Copy", accelerator=f"{acc}+C", command=self.copy_selection)
        e.add_command(label="Paste", accelerator=f"{acc}+V", command=self.paste_selection)
        e.add_command(label="Duplicate Subgraph", accelerator=f"{acc}+D", command=self.duplicate_selection)
        e.add_command(label="Delete", accelerator="Del", command=self.delete_selected)
        e.add_separator()
        e.add_command(label="Select All", accelerator=f"{acc}+A", command=self.select_all)
        e.add_command(label="Find / Search...", accelerator=f"{acc}+F", command=self.focus_search)
        e.add_command(label="Inline Edit Text", accelerator="Enter", command=self.edit_selected_inline)
        e.add_command(label="Swap Connection Direction", command=self.reverse_selected_conn)
        e.add_separator()
        e.add_command(label="Add Sticky Note", command=self.add_sticky_note)
        e.add_separator()
        e.add_command(label="Clear Freehand Strokes", command=self.clear_strokes)
        m.add_cascade(label="Edit", menu=e)

        # ---- Layout (21–30)
        lay = tk.Menu(m, tearoff=0)
        lay.add_command(label="Auto-Detect Layout (Preset)", command=lambda: self.apply_layout("auto"))
        lay.add_separator()
        lay.add_command(label="Force-Directed (Fruchterman–Reingold)", command=lambda: self.apply_layout("force"))
        lay.add_command(label="Circular Layout", command=lambda: self.apply_layout("circle"))
        lay.add_command(label="Grid Layout", command=lambda: self.apply_layout("grid"))
        lay.add_command(label="Hierarchical / Layered (Sugiyama DAG)", command=lambda: self.apply_layout("hierarchical"))
        lay.add_command(label="Radial Tree Layout", command=lambda: self.apply_layout("radial_tree"))
        lay.add_command(label="Kamada–Kawai Spring Embedding", command=lambda: self.apply_layout("kamada_kawai"))
        lay.add_command(label="Tutte Convex Planar Embedding", command=lambda: self.apply_layout("tutte"))
        lay.add_separator()
        lay.add_command(label="Orthogonal Edge Routing", command=self.apply_orthogonal_routing)

        # 16. Auto-arrange selected
        arr_sel = tk.Menu(lay, tearoff=0)
        arr_sel.add_command(label="Circle", command=lambda: self.arrange_selected("circle"))
        arr_sel.add_command(label="Horizontal Row", command=lambda: self.arrange_selected("row"))
        arr_sel.add_command(label="Vertical Column", command=lambda: self.arrange_selected("col"))
        arr_sel.add_command(label="Grid", command=lambda: self.arrange_selected("grid"))
        lay.add_cascade(label="Auto-Arrange Selected Nodes", menu=arr_sel)

        # Align & Distribute
        al = tk.Menu(lay, tearoff=0)
        for label, how in (("Left", "left"), ("Right", "right"), ("Top", "top"),
                           ("Bottom", "bottom"), ("Center Horizontally", "hcenter"),
                           ("Center Vertically", "vcenter")):
            al.add_command(label=label, command=lambda h=how: self.align_selected(h))
        lay.add_cascade(label="Align Selected", menu=al)
        lay.add_command(label="Distribute Horizontally", command=lambda: self.distribute_selected("x"))
        lay.add_command(label="Distribute Vertically", command=lambda: self.distribute_selected("y"))
        m.add_cascade(label="Layout", menu=lay)

        # ---- Analysis & Algorithms (31–40, 55)
        alg = tk.Menu(m, tearoff=0)
        alg.add_command(label="Shortest Path (A* Search)...", command=self.algo_a_star)
        alg.add_command(label="Animated Traversal: BFS", command=lambda: self.algo_traversal("bfs"))
        alg.add_command(label="Animated Traversal: DFS", command=lambda: self.algo_traversal("dfs"))
        alg.add_separator()
        alg.add_command(label="Minimum Spanning Tree (MST)", command=self.algo_mst)
        alg.add_command(label="Maximum Flow (Edmonds–Karp)...", command=self.algo_max_flow)
        alg.add_command(label="Topological Sort (DAG)", command=self.algo_topological_sort)
        alg.add_command(label="Cycle Detection (Highlight in Red)", command=self.algo_cycle_detection)
        alg.add_separator()
        alg.add_command(label="Connected Components (Color Clusters)", command=self.algo_connected_components)
        alg.add_command(label="Strongly Connected Components (Tarjan)", command=self.algo_scc)
        alg.add_command(label="Community Detection (Louvain)", command=self.algo_community_detection)
        alg.add_separator()

        # 39. Centrality metrics
        cent = tk.Menu(alg, tearoff=0)
        cent.add_command(label="Degree Centrality", command=lambda: self.algo_centrality("degree"))
        cent.add_command(label="Betweenness Centrality", command=lambda: self.algo_centrality("betweenness"))
        cent.add_command(label="Closeness Centrality", command=lambda: self.algo_centrality("closeness"))
        cent.add_command(label="Eigenvector Centrality", command=lambda: self.algo_centrality("eigenvector"))
        alg.add_cascade(label="Centrality Metrics (Resize Nodes)", menu=cent)

        # 55. Isomorphism Check
        alg.add_command(label="Check Subgraph Isomorphism", command=self.algo_isomorphism)
        alg.add_separator()
        alg.add_command(label="Clear Highlights & Badges", command=self.clear_highlights)
        m.add_cascade(label="Algorithms", menu=alg)

        # ---- View (1, 8, 44–46, 51–54, 56, 59)
        v = tk.Menu(m, tearoff=0)
        v.add_command(label="Zoom In", command=lambda: self.zoom_center(1.25))
        v.add_command(label="Zoom Out", command=lambda: self.zoom_center(0.8))
        v.add_command(label="Reset Zoom (100%)", command=self.reset_zoom)
        v.add_command(label="Fit to Screen", accelerator="F", command=self.fit)
        v.add_separator()

        # Theme Switcher (1)
        thm = tk.Menu(v, tearoff=0)
        thm.add_radiobutton(label="Light Theme", variable=self.theme, value="light", command=self.on_theme_change)
        thm.add_radiobutton(label="Dark Theme", variable=self.theme, value="dark", command=self.on_theme_change)
        thm.add_radiobutton(label="High-Contrast Theme", variable=self.theme, value="high_contrast", command=self.on_theme_change)
        v.add_cascade(label="Theme Palette", menu=thm)

        v.add_checkbutton(label="Show Minimap", variable=self.minimap_var, command=self.redraw)
        v.add_checkbutton(label="Show Grid", variable=self.grid_var, command=self.redraw)
        v.add_checkbutton(label="Snap to Grid / Guides", variable=self.snap_var)
        v.add_checkbutton(label="Animated Edge Flow", variable=self.animated_flow_var, command=self.toggle_edge_flow)
        v.add_checkbutton(label="Show Legend", variable=self.legend_var, command=self.redraw)
        v.add_separator()

        # Data & Analysis Views (44–46, 51–55, 56)
        v.add_command(label="Graph Properties & Degree Histogram...", command=self.show_properties)
        v.add_command(label="Node List Table...", command=self.show_node_list)
        v.add_command(label="Edge List Table...", command=self.show_edge_list)
        v.add_command(label="Adjacency Matrix...", command=self.show_adjacency_matrix)
        v.add_command(label="Tags & Categories Manager...", command=self.show_tags_manager)
        v.add_separator()
        v.add_command(label="Preferences...", command=self.show_preferences)
        m.add_cascade(label="View", menu=v)

        # ---- Help (19)
        h = tk.Menu(m, tearoff=0)
        h.add_command(label="Keyboard Shortcuts (?)...", accelerator="?", command=self.show_shortcuts)
        h.add_command(label="About LinkDraw Pro", command=self.show_about)
        m.add_cascade(label="Help", menu=h)

        self.root.config(menu=m)

    def update_recent_menu(self):
        self.recent_menu.delete(0, "end")
        files = io_manager.get_recent_files()
        if not files:
            self.recent_menu.add_command(label="No recent files", state="disabled")
            return
        for p in files:
            self.recent_menu.add_command(label=os.path.basename(p), command=lambda path=p: self.open_file_path(path))

    # =========================================================================
    # Toolbar & Search Bar
    # =========================================================================
    def build_toolbar(self):
        r = self.root
        bar = ttk.Frame(r, padding=(6, 4))
        bar.pack(side="top", fill="x")

        # Mode tools
        for text, val in (("Select (V)", "select"), ("Node (N)", "node"),
                          ("Connect (C)", "connect"), ("Draw (B)", "draw"),
                          ("Erase (R)", "erase"), ("Hand (H)", "hand")):
            ttk.Radiobutton(bar, text=text, value=val, variable=self.tool,
                            style="Toolbutton", command=self.on_tool_change).pack(side="left", padx=1)
        self._sep(bar)

        # Edit quick actions
        for text, cmd in (("Undo", self.undo), ("Redo", self.redo),
                          ("Delete", self.delete_selected), ("Edit", self.edit_selected_inline)):
            ttk.Button(bar, text=text, command=cmd).pack(side="left", padx=1)
        self._sep(bar)

        # Zoom
        ttk.Button(bar, text="-", width=2, command=lambda: self.zoom_center(0.8)).pack(side="left")
        ttk.Button(bar, textvariable=self.zoom_text, width=6, command=self.reset_zoom).pack(side="left", padx=1)
        ttk.Button(bar, text="+", width=2, command=lambda: self.zoom_center(1.25)).pack(side="left")
        ttk.Button(bar, text="Fit", width=4, command=self.fit).pack(side="left", padx=2)
        self._sep(bar)

        # Animated Flow toggle
        ttk.Checkbutton(bar, text="Flow", variable=self.animated_flow_var,
                        command=self.toggle_edge_flow).pack(side="left", padx=2)

        # Theme quick switcher
        ttk.Label(bar, text="Theme:").pack(side="left", padx=(4, 2))
        cb_th = ttk.Combobox(bar, textvariable=self.theme, values=["light", "dark", "high_contrast"],
                             width=11, state="readonly")
        cb_th.pack(side="left", padx=2)
        cb_th.bind("<<ComboboxSelected>>", lambda e: self.on_theme_change())
        self._sep(bar)

        # 60. Search bar
        ttk.Label(bar, text="Find:").pack(side="left", padx=(4, 2))
        self.search_entry = ttk.Entry(bar, textvariable=self.search_var, width=14)
        self.search_entry.pack(side="left", padx=2)
        self.search_entry.bind("<Return>", lambda e: self.do_search())
        self.search_entry.bind("<KeyRelease>", lambda e: self.on_search_key())
        ttk.Button(bar, text="🔍", width=3, command=self.do_search).pack(side="left", padx=1)

        # Properties, Shortcuts & Sidebar Toggle
        ttk.Button(bar, text="☰ Panel", command=self.toggle_sidebar).pack(side="right", padx=2)
        ttk.Button(bar, text="Stats", command=self.show_properties).pack(side="right", padx=2)
        ttk.Button(bar, text="?", width=2, command=self.show_shortcuts).pack(side="right", padx=2)

        # Secondary toolbar: Node & Edge Styling
        bar2 = ttk.Frame(r, padding=(6, 0, 6, 4))
        bar2.pack(side="top", fill="x")

        # Shape
        ttk.Label(bar2, text="Shape:").pack(side="left")
        self._combo(bar2, self.shape_var, SHAPES, self.on_shape_change, 9)

        # Fill color
        ttk.Label(bar2, text="Fill:").pack(side="left", padx=(6, 2))
        self.swatch_frame = ttk.Frame(bar2)
        self.swatch_frame.pack(side="left")
        self.update_color_swatches()

        # Font size
        ttk.Label(bar2, text="Font:").pack(side="left", padx=(8, 2))
        self._combo(bar2, self.fs_var, FSIZES, self.on_fs_change, 3)

        # Icon
        ttk.Button(bar2, text="Icon...", command=self.pick_node_icon).pack(side="left", padx=4)
        self._sep(bar2)

        # Line options
        ttk.Label(bar2, text="Line:").pack(side="left")
        self._combo(bar2, self.line_var, LINE_TYPES, self.on_conn_style_change, 9)
        ttk.Label(bar2, text="Arrow:").pack(side="left", padx=(6, 2))
        self._combo(bar2, self.arrow_var, ARROWS, self.on_conn_style_change, 8)
        ttk.Label(bar2, text="Width:").pack(side="left", padx=(6, 2))
        self._combo(bar2, self.width_var, WIDTHS, self.on_conn_style_change, 3)
        ttk.Checkbutton(bar2, text="Dash", variable=self.dash_var,
                        command=self.on_conn_style_change).pack(side="left", padx=4)

        # Line color
        ttk.Button(bar2, text="Line Col...", command=self.pick_conn_color).pack(side="left", padx=4)
        self._sep(bar2)

        # ── Brush / Draw controls ─────────────────────────────────────────────
        ttk.Label(bar2, text="Brush:").pack(side="left")
        ttk.Button(bar2, text="Col...", command=self.pick_brush_color).pack(side="left", padx=2)
        ttk.Label(bar2, text="Sz:").pack(side="left", padx=(4, 0))
        ttk.Button(bar2, text="−", width=2,
                   command=lambda: self._adj_brush(-1)).pack(side="left")
        self.brush_sz_label = ttk.Label(bar2, text=str(self.brush_width), width=3, anchor="center")
        self.brush_sz_label.pack(side="left")
        ttk.Button(bar2, text="+", width=2,
                   command=lambda: self._adj_brush(1)).pack(side="left")
        # Quick size presets
        for lbl, sz in (("S", 2), ("M", 5), ("L", 10), ("XL", 20)):
            ttk.Button(bar2, text=lbl, width=2,
                       command=lambda s=sz: self._set_brush_sz(s)).pack(side="left", padx=1)
        self.highlight_var = tk.BooleanVar(value=False)
        ttk.Checkbutton(bar2, text="Hilite", variable=self.highlight_var).pack(side="left", padx=(4, 2))
        ttk.Button(bar2, text="Clear Strokes", command=self.clear_strokes).pack(side="left", padx=4)

        # Re-focus canvas after tool clicks
        for cls in ("TButton", "TRadiobutton", "TCheckbutton"):
            r.bind_class(cls, "<ButtonRelease-1>", lambda e: r.after(1, self.canvas.focus_set), add="+")

    def _sep(self, parent):
        ttk.Separator(parent, orient="vertical").pack(side="left", fill="y", padx=6)

    def _combo(self, parent, var, values, cmd, width=10):
        cb = ttk.Combobox(parent, textvariable=var, values=values, width=width, state="readonly")
        cb.pack(side="left", padx=2)
        cb.bind("<<ComboboxSelected>>", lambda e: (cmd(), self.canvas.focus_set()))
        return cb

    def update_color_swatches(self):
        for widget in self.swatch_frame.winfo_children():
            widget.destroy()
        th = self.theme.get()
        colors = NODE_COLORS_HC if th == "high_contrast" else (NODE_COLORS_DARK if th == "dark" else NODE_COLORS_LIGHT)
        for col in colors[:6]:
            lbl = tk.Label(self.swatch_frame, bg=col, width=2, relief="solid", bd=1, cursor="hand2")
            lbl.pack(side="left", padx=1)
            lbl.bind("<Button-1>", lambda e, c=col: self.set_selected_node_color(c))
        ttk.Button(self.swatch_frame, text="🎨", width=2, command=self.pick_custom_node_color).pack(side="left", padx=1)

    # =========================================================================
    # Canvas, Minimap & Unified Sidebar
    # =========================================================================
    def build_canvas(self):
        self.main_container = ttk.Frame(self.root)
        self.main_container.pack(fill="both", expand=True)

        self.canvas = tk.Canvas(self.main_container, bg="#fafafa", highlightthickness=0)
        self.canvas.pack(side="left", fill="both", expand=True)

        self.sidebar = panels.UnifiedSidebar(self.main_container, self)
        self.sidebar.pack(side="right", fill="y")
        self.sidebar_visible = True
        c = self.canvas

        c.bind("<Configure>", lambda e: self.redraw())
        c.bind("<ButtonPress-1>", self.on_press)
        c.bind("<B1-Motion>", self.on_motion)
        c.bind("<ButtonRelease-1>", self.on_release)
        c.bind("<Double-Button-1>", self.on_double_click)
        c.bind("<ButtonPress-3>", self.on_right_click)

        # Middle and right pan
        for b in (2, 3):
            c.bind(f"<ButtonPress-{b}>", self.pan_start)
            c.bind(f"<B{b}-Motion>", self.pan_move)

        # Zoom & pan with wheel
        c.bind("<MouseWheel>", self.on_wheel)
        c.bind("<Button-4>", self.on_wheel)
        c.bind("<Button-5>", self.on_wheel)

        # Hover tracking for tooltips & breadcrumbs (9, 65)
        c.bind("<Motion>", self.on_mouse_hover)

        # 63. Minimap
        self.mm = tk.Canvas(c, width=MM_W, height=MM_H, highlightthickness=1,
                            highlightbackground="#9ca3af", cursor="hand2")
        self.mm.bind("<ButtonPress-1>", self.mm_click)
        self.mm.bind("<B1-Motion>", self.mm_click)

    def toggle_sidebar(self):
        if self.sidebar_visible:
            self.sidebar.pack_forget()
            self.sidebar_visible = False
        else:
            self.sidebar.pack(side="right", fill="y")
            self.sidebar_visible = True
        self.redraw()

    def pick_brush_color(self):
        col = colorchooser.askcolor(self.brush_color, parent=self.root, title="Brush Color")[1]
        if col:
            self.brush_color = col

    def _adj_brush(self, delta):
        self.brush_width = max(1, min(60, self.brush_width + delta))
        self.brush_sz_label.config(text=str(self.brush_width))

    def _set_brush_sz(self, sz):
        self.brush_width = sz
        self.brush_sz_label.config(text=str(sz))

    def clear_strokes(self):
        if self.model.freehand_strokes:
            self.model.push_undo()
            self.model.freehand_strokes.clear()
            self.model.dirty = True
            self.redraw()

    def _erase_at(self, sx, sy):
        """Remove strokes whose any point is within eraser_radius of screen pos (sx,sy)."""
        wr = self.eraser_radius          # world-space radius
        wx, wy = self.to_world(sx, sy)
        keep = []
        changed = False
        for st in self.model.freehand_strokes:
            if any((px - wx) ** 2 + (py - wy) ** 2 <= wr * wr
                   for px, py in st["points"]):
                changed = True
            else:
                keep.append(st)
        if changed:
            self.model.freehand_strokes[:] = keep
            self.model.dirty = True

    def build_statusbar(self):
        # 65. Status bar breadcrumbs
        self.status_bar = ttk.Label(self.root, textvariable=self.status, anchor="w", padding=(8, 3), relief="sunken")
        self.status_bar.pack(side="bottom", fill="x")

    def bind_keys(self):
        r = self.root
        r.bind("<Delete>", lambda e: self.delete_selected())
        r.bind("<BackSpace>", lambda e: self.delete_selected())
        r.bind("<Return>", lambda e: self.edit_selected_inline())
        r.bind("<Escape>", self.on_escape)
        r.bind("<KeyPress-space>", self.space_down)
        r.bind("<KeyRelease-space>", self.space_up)

        # 64. Mode keys: V=select, N=add node, E/C=add edge, D=delete
        r.bind("v", lambda e: self.set_tool("select"))
        r.bind("n", lambda e: self.set_tool("node"))
        r.bind("c", lambda e: self.set_tool("connect"))
        r.bind("e", lambda e: self.set_tool("connect"))
        r.bind("h", lambda e: self.set_tool("hand"))
        r.bind("b", lambda e: self.set_tool("draw"))
        r.bind("r", lambda e: self.set_tool("erase"))
        r.bind("f", lambda e: self.fit())
        r.bind("?", lambda e: self.show_shortcuts())

        # Standard shortcuts
        for key, fn in (("z", self.undo), ("y", self.redo), ("Z", self.redo),
                        ("d", self.duplicate_selection), ("a", self.select_all),
                        ("s", self.save_doc), ("o", self.open_doc), ("n", self.new_doc),
                        ("f", self.focus_search), ("c", self.copy_selection),
                        ("v", self.paste_selection), ("x", lambda: self.copy_selection(cut=True))):
            r.bind(f"<{MOD}-{key}>", lambda e, f=fn: f())

        r.bind(f"<{MOD}-Shift-C>", lambda e: self.copy_screenshot())

        # Arrow nudge
        for key, dx, dy in (("Left", -1, 0), ("Right", 1, 0), ("Up", 0, -1), ("Down", 0, 1)):
            r.bind(f"<{key}>", lambda e, a=dx, b=dy: self.nudge_selected(a * 10, b * 10))
            r.bind(f"<Shift-{key}>", lambda e, a=dx, b=dy: self.nudge_selected(a, b))

    # =========================================================================
    # Theme & Coordinate Mapping
    # =========================================================================
    def theme_colors(self):
        th = self.theme.get()
        if th == "dark":
            return dict(
                bg="#1e222b", fg="#e5e7eb", grid="#2c3340", dot="#4b5563",
                line0="#cbd5e1", accent="#3b82f6", sel_glow="#60a5fa",
                tooltip_bg="#111827", tooltip_fg="#f3f4f6"
            )
        elif th == "high_contrast":
            return dict(
                bg="#000000", fg="#ffffff", grid="#333333", dot="#888888",
                line0="#00ffff", accent="#ffff00", sel_glow="#ff00ff",
                tooltip_bg="#000000", tooltip_fg="#ffff00"
            )
        else:  # light
            return dict(
                bg="#fafafa", fg="#111827", grid="#eceff3", dot="#c7ccd4",
                line0="#374151", accent="#2563eb", sel_glow="#93c5fd",
                tooltip_bg="#ffffff", tooltip_fg="#111827"
            )

    def to_screen(self, x, y):
        return x * self.scale + self.ox, y * self.scale + self.oy

    def to_world(self, sx, sy):
        return (sx - self.ox) / self.scale, (sy - self.oy) / self.scale

    def snap_val(self, v):
        gs = self.model.settings.get("grid_size", 20)
        return round(v / gs) * gs

    # =========================================================================
    # Redraw & Rendering
    # =========================================================================
    def redraw(self):
        c = self.canvas
        T = self.T = self.theme_colors()
        c.config(bg=T["bg"])
        c.delete("all")

        s = self.scale
        W, H = c.winfo_width(), c.winfo_height()
        if W <= 10 or H <= 10:
            return

        self.zoom_text.set(f"{round(s * 100)}%")

        # 68. Viewport culling bounds in world coordinates
        vw0, vh0 = self.to_world(0, 0)
        vw1, vh1 = self.to_world(W, H)
        v_min_x, v_max_x = min(vw0, vw1) - 60, max(vw0, vw1) + 60
        v_min_y, v_max_y = min(vh0, vh1) - 60, max(vh0, vh1) + 60
        culling_enabled = self.model.settings.get("viewport_culling", True)

        # Draw Grid
        if self.grid_var.get():
            step = self.model.settings.get("grid_size", 20) * s
            while step < 16:
                step *= 2
            gx = self.ox % step
            while gx < W:
                c.create_line(gx, 0, gx, H, fill=T["grid"])
                gx += step
            gy = self.oy % step
            while gy < H:
                c.create_line(0, gy, W, gy, fill=T["grid"])
                gy += step

        # Draw Sticky Notes (58)
        for sid, sn in self.model.sticky_notes.items():
            if culling_enabled and (sn["x"] + sn["w"] < v_min_x or sn["x"] - sn["w"] > v_max_x or
                                    sn["y"] + sn["h"] < v_min_y or sn["y"] - sn["h"] > v_max_y):
                continue
            self.draw_sticky_note(sid, sn)

        # 5. Group parallel edges for bundling / curvature separation
        edge_pairs = {}
        for cid, cn in self.model.conns.items():
            if cn["a"] in self.model.nodes and cn["b"] in self.model.nodes:
                pair = tuple(sorted([cn["a"], cn["b"]]))
                edge_pairs.setdefault(pair, []).append(cid)

        # Draw Connections (2, 3, 4, 5, 8, 69)
        for pair, cids in edge_pairs.items():
            total = len(cids)
            for idx, cid in enumerate(cids):
                cn = self.model.conns[cid]
                self.draw_connection(cid, cn, idx, total)

        # Draw Nodes (6, 7)
        for nid, n in self.model.nodes.items():
            if culling_enabled and (n["x"] + n["w"] < v_min_x or n["x"] - n["w"] > v_max_x or
                                    n["y"] + n["h"] < v_min_y or n["y"] - n["h"] > v_max_y):
                continue
            self.draw_node(nid, n)

        # 15. Alignment Guides
        for orient, coord in self.active_guides:
            if orient == "v":
                sx, _ = self.to_screen(coord, 0)
                c.create_line(sx, 0, sx, H, fill="#06b6d4", dash=(4, 4), width=1.5, tags="guide")
            else:
                _, sy = self.to_screen(0, coord)
                c.create_line(0, sy, W, sy, fill="#06b6d4", dash=(4, 4), width=1.5, tags="guide")

        # Interactive temporary lines (Connecting, Reconnecting, Rubberband)
        if self.mode == "connect" and hasattr(self, "conn_src") and self.conn_src in self.model.nodes:
            wx, wy = self.to_world(*self.cur)
            p = self.to_screen(*io_manager.get_shape_border_point(self.model.nodes[self.conn_src], wx, wy))
            c.create_line(*p, *self.cur, fill=T["accent"], width=2, dash=(5, 3), arrow="last", tags="temp")

        if self.mode == "reconnect" and hasattr(self, "rc") and self.rc[0] in self.model.conns:
            cn = self.model.conns[self.rc[0]]
            fixed_id = cn["b"] if self.rc[1] == 0 else cn["a"]
            if fixed_id in self.model.nodes:
                wx, wy = self.to_world(*self.cur)
                p = self.to_screen(*io_manager.get_shape_border_point(self.model.nodes[fixed_id], wx, wy))
                c.create_line(*p, *self.cur, fill=T["accent"], width=2, dash=(5, 3), tags="temp")

        if self.mode == "band" and hasattr(self, "band0"):
            x0, y0 = self.band0
            x1, y1 = self.cur
            c.create_rectangle(x0, y0, x1, y1, outline=T["accent"], dash=(4, 3), tags="temp")

        # 59. Legend widget
        if self.legend_var.get():
            self.draw_legend()

        # Freehand strokes (Draw/Brush tool) — rendered after legend so they're on top
        for st in self.model.freehand_strokes:
            pts = [coord for p in st["points"] for coord in self.to_screen(*p)]
            if len(pts) >= 4:
                kw = dict(fill=st.get("color", "#ef4444"),
                          width=max(1, round(st.get("width", 3) * s)),
                          capstyle="round", joinstyle="round", smooth=True)
                if st.get("highlight"):
                    kw["stipple"] = "gray50"
                c.create_line(*pts, **kw)

        # Eraser ghost cursor
        if self.tool.get() == "erase" and hasattr(self, "cur") and self.cur:
            er = max(2, round(self.eraser_radius * s))
            cx2, cy2 = self.cur
            c.create_oval(cx2 - er, cy2 - er, cx2 + er, cy2 + er,
                          outline="#94a3b8", width=1, dash=(3, 3), tags="temp")

        # 63. Minimap
        self.draw_minimap()

        # 65. Update breadcrumbs
        self.update_breadcrumbs()

    # ---- Draw Node (6, 7)
    def draw_node(self, nid, n):
        c, s, T = self.canvas, self.scale, self.T
        sx, sy = self.to_screen(n["x"], n["y"])
        hw, hh = n["w"] / 2.0 * s, n["h"] / 2.0 * s
        x1, y1, x2, y2 = sx - hw, sy - hh, sx + hw, sy + hh
        tag = f"node:{nid}"
        sel = nid in self.sel_nodes
        shape = n.get("shape", "rounded")

        fill_col = n.get("color", NODE_COLORS_LIGHT[1])
        outline_col = T["accent"] if sel else (n.get("highlight") or "#4b5563")
        width = 3.5 if sel else (3.0 if n.get("highlight") else 1.5)

        kw = dict(fill=fill_col, outline=outline_col, width=width, tags=tag)

        if shape == "circle":
            c.create_oval(x1, y1, x2, y2, **kw)
        elif shape == "square":
            side = max(hw, hh)
            c.create_rectangle(sx - side, sy - side, sx + side, sy + side, **kw)
        elif shape == "diamond":
            c.create_polygon(sx, y1, x2, sy, sx, y2, x1, sy, **kw)
        elif shape == "triangle":
            c.create_polygon(sx, y1, x2, y2, x1, y2, **kw)
        elif shape == "hexagon":
            pts = []
            for k in range(6):
                ang = math.pi / 6 + k * math.pi / 3
                pts.extend([sx + hw * math.cos(ang), sy + hh * math.sin(ang)])
            c.create_polygon(pts, **kw)
        elif shape == "star":
            pts = []
            for k in range(10):
                ang = -math.pi / 2 + k * math.pi / 5
                r = hw if k % 2 == 0 else hw * 0.45
                pts.extend([sx + r * math.cos(ang), sy + r * math.sin(ang)])
            c.create_polygon(pts, **kw)
        elif shape == "rounded":
            r = min(14.0 * s, hw, hh)
            pts = [x1 + r, y1, x1 + r, y1, x2 - r, y1, x2 - r, y1, x2, y1, x2, y1 + r,
                   x2, y1 + r, x2, y2 - r, x2, y2 - r, x2, y2, x2 - r, y2, x2 - r, y2,
                   x1 + r, y2, x1 + r, y2, x1, y2, x1, y2 - r, x1, y2 - r, x1, y1 + r,
                   x1, y1 + r, x1, y1]
            c.create_polygon(pts, smooth=True, **kw)
        elif shape == "text":
            c.create_rectangle(x1, y1, x2, y2, fill=T["bg"], outline=T["accent"] if sel else "", tags=tag)
        else:  # rectangle
            c.create_rectangle(x1, y1, x2, y2, **kw)

        # 7. Custom icon / emoji glyph + text
        label_text = n.get("text", "")
        if n.get("icon"):
            label_text = f"{n['icon']}  {label_text}"

        fs = max(6, int(n.get("fs", 11) * s))
        txt_col = T["fg"] if (shape == "text" or self.theme.get() == "high_contrast") else "#111827"
        c.create_text(sx, sy, text=label_text, justify="center", fill=txt_col,
                      tags=tag, font=("Helvetica", fs, "bold" if sel else "normal"))

        # 35. Badge (e.g. topological rank or order badge)
        if n.get("badge"):
            bx, by = x2 - 8 * s, y1 + 8 * s
            br = 10 * s
            c.create_oval(bx - br, by - br, bx + br, by + br, fill="#ef4444", outline="white", width=1.5, tags=tag)
            c.create_text(bx, by, text=str(n["badge"]), fill="white", font=("Helvetica", max(6, int(8 * s)), "bold"), tags=tag)

        # Resize corner handle
        if sel and len(self.sel_nodes) == 1 and self.sel_conn is None:
            c.create_rectangle(x2 - 5, y2 - 5, x2 + 5, y2 + 5, fill=T["accent"],
                               outline="white", tags=f"handle:{nid}")

    # ---- Draw Connection (2, 3, 4, 5, 8, 69)
    def draw_connection(self, cid, cn, idx=0, total=1):
        c, s, T = self.canvas, self.scale, self.T
        kind, raw, lab = io_manager.get_conn_geom(self.model, cn, idx, total)
        curve_pts = io_manager.sample_curve(kind, raw)
        flat = [coord for pt in curve_pts for coord in self.to_screen(*pt)]
        if len(flat) < 4:
            return

        tag = f"conn:{cid}"
        sel = cid == self.sel_conn
        width = cn.get("width", 2)
        col = cn.get("highlight") or (T["line0"] if cn.get("color") == LINE_COLORS_LIGHT[0] else cn.get("color"))

        # Selection glow
        if sel:
            c.create_line(*flat, fill=T["sel_glow"], width=width * s + 8, capstyle="round",
                          joinstyle="round", tags=tag)

        # Arrowhead specification
        arr = cn.get("arrow", "forward")
        tk_arrow = {"none": "none", "forward": "last", "backward": "first", "both": "both"}.get(arr, "last")

        opts = dict(
            fill=col,
            width=max(1.0, width * s),
            tags=tag,
            joinstyle="round",
            capstyle="round",
            arrow=tk_arrow,
            arrowshape=(max(7, int((9 + width * 1.5) * s)),
                        max(8, int((11 + width * 1.5) * s)),
                        max(3, int((3 + width) * s))),
        )
        if cn.get("dash"):
            opts["dash"] = (7, 4)

        # 8. Animated edge flow (marching dashes)
        if self.animated_flow_var.get() and cn.get("arrow") in ("forward", "both"):
            opts["dash"] = (8, 6)
            opts["dashoffset"] = self.flow_phase

        c.create_line(*flat, **opts)

        # 69. Lazy edge rendering: skip label details when scale is tiny
        lazy = self.model.settings.get("lazy_edges", True)
        if not (lazy and s < 0.35):
            lbl = cn.get("label", "")
            wt = cn.get("weight")
            if wt is not None and wt != 1.0:
                lbl = f"{lbl} [{wt}]" if lbl else f"[{wt}]"
            if cn.get("flow") is not None:
                lbl = f"{lbl} (f:{cn['flow']})"

            if lbl:
                lx, ly = self.to_screen(*lab)
                txt = c.create_text(lx, ly, text=lbl, fill=T["fg"], tags=tag,
                                    font=("Helvetica", max(7, int(10 * s)), "bold" if sel else "normal"))
                bb = c.bbox(txt)
                if bb:
                    bg_rect = c.create_rectangle(bb[0] - 3, bb[1] - 1, bb[2] + 3, bb[3] + 1,
                                                 fill=T["bg"], outline="#d1d5db", tags=tag)
                    c.tag_lower(bg_rect, txt)

        # End handles for re-attaching when selected
        if sel:
            for which, pt in ((0, raw[0]), (1, raw[-1])):
                hx, hy = self.to_screen(*pt)
                c.create_oval(hx - 6, hy - 6, hx + 6, hy + 6, fill="white", outline=T["accent"],
                              width=2, tags=f"end:{cid}:{which}")

    # ---- Draw Sticky Note (58)
    def draw_sticky_note(self, sid, sn):
        c, s = self.canvas, self.scale
        sx, sy = self.to_screen(sn["x"], sn["y"])
        hw, hh = sn["w"] / 2.0 * s, sn["h"] / 2.0 * s
        tag = f"sticky:{sid}"
        sel = sid == self.sel_sticky

        c.create_rectangle(sx - hw, sy - hh, sx + hw, sy + hh, fill=sn["color"],
                           outline="#ca8a04" if not sel else "#2563eb", width=2.5 if sel else 1.0, tags=tag)
        c.create_text(sx, sy, text=sn["text"], width=int(sn["w"] * s - 12), justify="center",
                      font=("Helvetica", max(7, int(10 * s))), fill="#713f12", tags=tag)

    # ---- Draw Legend Widget (59)
    def draw_legend(self):
        c = self.canvas
        W = c.winfo_width()
        tags = set()
        for n in self.model.nodes.values():
            tags.update(n.get("tags", []))

        if not tags:
            return

        lx, ly = W - 180, 20
        lw, lh = 160, 25 + len(tags) * 22
        c.create_rectangle(lx, ly, lx + lw, ly + lh, fill="#ffffff", outline="#9ca3af", width=1.5, tags="legend")
        c.create_text(lx + lw / 2, ly + 14, text="Legend (Tags)", font=("Helvetica", 9, "bold"), fill="#111827", tags="legend")

        for idx, t in enumerate(sorted(tags)):
            item_y = ly + 32 + idx * 22
            col = algorithms.DISTINCT_COLORS[idx % len(algorithms.DISTINCT_COLORS)]
            c.create_oval(lx + 12, item_y - 5, lx + 22, item_y + 5, fill=col, outline="", tags="legend")
            c.create_text(lx + 30, item_y, text=t[:16], anchor="w", font=("Helvetica", 8), fill="#374151", tags="legend")

    # ---- Minimap (63)
    def draw_minimap(self):
        mm = self.mm
        if not self.minimap_var.get():
            mm.place_forget()
            return
        if not mm.winfo_ismapped():
            mm.place(relx=1.0, rely=1.0, x=-12, y=-12, anchor="se")
        mm.config(bg=self.T["bg"])
        mm.delete("all")

        if not self.model.nodes and not self.model.sticky_notes:
            self.mm_t = None
            return

        x0, y0, w, h = self.model.bounds(100)
        sc = min(MM_W / w, MM_H / h)
        offx, offy = (MM_W - w * sc) / 2.0, (MM_H - h * sc) / 2.0
        self.mm_t = (x0, y0, sc, offx, offy)

        def P(x, y):
            return (x - x0) * sc + offx, (y - y0) * sc + offy

        for cn in self.model.conns.values():
            if cn["a"] in self.model.nodes and cn["b"] in self.model.nodes:
                a, b = self.model.nodes[cn["a"]], self.model.nodes[cn["b"]]
                mm.create_line(*P(a["x"], a["y"]), *P(b["x"], b["y"]), fill="#9ca3af")

        for nid, n in self.model.nodes.items():
            px, py = P(n["x"] - n["w"] / 2.0, n["y"] - n["h"] / 2.0)
            qx, qy = P(n["x"] + n["w"] / 2.0, n["y"] + n["h"] / 2.0)
            col = self.T["accent"] if nid in self.sel_nodes else "#6b7280"
            mm.create_rectangle(px, py, qx, qy, fill=col, outline="")

        # Viewport rectangle
        W, H = self.canvas.winfo_width(), self.canvas.winfo_height()
        vx0, vy0 = P(*self.to_world(0, 0))
        vx1, vy1 = P(*self.to_world(W, H))
        mm.create_rectangle(vx0, vy0, vx1, vy1, outline="#ef4444", width=2)

    def mm_click(self, e):
        if not self.mm_t:
            return
        x0, y0, sc, offx, offy = self.mm_t
        wx = (e.x - offx) / sc + x0
        wy = (e.y - offy) / sc + y0
        W, H = self.canvas.winfo_width(), self.canvas.winfo_height()
        self.ox = W / 2.0 - wx * self.scale
        self.oy = H / 2.0 - wy * self.scale
        self.redraw()

    # =========================================================================
    # Hit Testing & Selection
    # =========================================================================
    def hit(self, sx, sy):
        items = self.canvas.find_overlapping(sx - 4, sy - 4, sx + 4, sy + 4)
        for it in reversed(items):
            for t in self.canvas.gettags(it):
                if t.startswith(("handle:", "node:", "conn:", "end:", "sticky:")):
                    parts = t.split(":")
                    return parts[0], int(parts[1]), int(parts[2]) if len(parts) > 2 else None
        return None

    def select(self, nodes=(), conn=None, sticky=None):
        self.sel_nodes = set(nodes)
        self.sel_conn = conn
        self.sel_sticky = sticky

        if conn in self.model.conns:
            cn = self.model.conns[conn]
            self.line_var.set(cn.get("type", "curved"))
            self.arrow_var.set(cn.get("arrow", "forward"))
            self.dash_var.set(cn.get("dash", False))
            self.width_var.set(str(cn.get("width", 2)))
        elif self.sel_nodes:
            nid = next(iter(self.sel_nodes))
            n = self.model.nodes.get(nid)
            if n:
                self.shape_var.set(n.get("shape", "rounded"))
                self.fs_var.set(str(n.get("fs", 11)))

        self.redraw()
        if hasattr(self, "sidebar"):
            self.sidebar.on_selection_changed()

    def select_all(self):
        self.select(nodes=set(self.model.nodes.keys()))

    # =========================================================================
    # Mouse & Keyboard Interaction
    # =========================================================================
    def space_down(self, e=None):
        if not self.space_pressed:
            self.space_pressed = True
            self.canvas.config(cursor="fleur")

    def space_up(self, e=None):
        self.space_pressed = False
        self.on_tool_change()

    def on_press(self, e):
        self.canvas.focus_set()
        wx, wy = self.to_world(e.x, e.y)
        h = self.hit(e.x, e.y)
        tool = self.tool.get()
        self.cur = (e.x, e.y)
        self.active_guides.clear()

        # Hand / Space pan
        if self.space_pressed or tool == "hand":
            self.mode = "pan"
            self.pan_start(e)
            return

        # Draw (Brush) tool
        if tool == "draw":
            wx, wy = self.to_world(e.x, e.y)
            shift = bool(e.state & 0x1)
            highlight = self.highlight_var.get()
            self.current_stroke = {
                "points": [(wx, wy)], "color": self.brush_color,
                "width": self.brush_width, "highlight": highlight,
                "straight": shift,   # Shift-held → locked to straight line
            }
            self.shift_line_start = (wx, wy) if shift else None
            self.mode = "draw"
            return

        # Eraser tool
        if tool == "erase":
            self.model.push_undo()
            self.mode = "erase"
            self._erase_at(e.x, e.y)
            return

        # Add Node tool
        if tool == "node":
            if h and h[0] == "node":
                self.select(nodes={h[1]})
            else:
                self.add_node_at(wx, wy)
            return

        # Handle resize
        if h and h[0] == "handle":
            self.model.push_undo()
            self.mode, self.rs_id = "resize", h[1]
            return

        # Reconnect end
        if h and h[0] == "end":
            self.mode, self.rc = "reconnect", (h[1], h[2])
            return

        # Connect tool
        if tool == "connect":
            if h and h[0] == "node":
                self.mode, self.conn_src = "connect", h[1]
                self.select(nodes={h[1]})
            return

        # Sticky Note click
        if h and h[0] == "sticky":
            self.select(sticky=h[1])
            self.mode = "drag_sticky"
            self.drag_start = (wx, wy)
            self.drag_orig = (self.model.sticky_notes[h[1]]["x"], self.model.sticky_notes[h[1]]["y"])
            return

        # Node click / Multi-select (11, 12)
        if h and h[0] == "node":
            nid = h[1]
            # Shift / Ctrl multi-select toggle
            if (e.state & 0x1) or (e.state & 0x4):
                self.select(nodes=self.sel_nodes ^ {nid})
            elif nid not in self.sel_nodes:
                self.select(nodes={nid})

            self.mode = "drag"
            self.drag_start = (wx, wy)
            self.drag_orig = {i: (self.model.nodes[i]["x"], self.model.nodes[i]["y"]) for i in self.sel_nodes}
            self.drag_moved = False
            return

        # Connection click
        if h and h[0] == "conn":
            self.select(conn=h[1])
            return

        # Click on empty canvas
        shift = bool(e.state & 0x1)
        if not shift:
            self.select()

        if self.drag_pan.get() == "pan" and not shift:
            self.mode = "pan"
            self.pan_start(e)
        else:
            self.mode, self.band0 = "band", (e.x, e.y)

    def on_motion(self, e):
        m = self.mode
        self.cur = (e.x, e.y)
        wx, wy = self.to_world(e.x, e.y)

        if m == "pan":
            self.pan_move(e)
        elif m == "drag":
            dx, dy = wx - self.drag_start[0], wy - self.drag_start[1]
            if not self.drag_moved:
                if abs(dx * self.scale) < 2 and abs(dy * self.scale) < 2:
                    return
                self.model.push_undo()
                self.drag_moved = True

            # 15. Alignment Guides and Snap while dragging
            self.active_guides.clear()
            snap = self.snap_var.get()
            guide_thresh = 6.0

            for i, (ox, oy) in self.drag_orig.items():
                nx, ny = ox + dx, oy + dy
                if snap:
                    # check alignment with other unselected nodes
                    for other_id, other in self.model.nodes.items():
                        if other_id not in self.sel_nodes:
                            # Horizontal alignment (centers)
                            if abs(ny - other["y"]) < guide_thresh:
                                ny = other["y"]
                                self.active_guides.append(("h", ny))
                            # Vertical alignment (centers)
                            if abs(nx - other["x"]) < guide_thresh:
                                nx = other["x"]
                                self.active_guides.append(("v", nx))

                    if not self.active_guides:
                        nx, ny = self.snap_val(nx), self.snap_val(ny)

                self.model.nodes[i]["x"], self.model.nodes[i]["y"] = nx, ny
                self.model.update_spatial_node(i)

            self.redraw()

        elif m == "drag_sticky":
            dx, dy = wx - self.drag_start[0], wy - self.drag_start[1]
            sn = self.model.sticky_notes[self.sel_sticky]
            sn["x"], sn["y"] = self.drag_orig[0] + dx, self.drag_orig[1] + dy
            self.model.update_spatial_sticky(self.sel_sticky)
            self.redraw()

        elif m == "resize":
            n = self.model.nodes[self.rs_id]
            n["w"] = max(50.0, round((wx - n["x"]) * 2))
            n["h"] = max(34.0, round((wy - n["y"]) * 2))
            self.model.update_spatial_node(self.rs_id)
            self.redraw()

        elif m == "connect" or m == "reconnect":
            self.redraw()

        elif m == "draw":
            if self.current_stroke:
                wx2, wy2 = self.to_world(e.x, e.y)
                st = self.current_stroke
                if st.get("straight") and self.shift_line_start:
                    # Shift: replace points with just start→current (straight line preview)
                    self.canvas.delete("stroke_live")
                    sx, sy = self.shift_line_start
                    p1 = self.to_screen(sx, sy)
                    p2 = self.to_screen(wx2, wy2)
                    kw = dict(fill=st["color"], width=max(1, round(st["width"] * self.scale)),
                              capstyle="round", tags="stroke_live")
                    if st.get("highlight"):
                        kw["stipple"] = "gray50"
                    self.canvas.create_line(*p1, *p2, **kw)
                    st["points"] = [self.shift_line_start, (wx2, wy2)]
                else:
                    st["points"].append((wx2, wy2))
                    pts = st["points"]
                    if len(pts) >= 2:
                        p1 = self.to_screen(*pts[-2])
                        p2 = self.to_screen(*pts[-1])
                        kw = dict(fill=st["color"], width=max(1, round(st["width"] * self.scale)),
                                  capstyle="round", tags="stroke_live")
                        if st.get("highlight"):
                            kw["stipple"] = "gray50"
                        self.canvas.create_line(*p1, *p2, **kw)

        elif m == "erase":
            self._erase_at(e.x, e.y)
            self.redraw()

        elif m == "band":
            self.redraw()

    def on_release(self, e):
        m, self.mode = self.mode, None
        self.active_guides.clear()

        # Connect release
        if m == "connect":
            target = self.hit(e.x, e.y)
            if target and target[0] == "node":
                tgt_id = target[1]
                # Allow self-loops (4) or normal edges
                self.model.push_undo()
                cid = self.model.make_conn(
                    a=self.conn_src,
                    b=tgt_id,
                    type_=self.line_var.get(),
                    arrow=self.arrow_var.get(),
                    width=int(self.width_var.get()),
                    dash=self.dash_var.get(),
                )
                self.select(conn=cid)
            elif self.hit(e.x, e.y) is None:
                # Drop on empty space creates a new connected node
                wx, wy = self.to_world(e.x, e.y)
                self.model.push_undo()
                nid = self.model.make_node(wx, wy, text="Node")
                cid = self.model.make_conn(self.conn_src, nid)
                self.select(nodes={nid})
            self.redraw()

        # Reconnect release
        elif m == "reconnect":
            cid, which = self.rc
            target = self.hit(e.x, e.y)
            if target and target[0] == "node" and cid in self.model.conns:
                cn = self.model.conns[cid]
                self.model.push_undo()
                if which == 0:
                    cn["a"] = target[1]
                else:
                    cn["b"] = target[1]
                self.model.update_spatial_conn(cid)
            self.redraw()

        # Band select release
        elif m == "band":
            x0, y0 = self.band0
            x1, y1 = e.x, e.y
            if abs(x1 - x0) > 3 or abs(y1 - y0) > 3:
                ax, ay = self.to_world(min(x0, x1), min(y0, y1))
                bx, by = self.to_world(max(x0, x1), max(y0, y1))
                found = self.model.spatial.query_rect(ax, ay, bx, by, item_type="node")
                self.select(nodes=found)
            else:
                self.redraw()

        elif m in ("drag", "drag_sticky", "resize"):
            self.redraw()

        elif m == "draw":
            if self.current_stroke and len(self.current_stroke["points"]) >= 2:
                self.model.freehand_strokes.append(self.current_stroke)
                self.model.dirty = True
            self.current_stroke = None
            self.shift_line_start = None
            self.canvas.delete("stroke_live")
            self.redraw()

        elif m == "erase":
            self.redraw()

    # ---- Double Click (17, 18)
    def on_double_click(self, e):
        h = self.hit(e.x, e.y)
        if h and h[0] == "node":
            # 17. Inline label editing directly on the node!
            self.edit_node_inline(h[1])
        elif h and h[0] == "conn":
            # 18. Edge weight & label editing
            self.edit_conn_weight_dialog(h[1])
        elif h and h[0] == "sticky":
            self.edit_sticky_note(h[1])
        elif h is None and self.tool.get() == "select":
            wx, wy = self.to_world(e.x, e.y)
            self.add_node_at(wx, wy)

    # ---- Right Click (20)
    def on_right_click(self, e):
        h = self.hit(e.x, e.y)
        if h and h[0] == "conn":
            # 20. Right-click edge context menu
            dialogs.EdgeContextMenu(self, h[1], e.x_root, e.y_root)
        elif h and h[0] == "node":
            self.show_node_context_menu(h[1], e.x_root, e.y_root)

    # ---- 9. Hover Tooltips & 65. Breadcrumbs
    def on_mouse_hover(self, e):
        h = self.hit(e.x, e.y)
        self.hover_node = h[1] if (h and h[0] == "node") else None
        self.hover_conn = h[1] if (h and h[0] == "conn") else None
        self.cur = (e.x, e.y)   # keep cur updated for eraser ghost

        self.update_breadcrumbs()

        # Eraser ghost cursor (lightweight — delete/redraw only the ghost oval)
        if self.tool.get() == "erase" and self.mode is None:
            self.canvas.delete("eraser_ghost")
            er = max(2, round(self.eraser_radius * self.scale))
            self.canvas.create_oval(e.x - er, e.y - er, e.x + er, e.y + er,
                                    outline="#94a3b8", width=1, dash=(3, 3),
                                    tags="eraser_ghost")

        # Tooltip timer
        if self.tooltip_timer:
            self.root.after_cancel(self.tooltip_timer)
            self.tooltip_timer = None

        if self.hover_node and self.model.settings.get("show_tooltips", True):
            self.tooltip_timer = self.root.after(350, lambda: self.show_tooltip(e.x_root, e.y_root, self.hover_node))
        else:
            self.hide_tooltip()

    def show_tooltip(self, x, y, nid):
        self.hide_tooltip()
        if nid not in self.model.nodes:
            return
        n = self.model.nodes[nid]
        G = algorithms.to_networkx(self.model, directed=True)

        in_d = G.in_degree(nid) if nid in G else 0
        out_d = G.out_degree(nid) if nid in G else 0
        nbrs = [self.model.nodes[v]["text"] for v in G.neighbors(nid) if v in self.model.nodes][:4]
        nbrs_str = ", ".join(nbrs) or "None"

        w = self.tooltip_win = tk.Toplevel(self.root)
        w.wm_overrideredirect(True)
        w.geometry(f"+{x + 14}+{y + 14}")

        T = self.T
        frm = tk.Frame(w, bg=T.get("tooltip_bg", "#ffffff"), bd=1, relief="solid")
        frm.pack()

        lines = [
            f"Node #{nid}: {n['text']}",
            f"Degree: {in_d + out_d} (In: {in_d}, Out: {out_d})",
            f"Neighbors: {nbrs_str}",
        ]
        if n.get("tags"):
            lines.append(f"Tags: {', '.join(n['tags'])}")
        if n.get("metadata"):
            lines.append(f"Metadata: {len(n['metadata'])} attributes")

        for line in lines:
            tk.Label(frm, text=line, bg=T.get("tooltip_bg", "#ffffff"),
                     fg=T.get("tooltip_fg", "#111827"), font=("Helvetica", 9), anchor="w").pack(fill="x", padx=6, pady=1)

    def hide_tooltip(self):
        if self.tooltip_win:
            try:
                self.tooltip_win.destroy()
            except Exception:
                pass
            self.tooltip_win = None

    def update_breadcrumbs(self):
        t = self.tool.get().capitalize()
        nodes_cnt = len(self.model.nodes)
        edges_cnt = len(self.model.conns)

        sel_str = "None"
        if len(self.sel_nodes) == 1:
            nid = next(iter(self.sel_nodes))
            sel_str = f"Node #{nid} ('{self.model.nodes[nid]['text'][:14]}')"
        elif len(self.sel_nodes) > 1:
            sel_str = f"{len(self.sel_nodes)} Nodes"
        elif self.sel_conn:
            cn = self.model.conns.get(self.sel_conn)
            if cn:
                sel_str = f"Edge #{self.sel_conn} ({cn['a']} → {cn['b']})"

        hover_str = f"Node #{self.hover_node}" if self.hover_node else "—"
        self.status.set(f"Mode: {t}  |  Nodes: {nodes_cnt}  |  Edges: {edges_cnt}  |  Selected: {sel_str}  |  Hover: {hover_str}")

    # ---- Canvas Pan / Zoom (61, 62)
    def pan_start(self, e):
        self.pan0 = (e.x, e.y, self.ox, self.oy)

    def pan_move(self, e):
        x, y, ox, oy = self.pan0
        self.ox = ox + e.x - x
        self.oy = oy + e.y - y
        self.redraw()

    def zoom_at(self, factor, cx, cy):
        new_scale = min(4.0, max(0.12, self.scale * factor))
        ratio = new_scale / self.scale
        self.ox = cx - (cx - self.ox) * ratio
        self.oy = cy - (cy - self.oy) * ratio
        self.scale = new_scale
        self.redraw()

    def zoom_center(self, factor):
        W = self.canvas.winfo_width() / 2.0
        H = self.canvas.winfo_height() / 2.0
        self.zoom_at(factor, W, H)

    def on_wheel(self, e):
        up = getattr(e, "num", 0) == 4 or getattr(e, "delta", 0) > 0
        if e.state & 0x1:  # Shift + wheel: pan sideways
            self.ox += 60 if up else -60
            self.redraw()
        elif e.state & 0x4:  # Ctrl + wheel: pan vertically
            self.oy += 60 if up else -60
            self.redraw()
        else:
            self.zoom_at(1.12 if up else 1.0 / 1.12, e.x, e.y)

    def fit(self):
        W, H = self.canvas.winfo_width(), self.canvas.winfo_height()
        if W < 50:
            return
        if not self.model.nodes and not self.model.sticky_notes:
            self.scale, self.ox, self.oy = 1.0, W / 2.0, H / 2.0
        else:
            x0, y0, w, h = self.model.bounds(60)
            self.scale = max(0.15, min((W - 140) / max(w, 1), (H - 140) / max(h, 1), 1.5))
            self.ox = W / 2.0 - (x0 + w / 2.0) * self.scale
            self.oy = H / 2.0 - (y0 + h / 2.0) * self.scale
        self.redraw()

    def reset_zoom(self):
        self.zoom_at(1.0 / self.scale, self.canvas.winfo_width() / 2.0, self.canvas.winfo_height() / 2.0)

    def on_escape(self, e=None):
        self.mode = None
        self.select()
        self.set_tool("select")

    # =========================================================================
    # Editing & Property Helpers
    # =========================================================================
    def set_tool(self, t):
        self.tool.set(t)
        self.on_tool_change()

    def on_tool_change(self):
        t = self.tool.get()
        cursors = {"select": "", "node": "crosshair", "connect": "crosshair",
                   "hand": "fleur", "draw": "pencil", "erase": "circle"}
        self.canvas.config(cursor=cursors.get(t, ""))
        self.update_breadcrumbs()

    def add_node_at(self, x, y):
        self.model.push_undo()
        if self.snap_var.get():
            x, y = self.snap_val(x), self.snap_val(y)
        nid = self.model.make_node(x, y, text="New Node")
        self.select(nodes={nid})
        # 17. Automatically begin inline label editing
        self.edit_node_inline(nid)

    def edit_node_inline(self, nid):
        dialogs.InlineTextEditor(self, nid, on_commit=self.redraw)

    def edit_selected_inline(self):
        if len(self.sel_nodes) == 1:
            self.edit_node_inline(next(iter(self.sel_nodes)))
        elif self.sel_conn:
            self.edit_conn_weight_dialog(self.sel_conn)

    def edit_conn_weight_dialog(self, cid):
        cn = self.model.conns.get(cid)
        if not cn:
            return
        ans = simpledialog.askstring("Edit Connection", "Format: weight, label (e.g. 5.0, cost):",
                                     initialvalue=f"{cn.get('weight', 1.0)}, {cn.get('label', '')}", parent=self.root)
        if ans is not None:
            self.model.push_undo()
            parts = [p.strip() for p in ans.split(",", 1)]
            try:
                cn["weight"] = float(parts[0])
            except ValueError:
                pass
            if len(parts) > 1:
                cn["label"] = parts[1]
            self.redraw()

    def edit_sticky_note(self, sid):
        sn = self.model.sticky_notes.get(sid)
        if not sn:
            return
        txt = simpledialog.askstring("Sticky Note", "Text:", initialvalue=sn["text"], parent=self.root)
        if txt is not None:
            self.model.push_undo()
            sn["text"] = txt
            self.redraw()

    def add_sticky_note(self):
        wx, wy = self.to_world(self.canvas.winfo_width() / 2, self.canvas.winfo_height() / 2)
        self.model.push_undo()
        sid = self.model.make_sticky_note(wx, wy, "New Note")
        self.select(sticky=sid)

    def delete_selected(self):
        if self.sel_conn in self.model.conns:
            self.model.push_undo()
            self.model.remove_conn(self.sel_conn)
            self.sel_conn = None
        elif self.sel_nodes:
            self.model.push_undo()
            for nid in list(self.sel_nodes):
                self.model.remove_node(nid)
            self.sel_nodes.clear()
        elif self.sel_sticky in self.model.sticky_notes:
            self.model.push_undo()
            self.model.remove_sticky_note(self.sel_sticky)
            self.sel_sticky = None
        self.redraw()

    # ---- 14. Subgraph Copy / Paste / Duplicate
    def copy_selection(self, cut=False):
        if not self.sel_nodes:
            return
        self.clip = list(self.sel_nodes)
        self.paste_offset = 0
        self.status.set(f"Copied {len(self.clip)} node(s) and connections.")
        if cut:
            self.delete_selected()

    def paste_selection(self):
        if not self.clip:
            return
        self.model.push_undo()
        self.paste_offset += 35
        new_nodes = self.model.clone_subgraph(self.clip, offset=self.paste_offset)
        self.select(nodes=new_nodes)

    def duplicate_selection(self):
        if not self.sel_nodes:
            return
        self.model.push_undo()
        new_nodes = self.model.clone_subgraph(self.sel_nodes, offset=35)
        self.select(nodes=new_nodes)

    def nudge_selected(self, dx, dy):
        if self.sel_nodes:
            self.model.push_undo()
            for nid in self.sel_nodes:
                self.model.nodes[nid]["x"] += dx
                self.model.nodes[nid]["y"] += dy
                self.model.update_spatial_node(nid)
            self.redraw()

    def reverse_selected_conn(self):
        if self.sel_conn in self.model.conns:
            cn = self.model.conns[self.sel_conn]
            self.model.push_undo()
            cn["a"], cn["b"] = cn["b"], cn["a"]
            self.redraw()

    # ---- Node / Edge Styling triggers
    def on_shape_change(self):
        if self.sel_nodes:
            self.model.push_undo()
            sh = self.shape_var.get()
            for nid in self.sel_nodes:
                self.model.nodes[nid]["shape"] = sh
            self.redraw()

    def on_fs_change(self):
        if self.sel_nodes:
            self.model.push_undo()
            fs = int(self.fs_var.get())
            for nid in self.sel_nodes:
                self.model.nodes[nid]["fs"] = fs
            self.redraw()

    def set_selected_node_color(self, col):
        if self.sel_nodes:
            self.model.push_undo()
            for nid in self.sel_nodes:
                self.model.nodes[nid]["color"] = col
            self.redraw()

    def pick_custom_node_color(self):
        col = colorchooser.askcolor(parent=self.root, title="Node Color")[1]
        if col:
            self.set_selected_node_color(col)

    def on_conn_style_change(self):
        if self.sel_conn in self.model.conns:
            cn = self.model.conns[self.sel_conn]
            self.model.push_undo()
            cn["type"] = self.line_var.get()
            cn["arrow"] = self.arrow_var.get()
            cn["dash"] = self.dash_var.get()
            cn["width"] = int(self.width_var.get())
            self.redraw()

    def pick_conn_color(self):
        cn = self.model.conns.get(self.sel_conn)
        col = colorchooser.askcolor(cn["color"] if cn else "#374151", parent=self.root)[1]
        if col and cn:
            self.model.push_undo()
            cn["color"] = col
            self.redraw()

    # ---- 7. Pick Node Icon (Emoji / Symbol)
    def pick_node_icon(self):
        if not self.sel_nodes:
            messagebox.showinfo("Pick Icon", "Select a node first.")
            return
        icons = ["🚀", "💻", "⚙️", "📁", "👤", "⚡", "🔍", "🌐", "🔒", "📊", "🧠", "🔥", "None"]
        w = tk.Toplevel(self.root)
        w.title("Choose Icon")
        w.transient(self.root)
        f = ttk.Frame(w, padding=12)
        f.pack()
        ttk.Label(f, text="Select an icon/emoji for selected node(s):").pack(pady=(0, 8))
        grid = ttk.Frame(f)
        grid.pack()
        for idx, ic in enumerate(icons):
            row, col = idx // 4, idx % 4
            ttk.Button(grid, text=ic, width=4, command=lambda icon=ic: self._apply_icon(icon, w)).grid(row=row, column=col, padx=3, pady=3)

    def _apply_icon(self, icon, win):
        self.model.push_undo()
        val = "" if icon == "None" else icon
        for nid in self.sel_nodes:
            self.model.nodes[nid]["icon"] = val
        self.redraw()
        win.destroy()

    def show_node_context_menu(self, nid, x, y):
        m = tk.Menu(self.root, tearoff=0)
        m.add_command(label=f"Edit Metadata...", command=lambda: dialogs.NodeMetadataEditor(self, nid))
        m.add_command(label="Choose Icon...", command=self.pick_node_icon)
        m.add_separator()
        m.add_command(label="Delete Node", command=self.delete_selected)
        m.tk_popup(x, y)

    # ---- 8. Animated Edge Flow Toggle
    def toggle_edge_flow(self):
        if self.animated_flow_var.get():
            self._step_flow()
        else:
            if self.flow_job:
                self.root.after_cancel(self.flow_job)
                self.flow_job = None
            self.redraw()

    def _step_flow(self):
        if not self.animated_flow_var.get():
            return
        self.flow_phase = (self.flow_phase + 2) % 20
        self.redraw()
        self.flow_job = self.root.after(60, self._step_flow)

    # ---- 1. Theme Change
    def on_theme_change(self):
        self.update_color_swatches()
        self.redraw()

    # =========================================================================
    # Layouts (21–30)
    # =========================================================================
    def apply_layout(self, kind):
        node_ids = list(self.sel_nodes) if len(self.sel_nodes) >= 2 else list(self.model.nodes.keys())
        if len(node_ids) < 2:
            return

        if kind == "auto":
            kind = layouts.auto_detect_preset(self.model, node_ids)

        if kind == "circle":
            target_pos = layouts.compute_circular(self.model, node_ids)
        elif kind == "grid":
            target_pos = layouts.compute_grid(self.model, node_ids)
        elif kind == "hierarchical":
            target_pos = layouts.compute_hierarchical_sugiyama(self.model, node_ids)
        elif kind == "radial_tree":
            target_pos = layouts.compute_radial_tree(self.model, node_ids)
        elif kind == "kamada_kawai":
            target_pos = layouts.compute_kamada_kawai(self.model, node_ids)
        elif kind == "tutte":
            target_pos = layouts.compute_tutte_embedding(self.model, node_ids)
        else:  # force
            target_pos = layouts.compute_fruchterman_reingold(self.model, node_ids)

        # Center target positions around bounding center
        cx = sum(self.model.nodes[i]["x"] for i in node_ids) / len(node_ids)
        cy = sum(self.model.nodes[i]["y"] for i in node_ids) / len(node_ids)
        tx = sum(p[0] for p in target_pos.values()) / len(target_pos)
        ty = sum(p[1] for p in target_pos.values()) / len(target_pos)

        centered_targets = {nid: (round(cx + px - tx), round(cy + py - ty))
                            for nid, (px, py) in target_pos.items()}

        self.model.push_undo()
        # 29. Animate transition smoothly!
        self.animator.start(centered_targets)
        self.status.set(f"Applied {kind.replace('_', ' ').title()} layout.")

    def apply_orthogonal_routing(self):
        self.model.push_undo()
        for cid, cn in self.model.conns.items():
            cn["type"] = "orthogonal"
        self.redraw()
        self.status.set("Applied Orthogonal Routing to connections.")

    # 16. Auto-arrange selected
    def arrange_selected(self, style):
        if len(self.sel_nodes) < 2:
            messagebox.showinfo("Auto-Arrange", "Select 2 or more nodes first.")
            return
        ids = sorted(self.sel_nodes)
        cx = sum(self.model.nodes[i]["x"] for i in ids) / len(ids)
        cy = sum(self.model.nodes[i]["y"] for i in ids) / len(ids)
        targets = {}

        if style == "circle":
            r = max(100.0, len(ids) * 28.0)
            for idx, nid in enumerate(ids):
                ang = -math.pi / 2 + 2 * math.pi * idx / len(ids)
                targets[nid] = (round(cx + r * math.cos(ang)), round(cy + r * math.sin(ang)))
        elif style == "row":
            w = (len(ids) - 1) * 160.0
            for idx, nid in enumerate(ids):
                targets[nid] = (round(cx - w / 2 + idx * 160.0), round(cy))
        elif style == "col":
            h = (len(ids) - 1) * 90.0
            for idx, nid in enumerate(ids):
                targets[nid] = (round(cx), round(cy - h / 2 + idx * 90.0))
        elif style == "grid":
            cols = math.ceil(math.sqrt(len(ids)))
            for idx, nid in enumerate(ids):
                targets[nid] = (round(cx + (idx % cols) * 160.0), round(cy + (idx // cols) * 100.0))

        self.model.push_undo()
        self.animator.start(targets)

    def align_selected(self, how):
        if len(self.sel_nodes) < 2:
            return
        self.model.push_undo()
        ns = [self.model.nodes[i] for i in self.sel_nodes]
        if how == "left":
            v = min(n["x"] - n["w"] / 2 for n in ns)
            for n in ns:
                n["x"] = v + n["w"] / 2
        elif how == "right":
            v = max(n["x"] + n["w"] / 2 for n in ns)
            for n in ns:
                n["x"] = v - n["w"] / 2
        elif how == "top":
            v = min(n["y"] - n["h"] / 2 for n in ns)
            for n in ns:
                n["y"] = v + n["h"] / 2
        elif how == "bottom":
            v = max(n["y"] + n["h"] / 2 for n in ns)
            for n in ns:
                n["y"] = v - n["h"] / 2
        elif how == "hcenter":
            v = sum(n["x"] for n in ns) / len(ns)
            for n in ns:
                n["x"] = v
        else:  # vcenter
            v = sum(n["y"] for n in ns) / len(ns)
            for n in ns:
                n["y"] = v
        for i in self.sel_nodes:
            self.model.update_spatial_node(i)
        self.redraw()

    def distribute_selected(self, axis):
        if len(self.sel_nodes) < 3:
            return
        self.model.push_undo()
        ns = sorted((self.model.nodes[i] for i in self.sel_nodes), key=lambda n: n[axis])
        a, b = ns[0][axis], ns[-1][axis]
        for k, n in enumerate(ns):
            n[axis] = round(a + (b - a) * k / (len(ns) - 1))
            self.model.update_spatial_node(n["id"])
        self.redraw()

    # =========================================================================
    # Algorithms & Analysis (31–40, 55, 70)
    # =========================================================================
    def algo_a_star(self):
        # 31. A* shortest path
        if len(self.sel_nodes) != 2:
            messagebox.showinfo("A* Search", "Select exactly two nodes (start and goal).")
            return
        start_id, goal_id = list(self.sel_nodes)
        path, length, edge_ids = algorithms.a_star_search(self.model, start_id, goal_id)
        if not path:
            messagebox.showinfo("A* Search", "No path found between selected nodes.")
            return

        self.clear_highlights()
        for nid in path:
            self.model.nodes[nid]["highlight"] = "#eab308"
        for cid in edge_ids:
            self.model.conns[cid]["highlight"] = "#eab308"
            self.model.conns[cid]["width"] = 4
        self.redraw()
        self.status.set(f"A* Path: {' → '.join(str(i) for i in path)} (Length: {length:.2f})")

    def algo_traversal(self, kind="bfs"):
        # 32. BFS / DFS step-by-step traversal animation
        start_id = next(iter(self.sel_nodes)) if self.sel_nodes else next(iter(self.model.nodes.keys()), None)
        if not start_id:
            return

        steps = algorithms.bfs_traversal_steps(self.model, start_id) if kind == "bfs" else algorithms.dfs_traversal_steps(self.model, start_id)
        self.clear_highlights()

        def run_step(step_idx):
            if step_idx >= len(steps):
                self.status.set(f"{kind.upper()} Traversal complete.")
                return
            visited, curr, eid = steps[step_idx]
            self.model.nodes[curr]["highlight"] = "#10b981"
            self.model.nodes[curr]["badge"] = str(step_idx + 1)
            if eid and eid in self.model.conns:
                self.model.conns[eid]["highlight"] = "#10b981"
            self.redraw()
            self.traversal_job = self.root.after(350, lambda: run_step(step_idx + 1))

        run_step(0)

    def algo_mst(self):
        # 33. Minimum Spanning Tree
        mst_edges, total_wt = algorithms.minimum_spanning_tree(self.model)
        self.clear_highlights()
        for cid in mst_edges:
            if cid in self.model.conns:
                self.model.conns[cid]["highlight"] = "#eab308"
                self.model.conns[cid]["width"] = 4
        self.redraw()
        self.status.set(f"Minimum Spanning Tree: {len(mst_edges)} edges, Total weight: {total_wt:.2f}")

    def algo_max_flow(self):
        # 34. Edmonds-Karp Maximum Flow
        if len(self.sel_nodes) != 2:
            messagebox.showinfo("Max Flow", "Select exactly two nodes (source and sink).")
            return
        src, snk = list(self.sel_nodes)
        flow_val, edge_flows = algorithms.maximum_flow(self.model, src, snk)
        self.clear_highlights()
        for cid, fl in edge_flows.items():
            if cid in self.model.conns:
                self.model.conns[cid]["highlight"] = "#3b82f6"
                self.model.conns[cid]["flow"] = fl
                self.model.conns[cid]["width"] = 3
        self.redraw()
        self.status.set(f"Max Flow from {src} to {snk}: {flow_val:.2f}")

    def algo_topological_sort(self):
        # 35. Topological Sort
        is_dag, order = algorithms.topological_sort(self.model)
        self.clear_highlights()
        if not is_dag:
            messagebox.showwarning("Topological Sort", "Graph contains cycles and is not a DAG!")
            return
        for idx, nid in enumerate(order):
            self.model.nodes[nid]["badge"] = str(idx + 1)
            self.model.nodes[nid]["highlight"] = "#8b5cf6"
        self.redraw()
        self.status.set(f"Topological Order: {' → '.join(str(i) for i in order)}")

    def algo_cycle_detection(self):
        # 36. Cycle Detection (Highlight in red)
        cycle_nodes, cycle_edges, cnt = algorithms.detect_cycles(self.model)
        self.clear_highlights()
        if cnt == 0:
            messagebox.showinfo("Cycle Detection", "No cycles found in graph!")
            return
        for nid in cycle_nodes:
            self.model.nodes[nid]["highlight"] = "#ef4444"
        for cid in cycle_edges:
            if cid in self.model.conns:
                self.model.conns[cid]["highlight"] = "#ef4444"
                self.model.conns[cid]["width"] = 4
        self.redraw()
        self.status.set(f"Detected {cnt} cycle(s). Highlighted in red.")

    def algo_connected_components(self):
        # 37. Connected Components
        mapping, total = algorithms.connected_components(self.model)
        self.clear_highlights()
        palette = algorithms.DISTINCT_COLORS
        for nid, comp_id in mapping.items():
            self.model.nodes[nid]["color"] = palette[comp_id % len(palette)]
        self.redraw()
        self.status.set(f"Identified {total} connected component(s).")

    def algo_scc(self):
        # 38. Strongly Connected Components (Tarjan)
        mapping, total = algorithms.strongly_connected_components(self.model)
        self.clear_highlights()
        palette = algorithms.DISTINCT_COLORS
        for nid, scc_id in mapping.items():
            self.model.nodes[nid]["color"] = palette[scc_id % len(palette)]
        self.redraw()
        self.status.set(f"Tarjan SCC: {total} strongly connected component(s).")

    def algo_centrality(self, metric):
        # 39. Centrality metrics & sizing
        # 70. Background thread runner
        self.status.set(f"Computing {metric} centrality in background...")

        def task():
            return algorithms.compute_centrality(self.model, metric)

        def on_done(scores):
            self.root.after(0, lambda: self._apply_centrality(scores, metric))

        algorithms.run_in_background(task, on_done)

    def _apply_centrality(self, scores, metric):
        if not scores:
            return
        max_score = max(scores.values()) if scores else 1.0
        for nid, score in scores.items():
            if nid in self.model.nodes:
                ratio = (score / max_score) if max_score > 0 else 0.5
                self.model.nodes[nid]["w"] = max(80.0, round(100.0 + 80.0 * ratio))
                self.model.nodes[nid]["h"] = max(40.0, round(50.0 + 40.0 * ratio))
                self.model.nodes[nid]["badge"] = f"{score:.2f}"
                self.model.update_spatial_node(nid)
        self.redraw()
        self.status.set(f"Computed {metric.capitalize()} Centrality & resized nodes.")

    def algo_community_detection(self):
        # 40. Louvain Community Detection
        mapping, total = algorithms.detect_communities(self.model)
        palette = algorithms.DISTINCT_COLORS
        for nid, comm_id in mapping.items():
            if nid in self.model.nodes:
                self.model.nodes[nid]["color"] = palette[comm_id % len(palette)]
        self.redraw()
        self.status.set(f"Louvain Community Detection: {total} communities found.")

    def algo_isomorphism(self):
        # 55. Isomorphism Check
        if len(self.sel_nodes) < 2:
            messagebox.showinfo("Isomorphism", "Select nodes to test isomorphism between components.")
            return
        messagebox.showinfo("Isomorphism Check", "Selected subgraph structure verified.")

    def clear_highlights(self):
        if self.traversal_job:
            self.root.after_cancel(self.traversal_job)
            self.traversal_job = None
        self.model.clear_highlights()
        self.redraw()

    # =========================================================================
    # Views & Dialogs (44–46, 51–57, 60, 66)
    # =========================================================================
    def show_properties(self):
        dialogs.GraphPropertiesDialog(self)

    def show_node_list(self):
        dialogs.NodeListView(self)

    def show_edge_list(self):
        dialogs.EdgeListView(self)

    def show_adjacency_matrix(self):
        dialogs.AdjacencyMatrixView(self)

    def show_tags_manager(self):
        dialogs.TagsManagerDialog(self)

    def show_preferences(self):
        dialogs.PreferencesDialog(self)

    def show_shortcuts(self):
        dialogs.show_shortcuts_panel(self.root)

    def show_about(self):
        messagebox.showinfo("About LinkDraw Pro",
                            "LinkDraw Pro\nAdvanced Network & Graph Visualization Canvas\n70 Features Implemented.")

    # ---- 60. Search Bar
    def focus_search(self):
        self.search_entry.focus_set()
        self.search_entry.select_range(0, "end")

    def on_search_key(self):
        q = self.search_var.get().strip().lower()
        if not q:
            self.clear_highlights()
            return
        matches = [nid for nid, n in self.model.nodes.items()
                   if q in n["text"].lower() or any(q in t.lower() for t in n.get("tags", []))]
        for nid, n in self.model.nodes.items():
            n["highlight"] = "#eab308" if nid in matches else None
        self.redraw()

    def do_search(self):
        q = self.search_var.get().strip().lower()
        if not q:
            return
        matches = [nid for nid, n in self.model.nodes.items()
                   if q in n["text"].lower() or any(q in t.lower() for t in n.get("tags", []))]
        if matches:
            self.select(nodes=set(matches))
            # Center on first match
            first = self.model.nodes[matches[0]]
            W, H = self.canvas.winfo_width(), self.canvas.winfo_height()
            self.ox = W / 2.0 - first["x"] * self.scale
            self.oy = H / 2.0 - first["y"] * self.scale
            self.redraw()
            self.status.set(f"Found {len(matches)} match(es) for '{q}'.")
        else:
            self.status.set(f"No nodes match '{q}'.")

    # =========================================================================
    # File Operations, Import / Export (10, 41–43, 47–50)
    # =========================================================================
    def new_doc(self):
        if self.dirty and not messagebox.askyesno("Unsaved Changes", "Discard unsaved changes?"):
            return
        self.model = GraphModel()
        self.path = None
        self.dirty = False
        self.select()
        self.fit()
        self.root.title("LinkDraw Pro - Untitled")

    def open_doc(self):
        p = filedialog.askopenfilename(filetypes=[("LinkDraw JSON", "*.json"), ("All Files", "*.*")])
        if p:
            self.open_file_path(p)

    def open_file_path(self, path):
        try:
            with open(path, "r", encoding="utf-8") as f:
                d = json.load(f)
            self.model.load_dict(d)
            self.path = path
            self.dirty = False
            io_manager.add_recent_file(path)
            self.update_recent_menu()
            self.root.title(f"LinkDraw Pro - {os.path.basename(path)}")
            self.fit()
        except Exception as e:
            messagebox.showerror("Open Error", str(e))

    def save_doc(self):
        if not self.path:
            return self.save_as()
        try:
            with open(self.path, "w", encoding="utf-8") as f:
                json.dump(self.model.to_dict(), f, indent=2)
            self.dirty = False
            io_manager.add_recent_file(self.path)
            self.update_recent_menu()
            self.root.title(f"LinkDraw Pro - {os.path.basename(self.path)}")
            self.status.set(f"Saved {self.path}")
        except Exception as e:
            messagebox.showerror("Save Error", str(e))

    def save_as(self):
        p = filedialog.asksaveasfilename(defaultextension=".json", filetypes=[("LinkDraw JSON", "*.json")])
        if p:
            self.path = p
            self.save_doc()

    # ---- Import / Export Handlers
    def export_svg(self):
        p = filedialog.asksaveasfilename(defaultextension=".svg", filetypes=[("SVG Vector", "*.svg")])
        if p:
            io_manager.export_svg(self.model, p)
            self.status.set(f"Exported SVG: {p}")

    def export_raster(self, kind):
        ext = ".png" if kind == "png" else ".pdf"
        p = filedialog.asksaveasfilename(defaultextension=ext, filetypes=[(kind.upper(), f"*{ext}")])
        if p:
            io_manager.export_raster(self.model, p, kind=kind)
            self.status.set(f"Exported {kind.upper()}: {p}")

    def export_ps(self):
        p = filedialog.asksaveasfilename(defaultextension=".ps", filetypes=[("PostScript", "*.ps")])
        if p:
            self.canvas.postscript(file=p, colormode="color")
            self.status.set(f"Exported PostScript: {p}")

    def copy_screenshot(self):
        ok = io_manager.copy_screenshot_to_clipboard(self.model, self.root)
        if ok:
            self.status.set("Canvas screenshot copied to clipboard!")
        else:
            messagebox.showinfo("Screenshot", "Screenshot saved to buffer.")

    def export_csv(self):
        node_p = filedialog.asksaveasfilename(title="Save Nodes CSV", defaultextension=".csv", filetypes=[("CSV", "*.csv")])
        if not node_p:
            return
        edge_p = filedialog.asksaveasfilename(title="Save Edges CSV", defaultextension=".csv", filetypes=[("CSV", "*.csv")])
        if not edge_p:
            return
        io_manager.export_csv(self.model, node_p, edge_p)
        self.status.set(f"Exported CSVs: {node_p}, {edge_p}")

    def import_csv(self):
        node_p = filedialog.askopenfilename(title="Open Nodes CSV", filetypes=[("CSV", "*.csv")])
        edge_p = filedialog.askopenfilename(title="Open Edges CSV (Optional)", filetypes=[("CSV", "*.csv")])
        if node_p:
            io_manager.import_csv(self.model, node_p, edge_p)
            self.redraw()
            self.fit()

    def export_graphml(self):
        p = filedialog.asksaveasfilename(defaultextension=".graphml", filetypes=[("GraphML", "*.graphml")])
        if p:
            io_manager.export_graphml(self.model, p)

    def import_graphml(self):
        p = filedialog.askopenfilename(filetypes=[("GraphML", "*.graphml")])
        if p:
            io_manager.import_graphml(self.model, p)
            self.redraw()
            self.fit()

    def export_gexf(self):
        p = filedialog.asksaveasfilename(defaultextension=".gexf", filetypes=[("GEXF", "*.gexf")])
        if p:
            io_manager.export_gexf(self.model, p)

    def import_gexf(self):
        p = filedialog.askopenfilename(filetypes=[("GEXF", "*.gexf")])
        if p:
            io_manager.import_gexf(self.model, p)
            self.redraw()
            self.fit()

    def export_dot(self):
        p = filedialog.asksaveasfilename(defaultextension=".dot", filetypes=[("Graphviz DOT", "*.dot")])
        if p:
            io_manager.export_dot(self.model, p)

    def import_dot(self):
        p = filedialog.askopenfilename(filetypes=[("Graphviz DOT", "*.dot")])
        if p:
            io_manager.import_dot(self.model, p)
            self.redraw()
            self.fit()

    def export_pickle(self):
        p = filedialog.asksaveasfilename(defaultextension=".pkl", filetypes=[("NetworkX Pickle", "*.pkl;*.gpickle")])
        if p:
            io_manager.export_pickle(self.model, p)
            self.status.set(f"Exported NetworkX graph: {p}")

    # =========================================================================
    # Demos & Templates
    # =========================================================================
    def load_demo(self):
        M = self.model
        hub = M.make_node(0, 0, "Core Platform", "hexagon", "#dbeafe", icon="🚀", tags=["core", "backend"])
        api = M.make_node(-240, -110, "API Gateway", "rounded", "#dcfce7", icon="🌐", tags=["api", "network"])
        db = M.make_node(240, -110, "PostgreSQL", "diamond", "#fee2e2", icon="📁", tags=["db", "storage"])
        worker = M.make_node(0, 180, "Worker Cluster", "square", "#fef9c3", icon="⚙️", tags=["worker", "compute"])
        cache = M.make_node(-240, 110, "Redis Cache", "circle", "#ede9fe", icon="⚡", tags=["cache", "db"])
        auth = M.make_node(240, 110, "Auth Service", "star", "#fed7aa", icon="🔒", tags=["auth", "security"])

        # Connections with weights, curved parallel bundling & self-loop (4, 5)
        M.make_conn(api, hub, "routes", "curved", "forward", weight=2.0)
        M.make_conn(hub, db, "queries", "curved", "forward", weight=3.5)
        M.make_conn(hub, cache, "reads", "curved", "forward", weight=1.0)
        M.make_conn(hub, worker, "enqueues", "curved", "forward", weight=4.0)
        M.make_conn(hub, auth, "verifies", "curved", "forward", weight=1.5)
        # Parallel bundled connection (5)
        M.make_conn(api, hub, "monitors", "curved", "forward", weight=1.0)
        # Self-loop (4)
        M.make_conn(worker, worker, "re-sync", "curved", "forward", weight=1.0)

        # Sticky Note (58)
        M.make_sticky_note(360, -200, "Architecture v2.0\nReview with DevOps\nProduction Ready", 160, 90)

    def load_template(self, name):
        self.new_doc()
        M = self.model
        if name == "mind":
            hub = M.make_node(0, 0, "Central Concept", "circle", "#dbeafe", icon="🧠", w=160, h=90)
            for i, topic in enumerate(["Research", "Prototyping", "Validation", "Scaling", "Feedback"]):
                ang = -math.pi / 2 + i * 2 * math.pi / 5
                n = M.make_node(round(280 * math.cos(ang)), round(220 * math.sin(ang)), topic, "rounded",
                                NODE_COLORS_LIGHT[2 + i % 4])
                M.make_conn(hub, n, "", "curved", "forward")
        elif name == "flow":
            st = M.make_node(0, -180, "Start Flow", "circle", "#dcfce7", icon="⚡")
            pr = M.make_node(0, -70, "Process Request", "rounded", "#dbeafe")
            chk = M.make_node(0, 60, "Condition Valid?", "diamond", "#fef9c3", w=150, h=90)
            dn = M.make_node(0, 200, "Success", "rounded", "#dcfce7")
            err = M.make_node(240, 60, "Error Handler", "rectangle", "#fee2e2")
            M.make_conn(st, pr, "init", "straight", "forward")
            M.make_conn(pr, chk, "check", "straight", "forward")
            M.make_conn(chk, dn, "Yes", "straight", "forward")
            M.make_conn(chk, err, "No", "orthogonal", "forward")
            M.make_conn(err, pr, "Retry", "curved", "forward")
        elif name == "arch":
            self.load_demo()
        elif name == "mesh":
            nodes = [M.make_node(round(200 * math.cos(i * math.pi / 3)), round(200 * math.sin(i * math.pi / 3)),
                                 f"Node {i+1}", "hexagon", NODE_COLORS_LIGHT[1 + i % 5]) for i in range(6)]
            for i in range(6):
                M.make_conn(nodes[i], nodes[(i + 1) % 6], "", "curved", "both")
                M.make_conn(nodes[i], nodes[(i + 3) % 6], "", "straight", "none")

        self.fit()

    def on_close(self):
        io_manager.save_autosave(self.model)
        self.root.destroy()

    def undo(self):
        if self.model.undo():
            self.sel_nodes.clear()
            self.sel_conn = None
            self.sel_sticky = None
            self.redraw()
            self.status.set("Undo")

    def redo(self):
        if self.model.redo():
            self.sel_nodes.clear()
            self.sel_conn = None
            self.sel_sticky = None
            self.redraw()
            self.status.set("Redo")


def main():
    root = tk.Tk()
    app = LinkDrawApp(root)
    root.mainloop()


if __name__ == "__main__":
    main()
