import datetime
import unittest

from snarchiver.models import Episode


def make(**kw):
    base = dict(number=1, title="As the Worm Turns", description="Body text.",
                air_date=datetime.date(2005, 8, 19),
                audio_url="https://media.grc.com/sn/sn-001.mp3",
                notes_url="https://www.grc.com/sn/notes-001.htm", source="grc")
    base.update(kw)
    return Episode(**base)


class TestEpisode(unittest.TestCase):
    def test_complete_episode(self):
        self.assertTrue(make().is_complete)

    def test_missing_audio_is_incomplete(self):
        self.assertFalse(make(audio_url=None).is_complete)

    def test_blank_description_is_incomplete(self):
        self.assertFalse(make(description="   ").is_complete)

    def test_notes_url_is_optional(self):
        self.assertTrue(make(notes_url=None).is_complete)
