"""Polling client for shared LinkDraw investigations stored directly in MongoDB."""
import json
import queue
import re
import threading
import time

from pymongo import MongoClient
from pymongo.errors import DuplicateKeyError, PyMongoError


POLL_INTERVAL_SECONDS = 2
PROJECT_ID_PATTERN = re.compile(r"^[A-Za-z0-9_-]{1,80}$")


def canonical_state(state):
    return json.dumps(
        mongo_safe_state(state),
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
    )


def mongo_safe_state(value):
    """Convert mappings to BSON-compatible documents without mutating the model."""
    if isinstance(value, dict):
        normalized = {}
        for key, child in value.items():
            string_key = str(key)
            if string_key in normalized:
                raise ValueError(f"Snapshot contains duplicate keys after BSON conversion: {string_key}")
            normalized[string_key] = mongo_safe_state(child)
        return normalized
    if isinstance(value, list):
        return [mongo_safe_state(item) for item in value]
    return value


class CollaborationClient:
    def __init__(self, mongo_uri, database_name, project_id, create_new, initial_state):
        if not mongo_uri or not mongo_uri.startswith(("mongodb://", "mongodb+srv://")):
            raise ValueError("Enter a valid mongodb:// or mongodb+srv:// connection URI.")
        if not database_name or not re.fullmatch(r"[A-Za-z0-9_-]{1,63}", database_name):
            raise ValueError("The MongoDB database name may contain only letters, numbers, hyphens, and underscores.")
        if not PROJECT_ID_PATTERN.fullmatch(project_id):
            raise ValueError("The shared investigation ID may contain only letters, numbers, hyphens, and underscores.")

        self.mongo_uri = mongo_uri
        self.database_name = database_name
        self.project_id = project_id
        self.create_new = create_new
        self.initial_state = mongo_safe_state(initial_state)
        self.events = queue.Queue()
        self._outbound = queue.Queue()
        self._stop = threading.Event()
        self._paused = threading.Event()
        self._thread = None
        self._mongo_client = None
        self._projects = None
        self.revision = None

    def start(self):
        if self._thread is not None:
            raise RuntimeError("The collaboration client has already been started.")
        self._thread = threading.Thread(target=self._run, name="LinkDrawCollaboration", daemon=True)
        self._thread.start()

    def submit(self, state, expected_revision):
        if self._stop.is_set() or self._paused.is_set():
            return
        self._outbound.put((state, expected_revision))

    @property
    def is_paused(self):
        return self._paused.is_set()

    def pause(self):
        self._paused.set()

    def resume(self, revision):
        self.revision = revision
        self._paused.clear()

    def stop(self):
        self._stop.set()
        if self._mongo_client is not None:
            self._mongo_client.close()

    def _read_project(self):
        return self._projects.find_one(
            {"_id": self.project_id},
            {"revision": 1, "state": 1},
        )

    def _create_project(self):
        self._projects.insert_one({
            "_id": self.project_id,
            "revision": 0,
            "state": self.initial_state,
            "updated_at": time.time(),
        })
        return {"revision": 0, "state": self.initial_state}

    def _save_project(self, state, expected_revision):
        state = mongo_safe_state(state)
        result = self._projects.update_one(
            {"_id": self.project_id, "revision": expected_revision},
            {
                "$set": {"state": state, "updated_at": time.time()},
                "$inc": {"revision": 1},
            },
        )
        if result.matched_count != 1:
            return None
        return expected_revision + 1

    def _emit_remote_state(self, project, event_type="remote"):
        if project is None:
            raise RuntimeError("The shared investigation was removed from MongoDB.")
        if project.get("state") is None:
            return
        self.revision = project["revision"]
        self.events.put({
            "type": event_type,
            "revision": self.revision,
            "state": project["state"],
        })

    def _run(self):
        try:
            self._mongo_client = MongoClient(self.mongo_uri)
            self._mongo_client.admin.command("ping")
            self._projects = self._mongo_client[self.database_name]["investigations"]
            project = self._read_project()
            if project is None:
                if not self.create_new:
                    self.events.put({
                        "type": "error",
                        "initial": True,
                        "message": "That shared investigation was not found. Check its ID or create a new one.",
                    })
                    return
                try:
                    project = self._create_project()
                except DuplicateKeyError:
                    self.events.put({
                        "type": "error",
                        "initial": True,
                        "message": "That investigation ID is already in use. Try connecting again.",
                    })
                    return
                self.revision = project["revision"]
                self.events.put({
                    "type": "created",
                    "revision": self.revision,
                    "state": project["state"],
                })
            else:
                if self.create_new:
                    self.events.put({
                        "type": "error",
                        "initial": True,
                        "message": "That generated investigation ID is already in use. Try creating it again.",
                    })
                    return
                self.revision = project["revision"]
                self.events.put({
                    "type": "joined",
                    "revision": self.revision,
                    "state": project["state"],
                })
        except PyMongoError as exc:
            self.events.put({
                "type": "error",
                "initial": True,
                "message": f"Cannot connect to MongoDB: {exc}",
            })
            return

        next_poll = time.monotonic() + POLL_INTERVAL_SECONDS
        while not self._stop.is_set():
            wait = max(0.0, next_poll - time.monotonic())
            try:
                state, expected_revision = self._outbound.get(timeout=wait)
            except queue.Empty:
                state = None
                expected_revision = None

            if state is not None and not self._paused.is_set():
                try:
                    revision = self._save_project(state, expected_revision)
                    if revision is None:
                        project = self._read_project()
                        self._emit_remote_state(project, "conflict")
                    else:
                        self.revision = revision
                        self.events.put({
                            "type": "saved",
                            "revision": revision,
                            "state": state,
                        })
                except PyMongoError as exc:
                    self.events.put({"type": "error", "message": f"MongoDB sync failed: {exc}"})
                next_poll = time.monotonic() + POLL_INTERVAL_SECONDS

            if self._stop.is_set() or time.monotonic() < next_poll:
                continue
            try:
                project = self._read_project()
                if project and project["revision"] != self.revision:
                    self._emit_remote_state(project)
            except PyMongoError as exc:
                self.events.put({"type": "error", "message": f"MongoDB polling failed: {exc}"})
            next_poll = time.monotonic() + POLL_INTERVAL_SECONDS
