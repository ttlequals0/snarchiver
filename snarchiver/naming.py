import re

# Local copy of MinusPod's local_import.FILENAME_RE; every stem is asserted
# against it before any file is written.
FILENAME_RE = re.compile(r"^(s\d{2,3}e\d{2,4})(?: - (.+))?$", re.IGNORECASE)

MAX_BASENAME_BYTES = 255
LONGEST_EXT = ".json"
_TEMP_SUFFIXES = (".part", ".tmp")
_HOSTILE = re.compile(r'[/\\:*?"<>|\x00-\x1f]')


def _truncate_utf8(text: str, limit: int) -> str:
    encoded = text.encode("utf-8")
    if len(encoded) <= limit:
        return text
    return encoded[:limit].decode("utf-8", "ignore").rstrip()


def _sanitize(title: str) -> str:
    cleaned = re.sub(r"\s+", " ", title).strip()
    cleaned = _HOSTILE.sub("-", cleaned)
    cleaned = cleaned.strip(". ")
    if not cleaned or cleaned == "-" * len(cleaned):
        return ""
    return cleaned


def episode_stem(number: int, title: str) -> str:
    prefix = f"s01e{number:04d} - "
    cleaned = _sanitize(title) or f"Episode {number}"
    budget = MAX_BASENAME_BYTES - len(prefix.encode()) - len(LONGEST_EXT.encode())
    cleaned = _truncate_utf8(cleaned, budget).strip(". ") or f"Episode {number}"
    if cleaned.lower().endswith(_TEMP_SUFFIXES):
        cleaned += "_"
    stem = prefix + cleaned
    if not FILENAME_RE.match(stem):
        raise ValueError(f"stem rejected by MinusPod pattern: {stem!r}")
    return stem
