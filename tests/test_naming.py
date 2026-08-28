import unittest

from snarchiver.naming import FILENAME_RE, MAX_BASENAME_BYTES, episode_stem


class TestEpisodeStem(unittest.TestCase):
    def test_basic_stem(self):
        self.assertEqual(episode_stem(1, "As the Worm Turns"),
                         "s01e0001 - As the Worm Turns")

    def test_four_digit_episode(self):
        self.assertEqual(episode_stem(1093, "Tokens in the Stream"),
                         "s01e1093 - Tokens in the Stream")

    def test_path_hostile_characters_replaced(self):
        stem = episode_stem(5, 'A/B: "C" <D>|E?F*G\\H')
        for bad in '/\\:*?"<>|':
            self.assertNotIn(bad, stem)

    def test_whitespace_collapsed(self):
        self.assertEqual(episode_stem(7, "Too    many\tspaces"),
                         "s01e0007 - Too many spaces")

    def test_trailing_dots_and_spaces_stripped(self):
        self.assertEqual(episode_stem(8, "Trailing dots...  "),
                         "s01e0008 - Trailing dots")

    def test_empty_title_falls_back(self):
        self.assertEqual(episode_stem(9, "   "), "s01e0009 - Episode 9")

    def test_title_of_only_bad_characters_falls_back(self):
        self.assertEqual(episode_stem(10, "///"), "s01e0010 - Episode 10")

    def test_long_title_truncated_under_byte_cap(self):
        stem = episode_stem(11, "x" * 400)
        self.assertLessEqual(len((stem + ".json").encode("utf-8")),
                             MAX_BASENAME_BYTES)

    def test_truncation_does_not_split_a_utf8_character(self):
        stem = episode_stem(12, "é" * 300)
        stem.encode("utf-8").decode("utf-8")  # must not raise

    def test_unicode_title_preserved(self):
        self.assertEqual(episode_stem(13, "Café Attack"),
                         "s01e0013 - Café Attack")

    def test_temp_suffix_is_neutralised(self):
        self.assertFalse(episode_stem(14, "dump.part").endswith(".part"))

    def test_byte_cap_invariant_with_temp_suffix(self):
        title = "x" * 234 + ".part"
        stem = episode_stem(1, title)
        self.assertLessEqual(len((stem + ".json").encode("utf-8")),
                             MAX_BASENAME_BYTES)

    def test_literal_dash_title_preserved(self):
        self.assertEqual(episode_stem(99, "-"), "s01e0099 - -")

    def test_every_stem_matches_minuspod_pattern(self):
        for number, title in [(1, "A"), (1093, "B"), (9, "   "), (11, "x" * 400)]:
            self.assertRegex(episode_stem(number, title), FILENAME_RE)
