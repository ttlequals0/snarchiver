import unittest
from unittest.mock import patch
import subprocess

from snarchiver.artwork import MAX_ASPECT, MIN_DIMENSION, acceptable, extract_cover


class TestAcceptable(unittest.TestCase):
    def test_square_photo_accepted(self):
        self.assertTrue(acceptable(526, 526))

    def test_typical_photos_accepted(self):
        for w, h in [(587, 436), (695, 580), (1043, 720), (2016, 1512), (511, 567)]:
            self.assertTrue(acceptable(w, h), f"{w}x{h} should be accepted")

    def test_wide_banner_rejected(self):
        # ep 450's page-1 image
        self.assertFalse(acceptable(868, 200))

    def test_narrow_banner_rejected(self):
        # ep 432's page-1 image
        self.assertFalse(acceptable(496, 194))

    def test_small_image_rejected(self):
        self.assertFalse(acceptable(120, 120))

    def test_min_dimension_boundary(self):
        self.assertTrue(acceptable(MIN_DIMENSION, MIN_DIMENSION))
        self.assertFalse(acceptable(MIN_DIMENSION - 1, MIN_DIMENSION))

    def test_aspect_boundary(self):
        # both sides stay above MIN_DIMENSION so only the ratio decides
        self.assertTrue(acceptable(1200, int(1200 / MAX_ASPECT)))
        self.assertFalse(acceptable(1200, int(1200 / MAX_ASPECT) - 20))

    def test_zero_dimension_rejected(self):
        self.assertFalse(acceptable(0, 500))


class TestExtractCoverRobustness(unittest.TestCase):
    @patch("snarchiver.artwork.subprocess.run")
    def test_extract_cover_handles_file_not_found(self, mock_run):
        mock_run.side_effect = FileNotFoundError("pdfimages not found")
        result = extract_cover("/tmp/test.pdf", "/tmp/out.jpg")
        self.assertFalse(result)

    @patch("snarchiver.artwork.subprocess.run")
    def test_extract_cover_handles_timeout(self, mock_run):
        mock_run.side_effect = subprocess.TimeoutExpired("pdfimages", timeout=60)
        result = extract_cover("/tmp/test.pdf", "/tmp/out.jpg")
        self.assertFalse(result)

    @patch("snarchiver.artwork.subprocess.run")
    def test_extract_cover_handles_empty_output(self, mock_run):
        mock_run.return_value.returncode = 0
        mock_run.return_value.stdout = ""
        result = extract_cover("/tmp/test.pdf", "/tmp/out.jpg")
        self.assertFalse(result)
