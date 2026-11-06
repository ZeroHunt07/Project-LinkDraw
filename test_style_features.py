import csv
import tempfile
import unittest
from pathlib import Path

import io_manager
from graph_model import GraphModel
from PIL import Image


class TestStyleFeatures(unittest.TestCase):
    def setUp(self):
        self.model = GraphModel()
        self.source = self.model.make_node(0, 0, "Source")
        self.target = self.model.make_node(180, 0, "Target")
        self.connection = self.model.make_conn(
            self.source,
            self.target,
            label="replicates",
            type_="orthogonal",
            arrow="both",
            color="#7c3aed",
            width=4,
            line_style="dash-dot",
        )

    def test_connection_defaults_and_legacy_dash_data(self):
        self.model.settings.update({
            "default_line_type": "straight",
            "default_arrow": "none",
            "default_line_style": "dotted",
            "default_line_color": "#16a34a",
            "default_line_width": 3,
        })
        created = self.model.make_conn(self.source, self.target)
        connection = self.model.conns[created]
        self.assertEqual(connection["type"], "straight")
        self.assertEqual(connection["arrow"], "none")
        self.assertEqual(connection["line_style"], "dotted")
        self.assertEqual(connection["color"], "#16a34a")
        self.assertEqual(connection["width"], 3)
        restored_settings = GraphModel()
        restored_settings.load_dict(self.model.to_dict())
        self.assertEqual(restored_settings.settings["default_line_style"], "dotted")
        self.assertEqual(restored_settings.settings["default_line_color"], "#16a34a")

        legacy = GraphModel()
        legacy.load_dict({
            "nodes": [],
            "conns": [{"id": 8, "a": 1, "b": 2, "dash": True}],
        })
        self.assertEqual(legacy.conns[8]["line_style"], "dashed")

    def test_csv_and_vector_exports_keep_connection_pattern(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            nodes_path = Path(temp_dir) / "nodes.csv"
            edges_path = Path(temp_dir) / "edges.csv"
            svg_path = Path(temp_dir) / "diagram.svg"
            dot_path = Path(temp_dir) / "diagram.dot"
            io_manager.export_csv(self.model, nodes_path, edges_path)

            with edges_path.open(encoding="utf-8", newline="") as edge_file:
                row = next(csv.DictReader(edge_file))
            self.assertEqual(row["line_style"], "dash-dot")
            restored = GraphModel()
            io_manager.import_csv(restored, nodes_path, edges_path)
            imported_connection = next(iter(restored.conns.values()))
            self.assertEqual(imported_connection["line_style"], "dash-dot")
            self.assertEqual(imported_connection["color"], "#7c3aed")

            io_manager.export_svg(self.model, svg_path)
            self.assertIn('stroke-dasharray="8 4 2 4"', svg_path.read_text(encoding="utf-8"))
            io_manager.export_dot(self.model, dot_path)
            self.assertIn('style="dashed"', dot_path.read_text(encoding="utf-8"))
            self.assertIn('penwidth="4"', dot_path.read_text(encoding="utf-8"))

    def test_graphml_and_gexf_keep_connection_style(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            for extension, export_graph, import_graph in (
                (".graphml", io_manager.export_graphml, io_manager.import_graphml),
                (".gexf", io_manager.export_gexf, io_manager.import_gexf),
            ):
                path = Path(temp_dir) / f"diagram{extension}"
                restored = GraphModel()
                export_graph(self.model, path)
                import_graph(restored, path)

                connection = next(iter(restored.conns.values()))
                self.assertEqual(connection["line_style"], "dash-dot")
                self.assertEqual(connection["color"], "#7c3aed")
                self.assertEqual(connection["width"], 4)
                self.assertEqual(connection["arrow"], "both")

    def test_node_typography_defaults_legacy_load_and_exports(self):
        legacy = GraphModel()
        legacy.load_dict({"nodes": [{"id": 7, "x": 0, "y": 0}], "conns": []})
        legacy_node = legacy.nodes[7]
        self.assertEqual(legacy_node["font_family"], "Helvetica")
        self.assertEqual(legacy_node["font_style"], "normal")
        self.assertEqual(legacy_node["text_color"], "")

        self.model.nodes[self.source].update({
            "text": "Styled node",
            "font_family": "Courier New",
            "font_style": "bold italic",
            "fs": 20,
            "text_color": "#123456",
        })
        restored = GraphModel()
        restored.load_dict(self.model.to_dict())
        self.assertEqual(restored.nodes[self.source]["font_family"], "Courier New")
        self.assertEqual(restored.nodes[self.source]["font_style"], "bold italic")
        self.assertEqual(restored.nodes[self.source]["text_color"], "#123456")

        with tempfile.TemporaryDirectory() as temp_dir:
            svg_path = Path(temp_dir) / "styled.svg"
            png_path = Path(temp_dir) / "styled.png"
            io_manager.export_svg(self.model, svg_path)
            svg = svg_path.read_text(encoding="utf-8")
            self.assertIn('font-family="Courier New"', svg)
            self.assertIn('font-weight="bold"', svg)
            self.assertIn('font-style="italic"', svg)
            self.assertIn('font-size="20"', svg)
            self.assertIn('fill="#123456">Styled node</text>', svg)

            io_manager.export_raster(self.model, png_path)
            with Image.open(png_path) as image:
                self.assertEqual(image.format, "PNG")
                self.assertGreater(image.width, 0)
                self.assertGreater(image.height, 0)


if __name__ == "__main__":
    unittest.main()
