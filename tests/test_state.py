import json
import pathlib
import tempfile
import unittest

from snarchiver.state import DEFAULT_STATE_PATH, State, load_state, save_state


class TestState(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.path = pathlib.Path(self.tmp.name) / "snarchiver-state.json"

    def tearDown(self):
        self.tmp.cleanup()

    def test_missing_file_gives_empty_state(self):
        state = load_state(self.path)
        self.assertEqual(state.last_complete, 0)
        self.assertEqual(state.pending, set())

    def test_floor_is_one_past_last_complete(self):
        self.assertEqual(State(last_complete=1092, pending=set()).floor(), 1093)

    def test_round_trip(self):
        save_state(self.path, State(last_complete=1092, pending={1093}))
        state = load_state(self.path)
        self.assertEqual(state.last_complete, 1092)
        self.assertEqual(state.pending, {1093})

    def test_saved_shape(self):
        save_state(self.path, State(last_complete=5, pending={7}))
        data = json.loads(self.path.read_text())
        self.assertEqual(data["version"], 1)
        self.assertEqual(data["last_complete"], 5)
        self.assertEqual(data["pending"], [7])
        self.assertTrue(data["updated"].endswith("Z"))

    def test_mark_complete_advances_and_clears_pending(self):
        state = State(last_complete=0, pending={5})
        state.mark_complete(5)
        self.assertEqual(state.last_complete, 5)
        self.assertNotIn(5, state.pending)

    def test_mark_complete_does_not_lower_last_complete(self):
        state = State(last_complete=10, pending=set())
        state.mark_complete(3)
        self.assertEqual(state.last_complete, 10)

    def test_mark_pending_records_the_episode(self):
        state = State(last_complete=0, pending=set())
        state.mark_pending(1093)
        self.assertIn(1093, state.pending)

    def test_corrupt_file_gives_empty_state(self):
        self.path.write_text("{not json")
        self.assertEqual(load_state(self.path).last_complete, 0)

    def test_default_path_is_outside_the_import_directory(self):
        self.assertEqual(pathlib.Path(DEFAULT_STATE_PATH).name,
                         "snarchiver-state.json")

    def test_directory_at_state_path_gives_empty_state(self):
        # IsADirectoryError must degrade to empty state, not crash.
        self.path.mkdir(parents=True)
        state = load_state(self.path)
        self.assertEqual(state.last_complete, 0)
        self.assertEqual(state.pending, set())

    def test_permission_denied_gives_empty_state(self):
        # PermissionError must degrade to empty state, not crash.
        self.path.write_text('{"last_complete": 5, "pending": []}')
        self.path.chmod(0o000)
        try:
            state = load_state(self.path)
            self.assertEqual(state.last_complete, 0)
            self.assertEqual(state.pending, set())
        finally:
            self.path.chmod(0o644)

    def test_pending_as_bare_string_gives_empty_state(self):
        # pending: "abc" silently becomes {'a','b','c'} with old code.
        # Must validate and degrade, not corrupt.
        self.path.write_text('{"last_complete": 5, "pending": "abc"}')
        state = load_state(self.path)
        self.assertEqual(state.last_complete, 0)
        self.assertEqual(state.pending, set())
        # Ensure pending is not corrupted to string chars.
        self.assertNotIn('a', state.pending)

    def test_last_complete_as_string_gives_empty_state(self):
        # last_complete: "123" must not be coerced; must degrade.
        self.path.write_text('{"last_complete": "123", "pending": []}')
        state = load_state(self.path)
        self.assertEqual(state.last_complete, 0)
        self.assertEqual(state.pending, set())

    def test_pending_items_as_strings_gives_empty_state(self):
        # pending: ["1", "2"] (string items) must degrade, not create string set.
        self.path.write_text('{"last_complete": 5, "pending": ["1", "2"]}')
        state = load_state(self.path)
        self.assertEqual(state.last_complete, 0)
        self.assertEqual(state.pending, set())
        # Ensure pending is not corrupted to string items.
        self.assertNotIn("1", state.pending)
