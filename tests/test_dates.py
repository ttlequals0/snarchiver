import datetime
import logging
import unittest

from snarchiver.dates import ISO_FORMAT, assign_publish_dates, parse_air_date
from snarchiver.models import Episode


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


def ep(number, y, m, d):
    return Episode(number=number, title=f"Ep {number}", description="x",
                   air_date=datetime.date(y, m, d), audio_url="u",
                   notes_url=None, source="grc")


class TestAssignPublishDates(unittest.TestCase):
    def test_midnight_utc_for_distinct_dates(self):
        out = assign_publish_dates([ep(1, 2005, 8, 19), ep(2, 2005, 8, 25)])
        self.assertEqual(out[1], "2005-08-19T00:00:00Z")
        self.assertEqual(out[2], "2005-08-25T00:00:00Z")

    def test_same_date_collision_is_nudged_one_minute(self):
        out = assign_publish_dates([ep(885, 2022, 8, 23), ep(886, 2022, 8, 23)])
        self.assertEqual(out[885], "2022-08-23T00:00:00Z")
        self.assertEqual(out[886], "2022-08-23T00:01:00Z")

    def test_nudge_preserves_calendar_date(self):
        out = assign_publish_dates([ep(885, 2022, 8, 23), ep(886, 2022, 8, 23)])
        self.assertTrue(out[886].startswith("2022-08-23T"))

    def test_backwards_date_is_pulled_forward(self):
        out = assign_publish_dates([ep(10, 2020, 5, 5), ep(11, 2020, 5, 1)])
        self.assertEqual(out[11], "2020-05-05T00:01:00Z")

    def test_result_is_strictly_increasing(self):
        eps = [ep(1, 2020, 1, 1), ep(2, 2020, 1, 1), ep(3, 2020, 1, 1)]
        out = assign_publish_dates(eps)
        values = [out[n] for n in sorted(out)]
        self.assertEqual(values, sorted(set(values)))

    def test_unsorted_input_is_ordered_by_episode_number(self):
        out = assign_publish_dates([ep(2, 2005, 8, 25), ep(1, 2005, 8, 19)])
        self.assertLess(out[1], out[2])

    def test_collision_logs_a_warning(self):
        with self.assertLogs("snarchiver.dates", level=logging.WARNING) as cm:
            assign_publish_dates([ep(885, 2022, 8, 23), ep(886, 2022, 8, 23)])
        self.assertIn("886", "".join(cm.output))
