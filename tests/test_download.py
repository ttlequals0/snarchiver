import io
import pathlib
import tempfile
import unittest

from snarchiver import download


class FakeResponse(io.BytesIO):
    def __init__(self, payload, headers=None):
        super().__init__(payload)
        self.headers = headers or {}

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        self.close()
        return False


class TestGetText(unittest.TestCase):
    def test_decodes_body(self):
        opener = lambda req, timeout: FakeResponse(b"<html>hi</html>")
        self.assertEqual(download.get_text("https://x/", opener=opener),
                         "<html>hi</html>")

    def test_retries_then_succeeds(self):
        calls = []

        def opener(req, timeout):
            calls.append(1)
            if len(calls) < 3:
                raise OSError("boom")
            return FakeResponse(b"ok")

        self.assertEqual(download.get_text("https://x/", opener=opener, backoff=0), "ok")
        self.assertEqual(len(calls), 3)

    def test_raises_after_exhausting_retries(self):
        def opener(req, timeout):
            raise OSError("boom")

        with self.assertRaises(OSError):
            download.get_text("https://x/", opener=opener, retries=2, backoff=0)

    def test_zero_retries_raises_value_error(self):
        opener = lambda req, timeout: FakeResponse(b"ok")
        with self.assertRaises(ValueError):
            download.get_text("https://x/", opener=opener, retries=0)

    def test_negative_retries_raises_value_error(self):
        opener = lambda req, timeout: FakeResponse(b"ok")
        with self.assertRaises(ValueError):
            download.get_text("https://x/", opener=opener, retries=-1)


class TestDownloadFile(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.dest = pathlib.Path(self.tmp.name) / "s01e0001 - T.mp3"

    def tearDown(self):
        self.tmp.cleanup()

    def test_writes_file_and_returns_size(self):
        opener = lambda req, timeout: FakeResponse(b"abcd",
                                                   {"Content-Length": "4"})
        written = download.download_file("https://x/a.mp3", self.dest, opener=opener)
        self.assertEqual(written, 4)
        self.assertEqual(self.dest.read_bytes(), b"abcd")

    def test_no_part_file_remains(self):
        opener = lambda req, timeout: FakeResponse(b"abcd",
                                                   {"Content-Length": "4"})
        download.download_file("https://x/a.mp3", self.dest, opener=opener)
        self.assertFalse(self.dest.with_name(self.dest.name + ".part").exists())

    def test_short_read_raises_and_leaves_no_final_file(self):
        opener = lambda req, timeout: FakeResponse(b"ab", {"Content-Length": "4"})
        with self.assertRaises(IOError):
            download.download_file("https://x/a.mp3", self.dest,
                                   opener=opener, retries=1, backoff=0)
        self.assertFalse(self.dest.exists())

    def test_missing_content_length_is_accepted(self):
        opener = lambda req, timeout: FakeResponse(b"abcd")
        self.assertEqual(
            download.download_file("https://x/a.mp3", self.dest, opener=opener), 4)
