import datetime
import json
import pathlib
import tempfile
import unittest
from unittest.mock import patch

from snarchiver.models import Episode
from snarchiver.sidecar import SIDECAR_KEYS, description_text, write_sidecars


def make(**kw):
    base = dict(number=1, title="As the Worm Turns", description="Body text.",
                air_date=datetime.date(2005, 8, 19),
                audio_url="https://media.grc.com/sn/sn-001.mp3",
                notes_url="https://www.grc.com/sn/notes-001.htm", source="grc")
    base.update(kw)
    return Episode(**base)


class TestDescriptionText(unittest.TestCase):
    def test_appends_show_notes_url(self):
        text = description_text(make())
        self.assertIn("Body text.", text)
        self.assertIn("Show notes: https://www.grc.com/sn/notes-001.htm", text)

    def test_omits_line_when_no_notes(self):
        self.assertNotIn("Show notes:", description_text(make(notes_url=None)))

    def test_body_ends_without_trailing_blank_lines(self):
        self.assertEqual(description_text(make(notes_url=None)), "Body text.")

    def test_empty_description_still_appends_show_notes(self):
        text = description_text(make(description=""))
        self.assertEqual(text, "\n\nShow notes: https://www.grc.com/sn/notes-001.htm")

    def test_whitespace_only_description_still_appends_show_notes(self):
        text = description_text(make(description="   \n\t "))
        self.assertEqual(text, "\n\nShow notes: https://www.grc.com/sn/notes-001.htm")

    def test_empty_description_and_no_notes_is_empty_string(self):
        self.assertEqual(description_text(make(description="  ", notes_url=None)), "")

    def test_description_already_ending_in_newline_gets_no_extra_blank_line(self):
        text = description_text(make(description="Body text.\n\n\n"))
        self.assertEqual(text,
                         "Body text.\n\nShow notes: https://www.grc.com/sn/notes-001.htm")


class TestWriteSidecars(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.out = pathlib.Path(self.tmp.name)
        self.stem = "s01e0001 - As the Worm Turns"
        write_sidecars(self.out, self.stem, make(), "2005-08-19T00:00:00Z")

    def tearDown(self):
        self.tmp.cleanup()

    def test_both_files_written(self):
        self.assertTrue((self.out / f"{self.stem}.txt").exists())
        self.assertTrue((self.out / f"{self.stem}.json").exists())

    def test_json_has_exactly_the_permitted_keys(self):
        data = json.loads((self.out / f"{self.stem}.json").read_text())
        self.assertEqual(set(data), SIDECAR_KEYS)

    def test_season_is_always_one(self):
        data = json.loads((self.out / f"{self.stem}.json").read_text())
        self.assertEqual(data["season"], 1)
        self.assertEqual(data["episode"], 1)

    def test_published_at_passed_through(self):
        data = json.loads((self.out / f"{self.stem}.json").read_text())
        self.assertEqual(data["published_at"], "2005-08-19T00:00:00Z")

    def test_txt_and_json_description_are_identical(self):
        text = (self.out / f"{self.stem}.txt").read_text(encoding="utf-8")
        data = json.loads((self.out / f"{self.stem}.json").read_text())
        self.assertEqual(text.rstrip("\n"), data["description"])

    def test_whitespace_only_description_is_composed_into_sidecars(self):
        stem = "s01e0004 - Blank"
        write_sidecars(self.out, stem, make(number=4, description="   \n "),
                       "2005-08-27T00:00:00Z")
        data = json.loads((self.out / f"{stem}.json").read_text())
        self.assertEqual(data["description"],
                         "\n\nShow notes: https://www.grc.com/sn/notes-001.htm")

    def test_description_ending_in_newline_is_composed_without_extra_blank_line(self):
        stem = "s01e0005 - Trailing Newline"
        write_sidecars(self.out, stem, make(number=5, description="Body.\n\n"),
                       "2005-08-28T00:00:00Z")
        data = json.loads((self.out / f"{stem}.json").read_text())
        self.assertEqual(data["description"],
                         "Body.\n\nShow notes: https://www.grc.com/sn/notes-001.htm")

    def test_files_are_utf8(self):
        write_sidecars(self.out, "s01e0002 - Café", make(number=2,
                       title="Café", description="Café attack"),
                       "2005-08-25T00:00:00Z")
        data = json.loads((self.out / "s01e0002 - Café.json")
                          .read_text(encoding="utf-8"))
        self.assertEqual(data["title"], "Café")

    def test_no_tmp_residue_after_successful_write(self):
        tmp_files = [f for f in self.out.iterdir() if str(f).endswith('.tmp')]
        self.assertEqual(len(tmp_files), 0)

    def test_writes_go_via_a_temp_file_the_importer_ignores_then_rename(self):
        # A naive direct write (json_path.write_text(...)) would also leave
        # no residue and also produce two different files, so those alone
        # don't prove atomicity. Assert the actual write/rename mechanism:
        # every write_text call targets an ignored-suffix temp path, and it
        # is renamed (not copied) into its final place.
        written = []
        renamed = []
        original_write_text = pathlib.Path.write_text
        original_replace = pathlib.Path.replace

        def spy_write_text(self, *a, **kw):
            written.append(self)
            return original_write_text(self, *a, **kw)

        def spy_replace(self, target):
            renamed.append((self, pathlib.Path(target)))
            return original_replace(self, target)

        with patch.object(pathlib.Path, 'write_text', spy_write_text), \
             patch.object(pathlib.Path, 'replace', spy_replace):
            write_sidecars(self.out, "s01e0099 - New", make(number=99),
                           "2005-08-19T00:00:00Z")

        self.assertEqual(len(written), 2)
        for path in written:
            self.assertTrue(path.name.endswith((".part", ".tmp")), path.name)
        self.assertEqual(len(renamed), 2)
        for tmp_path, final_path in renamed:
            self.assertIn(tmp_path, written)
            self.assertFalse(final_path.name.endswith((".part", ".tmp")))

    def test_json_present_if_txt_write_fails(self):
        stem = "s01e0003 - Test"
        episode = make(number=3, title="Test", description="Test desc")

        original_write_text = pathlib.Path.write_text

        def fail_on_txt_tmp(self, *args, **kwargs):
            if str(self).endswith('.txt.tmp'):
                raise IOError("Simulated write failure")
            return original_write_text(self, *args, **kwargs)

        with patch.object(pathlib.Path, 'write_text', fail_on_txt_tmp):
            with self.assertRaises(IOError):
                write_sidecars(self.out, stem, episode, "2005-08-26T00:00:00Z")

        self.assertTrue((self.out / f"{stem}.json").exists())
        self.assertFalse((self.out / f"{stem}.txt").exists())

    def test_rerun_fully_replaces_files(self):
        stem = "s01e0001 - As the Worm Turns"
        old_json = (self.out / f"{stem}.json").read_text()

        write_sidecars(self.out, stem, make(description="New description"),
                       "2005-08-19T00:00:00Z")

        new_json = (self.out / f"{stem}.json").read_text()
        self.assertNotEqual(old_json, new_json)
        self.assertIn("New description", new_json)

        tmp_files = [f for f in self.out.iterdir() if str(f).endswith('.tmp')]
        self.assertEqual(len(tmp_files), 0)

    def test_destination_is_never_observed_absent_during_rerun(self):
        # A naive rerun (json_path.write_text(...) directly) truncates the
        # destination before the new content lands, so a concurrent reader
        # (MinusPod's directory scan) could see it empty or missing. Prove
        # the real destination file is present with its OLD content right
        # up until the atomic rename, never absent/truncated in between.
        stem = "s01e0001 - As the Worm Turns"
        json_path = self.out / f"{stem}.json"
        txt_path = self.out / f"{stem}.txt"
        observations = []
        original_write_text = pathlib.Path.write_text

        def spy(self, *a, **kw):
            result = original_write_text(self, *a, **kw)
            if self.name.endswith(".json.tmp"):
                observations.append(json_path.exists() and bool(json_path.read_text()))
            elif self.name.endswith(".txt.tmp"):
                observations.append(txt_path.exists() and bool(txt_path.read_text()))
            return result

        with patch.object(pathlib.Path, 'write_text', spy):
            write_sidecars(self.out, stem, make(description="New description"),
                           "2005-08-19T00:00:00Z")

        self.assertEqual(len(observations), 2)  # sanity: both writes observed
        self.assertTrue(all(observations), observations)
