import datetime
import unittest

from snarchiver.dates import parse_air_date


class TestParseAirDate(unittest.TestCase):
    def test_abbreviated_month(self):
        self.assertEqual(parse_air_date("19 Aug 2005"), datetime.date(2005, 8, 19))

    def test_full_month(self):
        self.assertEqual(parse_air_date("07 June 2007"), datetime.date(2007, 6, 7))

    def test_four_letter_sept(self):
        # "Sept" is neither %b ("Sep") nor %B ("September")
        self.assertEqual(parse_air_date("27 Sept 2007"), datetime.date(2007, 9, 27))

    def test_missing_space_typo(self):
        # episode 1077 is published as "05 May2026"
        self.assertEqual(parse_air_date("05 May2026"), datetime.date(2026, 5, 5))

    def test_surrounding_whitespace(self):
        self.assertEqual(parse_air_date("  18 Aug 2026  "), datetime.date(2026, 8, 18))

    def test_unparseable_raises(self):
        with self.assertRaises(ValueError):
            parse_air_date("sometime in 2011")
