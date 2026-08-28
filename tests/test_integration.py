import json
import pathlib
import tempfile
import unittest

from snarchiver.catalog import build_catalog
from snarchiver.dates import assign_publish_dates
from snarchiver.naming import FILENAME_RE, episode_stem
from snarchiver.sidecar import write_sidecars

FIXTURES = pathlib.Path(__file__).parent / "fixtures"
SCHEMA = json.loads((FIXTURES / "episode-sidecar.schema.json").read_text())

_TYPES = {"string": str, "integer": int}


def validate(instance):
    """Hand-rolled check against the vendored schema; no jsonschema in stdlib."""
    errors = []
    properties = SCHEMA["properties"]
    if not SCHEMA.get("additionalProperties", True):
        for key in instance:
            if key not in properties:
                errors.append(f"unknown key {key}")
    for key, value in instance.items():
        rule = properties.get(key)
        if not rule:
            continue
        expected = _TYPES[rule["type"]]
        if expected is int and isinstance(value, bool):
            errors.append(f"{key} must not be a bool")
        elif not isinstance(value, expected):
            errors.append(f"{key} must be {rule['type']}")
            continue
        if "minLength" in rule and len(value) < rule["minLength"]:
            errors.append(f"{key} shorter than {rule['minLength']}")
        if "maxLength" in rule and len(value) > rule["maxLength"]:
            errors.append(f"{key} longer than {rule['maxLength']}")
        if "minimum" in rule and value < rule["minimum"]:
            errors.append(f"{key} below {rule['minimum']}")
    return errors


def fetch(url, **kwargs):
    pages = {
        "https://www.grc.com/securitynow.htm": "grc-current.htm",
        "https://www.grc.com/sn/past/2005.htm": "grc-2005.htm",
        "https://www.grc.com/sn/past/2012.htm": "grc-2012.htm",
        "https://www.grc.com/sn/past/2022.htm": "grc-2022.htm",
    }
    name = pages.get(url)
    if name:
        return (FIXTURES / name).read_text(encoding="utf-8", errors="replace")
    if url.endswith("/436"):
        return (FIXTURES / "twit-436.html").read_text(encoding="utf-8",
                                                      errors="replace")
    return "<html></html>"


class TestPipeline(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.result = build_catalog(fetch=fetch, twit_lookup={436}, probe=lambda url: False)
        cls.catalog = cls.result.episodes
        cls.published = assign_publish_dates(cls.catalog.values())

    def test_full_fixture_set_is_a_complete_fetch(self):
        self.assertTrue(self.result.complete)

    def test_catalog_spans_fixtures(self):
        self.assertIn(1, self.catalog)
        self.assertIn(1093, self.catalog)

    def test_twit_gap_recovered(self):
        self.assertEqual(self.catalog[436].title, "Time Traveling with Steve")

    def test_publish_dates_strictly_increasing(self):
        stamps = [self.published[n] for n in sorted(self.published)]
        self.assertEqual(stamps, sorted(stamps))
        self.assertEqual(len(stamps), len(set(stamps)))

    def test_known_collision_resolved(self):
        self.assertEqual(self.published[885], "2022-08-23T00:00:00Z")
        self.assertEqual(self.published[886], "2022-08-23T00:01:00Z")

    def test_every_stem_matches_minuspod_pattern(self):
        for episode in self.catalog.values():
            stem = episode_stem(episode.number, episode.title)
            self.assertRegex(stem, FILENAME_RE)

    def test_every_basename_under_byte_cap(self):
        for episode in self.catalog.values():
            stem = episode_stem(episode.number, episode.title)
            self.assertLess(len((stem + ".json").encode("utf-8")), 255)

    def test_every_sidecar_validates(self):
        with tempfile.TemporaryDirectory() as tmp:
            out = pathlib.Path(tmp)
            for episode in self.catalog.values():
                if not episode.is_complete:
                    continue
                stem = episode_stem(episode.number, episode.title)
                write_sidecars(out, stem, episode, self.published[episode.number])
                data = json.loads((out / f"{stem}.json").read_text(encoding="utf-8"))
                self.assertEqual(validate(data), [], f"ep {episode.number}")

    def test_unreleased_episode_excluded_from_writing(self):
        self.assertFalse(self.catalog[1093].is_complete)
