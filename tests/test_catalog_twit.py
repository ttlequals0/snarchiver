import datetime
import pathlib
import unittest

from snarchiver.catalog import grc_audio_url, parse_twit_page, twit_url

FIXTURES = pathlib.Path(__file__).parent / "fixtures"


class TestParseTwitPage(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        html_text = (FIXTURES / "twit-436.html").read_text(encoding="utf-8",
                                                           errors="replace")
        cls.episode = parse_twit_page(html_text, 436)

    def test_title_stripped_of_show_and_site_name(self):
        self.assertEqual(self.episode.title, "Time Traveling with Steve")

    def test_air_date_with_ordinal_suffix(self):
        self.assertEqual(self.episode.air_date, datetime.date(2013, 12, 25))

    def test_description_present(self):
        self.assertTrue(self.episode.description.strip())

    def test_audio_url_constructed(self):
        self.assertEqual(self.episode.audio_url,
                         "https://media.grc.com/sn/sn-436.mp3")

    def test_no_notes_url(self):
        self.assertIsNone(self.episode.notes_url)

    def test_notes_style_href_on_the_page_is_still_not_picked_up(self):
        # test_no_notes_url only proves the fixture page happens to have no
        # notes link; it would pass even if TWiT parsing wrongly extracted
        # one. Feed a page that DOES carry a notes-style href and confirm
        # it's still ignored -- TWiT pages have no show-notes concept.
        page = (
            '<meta property="og:title" content="Security Now: Has Notes Link | TWiT.TV">'
            '<div class="air-date">Dec 25th 2013</div>'
            '<meta property="og:description" content="desc">'
            '<a href="/sn/notes-436.htm">Show Notes</a>'
        )
        episode = parse_twit_page(page, 436)
        self.assertIsNotNone(episode)
        self.assertIsNone(episode.notes_url)

    def test_source_marked_twit(self):
        self.assertEqual(self.episode.source, "twit")

    def test_unparseable_page_returns_none(self):
        self.assertIsNone(parse_twit_page("<html><body>nope</body></html>", 999))


class TestUrlBuilders(unittest.TestCase):
    def test_twit_url(self):
        self.assertEqual(twit_url(436),
                         "https://twit.tv/shows/security-now/episodes/436")

    def test_audio_url_pads_to_three_digits(self):
        self.assertEqual(grc_audio_url(1), "https://media.grc.com/sn/sn-001.mp3")
        self.assertEqual(grc_audio_url(436), "https://media.grc.com/sn/sn-436.mp3")

    def test_audio_url_four_digits_unpadded(self):
        self.assertEqual(grc_audio_url(1058), "https://media.grc.com/sn/sn-1058.mp3")
