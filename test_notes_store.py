import json
import tempfile
import unittest
from pathlib import Path

import notes_store


class TestNotesStore(unittest.TestCase):
    def test_notes_round_trip_as_utf8(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            path = Path(temp_dir) / "nested" / "notes.json"
            note = notes_store.create_note()
            note.update(title="Meeting notes", body="Résumé\n- [ ] Follow up")

            notes_store.save_notes([note], path)

            self.assertEqual(notes_store.load_notes(path), [note])
            self.assertIn("Résumé", path.read_text(encoding="utf-8"))

    def test_missing_file_starts_with_no_notes(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            self.assertEqual(notes_store.load_notes(Path(temp_dir) / "missing.json"), [])

    def test_invalid_note_data_is_reported(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            path = Path(temp_dir) / "notes.json"
            path.write_text(json.dumps([{"title": "Missing required fields"}]), encoding="utf-8")

            with self.assertRaises(ValueError):
                notes_store.load_notes(path)


if __name__ == "__main__":
    unittest.main()
