import pathlib
import unittest

from snarchiver.catalog import KNOWN_GAPS, build_catalog, listing_urls

FIXTURES = pathlib.Path(__file__).parent / "fixtures"


class TestListingUrls(unittest.TestCase):
    def test_covers_current_page_and_every_year(self):
        urls = listing_urls()
        self.assertEqual(len(urls), 22)
        self.assertIn("https://www.grc.com/securitynow.htm", urls)
        self.assertIn("https://www.grc.com/sn/past/2005.htm", urls)
        self.assertIn("https://www.grc.com/sn/past/2025.htm", urls)

    def test_no_duplicate_urls(self):
        urls = listing_urls()
        self.assertEqual(len(urls), len(set(urls)))


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
        catalog = build_catalog(fetch=self.fetch, twit_lookup=set())
        self.assertIn(1, catalog)
        self.assertIn(885, catalog)
        self.assertIn(1093, catalog)

    def test_known_gaps_constant(self):
        self.assertEqual(KNOWN_GAPS, {436, 540, 643, 1058})

    def test_twit_fallback_fills_a_gap(self):
        catalog = build_catalog(fetch=self.fetch, twit_lookup={436})
        self.assertIn(436, catalog)
        self.assertEqual(catalog[436].source, "twit")

    def test_twit_not_consulted_when_grc_has_the_episode(self):
        build_catalog(fetch=self.fetch, twit_lookup={885})
        self.assertNotIn("https://twit.tv/shows/security-now/episodes/885",
                         self.fetched)

    def test_a_failing_page_does_not_abort_the_run(self):
        def flaky(url, **kwargs):
            if url.endswith("2005.htm"):
                raise OSError("unreachable")
            return self.fetch(url, **kwargs)

        catalog = build_catalog(fetch=flaky, twit_lookup=set())
        self.assertIn(1093, catalog)
        self.assertNotIn(1, catalog)
