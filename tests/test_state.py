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
