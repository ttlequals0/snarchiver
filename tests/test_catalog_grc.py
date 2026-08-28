import datetime
import pathlib
import unittest

from snarchiver.catalog import parse_listing_page

FIXTURES = pathlib.Path(__file__).parent / "fixtures"


def load(name):
    return (FIXTURES / name).read_text(encoding="utf-8", errors="replace")


class TestParseListingPage(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.current = {e.number: e for e in parse_listing_page(load("grc-current.htm"))}
        cls.y2005 = {e.number: e for e in parse_listing_page(load("grc-2005.htm"))}
        cls.y2022 = {e.number: e for e in parse_listing_page(load("grc-2022.htm"))}
        cls.y2016 = {e.number: e for e in parse_listing_page(load("grc-2016.htm"))}

    def test_current_page_episode_range(self):
        self.assertEqual(min(self.current), 1059)
        self.assertEqual(max(self.current), 1093)

    def test_old_layout_parses(self):
        # grc-2005.htm uses width="85%", not style="width:60em;"
        self.assertEqual(min(self.y2005), 1)

    def test_title_is_bold_text_only(self):
        self.assertEqual(self.y2005[1].title, "As the Worm Turns")

    def test_subtitle_joins_description_not_title(self):
        self.assertIn("first Internet worms", self.y2005[1].description)
        self.assertNotIn("first Internet worms", self.y2005[1].title)

    def test_air_date_parsed(self):
        self.assertEqual(self.y2005[1].air_date, datetime.date(2005, 8, 19))

    def test_typo_date_parsed(self):
        # ep 1077 is published as "05 May2026"
        self.assertEqual(self.current[1077].air_date, datetime.date(2026, 5, 5))

    def test_high_quality_audio_url(self):
        self.assertEqual(self.y2005[1].audio_url,
                         "https://media.grc.com/sn/sn-001.mp3")

    def test_low_quality_audio_rejected(self):
        for episode in self.current.values():
            if episode.audio_url:
                self.assertNotIn("-lq", episode.audio_url)

    def test_commented_out_audio_yields_none(self):
        # ep 1093's audio anchors sit inside an HTML comment
        self.assertIsNone(self.current[1093].audio_url)

    def test_commented_out_episode_still_has_title_and_description(self):
        self.assertTrue(self.current[1093].title)
        self.assertTrue(self.current[1093].description.strip())

    def test_notes_url_absolute(self):
        self.assertTrue(self.current[1092].notes_url.startswith("https://www.grc.com/"))

    def test_notes_url_matches_own_episode_number(self):
        # sn-436-notes.pdf is an orphan containing ep 437's notes, so the href
        # must be scraped rather than constructed
        self.assertIn("sn-1092-notes.pdf", self.current[1092].notes_url)

    def test_entities_unescaped(self):
        joined = " ".join(e.description for e in self.current.values())
        self.assertNotIn("&#8220;", joined)
        self.assertNotIn("&bull;", joined)

    def test_tags_stripped(self):
        for episode in self.current.values():
            self.assertNotIn("<", episode.description)

    def test_collision_page_has_both_episodes_same_date(self):
        self.assertEqual(self.y2022[885].air_date, self.y2022[886].air_date)

    def test_source_marked_grc(self):
        self.assertEqual(self.y2005[1].source, "grc")

    def test_episode_with_no_duration_field_still_parses(self):
        # ep 592's meta line has only one pipe: "Episode #592 | 27 Dec 2016 "
        self.assertIn(592, self.y2016)
        episode = self.y2016[592]
        self.assertEqual(episode.air_date, datetime.date(2016, 12, 27))
        self.assertTrue(episode.title)
        self.assertTrue(episode.description.strip())

    def test_episode_with_no_duration_field_is_incomplete(self):
        # ep 592's block has no audio href at all, so it must not be marked complete
        self.assertFalse(self.y2016[592].is_complete)

    def test_neighbouring_normal_episode_still_parses(self):
        # ep 591 has the usual two-pipe form with a duration; the relaxed
        # pattern must not change its result
        self.assertEqual(self.y2016[591].air_date, datetime.date(2016, 12, 20))
        self.assertEqual(self.y2016[591].title, "Law Meets Internet")
