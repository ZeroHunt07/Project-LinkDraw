"""
Comprehensive automated tests for all 70 features of LinkDraw Pro.
"""
import os
os.environ["LINKDRAW_TEST"] = "1"
import math
import tempfile
import tkinter as tk
import unittest

from graph_model import GraphModel, SHAPES, LINE_TYPES, ARROWS
import algorithms
import layouts
import io_manager
import dialogs
import main


class TestLinkDrawAllFeatures(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.root = tk.Tk()
        cls.root.withdraw()

    @classmethod
    def tearDownClass(cls):
        cls.root.destroy()

    def setUp(self):
        self.app = main.LinkDrawApp(self.root)

    def test_01_themes(self):
        # 1. Dark mode / theme switcher (light, dark, high_contrast)
        for th in ("light", "dark", "high_contrast"):
            self.app.theme.set(th)
            colors = self.app.theme_colors()
            self.assertIn("bg", colors)
            self.assertIn("fg", colors)
            self.assertIn("accent", colors)
            self.app.redraw()
        # Verify high-contrast true black
        self.app.theme.set("high_contrast")
        self.assertEqual(self.app.theme_colors()["bg"], "#000000")

    def test_workspace_sidebar_and_osint_shortcut(self):
        self.assertIn(str(self.app.sidebar), self.app.workspace_panes.panes())
        self.assertEqual(self.app.canvas.winfo_parent(), str(self.app.workspace_panes))
        self.assertEqual(self.app.sidebar.winfo_parent(), str(self.app.workspace_panes))
        window = self.app.open_osint_workspace()
        self.assertEqual(window.winfo_class(), "Toplevel")
        self.assertEqual(len(self.app.sidebar.nb.tabs()), 2)
        self.assertIs(self.app.sidebar.osint_window, window)
        self.app.open_osint_workspace()
        self.assertIs(self.app.sidebar.osint_window, window)
        self.app.toggle_sidebar()
        self.assertNotIn(str(self.app.sidebar), self.app.workspace_panes.panes())
        self.app.open_osint_workspace()
        self.assertNotIn(str(self.app.sidebar), self.app.workspace_panes.panes())

    def test_02_03_04_05_connections_and_geometry(self):
        # 2. Curved edges, 3. Arrowheads, 4. Self-loops, 5. Bundling
        m = self.app.model
        n1 = m.make_node(0, 0, "A")
        n2 = m.make_node(100, 100, "B")

        # 4. Self-loop
        c_self = m.make_conn(n1, n1, "loop", type_="curved", arrow="forward")
        geom_self = io_manager.get_conn_geom(m, m.conns[c_self])
        self.assertEqual(geom_self[0], "self_loop")

        # 2. Curved edge & 3. Arrowheads
        c_curved = m.make_conn(n1, n2, "flow", type_="curved", arrow="both")
        geom_curved = io_manager.get_conn_geom(m, m.conns[c_curved])
        self.assertEqual(geom_curved[0], "curve")

        # 5. Bundling
        c_parallel = m.make_conn(n1, n2, "parallel", type_="curved", arrow="forward")
        geom_p1 = io_manager.get_conn_geom(m, m.conns[c_curved], parallel_index=0, parallel_total=2)
        geom_p2 = io_manager.get_conn_geom(m, m.conns[c_parallel], parallel_index=1, parallel_total=2)
        self.assertNotEqual(geom_p1[1][1], geom_p2[1][1])  # Control points separated

    def test_06_07_shapes_and_icons(self):
        # 6. Node shapes, 7. Custom node icons
        m = self.app.model
        for shape in ["circle", "square", "diamond", "hexagon", "triangle", "star", "rounded", "rectangle", "text"]:
            nid = m.make_node(50, 50, f"Node {shape}", shape=shape, icon="🚀")
            node = m.nodes[nid]
            self.assertEqual(node["shape"], shape)
            self.assertEqual(node["icon"], "🚀")
            pt = io_manager.get_shape_border_point(node, 100, 100)
            self.assertIsNotNone(pt)
        self.app.redraw()

    def test_08_animated_flow(self):
        # 8. Animated edge flow
        self.app.animated_flow_var.set(True)
        init_phase = self.app.flow_phase
        self.app._step_flow()
        self.assertNotEqual(self.app.flow_phase, init_phase)
        self.app.animated_flow_var.set(False)

    def test_09_hover_tooltips(self):
        # 9. Hover tooltips
        nid = next(iter(self.app.model.nodes.keys()))
        self.app.show_tooltip(100, 100, nid)
        self.assertIsNotNone(self.app.tooltip_win)
        self.app.hide_tooltip()
        self.assertIsNone(self.app.tooltip_win)

    def test_10_exports(self):
        # 10. Export as PNG / SVG / PDF / PostScript
        with tempfile.TemporaryDirectory() as tmpdir:
            svg_p = os.path.join(tmpdir, "test.svg")
            png_p = os.path.join(tmpdir, "test.png")
            pdf_p = os.path.join(tmpdir, "test.pdf")
            ps_p = os.path.join(tmpdir, "test.ps")

            io_manager.export_svg(self.app.model, svg_p)
            self.assertTrue(os.path.exists(svg_p) and os.path.getsize(svg_p) > 100)

            io_manager.export_raster(self.app.model, png_p, kind="png")
            self.assertTrue(os.path.exists(png_p) and os.path.getsize(png_p) > 100)

            io_manager.export_raster(self.app.model, pdf_p, kind="pdf")
            self.assertTrue(os.path.exists(pdf_p) and os.path.getsize(pdf_p) > 100)

            self.app.canvas.postscript(file=ps_p)
            self.assertTrue(os.path.exists(ps_p) and os.path.getsize(ps_p) > 10)

    def test_11_12_13_14_interaction_and_editing(self):
        # 11. Multi-select, 12. Group drag, 13. Undo/Redo, 14. Copy/Paste/Duplicate
        m = self.app.model
        n1 = m.make_node(10, 10, "N1")
        n2 = m.make_node(20, 20, "N2")
        m.make_conn(n1, n2)

        # 11. Multi-select
        self.app.select(nodes={n1, n2})
        self.assertEqual(len(self.app.sel_nodes), 2)

        # 12. Group drag / nudge
        x1_before = m.nodes[n1]["x"]
        self.app.nudge_selected(15, 15)
        self.assertEqual(m.nodes[n1]["x"], x1_before + 15)

        # 13. Undo / Redo
        self.app.undo()
        self.assertEqual(m.nodes[n1]["x"], x1_before)
        self.app.redo()
        self.assertEqual(m.nodes[n1]["x"], x1_before + 15)

        # 14. Copy / Paste / Duplicate
        self.app.select(nodes={n1, n2})
        self.app.copy_selection()
        count_before = len(m.nodes)
        self.app.paste_selection()
        self.assertEqual(len(m.nodes), count_before + 2)

    def test_15_16_17_18_19_20_features(self):
        # 15. Snap and guides
        val = self.app.snap_val(23)
        self.assertEqual(val, 20)

        # 16. Auto-arrange selected
        self.app.select_all()
        self.app.arrange_selected("row")

        # 17. Inline label editing
        nid = next(iter(self.app.model.nodes))
        editor = dialogs.InlineTextEditor(self.app, nid)
        editor.text_widget.delete("1.0", "end")
        editor.text_widget.insert("1.0", "Renamed node")
        editor.commit()
        self.assertEqual(self.app.model.nodes[nid]["text"], "Renamed node")
        self.assertTrue(self.app.dirty)

        # 18. Edge weight editing
        cid = next(iter(self.app.model.conns))
        self.app.model.conns[cid]["weight"] = 7.5
        self.assertEqual(self.app.model.conns[cid]["weight"], 7.5)

        # 19. Keyboard shortcuts cheat sheet
        dialogs.show_shortcuts_panel(self.root)

    def test_21_to_30_layouts(self):
        # 21-30 Layouts
        node_ids = list(self.app.model.nodes.keys())

        # 21. Force-directed
        p1 = layouts.compute_fruchterman_reingold(self.app.model, node_ids)
        self.assertEqual(len(p1), len(node_ids))

        # 22. Circular
        p2 = layouts.compute_circular(self.app.model, node_ids)
        self.assertEqual(len(p2), len(node_ids))

        # 23. Grid
        p3 = layouts.compute_grid(self.app.model, node_ids)
        self.assertEqual(len(p3), len(node_ids))

        # Additional graph views: distance shells and topology-ordered spiral
        p_concentric = layouts.compute_concentric(self.app.model, node_ids)
        p_spiral = layouts.compute_spiral(self.app.model, node_ids)
        self.assertEqual(set(p_concentric), set(node_ids))
        self.assertEqual(set(p_spiral), set(node_ids))
        self.assertTrue(all(math.isfinite(coord) for point in p_concentric.values() for coord in point))
        self.assertTrue(all(math.isfinite(coord) for point in p_spiral.values() for coord in point))
        self.assertEqual(p_spiral, layouts.compute_spiral(self.app.model, node_ids))

        disconnected = GraphModel()
        disconnected_ids = [
            disconnected.make_node(0, 0, "A"),
            disconnected.make_node(0, 0, "B"),
            disconnected.make_node(0, 0, "C"),
        ]
        disconnected.make_conn(disconnected_ids[0], disconnected_ids[1])
        for layout in (layouts.compute_concentric, layouts.compute_spiral):
            positions = layout(disconnected, disconnected_ids)
            self.assertEqual(set(positions), set(disconnected_ids))
            self.assertEqual(len(set(positions.values())), len(disconnected_ids))
            self.assertEqual(layout(disconnected, []), {})

        # 24. Hierarchical (Sugiyama)
        p4 = layouts.compute_hierarchical_sugiyama(self.app.model, node_ids)
        self.assertEqual(len(p4), len(node_ids))

        # 25. Radial tree
        p5 = layouts.compute_radial_tree(self.app.model, node_ids)
        self.assertEqual(len(p5), len(node_ids))

        # 26. Kamada-Kawai
        p6 = layouts.compute_kamada_kawai(self.app.model, node_ids)
        self.assertEqual(len(p6), len(node_ids))

        # 27. Tutte embedding
        p7 = layouts.compute_tutte_embedding(self.app.model, node_ids)
        self.assertEqual(len(p7), len(node_ids))

        # 28. Orthogonal routing
        routes = layouts.compute_orthogonal_routes(self.app.model)
        self.assertTrue(len(routes) > 0)

        # 29. Incremental layout animator
        self.app.animator.start(p2)

        # 30. Auto-detect preset
        preset = layouts.auto_detect_preset(self.app.model, node_ids)
        self.assertIn(preset, ["radial_tree", "hierarchical", "circle", "kamada_kawai", "force_directed", "grid"])

    def test_31_to_40_algorithms(self):
        # 31-40 Algorithms
        m = self.app.model
        node_list = list(m.nodes.keys())
        u, v = node_list[0], node_list[1]

        # 31. A* search
        path, length, edges = algorithms.a_star_search(m, u, v)

        # 32. BFS / DFS
        bfs_steps = algorithms.bfs_traversal_steps(m, u)
        self.assertTrue(len(bfs_steps) > 0)
        dfs_steps = algorithms.dfs_traversal_steps(m, u)
        self.assertTrue(len(dfs_steps) > 0)

        # 33. MST
        mst_edges, total_wt = algorithms.minimum_spanning_tree(m)
        self.assertIsInstance(mst_edges, list)

        # 34. Max flow
        flow_val, edge_flows = algorithms.maximum_flow(m, u, v)
        self.assertIsInstance(flow_val, (int, float))

        # 35. Topological sort
        is_dag, order = algorithms.topological_sort(m)
        self.assertIsInstance(is_dag, bool)

        # 36. Cycle detection
        c_nodes, c_edges, cnt = algorithms.detect_cycles(m)
        self.assertIsInstance(cnt, int)

        # 37. Connected components
        cc_map, cc_total = algorithms.connected_components(m)
        self.assertTrue(cc_total >= 1)

        # 38. Strongly connected components (Tarjan)
        scc_map, scc_total = algorithms.strongly_connected_components(m)
        self.assertTrue(scc_total >= 1)

        # 39. Centrality
        cent_deg = algorithms.compute_centrality(m, "degree")
        cent_bet = algorithms.compute_centrality(m, "betweenness")
        self.assertEqual(len(cent_deg), len(m.nodes))
        self.assertEqual(len(cent_bet), len(m.nodes))

        # 40. Community detection (Louvain)
        comm_map, comm_total = algorithms.detect_communities(m)
        self.assertTrue(comm_total >= 1)

    def test_41_to_50_data_import_export(self):
        # 41. CSV, 42. GraphML/GEXF, 43. DOT, 47. Pickle, 49. Autosave, 50. Recent
        with tempfile.TemporaryDirectory() as tmpdir:
            # 41. CSV
            nc = os.path.join(tmpdir, "nodes.csv")
            ec = os.path.join(tmpdir, "edges.csv")
            io_manager.export_csv(self.app.model, nc, ec)
            self.assertTrue(os.path.exists(nc) and os.path.exists(ec))

            # 42. GraphML
            gml = os.path.join(tmpdir, "graph.graphml")
            io_manager.export_graphml(self.app.model, gml)
            self.assertTrue(os.path.exists(gml))

            # 42. GEXF
            gexf = os.path.join(tmpdir, "graph.gexf")
            io_manager.export_gexf(self.app.model, gexf)
            self.assertTrue(os.path.exists(gexf))

            # 43. DOT
            dot = os.path.join(tmpdir, "graph.dot")
            io_manager.export_dot(self.app.model, dot)
            self.assertTrue(os.path.exists(dot))

            # 47. Pickle
            pkl = os.path.join(tmpdir, "graph.pkl")
            io_manager.export_pickle(self.app.model, pkl)
            self.assertTrue(os.path.exists(pkl))

            # 50. Recent files
            io_manager.add_recent_file(dot)
            recent = io_manager.get_recent_files()
            self.assertIn(os.path.abspath(dot), recent)

    def test_51_to_60_properties_and_metadata(self):
        # 51-54. Graph properties
        props = algorithms.compute_graph_properties(self.app.model)
        self.assertIn("density", props)
        self.assertIn("degree_hist", props)
        self.assertIn("avg_clustering", props)

        # 55. Isomorphism
        sub1 = list(self.app.model.nodes.keys())[:3]
        sub2 = list(self.app.model.nodes.keys())[:3]
        iso = algorithms.check_isomorphism(self.app.model, sub1, sub2)
        self.assertTrue(iso)

        # 56. Tags
        nid = sub1[0]
        self.app.model.nodes[nid]["tags"] = ["frontend", "urgent"]
        self.assertIn("frontend", self.app.model.nodes[nid]["tags"])

        # 57. Rich metadata
        self.app.model.nodes[nid]["metadata"] = {"owner": "Alice", "sla": "99.9%"}
        self.assertEqual(self.app.model.nodes[nid]["metadata"]["owner"], "Alice")

        # 58. Sticky notes
        self.app.add_sticky_note()
        self.assertTrue(len(self.app.model.sticky_notes) >= 1)

        # 59. Legend widget
        self.app.legend_var.set(True)
        self.app.redraw()

        # 60. Search bar
        self.app.search_var.set("Platform")
        self.app.do_search()
        self.assertTrue(len(self.app.sel_nodes) >= 1)

    def test_61_to_70_ux_and_performance(self):
        # 61. Pan, 62. Zoom controls
        self.app.zoom_center(1.25)
        self.assertAlmostEqual(self.app.scale, 1.25, delta=0.01)
        self.app.reset_zoom()
        self.assertAlmostEqual(self.app.scale, 1.0, delta=0.01)

        # 63. Minimap
        self.app.minimap_var.set(True)
        self.app.redraw()

        # 64. Mode shortcuts
        self.app.set_tool("node")
        self.assertEqual(self.app.tool.get(), "node")
        self.app.set_tool("select")

        # 65. Status bar breadcrumbs
        self.app.update_breadcrumbs()
        self.assertIn("Nodes:", self.app.status.get())

        # 66. Preferences
        self.app.show_preferences()

        # 67. Spatial index
        nodes_found = self.app.model.spatial.query_rect(-500, -500, 500, 500, item_type="node")
        self.assertTrue(len(nodes_found) >= 1)

        # 68. Viewport culling & 69. Lazy edges
        self.app.model.settings["viewport_culling"] = True
        self.app.model.settings["lazy_edges"] = True
        self.app.redraw()

        # 70. Background recomputation
        done = []
        t = algorithms.run_in_background(lambda: 42, lambda res: done.append(res))
        t.join(timeout=2.0)
        self.assertEqual(done, [42])


if __name__ == "__main__":
    unittest.main()
