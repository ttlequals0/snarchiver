import datetime
import json
import pathlib
import tempfile
import unittest

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

    def test_permitted_keys_match_minuspod(self):
        self.assertEqual(SIDECAR_KEYS,
                         {"title", "description", "published_at", "season", "episode"})

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

    def test_files_are_utf8(self):
        write_sidecars(self.out, "s01e0002 - Café", make(number=2,
                       title="Café", description="Café attack"),
                       "2005-08-25T00:00:00Z")
        data = json.loads((self.out / "s01e0002 - Café.json")
                          .read_text(encoding="utf-8"))
        self.assertEqual(data["title"], "Café")
