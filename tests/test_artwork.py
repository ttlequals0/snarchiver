import unittest
from unittest.mock import patch, MagicMock
import subprocess
import tempfile
import pathlib

from snarchiver.artwork import MAX_ASPECT, MIN_DIMENSION, acceptable, extract_cover, _page_one_size


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
    def test_mock_pdfimages_stdout_format(self):
        """Verify mock stdout format parses correctly as per pdfimages output."""
        mock_stdout = (
            "page   num  type   width height color comp bpc  enc interp  object ID\n"
            "---------------------------------------------------------------------\n"
            "   1     0 image     600   400  icc     3   8  jpeg   no         8  0"
        )
        with patch("snarchiver.artwork.subprocess.run") as mock_run:
            result = MagicMock()
            result.returncode = 0
            result.stdout = mock_stdout
            mock_run.return_value = result
            size = _page_one_size("/tmp/test.pdf")
            self.assertEqual(size, (600, 400), "Mock stdout should parse to (600, 400)")

    def test_malformed_first_row_falls_through_to_a_later_usable_row(self):
        mock_stdout = (
            "page   num  type   width height color comp bpc  enc interp  object ID\n"
            "---------------------------------------------------------------------\n"
            "   1     0 image     N/A   N/A  icc     3   8  jpeg   no         8  0\n"
            "   1     1 image     600   400  icc     3   8  jpeg   no         9  0"
        )
        with patch("snarchiver.artwork.subprocess.run") as mock_run:
            result = MagicMock()
            result.returncode = 0
            result.stdout = mock_stdout
            mock_run.return_value = result
            size = _page_one_size("/tmp/test.pdf")
            self.assertEqual(size, (600, 400))

    def test_all_rows_malformed_returns_none(self):
        mock_stdout = (
            "page   num  type   width height color comp bpc  enc interp  object ID\n"
            "---------------------------------------------------------------------\n"
            "   1     0 image     N/A   N/A  icc     3   8  jpeg   no         8  0"
        )
        with patch("snarchiver.artwork.subprocess.run") as mock_run:
            result = MagicMock()
            result.returncode = 0
            result.stdout = mock_stdout
            mock_run.return_value = result
            self.assertIsNone(_page_one_size("/tmp/test.pdf"))

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
    def test_extract_cover_cleans_up_on_move_failure(self, mock_run):
        with tempfile.TemporaryDirectory() as tmpdir:
            dest = pathlib.Path(tmpdir) / "out.jpg"
            staged = dest.with_name(dest.name + ".part")

            def subprocess_side_effect(*args, **kwargs):
                result = MagicMock()
                result.returncode = 0
                if "-list" in args[0]:
                    result.stdout = (
                        "page   num  type   width height color comp bpc  enc interp  object ID\n"
                        "---------------------------------------------------------------------\n"
                        "   1     0 image     600   400  icc     3   8  jpeg   no         8  0"
                    )
                else:
                    work_dir = pathlib.Path(args[0][-1]).parent
                    (work_dir / "img-000.jpg").write_text("fake image data")
                return result

            mock_run.side_effect = subprocess_side_effect

            with patch.object(pathlib.Path, "replace") as mock_replace:
                mock_replace.side_effect = OSError("Disk full")
                result = extract_cover("/tmp/test.pdf", str(dest))
                self.assertFalse(result)
                self.assertFalse(staged.exists())
                self.assertFalse(dest.exists())
                mock_replace.assert_called_once()
