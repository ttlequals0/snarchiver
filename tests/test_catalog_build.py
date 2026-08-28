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
        result = build_catalog(fetch=self.fetch, twit_lookup=set())
        self.assertIn(1, result.episodes)
        self.assertIn(885, result.episodes)
        self.assertIn(1093, result.episodes)

    def test_fully_successful_fetch_is_complete(self):
        result = build_catalog(fetch=self.fetch, twit_lookup=set())
        self.assertTrue(result.complete)
        self.assertEqual(result.failed_pages, [])

    def test_known_gaps_constant(self):
        self.assertEqual(KNOWN_GAPS, {436, 540, 643, 1058})

    def test_twit_fallback_fills_a_gap(self):
        result = build_catalog(fetch=self.fetch, twit_lookup={436})
        self.assertIn(436, result.episodes)
        self.assertEqual(result.episodes[436].source, "twit")

    def test_twit_not_consulted_when_grc_has_the_episode(self):
        build_catalog(fetch=self.fetch, twit_lookup={885})
        self.assertNotIn("https://twit.tv/shows/security-now/episodes/885",
                         self.fetched)

    def test_a_failing_page_does_not_abort_the_run(self):
        def flaky(url, **kwargs):
            if url.endswith("2005.htm"):
                raise OSError("unreachable")
            return self.fetch(url, **kwargs)

        result = build_catalog(fetch=flaky, twit_lookup=set())
        self.assertIn(1093, result.episodes)
        self.assertNotIn(1, result.episodes)

    def test_a_failing_page_marks_the_catalog_incomplete(self):
        def flaky(url, **kwargs):
            if url.endswith("2005.htm"):
                raise OSError("unreachable")
            return self.fetch(url, **kwargs)

        result = build_catalog(fetch=flaky, twit_lookup=set())
        self.assertFalse(result.complete)
        self.assertIn("https://www.grc.com/sn/past/2005.htm", result.failed_pages)

    def test_a_failing_twit_lookup_marks_the_catalog_incomplete(self):
        def flaky(url, **kwargs):
            if url.endswith("/436"):
                raise OSError("unreachable")
            return self.fetch(url, **kwargs)

        result = build_catalog(fetch=flaky, twit_lookup={436})
        self.assertFalse(result.complete)
        self.assertIn("https://twit.tv/shows/security-now/episodes/436",
                      result.failed_pages)
