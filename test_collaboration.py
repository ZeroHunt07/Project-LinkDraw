import unittest
from unittest.mock import patch

from bson import BSON
from bson.errors import InvalidDocument
from collaboration_client import (
    CollaborationClient,
    POLL_INTERVAL_SECONDS,
    canonical_state,
    mongo_safe_state,
)
from drawing_tools import PageManager
from graph_model import GraphModel


class FakeMongoClient:
    def __init__(self, _uri):
        self.databases = {}
        self.admin = self

    def command(self, _command):
        return {"ok": 1}

    def __getitem__(self, database_name):
        return self.databases.setdefault(database_name, FakeDatabase())

    def close(self):
        pass

    def find_one(self, query, _projection=None):
        raise NotImplementedError

    def insert_one(self, document):
        raise NotImplementedError

    def update_one(self, query, update):
        raise NotImplementedError


class FakeDatabase:
    def __init__(self):
        self.collections = {}

    def __getitem__(self, collection_name):
        return self.collections.setdefault(collection_name, FakeCollection())


class FakeCollection:
    def __init__(self):
        self.documents = {}

    def find_one(self, query, _projection=None):
        return self.documents.get(query["_id"])

    def insert_one(self, document):
        self.documents[document["_id"]] = dict(document)

    def update_one(self, query, update):
        doc = self.documents.get(query["_id"])
        if doc is None or doc["revision"] != query["revision"]:
            class Result:
                matched_count = 0
            return Result()
        doc.update(update["$set"])
        doc["revision"] += update["$inc"]["revision"]

        class Result:
            matched_count = 1
        return Result()


class TestCollaborationClient(unittest.TestCase):
    def test_canonical_state_ignores_dictionary_order(self):
        first = {"nodes": [{"id": 1, "text": "A"}], "settings": {"grid": True}}
        second = {"settings": {"grid": True}, "nodes": [{"text": "A", "id": 1}]}
        self.assertEqual(canonical_state(first), canonical_state(second))

    def test_normalizes_integer_page_keys_for_bson(self):
        model = GraphModel()
        model.make_node(1, 2, "one")
        PageManager(model).persist()
        snapshot = model.to_dict()

        with self.assertRaises(InvalidDocument):
            BSON.encode({"state": snapshot})

        safe_snapshot = mongo_safe_state(snapshot)
        BSON.encode({"state": safe_snapshot})
        self.assertIn("1", safe_snapshot["pages"]["Page 1"]["nodes"])
        self.assertEqual(canonical_state(snapshot), canonical_state(safe_snapshot))

    def test_poll_interval_is_two_seconds(self):
        self.assertEqual(POLL_INTERVAL_SECONDS, 2)

    def test_rejects_non_mongodb_uri(self):
        with self.assertRaises(ValueError):
            CollaborationClient("https://example.com", "linkdraw", "case-1", False, {})

    def test_rejects_invalid_database_name(self):
        with self.assertRaises(ValueError):
            CollaborationClient("mongodb://localhost", "bad/name", "case-1", False, {})

    def test_rejects_invalid_project_id(self):
        with self.assertRaises(ValueError):
            CollaborationClient("mongodb://localhost", "linkdraw", "bad/id", False, {})

    def test_create_and_join_using_mongo_collection(self):
        fake_mongo = FakeMongoClient("mongodb://localhost")
        initial = {
            "nodes": [{"id": 1, "text": "first"}],
            "pages": {"Page 1": {"nodes": {1: {"id": 1, "text": "first"}}}},
        }
        expected = mongo_safe_state(initial)
        with patch("collaboration_client.MongoClient", return_value=fake_mongo):
            creator = CollaborationClient(
                "mongodb://localhost", "linkdraw", "case-1", True, initial
            )
            creator.start()
            created = creator.events.get(timeout=1)
            creator.stop()
        self.assertEqual(created["type"], "created")
        self.assertEqual(created["revision"], 0)

        with patch("collaboration_client.MongoClient", return_value=fake_mongo):
            joiner = CollaborationClient(
                "mongodb://localhost", "linkdraw", "case-1", False, {}
            )
            joiner.start()
            joined = joiner.events.get(timeout=1)
            joiner.stop()
        self.assertEqual(joined["type"], "joined")
        self.assertEqual(joined["state"], expected)


if __name__ == "__main__":
    unittest.main()
