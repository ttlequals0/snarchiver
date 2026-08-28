import pathlib
import unittest

from snarchiver.catalog import KNOWN_GAPS, build_catalog, discover_archive_urls, listing_urls

FIXTURES = pathlib.Path(__file__).parent / "fixtures"


def load(name):
    return (FIXTURES / name).read_text(encoding="utf-8", errors="replace")


class TestDiscoverArchiveUrls(unittest.TestCase):
    def test_finds_every_year_link_on_the_current_page(self):
        urls = discover_archive_urls(load("grc-current.htm"))
        self.assertIn("https://www.grc.com/sn/past/2005.htm", urls)
        self.assertIn("https://www.grc.com/sn/past/2025.htm", urls)
        self.assertEqual(len(urls), 21)

    def test_no_links_yields_empty_list(self):
        self.assertEqual(discover_archive_urls("<html></html>"), [])


class TestListingUrls(unittest.TestCase):
    def test_covers_current_page_and_every_discovered_year(self):
        urls = listing_urls(fetch=lambda url: load("grc-current.htm"))
        self.assertEqual(len(urls), 22)
        self.assertIn("https://www.grc.com/securitynow.htm", urls)
        self.assertIn("https://www.grc.com/sn/past/2005.htm", urls)
        self.assertIn("https://www.grc.com/sn/past/2025.htm", urls)

    def test_no_duplicate_urls(self):
        urls = listing_urls(fetch=lambda url: load("grc-current.htm"))
        self.assertEqual(len(urls), len(set(urls)))

    def test_falls_back_to_known_range_when_fetch_fails(self):
        def failing(url):
            raise OSError("unreachable")

        urls = listing_urls(fetch=failing)
        self.assertEqual(len(urls), 22)
        self.assertIn("https://www.grc.com/sn/past/2005.htm", urls)
        self.assertIn("https://www.grc.com/sn/past/2025.htm", urls)

    def test_falls_back_to_known_range_when_no_links_discovered(self):
        urls = listing_urls(fetch=lambda url: "<html></html>")
        self.assertEqual(len(urls), 22)

    def test_no_fetch_falls_back_to_known_range(self):
        urls = listing_urls()
        self.assertEqual(len(urls), 22)


class TestBuildCatalog(unittest.TestCase):
    def setUp(self):
        self.pages = {
            "https://www.grc.com/securitynow.htm": "grc-current.htm",
            "https://www.grc.com/sn/past/2005.htm": "grc-2005.htm",
            "https://www.grc.com/sn/past/2022.htm": "grc-2022.htm",
        }
        self.fetched = []

    def fetch(self, url, **kwargs):
        self.fetched.append(url)
        name = self.pages.get(url)
        if name:
            return (FIXTURES / name).read_text(encoding="utf-8", errors="replace")
        if url.endswith("/436"):
            return (FIXTURES / "twit-436.html").read_text(encoding="utf-8",
                                                          errors="replace")
        return "<html></html>"

    def test_merges_pages_into_one_catalog(self):
        result = build_catalog(fetch=self.fetch, twit_lookup=set(), probe=lambda url: False)
        self.assertIn(1, result.episodes)
        self.assertIn(885, result.episodes)
        self.assertIn(1093, result.episodes)

    def test_fully_successful_fetch_is_complete(self):
        result = build_catalog(fetch=self.fetch, twit_lookup=set(), probe=lambda url: False)
        self.assertTrue(result.complete)
        self.assertEqual(result.failed_pages, [])

    def test_known_gaps_constant(self):
        self.assertEqual(KNOWN_GAPS, {436, 540, 643, 1058})

    def test_twit_fallback_fills_a_gap(self):
        result = build_catalog(fetch=self.fetch, twit_lookup={436}, probe=lambda url: False)
        self.assertIn(436, result.episodes)
        self.assertEqual(result.episodes[436].source, "twit")

    def test_twit_not_consulted_when_grc_has_the_episode(self):
        build_catalog(fetch=self.fetch, twit_lookup={885}, probe=lambda url: False)
        self.assertNotIn("https://twit.tv/shows/security-now/episodes/885",
                         self.fetched)

    def test_a_failing_page_does_not_abort_the_run(self):
        def flaky(url, **kwargs):
            if url.endswith("2005.htm"):
                raise OSError("unreachable")
            return self.fetch(url, **kwargs)

        result = build_catalog(fetch=flaky, twit_lookup=set(), probe=lambda url: False)
        self.assertIn(1093, result.episodes)
        self.assertNotIn(1, result.episodes)

    def test_a_failing_page_marks_the_catalog_incomplete(self):
        def flaky(url, **kwargs):
            if url.endswith("2005.htm"):
                raise OSError("unreachable")
            return self.fetch(url, **kwargs)

        result = build_catalog(fetch=flaky, twit_lookup=set(), probe=lambda url: False)
        self.assertFalse(result.complete)
        self.assertIn("https://www.grc.com/sn/past/2005.htm", result.failed_pages)

    def test_a_failing_twit_lookup_marks_the_catalog_incomplete(self):
        def flaky(url, **kwargs):
            if url.endswith("/436"):
                raise OSError("unreachable")
            return self.fetch(url, **kwargs)

        result = build_catalog(fetch=flaky, twit_lookup={436}, probe=lambda url: False)
        self.assertFalse(result.complete)
        self.assertIn("https://twit.tv/shows/security-now/episodes/436",
                      result.failed_pages)


class TestAudioProbe(unittest.TestCase):
    """ep 592: metadata present, no audio href on the listing page at all."""

    def setUp(self):
        self.pages = {
            "https://www.grc.com/securitynow.htm": "grc-current.htm",
            "https://www.grc.com/sn/past/2016.htm": "grc-2016.htm",
        }

    def fetch(self, url, **kwargs):
        name = self.pages.get(url)
        if name:
            return (FIXTURES / name).read_text(encoding="utf-8", errors="replace")
        return "<html></html>"

    def test_probe_recovers_episode_with_metadata_and_no_audio(self):
        probed = []

        def probe(url):
            probed.append(url)
            return True

        result = build_catalog(fetch=self.fetch, twit_lookup=set(), probe=probe)
        episode = result.episodes[592]
        self.assertEqual(episode.audio_url, "https://media.grc.com/sn/sn-592.mp3")
        self.assertTrue(episode.is_complete)
        self.assertIn("https://media.grc.com/sn/sn-592.mp3", probed)

    def test_failed_probe_leaves_episode_incomplete(self):
        result = build_catalog(fetch=self.fetch, twit_lookup=set(),
                               probe=lambda url: False)
        episode = result.episodes[592]
        self.assertIsNone(episode.audio_url)
        self.assertFalse(episode.is_complete)

    def test_episode_with_audio_href_is_never_probed(self):
        probed = []

        def probe(url):
            probed.append(url)
            return True

        build_catalog(fetch=self.fetch, twit_lookup=set(), probe=probe)
        self.assertNotIn("https://media.grc.com/sn/sn-591.mp3", probed)

    def test_episode_without_description_is_never_probed(self):
        block = ('<a name="999"></a>Episode&nbsp;#999 | 01 Jan 2020 |'
                '<b>Test Title</b></td>'
                '</table></td></tr></table></td></tr></table>')
        pages = {"https://www.grc.com/securitynow.htm": block}

        def fetch(url, **kwargs):
            return pages.get(url, "<html></html>")

        probed = []

        def probe(url):
            probed.append(url)
            return True

        result = build_catalog(fetch=fetch, twit_lookup=set(), probe=probe)
        episode = result.episodes[999]
        self.assertEqual(episode.description, "")
        self.assertIsNone(episode.audio_url)
        self.assertEqual(probed, [])

    def test_probe_that_raises_leaves_episode_incomplete(self):
        def probe(url):
            raise OSError("boom")

        result = build_catalog(fetch=self.fetch, twit_lookup=set(), probe=probe)
        episode = result.episodes[592]
        self.assertIsNone(episode.audio_url)
        self.assertFalse(episode.is_complete)
