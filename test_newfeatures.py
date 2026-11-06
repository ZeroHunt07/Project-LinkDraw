import tempfile
import unittest
from pathlib import Path

import formula_engine
import io_manager
import linkdraw_investigation
from drawing_tools import LayerManager, PageManager
from graph_model import GraphModel
from PIL import Image


class TestNewFeatures(unittest.TestCase):
    def test_formula_sheet_arithmetic_ranges_and_errors(self):
        cells = {
            "A1": "3",
            "A2": "4",
            "B1": "=SUM(A1:A2)",
            "B2": "=B1^2",
        }
        self.assertEqual(formula_engine.evaluate_cell("B1", cells), 7)
        self.assertEqual(formula_engine.evaluate_cell("B2", cells), 49)
        with self.assertRaisesRegex(ValueError, "Circular reference"):
            formula_engine.evaluate_cell("A1", {"A1": "=B1", "B1": "=A1"})
        with self.assertRaisesRegex(ValueError, "Unsupported function"):
            formula_engine.evaluate_cell("A1", {"A1": "=__import__('os')"})

    def test_local_entity_detection(self):
        for value, expected in (
            ("https://example.com/path", "URL"),
            ("example.com", "Domain"),
            ("person@example.com", "Email"),
            ("192.0.2.1", "IP Address"),
            ("0123456789abcdef0123456789abcdef", "Hash"),
            ("+1 (555) 010-1234", "Phone"),
            ("not an indicator", ""),
        ):
            with self.subTest(value=value):
                self.assertEqual(linkdraw_investigation.detect_entity_type(value), expected)

    def test_layers_and_multiple_pages_persist(self):
        model = GraphModel()
        manager = PageManager(model)
        node_id = model.make_node(0, 0, "Page One")
        layer_manager = LayerManager(model)
        layer_manager.toggle_visible("Data")
        layer_manager.toggle_locked("Annotations")
        second_page = manager.add_page("Page 2")
        second_node = model.make_node(200, 0, "Page Two")
        manager.persist()

        loaded = GraphModel()
        loaded.load_dict(model.to_dict())
        loaded_pages = PageManager(loaded)
        self.assertEqual(loaded_pages.current_page, second_page)
        self.assertIn(second_node, loaded.nodes)
        loaded_pages.switch_page("Page 1")
        self.assertIn(node_id, loaded.nodes)
        self.assertFalse(loaded.settings["layers"]["Data"]["visible"])
        self.assertTrue(loaded.settings["layers"]["Annotations"]["locked"])
        self.assertGreater(loaded.new_id(), second_node)

    def test_custom_connection_bend_and_new_line_styles_export(self):
        model = GraphModel()
        start = model.make_node(0, 0, "Start")
        end = model.make_node(200, 0, "End")
        edge = model.make_conn(start, end, type_="straight", line_style="long-dash")
        straight = io_manager.get_conn_geom(model, model.conns[edge])
        model.conns[edge]["bend"] = 65
        curved = io_manager.get_conn_geom(model, model.conns[edge])
        self.assertEqual(straight[0], "line")
        self.assertEqual(curved[0], "curve")
        self.assertNotEqual(straight[1], curved[1])
        with tempfile.TemporaryDirectory() as temp_dir:
            path = Path(temp_dir) / "styled.svg"
            io_manager.export_svg(model, path)
            self.assertIn('stroke-dasharray="12 5"', path.read_text(encoding="utf-8"))

    def test_image_nodes_are_included_in_visual_exports(self):
        model = GraphModel()
        with tempfile.TemporaryDirectory() as temp_dir:
            image_path = Path(temp_dir) / "sample.png"
            svg_path = Path(temp_dir) / "diagram.svg"
            png_path = Path(temp_dir) / "diagram.png"
            Image.new("RGB", (20, 12), "#ff0000").save(image_path)
            node_id = model.make_node(0, 0, "Image")
            model.nodes[node_id]["image_path"] = str(image_path)
            io_manager.export_svg(model, svg_path)
            self.assertIn("data:image/png;base64,", svg_path.read_text(encoding="utf-8"))
            io_manager.export_raster(model, png_path)
            with Image.open(png_path) as exported:
                self.assertEqual(exported.format, "PNG")


if __name__ == "__main__":
    unittest.main()
