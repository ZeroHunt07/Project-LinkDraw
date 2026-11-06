"""Cross-platform storage for standalone LinkDraw notes."""
import json
import os
import sys
import tempfile
import uuid
from datetime import datetime, timezone
from pathlib import Path


def _notes_path():
    if os.name == "nt":
        base = Path(os.environ.get("APPDATA", Path.home() / "AppData" / "Roaming"))
    elif sys.platform == "darwin":
        base = Path.home() / "Library" / "Application Support"
    else:
        base = Path(os.environ.get("XDG_CONFIG_HOME", Path.home() / ".config"))
    return base / "LinkDraw" / "notes.json"


NOTES_PATH = _notes_path()


def timestamp_now():
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def create_note():
    return {
        "id": uuid.uuid4().hex,
        "title": "Untitled note",
        "body": "",
        "note_type": "Observation",
        "source_url": "",
        "tags": [],
        "linked_node_id": None,
        "linked_node_name": "",
        "updated_at": timestamp_now(),
    }


def load_notes(path=None):
    if path is None:
        path = NOTES_PATH
    try:
        with open(path, encoding="utf-8") as notes_file:
            notes = json.load(notes_file)
    except FileNotFoundError:
        return []

    if not isinstance(notes, list):
        raise ValueError("The notes file must contain a JSON list.")
    for note in notes:
        if not isinstance(note, dict) or not all(
            isinstance(note.get(key), str)
            for key in ("id", "title", "body", "updated_at")
        ):
            raise ValueError("The notes file contains an invalid note entry.")
    return notes


def save_notes(notes, path=None):
    if path is None:
        path = NOTES_PATH
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    temp_path = None
    try:
        with tempfile.NamedTemporaryFile(
            mode="w",
            encoding="utf-8",
            dir=path.parent,
            prefix=f".{path.name}.",
            suffix=".tmp",
            delete=False,
        ) as temp_file:
            temp_path = Path(temp_file.name)
            json.dump(notes, temp_file, ensure_ascii=False, indent=2)
            temp_file.write("\n")
        os.replace(temp_path, path)
    finally:
        if temp_path is not None and temp_path.exists():
            temp_path.unlink()
