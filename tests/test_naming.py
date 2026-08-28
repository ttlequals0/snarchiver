import unittest

from snarchiver.naming import FILENAME_RE, MAX_BASENAME_BYTES, episode_stem, sn_title


class TestSnTitle(unittest.TestCase):
    def test_formats_four_digit_episode_number(self):
        self.assertEqual(sn_title(19, "VPNs Three: Hamachi, iPig, and OpenVPN"),
                         "SN0019: VPNs Three: Hamachi, iPig, and OpenVPN")

    def test_pads_episode_number_to_four_digits(self):
        self.assertEqual(sn_title(1, "Title"), "SN0001: Title")

    def test_does_not_pad_beyond_four_digits(self):
        self.assertEqual(sn_title(1093, "Title"), "SN1093: Title")


class TestEpisodeStem(unittest.TestCase):
    def test_basic_stem(self):
        self.assertEqual(episode_stem(1, "As the Worm Turns"),
                         "s01e0001 - SN0001: As the Worm Turns")

    def test_four_digit_episode(self):
        self.assertEqual(episode_stem(1093, "Tokens in the Stream"),
                         "s01e1093 - SN1093: Tokens in the Stream")

    def test_path_hostile_characters_replaced(self):
        # The SN-prefix colon is expected and lives before the title; only
        # the sanitized title portion after it must be free of hostile chars.
        stem = episode_stem(5, 'A/B: "C" <D>|E?F*G\\H')
        prefix = "s01e0005 - SN0005: "
        self.assertTrue(stem.startswith(prefix), stem)
        title_part = stem[len(prefix):]
        for bad in '/\\:*?"<>|':
            self.assertNotIn(bad, title_part)

    def test_whitespace_collapsed(self):
        self.assertEqual(episode_stem(7, "Too    many\tspaces"),
                         "s01e0007 - SN0007: Too many spaces")

    def test_trailing_dots_and_spaces_stripped(self):
        self.assertEqual(episode_stem(8, "Trailing dots...  "),
                         "s01e0008 - SN0008: Trailing dots")

    def test_empty_title_falls_back(self):
        self.assertEqual(episode_stem(9, "   "), "s01e0009 - SN0009: Episode 9")

    def test_title_of_only_bad_characters_falls_back(self):
        self.assertEqual(episode_stem(10, "///"), "s01e0010 - SN0010: Episode 10")

    def test_long_title_truncated_under_byte_cap(self):
        stem = episode_stem(11, "x" * 400)
        self.assertLessEqual(len((stem + ".json").encode("utf-8")),
                             MAX_BASENAME_BYTES)

    def test_truncation_does_not_split_a_utf8_character(self):
        stem = episode_stem(12, "é" * 300)
        stem.encode("utf-8").decode("utf-8")  # must not raise

    def test_unicode_title_preserved(self):
        self.assertEqual(episode_stem(13, "Café Attack"),
                         "s01e0013 - SN0013: Café Attack")

    def test_temp_suffix_is_neutralised(self):
        self.assertFalse(episode_stem(14, "dump.part").endswith(".part"))

    def test_byte_cap_invariant_with_temp_suffix(self):
        title = "x" * 234 + ".part"
        stem = episode_stem(1, title)
        self.assertLessEqual(len((stem + ".json").encode("utf-8")),
                             MAX_BASENAME_BYTES)

    def test_byte_cap_invariant_with_longest_transient_suffix(self):
        # .json.tmp / .mp3.part / .jpg.part outlive .json alone on disk;
        # a maximal stem must still fit under the cap with any of them.
        stem = episode_stem(1, "x" * 400)
        for suffix in (".json.tmp", ".mp3.part", ".jpg.part"):
            self.assertLessEqual(len((stem + suffix).encode("utf-8")),
                                 MAX_BASENAME_BYTES, suffix)

    def test_literal_dash_title_preserved(self):
        self.assertEqual(episode_stem(99, "-"), "s01e0099 - SN0099: -")

    def test_every_stem_matches_minuspod_pattern(self):
        for number, title in [(1, "A"), (1093, "B"), (9, "   "), (11, "x" * 400)]:
            self.assertRegex(episode_stem(number, title), FILENAME_RE)

    # -- SN-prefix tests --------------------------------------------------

    def test_sn_prefix_worked_example(self):
        stem = episode_stem(19, "VPNs Three: Hamachi, iPig, and OpenVPN")
        self.assertEqual(stem,
                         "s01e0019 - SN0019: VPNs Three- Hamachi, iPig, and OpenVPN")

    def test_byte_cap_boundary_title_that_previously_just_fit(self):
        # Under the pre-SN-prefix budget (234 bytes), a 234-char title fit
        # exactly. The extra 8 bytes for "SN0001: " must now be reserved
        # too, so this title must be truncated further, not overflow.
        stem = episode_stem(1, "x" * 234)
        self.assertEqual(stem, "s01e0001 - SN0001: " + "x" * 226)
        self.assertLessEqual(len((stem + ".json.tmp").encode("utf-8")),
                             MAX_BASENAME_BYTES)
