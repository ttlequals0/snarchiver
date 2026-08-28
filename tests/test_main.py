import datetime
import pathlib
import tempfile
import unittest
from unittest import mock

from snarchiver.__main__ import (NETWORK_RESULTS, archive_episode, build_parser, main,
                                 select_targets)
from snarchiver.catalog import CatalogResult
from snarchiver.models import Episode
from snarchiver.state import State, load_state


def ep(number, *, audio="https://media.grc.com/sn/sn-001.mp3", desc="Body."):
    return Episode(number=number, title=f"Title {number}", description=desc,
                   air_date=datetime.date(2005, 8, 19), audio_url=audio,
                   notes_url=None, source="grc")


def completed_through(n):
    return set(range(1, n + 1))


class TestSelectTargets(unittest.TestCase):
    def setUp(self):
        self.catalog = {n: ep(n) for n in (1, 2, 3, 10, 11)}

    def test_uses_state_floor_by_default(self):
        state = State(completed=completed_through(10), pending=set())
        self.assertEqual([e.number for e in select_targets(self.catalog, state,
                                                           None, None)], [11])

    def test_explicit_from_overrides_floor(self):
        state = State(completed=completed_through(10), pending=set())
        self.assertEqual([e.number for e in select_targets(self.catalog, state,
                                                           2, None)], [2, 3, 10, 11])

    def test_to_bounds_the_top(self):
        state = State(completed=set(), pending=set())
        self.assertEqual([e.number for e in select_targets(self.catalog, state,
                                                           1, 3)], [1, 2, 3])

    def test_pending_below_floor_is_retried(self):
        state = State(completed=completed_through(10), pending={2})
        self.assertEqual([e.number for e in select_targets(self.catalog, state,
                                                           None, None)], [2, 11])

    def test_pending_above_to_is_excluded(self):
        # --to must bound pending the same as everything else.
        state = State(completed=set(), pending={11})
        self.assertEqual([e.number for e in select_targets(self.catalog, state,
                                                           1, 3)], [1, 2, 3])

    def test_pending_below_floor_and_within_to_is_retried(self):
        state = State(completed=completed_through(10), pending={2})
        self.assertEqual([e.number for e in select_targets(self.catalog, state,
                                                           None, 2)], [2])

    def test_targets_are_sorted_and_deduped(self):
        state = State(completed=set(), pending={1, 2})
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

    def test_mp3_appears_only_after_sidecars_are_written(self):
        # Regression for the partial-import window: a live-scanned directory
        # must never see a finished .mp3 with no .json.
        stem = "s01e0001 - Title 1"
        audio_path = self.out / f"{stem}.mp3"
        observed = {}

        def downloader(url, dest, **kwargs):
            dest.write_bytes(b"audio")
            observed["temp_name"] = dest.name
            observed["final_mp3_exists_mid_download"] = audio_path.exists()

        archive_episode(ep(1), "2005-08-19T00:00:00Z", self.out, self.state,
                        artwork=False, force=False, downloader=downloader)

        self.assertFalse(observed["final_mp3_exists_mid_download"])
        self.assertTrue(observed["temp_name"].endswith((".part", ".tmp")),
                        observed["temp_name"])
        self.assertTrue(audio_path.exists())
        self.assertTrue((self.out / f"{stem}.json").exists())
        self.assertTrue((self.out / f"{stem}.txt").exists())

    def test_sidecar_write_failure_is_pending_not_fatal(self):
        with mock.patch("snarchiver.__main__.write_sidecars",
                        side_effect=OSError("disk full")):
            result = archive_episode(ep(1), "2005-08-19T00:00:00Z", self.out,
                                     self.state, artwork=False, force=False,
                                     downloader=self.downloader)
        self.assertEqual(result, "failed")
        self.assertIn(1, self.state.pending)

    def test_naming_failure_is_pending_not_fatal(self):
        with mock.patch("snarchiver.__main__.episode_stem",
                        side_effect=ValueError("bad stem")):
            result = archive_episode(ep(1), "2005-08-19T00:00:00Z", self.out,
                                     self.state, artwork=False, force=False,
                                     downloader=self.downloader)
        self.assertEqual(result, "failed")
        self.assertIn(1, self.state.pending)

    def test_skip_repair_backfills_artwork_when_enabled(self):
        self.run_one(ep(1))
        stem = "s01e0001 - Title 1"
        self.calls.clear()

        episode = ep(1)
        episode.notes_url = "https://www.grc.com/sn/sn-0001-notes.pdf"

        def fake_artwork(episode_, out_dir, stem_):
            (out_dir / f"{stem_}.jpg").write_bytes(b"img")

        with mock.patch("snarchiver.__main__._try_artwork", side_effect=fake_artwork):
            result = archive_episode(episode, "2005-08-19T00:00:00Z", self.out,
                                     self.state, artwork=True, force=False,
                                     downloader=self.downloader)

        self.assertEqual(self.calls, [])  # no re-download
        self.assertTrue((self.out / f"{stem}.jpg").exists())
        self.assertEqual(result, "repaired")


class TestArchiveEpisodeDelayGating(unittest.TestCase):
    def test_no_network_results_exclude_delay(self):
        self.assertNotIn("skipped", NETWORK_RESULTS)
        self.assertNotIn("repaired", NETWORK_RESULTS)
        self.assertNotIn("incomplete", NETWORK_RESULTS)
        self.assertIn("downloaded", NETWORK_RESULTS)
        self.assertIn("failed", NETWORK_RESULTS)


class TestMainCatalogGap(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.out = pathlib.Path(self.tmp.name) / "out"
        self.state_path = pathlib.Path(self.tmp.name) / "state.json"

    def tearDown(self):
        self.tmp.cleanup()

    def fake_downloader(self, url, dest, **kwargs):
        dest.write_bytes(b"audio")

    def test_incomplete_catalog_caps_floor_and_exits_nonzero(self):
        # Episodes 6-7 are absent because a listing page failed to fetch,
        # not because the source genuinely skipped them.
        numbers = list(range(1, 6)) + list(range(8, 11))
        episodes = {n: ep(n) for n in numbers}
        result = CatalogResult(episodes=episodes,
                               failed_pages=["https://www.grc.com/sn/past/2020.htm"])

        with mock.patch("snarchiver.__main__.catalog_mod.build_catalog",
                        return_value=result), \
             mock.patch("snarchiver.__main__.download.download_file",
                        self.fake_downloader):
            exit_code = main(["--out", str(self.out), "--state", str(self.state_path),
                              "--delay", "0"])

        self.assertNotEqual(exit_code, 0)
        state = load_state(self.state_path)
        self.assertLess(state.last_complete, 6)
        # Episodes above the gap were still archived to disk.
        self.assertTrue((self.out / "s01e0010 - Title 10.mp3").exists())

    def test_complete_catalog_with_genuine_gap_advances_normally(self):
        # No failed pages: episode 6 is simply absent upstream and must not
        # block the floor.
        numbers = list(range(1, 6)) + [7]
        episodes = {n: ep(n) for n in numbers}
        result = CatalogResult(episodes=episodes, failed_pages=[])

        with mock.patch("snarchiver.__main__.catalog_mod.build_catalog",
                        return_value=result), \
             mock.patch("snarchiver.__main__.download.download_file",
                        self.fake_downloader):
            exit_code = main(["--out", str(self.out), "--state", str(self.state_path),
                              "--delay", "0"])

        self.assertEqual(exit_code, 0)
        state = load_state(self.state_path)
        self.assertEqual(state.last_complete, 7)

    def test_hole_in_this_runs_catalog_never_rolls_floor_back_below_prior_progress(self):
        # A prior, fully-successful run already got through episode 1090.
        # This run's catalog is missing early numbers (a page failed to
        # fetch) even though 1090 worth of progress is already recorded --
        # that must not roll the floor backwards. This is deliberate,
        # previously-undocumented behaviour of the catalog-gap handling.
        from snarchiver.state import State, save_state
        save_state(self.state_path, State(completed=set(range(1, 1091))))

        episodes = {n: ep(n) for n in (1091, 1093)}  # 1092 missing: a fetch hole
        result = CatalogResult(episodes=episodes,
                               failed_pages=["https://www.grc.com/sn/past/2024.htm"])

        with mock.patch("snarchiver.__main__.catalog_mod.build_catalog",
                        return_value=result), \
             mock.patch("snarchiver.__main__.download.download_file",
                        self.fake_downloader):
            exit_code = main(["--out", str(self.out), "--state", str(self.state_path),
                              "--delay", "0"])

        self.assertNotEqual(exit_code, 0)
        state = load_state(self.state_path)
        self.assertGreaterEqual(state.last_complete, 1090)


class TestMainSaveStateFailure(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.out = pathlib.Path(self.tmp.name) / "out"
        self.state_path = pathlib.Path(self.tmp.name) / "state.json"

    def tearDown(self):
        self.tmp.cleanup()

    def fake_downloader(self, url, dest, **kwargs):
        dest.write_bytes(b"audio")

    def test_save_state_failure_is_logged_and_archiving_continues(self):
        # A full disk or permission error writing state must not abort the
        # run: it should log and keep archiving the remaining episodes.
        episodes = {n: ep(n) for n in (1, 2, 3)}
        result = CatalogResult(episodes=episodes, failed_pages=[])

        with mock.patch("snarchiver.__main__.catalog_mod.build_catalog",
                        return_value=result), \
             mock.patch("snarchiver.__main__.download.download_file",
                        self.fake_downloader), \
             mock.patch("snarchiver.__main__.save_state",
                        side_effect=OSError("disk full")), \
             self.assertLogs("snarchiver", level="ERROR") as logs:
            exit_code = main(["--out", str(self.out), "--state", str(self.state_path),
                              "--delay", "0"])

        self.assertEqual(exit_code, 1)
        # All three episodes were still archived despite state never saving.
        for n in (1, 2, 3):
            self.assertTrue((self.out / f"s01e{n:04d} - Title {n}.mp3").exists())
        self.assertTrue(any("could not save state" in line for line in logs.output))


class TestMainIncompleteSummary(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.out = pathlib.Path(self.tmp.name) / "out"
        self.state_path = pathlib.Path(self.tmp.name) / "state.json"

    def tearDown(self):
        self.tmp.cleanup()

    def fake_downloader(self, url, dest, **kwargs):
        dest.write_bytes(b"audio")

    def test_end_of_run_summarizes_incomplete_episodes(self):
        episodes = {1: ep(1), 592: ep(592, audio=None), 1093: ep(1093, audio=None)}
        result = CatalogResult(episodes=episodes, failed_pages=[])

        with mock.patch("snarchiver.__main__.catalog_mod.build_catalog",
                        return_value=result), \
             mock.patch("snarchiver.__main__.download.download_file",
                        self.fake_downloader), \
             self.assertLogs("snarchiver", level="WARNING") as logs:
            main(["--out", str(self.out), "--state", str(self.state_path),
                 "--delay", "0"])

        summary_lines = [line for line in logs.output if "skipped as incomplete" in line]
        self.assertEqual(len(summary_lines), 1)
        self.assertIn("2", summary_lines[0])
        self.assertIn("592", summary_lines[0])
        self.assertIn("1093", summary_lines[0])

    def test_no_summary_line_when_nothing_incomplete(self):
        episodes = {1: ep(1)}
        result = CatalogResult(episodes=episodes, failed_pages=[])

        with mock.patch("snarchiver.__main__.catalog_mod.build_catalog",
                        return_value=result), \
             mock.patch("snarchiver.__main__.download.download_file",
                        self.fake_downloader), \
             self.assertLogs("snarchiver", level="INFO") as logs:
            main(["--out", str(self.out), "--state", str(self.state_path),
                 "--delay", "0"])

        self.assertFalse(any("skipped as incomplete" in line for line in logs.output))


class TestMainDelaySkipsNoOpEpisodes(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.out = pathlib.Path(self.tmp.name) / "out"
        self.state_path = pathlib.Path(self.tmp.name) / "state.json"

    def tearDown(self):
        self.tmp.cleanup()

    def fake_downloader(self, url, dest, **kwargs):
        dest.write_bytes(b"audio")

    def test_verification_pass_over_complete_archive_does_not_sleep(self):
        episodes = {n: ep(n) for n in (1, 2, 3)}
        result = CatalogResult(episodes=episodes, failed_pages=[])

        with mock.patch("snarchiver.__main__.catalog_mod.build_catalog",
                        return_value=result), \
             mock.patch("snarchiver.__main__.download.download_file",
                        self.fake_downloader), \
             mock.patch("snarchiver.__main__.time.sleep") as fake_sleep:
            main(["--out", str(self.out), "--state", str(self.state_path),
                 "--delay", "5"])
            fake_sleep.reset_mock()
            exit_code = main(["--out", str(self.out), "--state", str(self.state_path),
                              "--delay", "5", "--from", "1"])

        self.assertEqual(exit_code, 0)
        fake_sleep.assert_not_called()


class TestParser(unittest.TestCase):
    def test_defaults(self):
        args = build_parser().parse_args([])
        self.assertIsNone(args.from_)
        self.assertEqual(args.delay, 2.0)
        self.assertFalse(args.artwork)

    def test_from_and_to(self):
        args = build_parser().parse_args(["--from", "600", "--to", "700"])
        self.assertEqual((args.from_, args.to), (600, 700))
