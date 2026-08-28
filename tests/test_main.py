import datetime
import pathlib
import tempfile
import unittest

from snarchiver.__main__ import archive_episode, build_parser, select_targets
from snarchiver.models import Episode
from snarchiver.state import State


def ep(number, *, audio="https://media.grc.com/sn/sn-001.mp3", desc="Body."):
    return Episode(number=number, title=f"Title {number}", description=desc,
                   air_date=datetime.date(2005, 8, 19), audio_url=audio,
                   notes_url=None, source="grc")


class TestSelectTargets(unittest.TestCase):
    def setUp(self):
        self.catalog = {n: ep(n) for n in (1, 2, 3, 10, 11)}

    def test_uses_state_floor_by_default(self):
        state = State(last_complete=10, pending=set())
        self.assertEqual([e.number for e in select_targets(self.catalog, state,
                                                           None, None)], [11])

    def test_explicit_from_overrides_floor(self):
        state = State(last_complete=10, pending=set())
        self.assertEqual([e.number for e in select_targets(self.catalog, state,
                                                           2, None)], [2, 3, 10, 11])

    def test_to_bounds_the_top(self):
        state = State(last_complete=0, pending=set())
        self.assertEqual([e.number for e in select_targets(self.catalog, state,
                                                           1, 3)], [1, 2, 3])

    def test_pending_below_floor_is_retried(self):
        state = State(last_complete=10, pending={2})
        self.assertEqual([e.number for e in select_targets(self.catalog, state,
                                                           None, None)], [2, 11])

    def test_targets_are_sorted_and_deduped(self):
        state = State(last_complete=0, pending={1, 2})
        numbers = [e.number for e in select_targets(self.catalog, state, 1, None)]
        self.assertEqual(numbers, sorted(set(numbers)))


class TestArchiveEpisode(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.out = pathlib.Path(self.tmp.name)
        self.state = State()
        self.calls = []

    def tearDown(self):
        self.tmp.cleanup()

    def downloader(self, url, dest, **kwargs):
        self.calls.append(url)
        dest.write_bytes(b"audio")
        return 5

    def run_one(self, episode, **kw):
        return archive_episode(episode, "2005-08-19T00:00:00Z", self.out,
                               self.state, artwork=False, force=False,
                               downloader=self.downloader, **kw)

    def test_writes_all_three_files(self):
        self.run_one(ep(1))
        stem = "s01e0001 - Title 1"
        for ext in (".mp3", ".txt", ".json"):
            self.assertTrue((self.out / f"{stem}{ext}").exists(), ext)

    def test_returns_downloaded_and_marks_complete(self):
        self.assertEqual(self.run_one(ep(1)), "downloaded")
        self.assertEqual(self.state.last_complete, 1)

    def test_missing_audio_is_incomplete_and_pending(self):
        self.assertEqual(self.run_one(ep(9, audio=None)), "incomplete")
        self.assertIn(9, self.state.pending)
        self.assertEqual(self.calls, [])

    def test_blank_description_is_incomplete(self):
        self.assertEqual(self.run_one(ep(9, desc="  ")), "incomplete")
        self.assertIn(9, self.state.pending)

    def test_existing_audio_is_skipped(self):
        self.run_one(ep(1))
        self.calls.clear()
        self.assertEqual(self.run_one(ep(1)), "skipped")
        self.assertEqual(self.calls, [])

    def test_force_redownloads(self):
        self.run_one(ep(1))
        self.calls.clear()
        result = archive_episode(ep(1), "2005-08-19T00:00:00Z", self.out,
                                 self.state, artwork=False, force=True,
                                 downloader=self.downloader)
        self.assertEqual(result, "downloaded")
        self.assertEqual(len(self.calls), 1)

    def test_skip_repairs_missing_sidecars_without_redownload(self):
        self.run_one(ep(1))
        stem = "s01e0001 - Title 1"
        (self.out / f"{stem}.txt").unlink()
        (self.out / f"{stem}.json").unlink()
        self.calls.clear()

        result = self.run_one(ep(1))

        self.assertEqual(self.calls, [])
        self.assertTrue((self.out / f"{stem}.txt").exists())
        self.assertTrue((self.out / f"{stem}.json").exists())
        self.assertEqual(self.state.last_complete, 1)
        self.assertEqual(result, "repaired")

    def test_download_failure_is_pending_not_fatal(self):
        def failing(url, dest, **kwargs):
            raise OSError("network gone")

        result = archive_episode(ep(1), "2005-08-19T00:00:00Z", self.out,
                                 self.state, artwork=False, force=False,
                                 downloader=failing)
        self.assertEqual(result, "failed")
        self.assertIn(1, self.state.pending)


class TestParser(unittest.TestCase):
    def test_defaults(self):
        args = build_parser().parse_args([])
        self.assertIsNone(args.from_)
        self.assertEqual(args.delay, 2.0)
        self.assertFalse(args.artwork)

    def test_from_and_to(self):
        args = build_parser().parse_args(["--from", "600", "--to", "700"])
        self.assertEqual((args.from_, args.to), (600, 700))
