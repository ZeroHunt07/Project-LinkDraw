import unittest

import linkdraw_investigation
from graph_model import GraphModel


class TestInvestigationFeatures(unittest.TestCase):
    def test_entity_palette_and_transforms_are_available(self):
        self.assertIn("Domain", linkdraw_investigation.ENTITY_TYPES)
        self.assertEqual(
            linkdraw_investigation.InvestigationEngine.get_available_transforms("Email"),
            [
                ("Extract domain", "email_to_domain"),
                ("Extract username", "email_to_username"),
            ],
        )

    def test_email_transforms_create_typed_connected_entities(self):
        model = GraphModel()
        source_id = model.make_node(0, 0, "alice@example.com")
        model.nodes[source_id]["entity_type"] = "Email"

        spawned = linkdraw_investigation.InvestigationEngine.run_transform(
            "email_to_domain", model.nodes[source_id], model
        )

        self.assertEqual(len(spawned), 1)
        target = model.nodes[spawned[0]]
        self.assertEqual(target["text"], "example.com")
        self.assertEqual(target["entity_type"], "Domain")
        self.assertEqual(len(model.conns), 1)

        second_run = linkdraw_investigation.InvestigationEngine.run_transform(
            "email_to_domain", model.nodes[source_id], model
        )
        self.assertEqual(second_run, [])
        self.assertEqual(len(model.nodes), 2)
        self.assertEqual(len(model.conns), 1)

    def test_pagerank_metric_updates_requested_view(self):
        model = GraphModel()
        first = model.make_node(0, 0, "A")
        second = model.make_node(100, 0, "B")
        model.make_conn(first, second)

        linkdraw_investigation.apply_metric_view(model, metric="pagerank", mode="both")

        self.assertTrue(all(node["w"] >= 80 for node in model.nodes.values()))
        self.assertTrue(all(node["h"] >= 40 for node in model.nodes.values()))
        self.assertTrue(all(node["color"].startswith("#") for node in model.nodes.values()))
        self.assertEqual(model.spatial.query_rect(-100, -100, 200, 100, item_type="node"), {first, second})


if __name__ == "__main__":
    unittest.main()
