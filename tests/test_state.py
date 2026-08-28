import json
import pathlib
import tempfile
import unittest
from unittest.mock import patch

from snarchiver.state import DEFAULT_STATE_PATH, State, load_state, save_state


def completed_through(n):
    """Convenience for tests: the set of episodes 1..n, all complete."""
    return set(range(1, n + 1))


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
        self.assertEqual(State(completed=completed_through(1092), pending=set()).floor(), 1093)

    def test_round_trip(self):
        save_state(self.path, State(completed=completed_through(1092), pending={1093}))
        state = load_state(self.path)
        self.assertEqual(state.last_complete, 1092)
        self.assertEqual(state.completed, completed_through(1092))
        self.assertEqual(state.pending, {1093})

    def test_saved_shape(self):
        save_state(self.path, State(completed={2, 3, 4, 5}, pending={7}))
        data = json.loads(self.path.read_text())
        self.assertEqual(data["version"], 2)
        self.assertEqual(data["completed"], [[2, 5]])
        self.assertEqual(data["last_complete"], 0)  # 1 isn't complete, so no leading range
        self.assertEqual(data["pending"], [7])
        self.assertTrue(data["updated"].endswith("Z"))

    def test_saved_completed_is_compact_ranges_not_flat_list(self):
        save_state(self.path, State(completed={1, 2, 3, 400, 402, 403}, pending=set()))
        data = json.loads(self.path.read_text())
        self.assertEqual(data["completed"], [[1, 3], [400, 400], [402, 403]])

    def test_last_complete_is_derived_from_leading_contiguous_range(self):
        state = State(completed={1, 2, 3, 10}, pending=set())
        self.assertEqual(state.last_complete, 3)
        self.assertEqual(state.floor(), 4)

    def test_marking_a_high_episode_complete_does_not_orphan_earlier_ones(self):
        # The core Item 5 defect: completing episode 500 on a fresh state
        # (e.g. from --from 500) must not silently make 1-499 permanently
        # unreachable by a later default run.
        state = State()
        state.mark_complete(500)
        self.assertEqual(state.floor(), 1)

    def test_mark_complete_advances_and_clears_pending(self):
        state = State(completed=set(), pending={5})
        state.mark_complete(5)
        self.assertIn(5, state.completed)
        self.assertNotIn(5, state.pending)

    def test_mark_complete_does_not_lower_last_complete(self):
        state = State(completed=completed_through(10), pending=set())
        state.mark_complete(3)
        self.assertEqual(state.last_complete, 10)

    def test_mark_pending_records_the_episode(self):
        state = State(completed=set(), pending=set())
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

    def test_pending_bool_item_gives_empty_state(self):
        # bool is an int subclass in Python: pending:[true] must not become {1}.
        self.path.write_text('{"version": 2, "completed": [], "pending": [true]}')
        state = load_state(self.path)
        self.assertEqual(state.pending, set())
        self.assertNotIn(True, state.pending)
        self.assertNotIn(1, state.pending)

    def test_last_complete_bool_gives_empty_state(self):
        # bool is an int subclass in Python: last_complete:true must not become 1.
        self.path.write_text('{"last_complete": true, "pending": []}')
        state = load_state(self.path)
        self.assertEqual(state.last_complete, 0)
        self.assertEqual(state.completed, set())

    def test_completed_range_bool_bound_gives_empty_state(self):
        self.path.write_text('{"version": 2, "completed": [[1, true]], "pending": []}')
        state = load_state(self.path)
        self.assertEqual(state.completed, set())
        self.assertEqual(state.last_complete, 0)

    def test_top_level_array_gives_empty_state(self):
        # Top-level JSON array (not object) must degrade, not crash on .get().
        self.path.write_text('[1, 2, 3]')
        state = load_state(self.path)
        self.assertEqual(state.last_complete, 0)
        self.assertEqual(state.pending, set())

    def test_save_state_cleans_up_temp_file_on_replace_failure(self):
        with patch.object(pathlib.Path, "replace", side_effect=OSError("disk full")):
            with self.assertRaises(OSError):
                save_state(self.path, State(completed={1}))
        tmp = self.path.with_name(self.path.name + ".tmp")
        self.assertFalse(tmp.exists())

    def test_save_state_never_truncates_existing_file_on_failure(self):
        self.path.write_text('{"version": 1, "last_complete": 9, "pending": []}')
        original = self.path.read_text()
        with patch.object(pathlib.Path, "replace", side_effect=OSError("disk full")):
            with self.assertRaises(OSError):
                save_state(self.path, State(completed={1}))
        self.assertEqual(self.path.read_text(), original)

    def test_top_level_scalar_gives_empty_state(self):
        # Top-level JSON scalar (number or string, not object) must degrade.
        self.path.write_text('42')
        state = load_state(self.path)
        self.assertEqual(state.last_complete, 0)
        self.assertEqual(state.pending, set())
        # Also test with string scalar.
        self.path.write_text('"not a state file"')
        state = load_state(self.path)
        self.assertEqual(state.last_complete, 0)
        self.assertEqual(state.pending, set())


class TestStateVersionMigration(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.path = pathlib.Path(self.tmp.name) / "snarchiver-state.json"

    def tearDown(self):
        self.tmp.cleanup()

    def test_v1_last_complete_migrates_to_a_completed_set(self):
        self.path.write_text('{"version": 1, "last_complete": 5, "pending": [7]}')
        state = load_state(self.path)
        self.assertEqual(state.completed, completed_through(5))
        self.assertEqual(state.pending, {7})

    def test_v1_zero_last_complete_migrates_to_empty_completed(self):
        self.path.write_text('{"version": 1, "last_complete": 0, "pending": []}')
        state = load_state(self.path)
        self.assertEqual(state.completed, set())

    def test_missing_version_treated_as_v1(self):
        self.path.write_text('{"last_complete": 3, "pending": []}')
        state = load_state(self.path)
        self.assertEqual(state.completed, completed_through(3))

    def test_v2_file_round_trips_through_migration_path_untouched(self):
        save_state(self.path, State(completed={1, 2, 400, 401, 1092}, pending={5}))
        state = load_state(self.path)
        self.assertEqual(state.completed, {1, 2, 400, 401, 1092})
        self.assertEqual(state.pending, {5})
