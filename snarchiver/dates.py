import datetime
import re

_MISSING_SPACE = re.compile(r"([A-Za-z])(\d)")
_SEPT = re.compile(r"\bSept\b", re.IGNORECASE)
_FORMATS = ("%d %b %Y", "%d %B %Y")


def parse_air_date(raw: str) -> datetime.date:
    s = _MISSING_SPACE.sub(r"\1 \2", raw.strip())
    s = _SEPT.sub("Sep", s)
    s = re.sub(r"\s+", " ", s)
    for fmt in _FORMATS:
        try:
            return datetime.datetime.strptime(s, fmt).date()
        except ValueError:
            continue
    raise ValueError(f"unrecognized air date: {raw!r}")
