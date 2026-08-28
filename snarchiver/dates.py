import datetime
import logging
import re

_MISSING_SPACE = re.compile(r"([A-Za-z])(\d)")
_SEPT = re.compile(r"\bSept\b", re.IGNORECASE)
_FORMATS = ("%d %b %Y", "%d %B %Y")

logger = logging.getLogger(__name__)
ISO_FORMAT = "%Y-%m-%dT%H:%M:%SZ"
_NUDGE = datetime.timedelta(minutes=1)


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


def assign_publish_dates(episodes) -> dict[int, str]:
    """Episode number -> ISO timestamp, strictly increasing by episode number.

    MinusPod rejects equal or decreasing dates outright, so collisions are
    nudged forward rather than left to fail the whole import.
    """
    out: dict[int, str] = {}
    previous = None
    for episode in sorted(episodes, key=lambda e: e.number):
        stamp = datetime.datetime(
            episode.air_date.year, episode.air_date.month, episode.air_date.day,
            tzinfo=datetime.timezone.utc,
        )
        if previous is not None and stamp <= previous:
            nudged = previous + _NUDGE
            logger.warning(
                "ep %d: air date %s is not after ep before it; using %s",
                episode.number, episode.air_date.isoformat(),
                nudged.strftime(ISO_FORMAT),
            )
            stamp = nudged
        out[episode.number] = stamp.strftime(ISO_FORMAT)
        previous = stamp
    return out
