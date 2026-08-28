import html
import logging
import re
from urllib.parse import urljoin

from snarchiver.dates import parse_air_date
from snarchiver.models import Episode

logger = logging.getLogger(__name__)

GRC_BASE = "https://www.grc.com/"

_BLOCK_RE = re.compile(r'<a name="(\d+)"></a>(.*?)(?=<a name="\d+"></a>|\Z)', re.S)
_COMMENT_RE = re.compile(r"<!--.*?-->", re.S)
_META_RE = re.compile(r"Episode&nbsp;#(\d+)\s*\|\s*([^|<]+?)\s*\|")
_TITLE_RE = re.compile(r"<b>(.*?)</b>", re.S)
_AUDIO_RE = re.compile(r"https://media\.grc\.com/sn/sn-\d+\.mp3")
_NOTES_RE = re.compile(r'href="([^"]*notes[^"]*)"')
_TAG_RE = re.compile(r"<[^>]+>")


def _text(fragment: str) -> str:
    plain = html.unescape(_TAG_RE.sub(" ", fragment))
    return re.sub(r"\s+", " ", plain).strip()


def parse_listing_page(page_html: str) -> list[Episode]:
    episodes = []
    for _, raw_block in _BLOCK_RE.findall(page_html):
        block = _COMMENT_RE.sub(" ", raw_block)  # before any link extraction
        meta = _META_RE.search(block)
        title_match = _TITLE_RE.search(block)
        if not meta or not title_match:
            continue
        try:
            air_date = parse_air_date(meta.group(2))
        except ValueError:
            logger.warning("ep %s: unparseable air date %r", meta.group(1), meta.group(2))
            continue

        tail = block[title_match.end():]
        cut = tail.find("</td>")
        description = _text(tail if cut < 0 else tail[:cut])

        audio = _AUDIO_RE.search(block)
        notes = _NOTES_RE.search(block)
        episodes.append(Episode(
            number=int(meta.group(1)),
            title=_text(title_match.group(1)),
            description=description,
            air_date=air_date,
            audio_url=audio.group(0) if audio else None,
            notes_url=urljoin(GRC_BASE, notes.group(1)) if notes else None,
            source="grc",
        ))
    return episodes
