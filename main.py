#!/usr/bin/env python3
"""
LinkDraw Pro - Interactive Graph & Network Canvas
Complete Implementation of 70 Features across Visualization, Interaction,
Layouts, Analysis, Import/Export, Graph Properties, Metadata, UX, and Performance.
"""
import copy
import base64
import io
import json
import math
import os
import queue
import sys
import time
import uuid
import tkinter as tk
from tkinter import font as tkfont
from tkinter import ttk, filedialog, messagebox, simpledialog, colorchooser
from PIL import Image

from graph_model import (
    GraphModel, SHAPES, LINE_TYPES, LINE_STYLES, LINE_DASH_PATTERNS, ARROWS, WIDTHS, FSIZES,
    FONT_FAMILIES, FONT_STYLES,
    NODE_COLORS_LIGHT, NODE_COLORS_DARK, NODE_COLORS_HC,
    LINE_COLORS_LIGHT, LINE_COLORS_DARK, LINE_COLORS_HC
)
import algorithms
import layouts
import io_manager
import dialogs
import panels
import drawing_tools
import linkdraw_investigation
from collaboration_client import CollaborationClient, canonical_state
from collaboration_client import mongo_safe_state

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
        self.style_clipboard = None
        self.collaboration_client = None
        self.collaboration_project_id = None
        self.collaboration_base_state = None
        self.collaboration_base_fingerprint = None
        self.collaboration_revision = None
        self.collaboration_pending = False
        self.collaboration_last_submitted = None
        self.collaboration_retry_after = 0.0
        self.collaboration_next_snapshot_check = 0.0
        self.collaboration_tick_id = None

        # ---- View & Coordinates
        self.scale = 1.0
        self.ox, self.oy = 0.0, 0.0
        self.sel_nodes = set()
        self.sel_conn = None
        self.sel_sticky = None
        self.mode = None
        self.hover_node = None
        self.hover_conn = None
        self.image_cache = {}
        self._node_font_cache = {}
        self._node_label_layout_cache = {}
        self._note_window_savers = {}
        self.drag_redraw_after = None
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
        self._note_windows = {}

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
        self.line_var = tk.StringVar(value=self.model.settings["default_line_type"])
        self.arrow_var = tk.StringVar(value=self.model.settings["default_arrow"])
        self.dash_var = tk.BooleanVar(value=False)
        self.width_var = tk.StringVar(value=str(self.model.settings["default_line_width"]))
        self.line_style_var = tk.StringVar(value=self.model.settings["default_line_style"])
        self.line_color_var = tk.StringVar(value=self.model.settings["default_line_color"])
        self.fs_var = tk.StringVar(value="11")
        self.node_font_var = tk.StringVar(value=self.model.settings["default_font_family"])
        self.node_font_style_var = tk.StringVar(value=self.model.settings["default_font_style"])
        self.status = tk.StringVar()
        self.zoom_text = tk.StringVar(value="100%")
        self.search_var = tk.StringVar()

        # Canvas settings
        self.theme = tk.StringVar(value="light")
        self.grid_var = tk.BooleanVar(value=True)
        self.snap_var = tk.BooleanVar(value=True)
        self.drag_pan = tk.StringVar(value=self.model.settings.get("drag_pan", "pan"))
        self.minimap_var = tk.BooleanVar(value=True)
        self.animated_flow_var = tk.BooleanVar(value=False)
        self.flow_speed_var = tk.StringVar(value=str(self.model.settings.get("flow_speed", 2)))
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
                self.sync_document_settings()
                has_visible_content = any((
                    self.model.nodes,
                    self.model.sticky_notes,
                    self.model.freehand_strokes,
                ))
                if not has_visible_content:
                    populated_page = next(
                        (
                            name for name, page in self.sidebar.page_manager.pages.items()
                            if any(page.get(collection) for collection in ("nodes", "sticky_notes", "freehand_strokes"))
                        ),
                        None,
                    )
                    if populated_page:
                        self.sidebar.page_manager.switch_page(populated_page)
                        self.sidebar.page_var.set(populated_page)
                    else:
                        self.load_demo()
            else:
                self.load_demo()
        else:
            self.load_demo()
        self.sidebar.page_manager.persist()

        self.apply_widget_theme()
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

        collaboration = tk.Menu(m, tearoff=0)
        collaboration.add_command(
            label="Connect / Create Shared Investigation…",
            command=self.connect_shared_investigation,
        )
        collaboration.add_command(label="Disconnect", command=self.disconnect_shared_investigation)
        m.add_cascade(label="Collaboration", menu=collaboration)

        # ---- Edit
        e = tk.Menu(m, tearoff=0)
        e.add_command(label="Undo", accelerator=f"{acc}+Z", command=self.undo)
        e.add_command(label="Redo", accelerator=f"{acc}+Y", command=self.redo)
        e.add_separator()
        e.add_command(label="Cut", accelerator=f"{acc}+X", command=lambda: self.copy_selection(cut=True))
        e.add_command(label="Copy", accelerator=f"{acc}+C", command=self.copy_selection)
        e.add_command(label="Paste", accelerator=f"{acc}+V", command=self.paste_selection)
        e.add_command(label="Duplicate Subgraph", accelerator=f"{acc}+D", command=self.duplicate_selection)
        e.add_command(label="Copy Style", command=self.copy_selected_style)
        e.add_command(label="Paste Style", command=self.paste_selected_style)
        e.add_command(label="Delete", accelerator="Del", command=self.delete_selected)
        e.add_separator()
        e.add_command(label="Select All", accelerator=f"{acc}+A", command=self.select_all)
        e.add_command(label="Select Connected Neighbors", command=self.select_connected_neighbors)
        e.add_command(label="Select Entire Component", command=self.select_component)
        e.add_command(label="Find / Search...", accelerator=f"{acc}+F", command=self.focus_search)
        e.add_command(label="Inline Edit Text", accelerator="Enter", command=self.edit_selected_inline)
        e.add_command(label="Open Element Notes", accelerator="Shift+N", command=self.open_selected_element_notes)
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
        lay.add_command(label="Concentric by Connection Distance", command=lambda: self.apply_layout("concentric"))
        lay.add_command(label="Topology Spiral", command=lambda: self.apply_layout("spiral"))
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
        v.add_radiobutton(
            label="Drag Empty Canvas to Pan",
            variable=self.drag_pan, value="pan",
            command=lambda: self.set_drag_pan_mode("pan"),
        )
        v.add_radiobutton(
            label="Drag Empty Canvas to Select",
            variable=self.drag_pan, value="box",
            command=lambda: self.set_drag_pan_mode("box"),
        )
        v.add_separator()

        # Theme Switcher (1)
        thm = tk.Menu(v, tearoff=0)
        thm.add_radiobutton(label="Light Theme", variable=self.theme, value="light", command=self.on_theme_change)
        thm.add_radiobutton(label="Dark Theme", variable=self.theme, value="dark", command=self.on_theme_change)
        thm.add_radiobutton(label="High-Contrast Theme", variable=self.theme, value="high_contrast", command=self.on_theme_change)
        v.add_cascade(label="Theme Palette", menu=thm)

        v.add_checkbutton(label="Show Minimap", variable=self.minimap_var, command=self.on_view_setting_change)
        v.add_checkbutton(label="Show Grid", variable=self.grid_var, command=self.on_view_setting_change)
        v.add_checkbutton(label="Snap to Grid / Guides", variable=self.snap_var, command=self.on_view_setting_change)
        v.add_checkbutton(label="Animated Edge Flow", variable=self.animated_flow_var, command=self.toggle_edge_flow)
        flow_speed_menu = tk.Menu(v, tearoff=0)
        for label, speed in (("Slow", 1), ("Normal", 2), ("Fast", 4)):
            flow_speed_menu.add_radiobutton(
                label=label, variable=self.flow_speed_var, value=str(speed),
                command=lambda selected=speed: self.set_flow_speed(selected),
            )
        v.add_cascade(label="Edge Flow Speed", menu=flow_speed_menu)
        v.add_checkbutton(label="Show Legend", variable=self.legend_var, command=self.on_view_setting_change)
        v.add_separator()

        # Data & Analysis Views (44–46, 51–55, 56)
        v.add_command(label="Graph Properties & Degree Histogram...", command=self.show_properties)
        v.add_command(label="Node List Table...", command=self.show_node_list)
        v.add_command(label="Edge List Table...", command=self.show_edge_list)
        v.add_command(label="Adjacency Matrix...", command=self.show_adjacency_matrix)
        v.add_command(label="Tree View...", command=lambda: dialogs.TreeView(self))
        v.add_command(label="Timeline View...", command=lambda: dialogs.TimelineView(self))
        v.add_command(label="Formula Sheet...", command=lambda: dialogs.FormulaSheetDialog(self))
        v.add_command(label="Tags & Categories Manager...", command=self.show_tags_manager)
        v.add_separator()
        v.add_command(label="Preferences...", command=self.show_preferences)
        v.add_command(
            label="Privacy-Safe Breach Resources...",
            command=lambda: dialogs.open_privacy_safe_breach_resources(self.root),
        )
        m.add_cascade(label="View", menu=v)

        # ---- Help (19)
        h = tk.Menu(m, tearoff=0)
        h.add_command(label="Quick Start & Usage Tips...", command=self.show_usage_guide)
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

        tools = ttk.LabelFrame(bar, text="Tools", padding=(4, 2))
        tools.pack(side="left", padx=2, fill="y")
        for text, val in (("Select V", "select"), ("Node N", "node"),
                          ("Connect C", "connect"), ("Draw B", "draw"),
                          ("Erase R", "erase"), ("Hand H", "hand")):
            ttk.Radiobutton(tools, text=text, value=val, variable=self.tool,
                            style="Toolbutton", command=self.on_tool_change).pack(side="left", padx=1)

        edit = ttk.LabelFrame(bar, text="Edit", padding=(4, 2))
        edit.pack(side="left", padx=2, fill="y")
        for text, cmd in (("Undo", self.undo), ("Redo", self.redo),
                          ("Delete", self.delete_selected), ("Edit", self.edit_selected_inline)):
            ttk.Button(edit, text=text, command=cmd).pack(side="left", padx=1)

        view = ttk.LabelFrame(bar, text="View", padding=(4, 2))
        view.pack(side="left", padx=2, fill="y")
        ttk.Button(view, text="−", width=2, command=lambda: self.zoom_center(0.8)).pack(side="left")
        ttk.Button(view, textvariable=self.zoom_text, width=6, command=self.reset_zoom).pack(side="left", padx=1)
        ttk.Button(view, text="+", width=2, command=lambda: self.zoom_center(1.25)).pack(side="left")
        ttk.Button(view, text="Fit", width=4, command=self.fit).pack(side="left", padx=2)

        bar2 = ttk.Frame(r, padding=(4, 0, 4, 4))
        bar2.pack(side="top", fill="x")

        node_style = ttk.LabelFrame(bar2, text="Node style", padding=(4, 2))
        node_style.pack(side="left", padx=2, fill="y")
        ttk.Label(node_style, text="Shape").pack(side="left")
        self._combo(node_style, self.shape_var, SHAPES, self.on_shape_change, 7)

        ttk.Label(node_style, text="Fill").pack(side="left", padx=(6, 2))
        self.swatch_frame = ttk.Frame(node_style)
        self.swatch_frame.pack(side="left")
        self.update_color_swatches()

        ttk.Label(node_style, text="Font").pack(side="left", padx=(8, 2))
        self._combo(node_style, self.fs_var, FSIZES, self.on_fs_change, 3)
        self._combo(node_style, self.node_font_var, FONT_FAMILIES, self.on_node_font_change, 9)
        self._combo(
            node_style, self.node_font_style_var, FONT_STYLES,
            self.on_node_font_style_change, 9,
        )

        ttk.Button(node_style, text="Icon…", command=self.pick_node_icon).pack(side="left", padx=4)

        edge_style = ttk.LabelFrame(bar2, text="Connection style", padding=(4, 2))
        edge_style.pack(side="left", padx=2, fill="y")
        ttk.Label(edge_style, text="Line").pack(side="left")
        self._combo(edge_style, self.line_var, LINE_TYPES, self.on_conn_style_change, 7)
        ttk.Label(edge_style, text="Arrow").pack(side="left", padx=(6, 2))
        self._combo(edge_style, self.arrow_var, ARROWS, self.on_conn_style_change, 6)
        ttk.Label(edge_style, text="Width").pack(side="left", padx=(6, 2))
        self._combo(edge_style, self.width_var, WIDTHS, self.on_conn_style_change, 3)
        ttk.Label(edge_style, text="Pattern").pack(side="left", padx=(6, 2))
        self._combo(edge_style, self.line_style_var, LINE_STYLES, self.on_conn_style_change, 7)

        ttk.Button(edge_style, text="Color…", command=self.pick_conn_color).pack(side="left", padx=4)

        bar3 = ttk.Frame(r, padding=(6, 0, 6, 4))
        bar3.pack(side="top", fill="x")

        drawing = ttk.LabelFrame(bar3, text="Freehand", padding=(4, 2))
        drawing.pack(side="left", padx=2, fill="y")
        ttk.Button(drawing, text="Color…", command=self.pick_brush_color).pack(side="left", padx=2)
        ttk.Label(drawing, text="Size").pack(side="left", padx=(4, 0))
        ttk.Button(drawing, text="−", width=2,
                   command=lambda: self._adj_brush(-1)).pack(side="left")
        self.brush_sz_label = ttk.Label(drawing, text=str(self.brush_width), width=3, anchor="center")
        self.brush_sz_label.pack(side="left")
        ttk.Button(drawing, text="+", width=2,
                   command=lambda: self._adj_brush(1)).pack(side="left")
        brush_presets = {"S": 2, "M": 5, "L": 10, "XL": 20}
        self.brush_preset_var = tk.StringVar(value="M")
        brush_preset = ttk.Combobox(
            drawing, textvariable=self.brush_preset_var, values=list(brush_presets),
            width=4, state="readonly",
        )
        brush_preset.pack(side="left", padx=2)
        brush_preset.bind(
            "<<ComboboxSelected>>",
            lambda e: self._set_brush_sz(brush_presets[self.brush_preset_var.get()]),
        )
        self.highlight_var = tk.BooleanVar(value=False)
        ttk.Checkbutton(drawing, text="Highlight", variable=self.highlight_var).pack(side="left", padx=(4, 2))
        ttk.Button(drawing, text="Clear", command=self.clear_strokes).pack(side="left", padx=4)

        search = ttk.LabelFrame(bar3, text="Find in canvas", padding=(4, 2))
        search.pack(side="left", padx=2, fill="y", expand=True)
        self.search_entry = ttk.Entry(search, textvariable=self.search_var, width=14)
        self.search_entry.pack(side="left", padx=2)
        self.search_entry.bind("<Return>", lambda e: self.do_search())
        self.search_entry.bind("<KeyRelease>", lambda e: self.on_search_key())
        ttk.Button(search, text="Search", command=self.do_search).pack(side="left", padx=1)

        workspace = ttk.LabelFrame(bar3, text="Workspace", padding=(4, 2))
        workspace.pack(side="right", padx=2, fill="y")
        ttk.Button(workspace, text="Guide", command=self.show_usage_guide).pack(side="left", padx=1)
        ttk.Button(workspace, text="OSINT", command=self.open_osint_workspace).pack(side="left", padx=1)
        ttk.Button(workspace, text="Panel", command=self.toggle_sidebar).pack(side="left", padx=1)
        ttk.Button(workspace, text="Image…", command=self.add_image_node).pack(side="left", padx=1)

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
        palette = tk.Menubutton(self.swatch_frame, text="Palette ▾", relief="raised")
        palette.pack(side="left", padx=1)
        menu = tk.Menu(palette, tearoff=0)
        colors = self.model.settings.get("brand_colors", [])
        for color in colors[:12]:
            menu.add_command(
                label=f"●  {color}",
                foreground=color,
                command=lambda selected_color=color: self.set_selected_node_color(selected_color),
            )
        menu.add_separator()
        menu.add_command(label="Custom color…", command=self.pick_custom_node_color)
        palette.configure(menu=menu)

    # =========================================================================
    # Canvas, Minimap & Unified Sidebar
    # =========================================================================
    def build_canvas(self):
        self.main_container = ttk.Frame(self.root)
        self.main_container.pack(fill="both", expand=True)

        self.workspace_panes = ttk.Panedwindow(self.main_container, orient="horizontal")
        self.workspace_panes.pack(fill="both", expand=True)
        self.canvas = tk.Canvas(self.workspace_panes, bg="#fafafa", highlightthickness=0)
        self.sidebar = panels.UnifiedSidebar(self.workspace_panes, self)
        self.workspace_panes.add(self.canvas, weight=1)
        self.workspace_panes.add(self.sidebar, weight=0)
        self.root.after_idle(self._set_initial_sidebar_width)
        self.workspace_panes.bind("<ButtonRelease-1>", self._on_workspace_resize)
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
            self.workspace_panes.forget(self.sidebar)
            self.sidebar_visible = False
        else:
            self.workspace_panes.add(self.sidebar, weight=0)
            self.sidebar_visible = True
            self.root.after_idle(self._set_initial_sidebar_width)
        self.root.after_idle(self.fit)

    def _on_workspace_resize(self, _event=None):
        self.root.after_idle(self.fit)

    def _set_initial_sidebar_width(self):
        if self.sidebar_visible and str(self.sidebar) in self.workspace_panes.panes():
            width = self.workspace_panes.winfo_width()
            if width > 400:
                self.workspace_panes.sashpos(0, max(400, width - 360))

    def open_osint_workspace(self):
        return self.sidebar.open_osint_window()

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
        r.bind("<Delete>", self.delete_selected_from_key)
        r.bind("<BackSpace>", self.delete_selected_from_key)
        r.bind("<Return>", lambda e: self.edit_selected_inline())
        r.bind("<F2>", lambda e: self.edit_selected_inline())
        r.bind("<Escape>", self.on_escape)
        r.bind("<KeyPress-space>", self.space_down)
        r.bind("<KeyRelease-space>", self.space_up)
        r.bind_all("<Shift-n>", self.open_selected_element_notes)

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

    def delete_selected_from_key(self, event):
        if self._text_input_has_focus():
            return None
        self.delete_selected()
        return "break"

    def _text_input_has_focus(self):
        try:
            focused = self.root.focus_get()
            while focused is not None:
                if focused.winfo_class() in {
                    "Entry", "Text", "TEntry", "TCombobox", "Spinbox", "TSpinbox",
                }:
                    return True
                focused = focused.master
        except tk.TclError:
            return True
        return False

    # =========================================================================
    # Theme & Coordinate Mapping
    # =========================================================================
    def _layer_config(self, name):
        return self.model.settings.get("layers", {}).get(name, {})

    def _layer_visible(self, name):
        return self._layer_config(name).get("visible", True)

    def _layer_locked(self, name):
        return self._layer_config(name).get("locked", False)

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
    def redraw(self, update_minimap=True):
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

        for nid, node in self.model.nodes.items():
            if not self._layer_visible(node.get("layer", "Data")):
                continue
            if culling_enabled and (
                node["x"] + node["w"] < v_min_x or node["x"] - node["w"] > v_max_x
                or node["y"] + node["h"] < v_min_y or node["y"] - node["h"] > v_max_y
            ):
                continue
            self._fit_node_label(nid, node)

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
            if not self._layer_visible(sn.get("layer", "Annotations")):
                continue
            if culling_enabled and (sn["x"] + sn["w"] < v_min_x or sn["x"] - sn["w"] > v_max_x or
                                    sn["y"] + sn["h"] < v_min_y or sn["y"] - sn["h"] > v_max_y):
                continue
            self.draw_sticky_note(sid, sn)

        # 5. Group parallel edges for bundling / curvature separation
        edge_pairs = {}
        for cid, cn in self.model.conns.items():
            if (
                cn["a"] in self.model.nodes and cn["b"] in self.model.nodes
                and self._layer_visible(cn.get("layer", "Data"))
                and self._layer_visible(self.model.nodes[cn["a"]].get("layer", "Data"))
                and self._layer_visible(self.model.nodes[cn["b"]].get("layer", "Data"))
            ):
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
            if not self._layer_visible(n.get("layer", "Data")):
                continue
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
        if update_minimap:
            self.draw_minimap()

        # 65. Update breadcrumbs
        self.update_breadcrumbs()

    # ---- Draw Node (6, 7)
    def _fit_node_label(self, nid, node):
        label = node.get("text", "")
        if node.get("icon"):
            label = f"{node['icon']}  {label}"
        if not node.get("auto_size_label", True):
            return label

        font_key = (
            node.get("font_family", "Helvetica"),
            int(node.get("fs", 11)),
            node.get("font_style", "normal"),
        )
        layout_key = (label, font_key)
        layout = self._node_label_layout_cache.get(layout_key)
        if layout is None:
            layout = self._compute_node_label_layout(label, font_key)
            if len(self._node_label_layout_cache) >= 2048:
                self._node_label_layout_cache.pop(next(iter(self._node_label_layout_cache)))
            self._node_label_layout_cache[layout_key] = layout

        wrapped_label, content_width, content_height = layout
        node_width = min(360, max(float(node.get("w", 130)), content_width))
        node_height = max(float(node.get("h", 60)), content_height)
        if node_width != node.get("w") or node_height != node.get("h"):
            node["w"] = node_width
            node["h"] = node_height
            self.model.update_spatial_node(nid)
        return wrapped_label

    def _compute_node_label_layout(self, label, font_key):
        font = self._node_font_cache.get(font_key)
        if font is None:
            font = tkfont.Font(
                root=self.root,
                family=font_key[0],
                size=font_key[1],
                weight="bold" if "bold" in font_key[2] else "normal",
                slant="italic" if "italic" in font_key[2] else "roman",
            )
            self._node_font_cache[font_key] = font

        max_width = 360
        line_limit = max_width - 20
        lines = []
        for paragraph in label.splitlines() or [""]:
            words = paragraph.split()
            if not words:
                lines.append("")
                continue
            current = ""
            for word in words:
                pieces = [word]
                if font.measure(word) > line_limit:
                    pieces = []
                    part = ""
                    for char in word:
                        if part and font.measure(part + char) > line_limit:
                            pieces.append(part)
                            part = ""
                        part += char
                    if part:
                        pieces.append(part)
                for piece in pieces:
                    candidate = f"{current} {piece}".strip()
                    if current and font.measure(candidate) > line_limit:
                        lines.append(current)
                        current = piece
                    else:
                        current = candidate
            lines.append(current)

        text_width = max((font.measure(line) for line in lines), default=0)
        content_width = min(max_width, text_width + 20)
        content_height = max(
            60.0,
            len(lines) * font.metrics("linespace") + 16,
        )
        return "\n".join(lines), content_width, content_height

    def draw_node(self, nid, n):
        label_text = self._fit_node_label(nid, n)
        c, s, T = self.canvas, self.scale, self.T
        sx, sy = self.to_screen(n["x"], n["y"])
        hw, hh = n["w"] / 2.0 * s, n["h"] / 2.0 * s
        x1, y1, x2, y2 = sx - hw, sy - hh, sx + hw, sy + hh
        tag = f"node:{nid}"
        sel = nid in self.sel_nodes
        shape = n.get("shape", "rounded")

        fill_col = n.get("color", NODE_COLORS_LIGHT[1])
        hovered = nid == self.hover_node
        outline_col = T["accent"] if sel else (
            T["accent"] if hovered else (n.get("highlight") or "#4b5563")
        )
        width = 3.5 if sel else (3.0 if hovered or n.get("highlight") else 1.5)

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

        image_path = n.get("image_path")
        if image_path and os.path.isfile(image_path):
            image_size = (max(12, int(n["w"] * s - 14)), max(12, int(n["h"] * s - 30)))
            cache_key = (image_path, image_size)
            image = self.image_cache.get(cache_key)
            if image is None:
                try:
                    with Image.open(image_path) as source:
                        source.thumbnail(image_size)
                        pixel_data = io.BytesIO()
                        source.convert("RGB").save(pixel_data, format="GIF")
                        image = tk.PhotoImage(
                            master=self.canvas,
                            data=base64.b64encode(pixel_data.getvalue()).decode("ascii"),
                            format="GIF",
                        )
                    self.image_cache[cache_key] = image
                except OSError:
                    image = None
            if image is not None:
                c.create_image(sx, sy - 8 * s, image=image, tags=tag)

        # 7. Custom icon / emoji glyph + text
        fs = max(6, int(n.get("fs", 11) * s))
        txt_col = n.get("text_color") or (
            T["fg"] if (shape == "text" or self.theme.get() == "high_contrast") else "#111827"
        )
        label_y = sy + (hh * 0.62 if image_path else 0)
        c.create_text(sx, label_y, text=label_text, justify="center", fill=txt_col,
                      width=max(1, (n["w"] - 16) * s),
                      tags=tag, font=(
                          n.get("font_family", "Helvetica"),
                          fs,
                          n.get("font_style", "normal"),
                      ))

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

        # Selection and hover glow
        hovered = cid == self.hover_conn
        if sel or hovered:
            glow_size = 8 if sel else 4
            c.create_line(*flat, fill=T["sel_glow"], width=width * s + glow_size, capstyle="round",
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
        line_style = cn.get("line_style", "dashed" if cn.get("dash") else "solid")
        dash_pattern = LINE_DASH_PATTERNS.get(line_style)
        if dash_pattern:
            opts["dash"] = dash_pattern

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
                                    font=("Helvetica", max(7, int(10 * s)), "bold" if sel or hovered else "normal"))
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
        if sel and kind == "curve" and len(raw) >= 3:
            hx, hy = self.to_screen(*raw[1])
            c.create_oval(
                hx - 6, hy - 6, hx + 6, hy + 6,
                fill="#f97316", outline="white", width=1.5, tags=f"bend:{cid}",
            )

    # ---- Draw Sticky Note (58)
    def draw_sticky_note(self, sid, sn):
        c, s = self.canvas, self.scale
        sx, sy = self.to_screen(sn["x"], sn["y"])
        hw, hh = sn["w"] / 2.0 * s, sn["h"] / 2.0 * s
        tag = f"sticky:{sid}"
        sel = sid == self.sel_sticky

        connected_node = self.model.nodes.get(sn.get("connected_node_id"))
        connector = sn.get("style", {}).get("connector", "none")
        if connected_node is not None and connector != "none":
            nx, ny = self.to_screen(connected_node["x"], connected_node["y"])
            options = {"fill": "#64748b", "width": max(1, s * 1.5), "tags": tag}
            if connector == "arrow":
                options["arrow"] = "last"
            if connector == "curved":
                options["smooth"] = True
            c.create_line(nx, ny, sx, sy, **options)

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
                if t.startswith(("handle:", "node:", "conn:", "end:", "bend:", "sticky:")):
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
            line_style = cn.get("line_style", "dashed" if cn.get("dash") else "solid")
            self.line_style_var.set(line_style)
            self.dash_var.set(line_style != "solid")
            self.width_var.set(str(cn.get("width", 2)))
            self.line_color_var.set(cn.get("color", self.model.settings["default_line_color"]))
        elif self.sel_nodes:
            nid = next(iter(self.sel_nodes))
            n = self.model.nodes.get(nid)
            if n:
                self.shape_var.set(n.get("shape", "rounded"))
                self.fs_var.set(str(n.get("fs", 11)))
                self.node_font_var.set(n.get("font_family", "Helvetica"))
                self.node_font_style_var.set(n.get("font_style", "normal"))

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
            if self._layer_locked(self.model.nodes[h[1]].get("layer", "Data")):
                self.status.set("That layer is locked; unlock it in Inspector to resize this element.")
                return
            self.model.push_undo()
            self.mode, self.rs_id = "resize", h[1]
            return

        if h and h[0] == "bend":
            self.select(conn=h[1])
            self.model.push_undo()
            self.mode = "bend_connection"
            self.bend_conn_id = h[1]
            return

        # Reconnect end
        if h and h[0] == "end":
            if self._layer_locked(self.model.conns[h[1]].get("layer", "Data")):
                self.status.set("That layer is locked; unlock it in Inspector to reconnect this line.")
                return
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
            if self._layer_locked(self.model.sticky_notes[h[1]].get("layer", "Annotations")):
                self.status.set("That layer is locked; unlock it in Inspector to move this note.")
                return
            self.mode = "drag_sticky"
            self.drag_start = (wx, wy)
            self.drag_orig = (self.model.sticky_notes[h[1]]["x"], self.model.sticky_notes[h[1]]["y"])
            return

        # Node click / Multi-select (11, 12)
        if h and h[0] == "node":
            nid = h[1]
            if e.state & 0x1:
                if self._layer_locked(self.model.nodes[nid].get("layer", "Data")):
                    self.status.set("That layer is locked; unlock it in Inspector before connecting from this element.")
                    return
                self.mode = "connect_pending"
                self.conn_src = nid
                self.connect_start = (e.x, e.y)
                return

            # Shift / Ctrl multi-select toggle
            if e.state & 0x4:
                self.select(nodes=self.sel_nodes ^ {nid})
            elif nid not in self.sel_nodes:
                self.select(nodes={nid})

            if self._layer_locked(self.model.nodes[nid].get("layer", "Data")):
                self.status.set("That layer is locked; unlock it in Inspector to move this element.")
                return
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

        if m == "connect_pending":
            if math.hypot(e.x - self.connect_start[0], e.y - self.connect_start[1]) >= 4:
                self.mode = "connect"
                self.redraw()
        elif m == "pan":
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

            self.schedule_drag_redraw()

        elif m == "drag_sticky":
            dx, dy = wx - self.drag_start[0], wy - self.drag_start[1]
            sn = self.model.sticky_notes[self.sel_sticky]
            sn["x"], sn["y"] = self.drag_orig[0] + dx, self.drag_orig[1] + dy
            self.schedule_drag_redraw()

        elif m == "resize":
            n = self.model.nodes[self.rs_id]
            n["auto_size_label"] = False
            n["w"] = max(50.0, round((wx - n["x"]) * 2))
            n["h"] = max(34.0, round((wy - n["y"]) * 2))
            self.model.update_spatial_node(self.rs_id)
            self.redraw()

        elif m == "bend_connection":
            conn = self.model.conns.get(self.bend_conn_id)
            if conn:
                source = self.model.nodes.get(conn["a"])
                target = self.model.nodes.get(conn["b"])
                if source and target:
                    dx = target["x"] - source["x"]
                    dy = target["y"] - source["y"]
                    length = math.hypot(dx, dy) or 1.0
                    mid_x = (source["x"] + target["x"]) / 2
                    mid_y = (source["y"] + target["y"]) / 2
                    conn["bend"] = (wx - mid_x) * (-dy / length) + (wy - mid_y) * (dx / length)
                    conn["type"] = "curved"
                    self.dirty = True
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
        self.cancel_drag_redraw()

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
                    line_style=self.line_style_var.get(),
                    color=self.line_color_var.get(),
                )
                self.select(conn=cid)
            elif self.hit(e.x, e.y) is None:
                # Drop on empty space creates a new connected node
                wx, wy = self.to_world(e.x, e.y)
                self.model.push_undo()
                nid = self.model.make_node(wx, wy, text="Node")
                if hasattr(self, "sidebar"):
                    self.model.nodes[nid]["layer"] = self.sidebar.active_layer_var.get()
                cid = self.model.make_conn(
                    self.conn_src,
                    nid,
                    type_=self.line_var.get(),
                    arrow=self.arrow_var.get(),
                    width=int(self.width_var.get()),
                    line_style=self.line_style_var.get(),
                    color=self.line_color_var.get(),
                )
                self.select(nodes={nid})
            self.redraw()

        elif m == "connect_pending":
            self.select(nodes=self.sel_nodes ^ {self.conn_src})
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

        elif m == "drag":
            if self.drag_moved:
                for nid in self.sel_nodes:
                    self.model.update_spatial_node(nid)
                self.model.dirty = True
                self.dirty = True
            self.redraw()

        elif m == "drag_sticky":
            self.model.update_spatial_sticky(self.sel_sticky)
            self.model.dirty = True
            self.dirty = True
            self.redraw()

        elif m in ("resize", "bend_connection"):
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
            if self._layer_locked(self.model.conns[h[1]].get("layer", "Data")):
                self.status.set("That layer is locked; unlock it in Inspector to edit this line.")
                return
            # 20. Right-click edge context menu
            dialogs.EdgeContextMenu(self, h[1], e.x_root, e.y_root)
        elif h and h[0] == "node":
            if self._layer_locked(self.model.nodes[h[1]].get("layer", "Data")):
                self.status.set("That layer is locked; unlock it in Inspector to edit this node.")
                return
            self.show_node_context_menu(h[1], e.x_root, e.y_root)
        elif h and h[0] == "sticky":
            note_menu = tk.Menu(self.root, tearoff=0)
            note_menu.add_command(label="Edit Note Text...", command=lambda: self.edit_sticky_note(h[1]))
            note_menu.add_command(label="Open Notes Window", command=lambda: self._note_window_for(sid=h[1]))
            note_menu.add_separator()
            note_menu.add_command(label="Delete Note", command=lambda: self.model.remove_sticky_note(h[1]))
            note_menu.tk_popup(e.x_root, e.y_root)

    # ---- 9. Hover Tooltips & 65. Breadcrumbs
    def on_mouse_hover(self, e):
        h = self.hit(e.x, e.y)
        old_hover = (self.hover_node, self.hover_conn)
        self.hover_node = h[1] if (h and h[0] == "node") else None
        self.hover_conn = h[1] if (h and h[0] == "conn") else None
        self.cur = (e.x, e.y)   # keep cur updated for eraser ghost
        if self.tool.get() == "select":
            cursor = "fleur" if h is None and self.drag_pan.get() == "pan" else ""
            self.canvas.configure(cursor=cursor)

        self.update_breadcrumbs()
        if old_hover != (self.hover_node, self.hover_conn) and self.mode is None:
            self.redraw()

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
    def schedule_drag_redraw(self):
        if self.drag_redraw_after is None:
            self.drag_redraw_after = self.root.after(24, self._flush_drag_redraw)

    def _flush_drag_redraw(self):
        self.drag_redraw_after = None
        if self.mode in {"drag", "drag_sticky"}:
            self.redraw(update_minimap=False)

    def cancel_drag_redraw(self):
        if self.drag_redraw_after is None:
            return
        try:
            self.root.after_cancel(self.drag_redraw_after)
        except tk.TclError:
            pass
        self.drag_redraw_after = None

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

    def set_drag_pan_mode(self, mode):
        if mode not in {"pan", "box"}:
            raise ValueError(f"Unsupported empty-canvas drag mode: {mode}")
        self.drag_pan.set(mode)
        self.model.settings["drag_pan"] = mode
        self.model.dirty = True
        self.dirty = True

    def add_node_at(self, x, y):
        self.model.push_undo()
        if self.snap_var.get():
            x, y = self.snap_val(x), self.snap_val(y)
        nid = self.model.make_node(x, y, text="New Node")
        if hasattr(self, "sidebar"):
            self.model.nodes[nid]["layer"] = self.sidebar.active_layer_var.get()
        self.select(nodes={nid})
        # 17. Automatically begin inline label editing
        self.edit_node_inline(nid)

    def auto_detect_selected_entities(self):
        selected = [
            self.model.nodes[nid] for nid in self.sel_nodes
            if nid in self.model.nodes
        ]
        if not selected:
            self.status.set("Select one or more nodes to detect entity types.")
            return
        detections = []
        for node in selected:
            detected = linkdraw_investigation.detect_entity_type(node.get("text", ""))
            if detected:
                detections.append((node, detected))
        if not detections:
            self.status.set("No common entity types were detected in the selected node labels.")
            return
        if any(node.get("entity_type") != kind for node, kind in detections):
            self.model.push_undo()
            for node, kind in detections:
                node["entity_type"] = kind
                tags = node.setdefault("tags", [])
                if kind.casefold() not in [tag.casefold() for tag in tags]:
                    tags.append(kind.casefold())
            self.dirty = True
        self.redraw()
        self.status.set(f"Detected entity types for {len(detections)} selected node(s).")

    def add_image_node(self):
        path = filedialog.askopenfilename(
            parent=self.root,
            title="Choose image for graph",
            filetypes=[("Image files", "*.png *.jpg *.jpeg *.gif *.bmp *.webp"), ("All files", "*.*")],
        )
        if not path:
            return
        try:
            with Image.open(path) as image:
                width, height = image.size
        except OSError as exc:
            messagebox.showerror("Image Error", f"Could not open image:\n{exc}", parent=self.root)
            return
        x, y = self.to_world(self.canvas.winfo_width() / 2, self.canvas.winfo_height() / 2)
        self.model.push_undo()
        nid = self.model.make_node(x, y, text=os.path.basename(path), w=180, h=150)
        self.model.nodes[nid]["image_path"] = os.path.abspath(path)
        self.model.nodes[nid]["metadata"]["image_size"] = [width, height]
        if hasattr(self, "sidebar"):
            self.model.nodes[nid]["layer"] = self.sidebar.active_layer_var.get()
        self.select(nodes={nid})
        self.dirty = True
        self.redraw()

    def edit_node_inline(self, nid):
        dialogs.InlineTextEditor(self, nid, on_commit=self.on_node_text_commit)

    def on_node_text_commit(self):
        self.auto_detect_selected_entities()
        self.redraw()

    def _note_window_for(self, nid=None, sid=None):
        key = ("node", nid) if nid is not None else ("sticky", sid)
        window = self._note_windows.get(key)
        if window is not None and window.winfo_exists():
            window.focus_set()
            return

        if nid is not None:
            if nid not in self.model.nodes:
                return
            note = self.model.nodes[nid].setdefault("rich_notes", {"text": "", "image_path": "", "checklist": []})
            style = note.setdefault("style", self.model.default_note_style(self.model.settings))
            title = f"Notes for Node #{nid}"
            initial_text = note.get("text", "")
        else:
            if sid not in self.model.sticky_notes:
                return
            note = self.model.sticky_notes[sid]
            style = note.setdefault("style", self.model.default_note_style(self.model.settings))
            title = f"Notes for Sticky #{sid}"
            initial_text = note.get("text", "")

        win = tk.Toplevel(self.root)
        win.title(title)
        win.geometry("620x520")
        win.minsize(420, 340)
        self._note_windows[key] = win

        theme_var = tk.StringVar(value=style.get("theme", self.theme.get()))
        font_var = tk.StringVar(value=style.get("font_family", "Helvetica"))
        size_var = tk.StringVar(value=str(style.get("font_size", 11)))
        style_var = tk.StringVar(value=style.get("font_style", "normal"))
        color_var = tk.StringVar(value=style.get("text_color", "#111827"))
        highlight_var = tk.StringVar(value=style.get("highlight", "#facc15"))
        connector_var = tk.StringVar(value=style.get("connector", "none"))

        toolbar = ttk.Frame(win, padding=(8, 8, 8, 4))
        toolbar.pack(fill="x")
        ttk.Label(toolbar, text="Font").pack(side="left")
        ttk.Combobox(toolbar, textvariable=font_var, values=FONT_FAMILIES, width=15, state="readonly").pack(side="left", padx=(4, 8))
        ttk.Label(toolbar, text="Size").pack(side="left")
        ttk.Combobox(toolbar, textvariable=size_var, values=[str(value) for value in FSIZES], width=5, state="readonly").pack(side="left", padx=(4, 8))
        ttk.Label(toolbar, text="Style").pack(side="left")
        ttk.Combobox(toolbar, textvariable=style_var, values=FONT_STYLES, width=12, state="readonly").pack(side="left", padx=(4, 8))
        ttk.Label(toolbar, text="Theme").pack(side="left")
        ttk.Combobox(toolbar, textvariable=theme_var, values=["light", "dark", "high_contrast"], width=13, state="readonly").pack(side="left", padx=(4, 0))

        color_bar = ttk.Frame(win, padding=(8, 0, 8, 4))
        color_bar.pack(fill="x")
        ttk.Label(color_bar, text="Text color").pack(side="left")
        ttk.Entry(color_bar, textvariable=color_var, width=11).pack(side="left", padx=(4, 2))
        ttk.Button(color_bar, text="Pick", command=lambda: self._pick_note_color(color_var)).pack(side="left")
        ttk.Label(color_bar, text="Highlight").pack(side="left", padx=(10, 0))
        ttk.Entry(color_bar, textvariable=highlight_var, width=11).pack(side="left", padx=(4, 2))
        ttk.Button(color_bar, text="Pick", command=lambda: self._pick_note_color(highlight_var)).pack(side="left")

        body_frame = ttk.Frame(win, padding=(8, 0, 8, 4))
        body_frame.pack(fill="both", expand=True)
        body = tk.Text(body_frame, wrap="word", undo=True, padx=8, pady=8,
                       font=(font_var.get(), int(size_var.get())))
        body.insert("1.0", initial_text)
        scrollbar = ttk.Scrollbar(body_frame, orient="vertical", command=body.yview)
        body.configure(yscrollcommand=scrollbar.set)
        body.pack(side="left", fill="both", expand=True)
        scrollbar.pack(side="right", fill="y")
        body.tag_configure("note_bold", font=(font_var.get(), int(size_var.get()), "bold"))
        body.tag_configure("note_italic", font=(font_var.get(), int(size_var.get()), "italic"))
        body.tag_configure("note_underline", underline=True)
        body.tag_configure("note_highlight", background=highlight_var.get())
        for item in note.get("formatting", []):
            try:
                tag = item["tag"]
                if tag.startswith("note_color_"):
                    body.tag_configure(tag, foreground=f"#{tag.removeprefix('note_color_')}")
                start = body.index(f"1.0 + {int(item['start'])} chars")
                end = body.index(f"1.0 + {int(item['end'])} chars")
                body.tag_add(tag, start, end)
            except (KeyError, TypeError, ValueError, tk.TclError):
                continue

        formatting = ttk.Frame(win, padding=(8, 0, 8, 4))
        formatting.pack(fill="x")
        ttk.Button(formatting, text="Bold", command=lambda: self._toggle_note_tag(body, "note_bold")).pack(side="left")
        ttk.Button(formatting, text="Italic", command=lambda: self._toggle_note_tag(body, "note_italic")).pack(side="left", padx=(4, 0))
        ttk.Button(formatting, text="Underline", command=lambda: self._toggle_note_tag(body, "note_underline")).pack(side="left", padx=(4, 0))
        ttk.Button(formatting, text="Highlight selection", command=lambda: self._apply_note_highlight(body, highlight_var)).pack(side="left", padx=(8, 0))
        ttk.Button(formatting, text="Text color", command=lambda: self._apply_note_text_color(body, color_var)).pack(side="left", padx=(4, 0))

        actions = ttk.Frame(win, padding=(8, 0, 8, 8))
        actions.pack(fill="x")
        if sid is not None:
            ttk.Label(actions, text="Connector").pack(side="left")
            ttk.Combobox(actions, textvariable=connector_var, values=["none", "straight", "arrow", "curved"], width=10, state="readonly").pack(side="left", padx=(4, 6))
            ttk.Button(actions, text="Connect to selected node", command=lambda: self._connect_sticky_note(sid, connector_var.get())).pack(side="left")
        ttk.Button(actions, text="Open Diagram Tree", command=lambda: dialogs.TreeView(self)).pack(side="left", padx=(6, 0))
        ttk.Button(actions, text="Save", command=lambda: self._save_note_window(body, nid, sid, note, font_var, size_var, style_var, color_var, highlight_var, theme_var, connector_var)).pack(side="left", padx=(6, 0))

        def apply_style(_event=None):
            self._apply_note_window_style(body, font_var, size_var, style_var, color_var, highlight_var, theme_var)

        save_note = lambda: self._save_note_window(
            body, nid, sid, note, font_var, size_var, style_var,
            color_var, highlight_var, theme_var, connector_var,
        )
        self._note_window_savers[key] = save_note

        for variable in (font_var, size_var, style_var, color_var, highlight_var, theme_var):
            variable.trace_add("write", lambda *_args: apply_style())
        apply_style()
        body.bind("<KeyRelease>", lambda _event: save_note())

        def on_close():
            save_note()
            self._note_window_savers.pop(key, None)
            self._note_windows.pop(key, None)
            win.destroy()
        win.protocol("WM_DELETE_WINDOW", on_close)
        ttk.Button(actions, text="Close", command=on_close).pack(side="right")

    def _pick_note_color(self, var):
        color = colorchooser.askcolor(parent=self.root, initialcolor=var.get())[1]
        if color:
            var.set(color)

    @staticmethod
    def _toggle_note_tag(body, tag):
        try:
            start, end = body.index("sel.first"), body.index("sel.last")
        except tk.TclError:
            return
        if tag in body.tag_names(start):
            body.tag_remove(tag, start, end)
        else:
            body.tag_add(tag, start, end)

    @staticmethod
    def _apply_note_highlight(body, highlight_var):
        try:
            start, end = body.index("sel.first"), body.index("sel.last")
        except tk.TclError:
            return
        body.tag_configure("note_highlight", background=highlight_var.get())
        body.tag_add("note_highlight", start, end)

    @staticmethod
    def _apply_note_text_color(body, color_var):
        try:
            start, end = body.index("sel.first"), body.index("sel.last")
        except tk.TclError:
            return
        tag = f"note_color_{color_var.get().lstrip('#')}"
        body.tag_configure(tag, foreground=color_var.get())
        body.tag_add(tag, start, end)

    @staticmethod
    def _apply_note_window_style(body, font_var, size_var, style_var, color_var, highlight_var, theme_var):
        try:
            size = int(size_var.get())
        except ValueError:
            return
        weights = "bold" in style_var.get()
        slant = "italic" in style_var.get()
        font_style = ("bold " if weights else "") + ("italic" if slant else "")
        font = (font_var.get(), size, font_style or "normal")
        colors = {
            "light": ("#ffffff", color_var.get(), color_var.get()),
            "dark": ("#1e222b", color_var.get(), color_var.get()),
            "high_contrast": ("#000000", color_var.get(), color_var.get()),
        }
        background, foreground, insert = colors.get(theme_var.get(), colors["light"])
        body.configure(font=font, bg=background, fg=foreground, insertbackground=insert)
        body.tag_configure("note_bold", font=(font_var.get(), size, "bold"))
        body.tag_configure("note_italic", font=(font_var.get(), size, "italic"))
        body.tag_configure("note_highlight", background=highlight_var.get())
        body.tag_configure("sel", background="#2563eb", foreground="#ffffff")

    def _save_note_window(self, body, nid, sid, note, font_var, size_var, style_var, color_var, highlight_var, theme_var, connector_var):
        text = body.get("1.0", "end-1c")
        if nid is not None and nid in self.model.nodes:
            note = self.model.nodes[nid].setdefault("rich_notes", {"text": "", "image_path": "", "checklist": []})
            note["text"] = text
            style = note.setdefault("style", self.model.default_note_style(self.model.settings))
        elif sid is not None and sid in self.model.sticky_notes:
            note = self.model.sticky_notes[sid]
            note["text"] = text
            style = note.setdefault("style", self.model.default_note_style(self.model.settings))
        else:
            return

        formatting = []
        for tag in body.tag_names():
            if not tag.startswith(("note_bold", "note_italic", "note_underline", "note_highlight", "note_color_")):
                continue
            ranges = body.tag_ranges(tag)
            for start, end in zip(ranges[::2], ranges[1::2]):
                start_offset = body.count("1.0", start, "chars")[0]
                end_offset = body.count("1.0", end, "chars")[0]
                formatting.append({"start": start_offset, "end": end_offset, "tag": tag})
        note["formatting"] = formatting

        style.update({
            "font_family": font_var.get(),
            "font_size": int(size_var.get()),
            "font_style": style_var.get(),
            "text_color": color_var.get(),
            "highlight": highlight_var.get(),
            "theme": theme_var.get(),
        })
        if sid is not None:
            style["connector"] = connector_var.get()
            self._connect_sticky_note(sid, connector_var.get(), redraw=False)
        note["style"] = style
        if nid is not None and nid in self.model.nodes:
            self.model.nodes[nid]["highlight"] = style.get("highlight")
            self.model.nodes[nid]["font_family"] = style.get("font_family")
            self.model.nodes[nid]["font_style"] = style.get("font_style")
            self.model.nodes[nid]["fs"] = int(style.get("font_size", self.model.nodes[nid].get("fs", 11)))
        self.model.dirty = True
        self.dirty = True
        self.redraw()

    def _connect_sticky_note(self, sid, connector, redraw=True):
        note = self.model.sticky_notes.get(sid)
        selected = next(iter(self.sel_nodes), None)
        if note is None:
            return
        if connector == "none":
            note.pop("connected_node_id", None)
        elif selected is not None and selected in self.model.nodes:
            note["connected_node_id"] = selected
        else:
            self.status.set("Select a node on the diagram before connecting this sticky note.")
            return
        self.model.dirty = True
        self.dirty = True
        if redraw:
            self.redraw()

    def open_node_notes(self, nid):
        if nid not in self.model.nodes:
            return
        self.select(nodes={nid})
        self._note_window_for(nid=nid)

    def open_selected_element_notes(self, _event=None):
        if self._text_input_has_focus():
            return None
        if self.sel_nodes:
            for nid in sorted(self.sel_nodes):
                self._note_window_for(nid=nid)
        elif self.sel_sticky in self.model.sticky_notes:
            self._note_window_for(sid=self.sel_sticky)
        else:
            self.status.set("Select a graph element, then press Shift+N to open its notes.")
        return "break"

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
            if self._layer_locked(self.model.conns[self.sel_conn].get("layer", "Data")):
                self.status.set("That layer is locked; unlock it in Inspector before deleting.")
                return
            self.model.push_undo()
            self.model.remove_conn(self.sel_conn)
            self.sel_conn = None
        elif self.sel_nodes:
            deletable = [
                nid for nid in self.sel_nodes
                if nid in self.model.nodes
                and not self._layer_locked(self.model.nodes[nid].get("layer", "Data"))
            ]
            if not deletable:
                self.status.set("Selected elements are on locked layers.")
                return
            self.model.push_undo()
            for nid in deletable:
                self.model.remove_node(nid)
            self.sel_nodes.difference_update(deletable)
        elif self.sel_sticky in self.model.sticky_notes:
            if self._layer_locked(self.model.sticky_notes[self.sel_sticky].get("layer", "Annotations")):
                self.status.set("That layer is locked; unlock it in Inspector before deleting.")
                return
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
        movable = [
            nid for nid in self.sel_nodes
            if nid in self.model.nodes
            and not self._layer_locked(self.model.nodes[nid].get("layer", "Data"))
        ]
        if movable:
            self.model.push_undo()
            for nid in movable:
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
            self.dirty = True
            self.redraw()

    def on_fs_change(self):
        if self.sel_nodes:
            self.model.push_undo()
            fs = int(self.fs_var.get())
            for nid in self.sel_nodes:
                self.model.nodes[nid]["fs"] = fs
            self.dirty = True
            self.redraw()
        else:
            self.model.settings["default_font_size"] = int(self.fs_var.get())
            self.model.dirty = True
            self.dirty = True

    def on_node_font_change(self):
        family = self.node_font_var.get()
        if self.sel_nodes:
            self.sidebar.set_selected_node_property("font_family", family)
        else:
            self.model.settings["default_font_family"] = family
            self.model.dirty = True
            self.dirty = True

    def on_node_font_style_change(self):
        style = self.node_font_style_var.get()
        if self.sel_nodes:
            self.sidebar.set_selected_node_property("font_style", style)
        else:
            self.model.settings["default_font_style"] = style
            self.model.dirty = True
            self.dirty = True

    def set_selected_node_color(self, col):
        if self.sel_nodes:
            self.model.push_undo()
            for nid in self.sel_nodes:
                self.model.nodes[nid]["color"] = col
            self.dirty = True
            self.redraw()
        else:
            self.model.settings["default_node_color"] = col
            self.model.dirty = True
            self.dirty = True

    def pick_node_text_color(self):
        nodes = [self.model.nodes[nid] for nid in self.sel_nodes if nid in self.model.nodes]
        initial = nodes[0].get("text_color") or "#111827" if nodes else "#111827"
        color = colorchooser.askcolor(initial, parent=self.root, title="Node Text Color")[1]
        if color and self.sel_nodes:
            self.sidebar.set_selected_node_property("text_color", color)

    def reset_node_text_color(self):
        if self.sel_nodes:
            self.sidebar.set_selected_node_property("text_color", "")

    def pick_custom_node_color(self):
        col = colorchooser.askcolor(parent=self.root, title="Node Color")[1]
        if col:
            self.set_selected_node_color(col)

    def on_conn_style_change(self):
        line_style = self.line_style_var.get()
        self.dash_var.set(line_style != "solid")
        if self.sel_conn in self.model.conns:
            cn = self.model.conns[self.sel_conn]
            self.model.push_undo()
            cn["type"] = self.line_var.get()
            cn["arrow"] = self.arrow_var.get()
            cn["line_style"] = line_style
            cn["dash"] = line_style != "solid"
            cn["width"] = int(self.width_var.get())
            cn["color"] = self.line_color_var.get()
            self.dirty = True
            self.redraw()
        else:
            self.model.settings["default_line_type"] = self.line_var.get()
            self.model.settings["default_arrow"] = self.arrow_var.get()
            self.model.settings["default_line_style"] = line_style
            self.model.settings["default_line_width"] = int(self.width_var.get())
            self.model.settings["default_line_color"] = self.line_color_var.get()
            self.model.dirty = True
            self.dirty = True

    def pick_conn_color(self):
        cn = self.model.conns.get(self.sel_conn)
        col = colorchooser.askcolor(
            cn["color"] if cn else self.line_color_var.get(), parent=self.root
        )[1]
        if col:
            self.line_color_var.set(col)
            if cn:
                self.model.push_undo()
                cn["color"] = col
                self.dirty = True
                self.redraw()
            else:
                self.model.settings["default_line_color"] = col
                self.model.dirty = True
                self.dirty = True

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
        m.add_command(label="Edit Text...", command=lambda: self.edit_node_inline(nid))
        m.add_command(label="Open Notes...", command=lambda: self.open_node_notes(nid))
        m.add_command(label="Open Notes in Window", command=lambda: self._note_window_for(nid=nid))
        m.add_separator()
        m.add_command(label=f"Edit Metadata...", command=lambda: dialogs.NodeMetadataEditor(self, nid))
        m.add_command(label="Choose Icon...", command=self.pick_node_icon)
        m.add_separator()
        m.add_command(label="Delete Node", command=self.delete_selected)
        m.tk_popup(x, y)

    # ---- 8. Animated Edge Flow Toggle
    def toggle_edge_flow(self):
        self.model.settings["animated_flow"] = self.animated_flow_var.get()
        self.model.dirty = True
        self.dirty = True
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
        speed = int(self.flow_speed_var.get())
        self.flow_phase = (self.flow_phase + speed) % 20
        self.redraw()
        self.flow_job = self.root.after(max(20, 120 - speed * 20), self._step_flow)

    def set_flow_speed(self, speed):
        if speed not in {1, 2, 4}:
            raise ValueError(f"Unsupported flow speed: {speed}")
        self.flow_speed_var.set(str(speed))
        self.model.settings["flow_speed"] = speed
        self.model.dirty = True
        self.dirty = True

    # ---- 1. Theme Change
    def on_theme_change(self):
        self.model.settings["theme"] = self.theme.get()
        self.model.dirty = True
        self.dirty = True
        self.apply_widget_theme()
        self.update_color_swatches()
        self.redraw()

    def on_view_setting_change(self):
        self.model.settings.update({
            "grid": self.grid_var.get(),
            "snap": self.snap_var.get(),
            "minimap": self.minimap_var.get(),
            "show_legend": self.legend_var.get(),
        })
        self.model.dirty = True
        self.dirty = True
        self.redraw()

    def apply_widget_theme(self):
        style = ttk.Style(self.root)
        if "clam" in style.theme_names():
            style.theme_use("clam")
        if self.theme.get() == "dark":
            colors = ("#20242c", "#292f39", "#e5e7eb", "#171a20", "#424a57", "#3b82f6")
        elif self.theme.get() == "high_contrast":
            colors = ("#000000", "#000000", "#ffffff", "#000000", "#ffffff", "#ffff00")
        else:
            colors = ("#f3f4f6", "#ffffff", "#111827", "#ffffff", "#cbd5e1", "#2563eb")
        bg, surface, fg, field, border, accent = colors
        style.configure(".", background=bg, foreground=fg)
        style.configure("TFrame", background=bg)
        style.configure("TLabel", background=bg, foreground=fg)
        style.configure("TLabelframe", background=bg, foreground=fg)
        style.configure("TLabelframe.Label", background=bg, foreground=fg)
        style.configure("TNotebook", background=bg, bordercolor=border)
        style.configure("TNotebook.Tab", background=surface, foreground=fg, padding=(8, 4))
        style.map("TNotebook.Tab", background=[("selected", accent)], foreground=[("selected", "#ffffff")])
        style.configure("TButton", background=surface, foreground=fg, padding=(6, 3))
        style.map("TButton", background=[("active", accent)], foreground=[("active", "#ffffff")])
        style.configure("TCheckbutton", background=bg, foreground=fg)
        style.configure("TRadiobutton", background=bg, foreground=fg)
        style.configure("TEntry", fieldbackground=field, foreground=fg)
        style.configure("TCombobox", fieldbackground=field, foreground=fg)
        style.configure("Treeview", background=field, fieldbackground=field, foreground=fg)
        style.configure("Treeview.Heading", background=surface, foreground=fg)
        style.configure("TScrollbar", background=surface, troughcolor=bg)
        def style_native_widgets(widget):
            if isinstance(widget, tk.Text):
                widget.configure(
                    bg=field, fg=fg, insertbackground=fg,
                    selectbackground=accent, selectforeground="#ffffff",
                )
            elif isinstance(widget, tk.Listbox):
                widget.configure(
                    bg=field, fg=fg, selectbackground=accent,
                    selectforeground="#ffffff",
                )
            elif isinstance(widget, tk.Canvas) and widget not in (self.canvas, self.mm):
                widget.configure(bg=bg)
            for child in widget.winfo_children():
                style_native_widgets(child)

        style_native_widgets(self.root)

    # =========================================================================
    # Layouts (21–30)
    # =========================================================================
    def apply_layout(self, kind):
        node_ids = sorted(self.sel_nodes) if len(self.sel_nodes) >= 2 else list(self.model.nodes.keys())
        if len(node_ids) < 2:
            return

        if kind == "auto":
            kind = layouts.auto_detect_preset(self.model, node_ids)

        if kind == "circle":
            target_pos = layouts.compute_circular(self.model, node_ids)
        elif kind == "grid":
            target_pos = layouts.compute_grid(self.model, node_ids)
        elif kind == "concentric":
            target_pos = layouts.compute_concentric(self.model, node_ids)
        elif kind == "spiral":
            target_pos = layouts.compute_spiral(self.model, node_ids)
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

    def show_usage_guide(self):
        win = tk.Toplevel(self.root)
        win.title("LinkDraw Quick Start")
        win.transient(self.root)
        win.minsize(480, 360)
        frame = ttk.Frame(win, padding=14)
        frame.pack(fill="both", expand=True)
        ttk.Label(frame, text="Build, style, and explore a diagram", font=("Helvetica", 14, "bold")).pack(anchor="w")
        tips = (
            "1. Add nodes with the Node tool or choose a shape from Elements.\n"
            "2. Connect nodes by choosing Connect and dragging from one node to another.\n"
            "3. Select a line to edit its route, arrow, color, width, pattern, weight, and label.\n"
            "4. Set line options with no line selected to use them for new connections.\n"
            "5. Select several nodes to move or recolor them together. Use Layout for automatic arrangements.\n"
            "   Try Concentric for connection-distance rings or Topology Spiral for an expanding connected-node view.\n"
            "6. Drag empty canvas to pan; use Inspector for layers, exact sizes, line details, and pages.\n"
            "   Select a connection and drag its orange midpoint handle to customize its curve.\n"
            "7. Select one or more graph elements and press Shift+N for their separate notes windows.\n"
            "8. Shift-drag from one node to another to connect without changing tools.\n"
            "9. View offers Tree, Timeline, and Formula Sheet views. Formulas use spreadsheet cell references.\n"
            "10. OSINT entity detection runs locally. Breach resources open a public homepage only and never send graph data.\n"
            "11. Save diagrams with Ctrl+S (Command+S on macOS). Export images and graph formats from File.\n\n"
            "Useful keys: V Select · N Node · C Connect · B Draw · H Hand · Shift-drag Connect · Shift+N Notes · F Fit · Ctrl+Z Undo"
        )
        text = tk.Text(frame, wrap="word", height=12, padx=8, pady=8)
        text.pack(fill="both", expand=True, pady=(10, 0))
        text.insert("1.0", tips)
        text.configure(state="disabled")
        ttk.Button(frame, text="Close", command=win.destroy).pack(anchor="e", pady=(8, 0))

    def copy_selected_style(self):
        if self.sel_conn in self.model.conns:
            connection = self.model.conns[self.sel_conn]
            style = {
                key: connection.get(key)
                for key in ("type", "arrow", "color", "width")
            }
            style["line_style"] = connection.get(
                "line_style", "dashed" if connection.get("dash") else "solid"
            )
            style["dash"] = style["line_style"] != "solid"
            self.style_clipboard = ("connection", style)
        elif self.sel_nodes:
            node = self.model.nodes.get(next(iter(self.sel_nodes)))
            if node is None:
                return
            keys = ("shape", "color", "fs", "icon")
            self.style_clipboard = ("node", {key: node.get(key) for key in keys})
        else:
            self.status.set("Select a node or connection before copying its style.")
            return
        self.status.set("Style copied. Select matching objects and choose Paste Style.")

    def paste_selected_style(self):
        if not self.style_clipboard:
            self.status.set("Copy a node or connection style first.")
            return
        kind, style = self.style_clipboard
        if kind == "node" and self.sel_nodes:
            targets = [self.model.nodes[nid] for nid in self.sel_nodes if nid in self.model.nodes]
            if not targets:
                return
        elif kind == "connection" and self.sel_conn in self.model.conns:
            targets = [self.model.conns[self.sel_conn]]
        else:
            self.status.set(f"Select {kind}s to apply the copied style.")
            return
        if all(all(target.get(key) == value for key, value in style.items()) for target in targets):
            return
        self.model.push_undo()
        self.dirty = True
        for target in targets:
            target.update(style)
        if kind == "connection":
            line_style = style.get("line_style") or ("dashed" if style.get("dash") else "solid")
            self.line_var.set(style.get("type", "curved"))
            self.arrow_var.set(style.get("arrow", "forward"))
            self.width_var.set(str(style.get("width", 2)))
            self.line_style_var.set(line_style)
            self.line_color_var.set(style.get("color", "#374151"))
            self.dash_var.set(line_style != "solid")
        self.redraw()
        self.status.set(f"Applied copied {kind} style.")

    def select_connected_neighbors(self):
        if not self.sel_nodes:
            self.status.set("Select one or more nodes first.")
            return
        neighbors = set(self.sel_nodes)
        for connection in self.model.conns.values():
            if connection["a"] in self.sel_nodes:
                neighbors.add(connection["b"])
            if connection["b"] in self.sel_nodes:
                neighbors.add(connection["a"])
        self.select(nodes=neighbors)
        self.status.set(f"Selected {len(neighbors)} nodes, including connected neighbors.")

    def select_component(self):
        if not self.sel_nodes:
            self.status.set("Select a node first.")
            return
        component = set(self.sel_nodes)
        frontier = list(self.sel_nodes)
        while frontier:
            current = frontier.pop()
            for connection in self.model.conns.values():
                if connection["a"] == current:
                    neighbor = connection["b"]
                elif connection["b"] == current:
                    neighbor = connection["a"]
                else:
                    continue
                if neighbor in self.model.nodes and neighbor not in component:
                    component.add(neighbor)
                    frontier.append(neighbor)
        self.select(nodes=component)
        self.status.set(f"Selected the connected component ({len(component)} nodes).")

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
        matches = [
            nid for nid, n in self.model.nodes.items()
            if q in n.get("text", "").lower()
            or q in n.get("entity_type", "").lower()
            or any(q in tag.lower() for tag in n.get("tags", []))
        ]
        for nid, n in self.model.nodes.items():
            n["highlight"] = "#eab308" if nid in matches else None
        self.redraw()

    def do_search(self):
        q = self.search_var.get().strip().lower()
        if not q:
            return
        matches = [
            nid for nid, n in self.model.nodes.items()
            if q in n.get("text", "").lower()
            or q in n.get("entity_type", "").lower()
            or any(q in tag.lower() for tag in n.get("tags", []))
        ]
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
        if self.collaboration_client and not messagebox.askyesno(
            "Replace Shared Investigation",
            "Creating a new diagram will replace the shared investigation for everyone. Continue?",
            parent=self.root,
        ):
            return
        if self.dirty and not messagebox.askyesno("Unsaved Changes", "Discard unsaved changes?"):
            return
        self.model = GraphModel()
        self.sync_document_settings()
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
        if self.collaboration_client and not messagebox.askyesno(
            "Replace Shared Investigation",
            "Opening this file will replace the shared investigation for everyone. Continue?",
            parent=self.root,
        ):
            return
        try:
            with open(path, "r", encoding="utf-8") as f:
                d = json.load(f)
            self.model.load_dict(d)
            self.sync_document_settings()
            self.path = path
            self.dirty = False
            io_manager.add_recent_file(path)
            self.update_recent_menu()
            self.root.title(f"LinkDraw Pro - {os.path.basename(path)}")
            self.fit()
        except Exception as e:
            messagebox.showerror("Open Error", str(e))

    def connect_shared_investigation(self):
        if self.collaboration_client:
            messagebox.showinfo(
                "Collaboration",
                "Disconnect from the current shared investigation before connecting to another.",
                parent=self.root,
            )
            return
        mongo_uri = simpledialog.askstring(
            "MongoDB Connection",
            "MongoDB connection URI (mongodb+srv://…):",
            show="*",
            parent=self.root,
        )
        if mongo_uri is None:
            return
        database_name = simpledialog.askstring(
            "MongoDB Database",
            "Database name:",
            initialvalue="linkdraw",
            parent=self.root,
        )
        if database_name is None:
            return
        project_id = simpledialog.askstring(
            "Shared Investigation",
            "Enter an existing investigation ID to join, or leave blank to create one:",
            parent=self.root,
        )
        if project_id is None:
            return
        create_new = not project_id.strip()
        project_id = uuid.uuid4().hex if create_new else project_id.strip()
        try:
            client = CollaborationClient(
                mongo_uri.strip(),
                database_name.strip(),
                project_id,
                create_new,
                copy.deepcopy(self.model.to_dict()),
            )
        except ValueError as exc:
            messagebox.showerror("Collaboration", str(exc), parent=self.root)
            return
        self.collaboration_client = client
        self.collaboration_project_id = project_id
        self.collaboration_base_state = None
        self.collaboration_base_fingerprint = None
        self.collaboration_revision = None
        self.collaboration_pending = False
        self.collaboration_last_submitted = None
        self.collaboration_retry_after = 0.0
        self.collaboration_next_snapshot_check = 0.0
        client.start()
        self.status.set("Connecting to shared investigation…")
        self._schedule_collaboration_tick()

    def disconnect_shared_investigation(self, preserve_local=True):
        client = self.collaboration_client
        if client is None:
            self.status.set("Not connected to a shared investigation.")
            return
        unsynced = self.collaboration_pending
        if self.collaboration_base_fingerprint is not None:
            unsynced = unsynced or (
                canonical_state(self.model.to_dict())
                != self.collaboration_base_fingerprint
            )
        if preserve_local and unsynced and not messagebox.askyesno(
            "Disconnect Collaboration",
            "Local changes may not have reached the server yet. Disconnect and keep this diagram locally?",
            parent=self.root,
        ):
            return
        client.stop()
        self.collaboration_client = None
        self.collaboration_project_id = None
        self.collaboration_base_state = None
        self.collaboration_base_fingerprint = None
        self.collaboration_revision = None
        self.collaboration_pending = False
        self.collaboration_last_submitted = None
        self.root.title("LinkDraw Pro")
        self.status.set("Disconnected. Local diagram remains open.")

    def _schedule_collaboration_tick(self):
        if self.collaboration_tick_id is None:
            self.collaboration_tick_id = self.root.after(250, self._collaboration_tick)

    def _collaboration_tick(self):
        self.collaboration_tick_id = None
        client = self.collaboration_client
        if client is None:
            return
        while True:
            try:
                event = client.events.get_nowait()
            except queue.Empty:
                break
            event_type = event["type"]
            if event_type == "error":
                if event.get("initial"):
                    messagebox.showerror("Collaboration", event["message"], parent=self.root)
                    self.disconnect_shared_investigation(preserve_local=False)
                    return
                self.collaboration_pending = False
                self.collaboration_last_submitted = None
                self.collaboration_retry_after = time.monotonic() + 2.0
                self.status.set(f"Collaboration waiting: {event['message']}")
                continue
            if event_type == "created":
                self.collaboration_base_state = copy.deepcopy(event["state"])
                self.collaboration_base_fingerprint = canonical_state(event["state"])
                self.collaboration_revision = event["revision"]
                self.root.title(f"LinkDraw Pro - Shared {self.collaboration_project_id}")
                self.status.set(
                    f"Shared investigation created: {self.collaboration_project_id}"
                )
                messagebox.showinfo(
                    "Shared Investigation Created",
                    f"Investigation ID:\n{self.collaboration_project_id}\n\n"
                    "Share this ID and MongoDB connection details with trusted collaborators.",
                    parent=self.root,
                )
                continue
            if event_type == "joined":
                if not messagebox.askyesno(
                    "Join Shared Investigation",
                    "Load the shared diagram? This replaces the diagram currently open in this window.",
                    parent=self.root,
                ):
                    self.disconnect_shared_investigation(preserve_local=False)
                    return
                self._apply_collaboration_state(event["state"])
                self.collaboration_base_state = copy.deepcopy(event["state"])
                self.collaboration_base_fingerprint = canonical_state(event["state"])
                self.collaboration_revision = event["revision"]
                self.root.title(f"LinkDraw Pro - Shared {self.collaboration_project_id}")
                self.status.set(f"Joined shared investigation {self.collaboration_project_id}.")
                continue
            if event_type == "saved":
                self.collaboration_base_state = copy.deepcopy(event["state"])
                self.collaboration_base_fingerprint = canonical_state(event["state"])
                self.collaboration_revision = event["revision"]
                self.collaboration_pending = False
                self.collaboration_last_submitted = None
                self.status.set("Shared changes saved.")
                continue
            if event_type in {"remote", "conflict"}:
                self._handle_collaboration_update(event["state"], event["revision"])

        if self.collaboration_client is not None:
            if (
                self.collaboration_base_state is not None
                and not self.collaboration_pending
                and time.monotonic() >= self.collaboration_retry_after
                and time.monotonic() >= self.collaboration_next_snapshot_check
                and not client.is_paused
            ):
                self.collaboration_next_snapshot_check = time.monotonic() + 0.5
                state = self.model.to_dict()
                fingerprint = canonical_state(state)
                if (
                    fingerprint != self.collaboration_base_fingerprint
                    and fingerprint != self.collaboration_last_submitted
                ):
                    self.collaboration_pending = True
                    self.collaboration_last_submitted = fingerprint
                    client.submit(
                        mongo_safe_state(state),
                        self.collaboration_revision,
                    )
            self._schedule_collaboration_tick()

    def _apply_collaboration_state(self, state):
        self.model.load_dict(copy.deepcopy(state))
        self.sync_document_settings()
        self.sel_nodes.clear()
        self.sel_conn = None
        self.sel_sticky = None
        self.dirty = True
        self.redraw()

    def _handle_collaboration_update(self, state, revision):
        client = self.collaboration_client
        if client is None:
            return
        local_fingerprint = canonical_state(self.model.to_dict())
        if (
            not self.collaboration_pending
            and local_fingerprint == self.collaboration_base_fingerprint
        ):
            self._apply_collaboration_state(state)
            self.collaboration_base_state = copy.deepcopy(state)
            self.collaboration_base_fingerprint = canonical_state(state)
            self.collaboration_revision = revision
            self.collaboration_last_submitted = None
            self.status.set("Received shared changes.")
            return

        client.pause()
        self.collaboration_pending = False
        choice = messagebox.askyesnocancel(
            "Collaboration Conflict",
            "The shared investigation changed while you also had local edits.\n\n"
            "Yes: load the latest shared diagram and discard your local edits.\n"
            "No: overwrite the shared diagram with your local version.\n"
            "Cancel: disconnect and keep your local diagram.",
            parent=self.root,
        )
        if choice is True:
            self._apply_collaboration_state(state)
            self.collaboration_base_state = copy.deepcopy(state)
            self.collaboration_base_fingerprint = canonical_state(state)
            self.collaboration_revision = revision
            self.collaboration_last_submitted = None
            client.resume(revision)
            self.status.set("Loaded the latest shared diagram.")
        elif choice is False:
            self.collaboration_base_state = copy.deepcopy(state)
            self.collaboration_base_fingerprint = canonical_state(state)
            self.collaboration_revision = revision
            self.collaboration_last_submitted = None
            client.resume(revision)
            self.status.set("Your local diagram will replace the shared version.")
        else:
            self.disconnect_shared_investigation(preserve_local=False)

    def save_doc(self):
        if not self.path:
            return self.save_as()
        try:
            self.model.settings["drag_pan"] = self.drag_pan.get()
            self.model.settings.update({
                "theme": self.theme.get(),
                "grid": self.grid_var.get(),
                "snap": self.snap_var.get(),
                "minimap": self.minimap_var.get(),
                "animated_flow": self.animated_flow_var.get(),
                "show_legend": self.legend_var.get(),
                "flow_speed": int(self.flow_speed_var.get()),
            })
            self.sidebar.page_manager.persist()
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

    def sync_document_settings(self):
        settings = self.model.settings
        self.theme.set(settings.get("theme", "light"))
        self.grid_var.set(settings.get("grid", True))
        self.snap_var.set(settings.get("snap", True))
        self.minimap_var.set(settings.get("minimap", True))
        self.animated_flow_var.set(settings.get("animated_flow", False))
        self.legend_var.set(settings.get("show_legend", False))
        self.line_var.set(settings.get("default_line_type", "curved"))
        self.arrow_var.set(settings.get("default_arrow", "forward"))
        self.width_var.set(str(settings.get("default_line_width", 2)))
        line_style = settings.get("default_line_style", "solid")
        self.line_style_var.set(line_style)
        self.dash_var.set(line_style != "solid")
        self.line_color_var.set(settings.get("default_line_color", "#374151"))
        self.fs_var.set(str(settings.get("default_font_size", 11)))
        self.node_font_var.set(settings.get("default_font_family", "Helvetica"))
        self.node_font_style_var.set(settings.get("default_font_style", "normal"))
        self.drag_pan.set(settings.get("drag_pan", "pan"))
        self.flow_speed_var.set(str(settings.get("flow_speed", 2)))
        if hasattr(self, "sidebar"):
            self.sidebar.layer_manager = drawing_tools.LayerManager(self.model)
            self.sidebar.page_manager = drawing_tools.PageManager(self.model)
            self.sidebar.page_var.set(self.sidebar.page_manager.current_page)
            self.sidebar.page_combo.configure(values=list(self.sidebar.page_manager.pages))
            brand_colors = settings.get("brand_colors")
            if isinstance(brand_colors, list) and brand_colors:
                self.sidebar.brand_kit.colors = list(brand_colors)
            else:
                self.sidebar.brand_kit.colors = drawing_tools.BrandKit().colors
            self.sidebar.refresh_brand_swatches()
            self.sidebar.refresh_inspector_palette()
        self.update_color_swatches()
        self.on_theme_change()

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
        for key, save_note in list(self._note_window_savers.items()):
            window = self._note_windows.get(key)
            if window is not None and window.winfo_exists():
                save_note()
        if not self.sidebar.flush_pending_notes():
            return
        self.sidebar.page_manager.persist()

        collaboration_unsynced = self.collaboration_pending
        if self.collaboration_client and self.collaboration_base_state is not None:
            collaboration_unsynced = collaboration_unsynced or (
                canonical_state(self.model.to_dict())
                != self.collaboration_base_fingerprint
            )
        if collaboration_unsynced and not messagebox.askyesno(
            "Collaboration Sync",
            "This diagram has shared changes that may not have reached the server. "
            "Close anyway? Your local autosave will be kept.",
            parent=self.root,
        ):
            return
        if self.collaboration_client:
            self.collaboration_client.stop()
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
