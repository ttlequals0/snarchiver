import datetime
import html
import logging
import re
from dataclasses import dataclass, field
from urllib.parse import urljoin

from snarchiver import download
from snarchiver.dates import parse_air_date
from snarchiver.models import Episode

logger = logging.getLogger(__name__)

GRC_BASE = "https://www.grc.com/"

_BLOCK_RE = re.compile(r'<a name="(\d+)"></a>(.*?)(?=<a name="\d+"></a>|\Z)', re.S)
_COMMENT_RE = re.compile(r"<!--.*?-->", re.S)
_META_RE = re.compile(r"Episode&nbsp;#(\d+)\s*\|\s*([^|<]+?)\s*(?:\||<)")
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


TWIT_BASE = "https://twit.tv/shows/security-now/episodes/"
MEDIA_BASE = "https://media.grc.com/sn/"

_OG_TITLE_RE = re.compile(r'<meta property="og:title" content="([^"]*)"')
_OG_DESC_RE = re.compile(r'<meta property="og:description" content="([^"]*)"')
_AIR_DATE_RE = re.compile(r'air-date">([^<]+)<')
_ORDINAL_RE = re.compile(r"(\d+)(?:st|nd|rd|th)")


def twit_url(number: int) -> str:
    return f"{TWIT_BASE}{number}"


def grc_audio_url(number: int) -> str:
    return f"{MEDIA_BASE}sn-{number:03d}.mp3"


def parse_twit_page(page_html: str, number: int) -> Episode | None:
    title_match = _OG_TITLE_RE.search(page_html)
    date_match = _AIR_DATE_RE.search(page_html)
    if not title_match or not date_match:
        return None

    title = html.unescape(title_match.group(1))
    title = re.sub(r"\s*\|\s*TWiT\.TV\s*$", "", title)
    title = re.sub(r"^\s*Security Now:\s*", "", title).strip()

    raw_date = _ORDINAL_RE.sub(r"\1", date_match.group(1)).strip()
    try:
        air_date = datetime.datetime.strptime(raw_date, "%b %d %Y").date()
    except ValueError:
        logger.warning("ep %d: unparseable TWiT date %r", number, date_match.group(1))
        return None

    desc_match = _OG_DESC_RE.search(page_html)
    return Episode(
        number=number,
        title=title,
        description=html.unescape(desc_match.group(1)).strip() if desc_match else "",
        air_date=air_date,
        audio_url=grc_audio_url(number),
        notes_url=None,
        source="twit",
    )


CURRENT_PAGE = "https://www.grc.com/securitynow.htm"
# Fallback only: used when the current page can't be fetched or yields no
# archive links. Normal operation discovers pages from CURRENT_PAGE itself.
ARCHIVE_YEARS = range(2005, 2026)

# GRC drops one episode at four year boundaries; all four are late-December.
KNOWN_GAPS = {436, 540, 643, 1058}

_ARCHIVE_LINK_RE = re.compile(r'href="(/sn/past/\d{4}\.htm)"')


def discover_archive_urls(page_html: str) -> list[str]:
    """Archive-year page URLs linked from the current page's sidebar."""
    paths = sorted(set(_ARCHIVE_LINK_RE.findall(page_html)))
    return [urljoin(GRC_BASE, path) for path in paths]


def listing_urls(*, fetch=None) -> list[str]:
    archive_urls = []
    if fetch is not None:
        try:
            archive_urls = discover_archive_urls(fetch(CURRENT_PAGE))
        except Exception as exc:
            logger.warning("could not discover archive pages: %s", exc)
    if not archive_urls:
        archive_urls = [
            f"https://www.grc.com/sn/past/{year}.htm" for year in ARCHIVE_YEARS
        ]
    return [CURRENT_PAGE] + archive_urls


@dataclass
class CatalogResult:
    episodes: dict[int, Episode]
    # URLs (listing or TWiT fallback pages) that failed to fetch. Any entry
    # here means the episode numbering may have holes that are fetch
    # artifacts rather than genuine upstream gaps.
    failed_pages: list[str] = field(default_factory=list)

    @property
    def complete(self) -> bool:
        return not self.failed_pages


def build_catalog(*, fetch=download.get_text, twit_lookup=None) -> CatalogResult:
    if twit_lookup is None:
        twit_lookup = set(KNOWN_GAPS)

    catalog: dict[int, Episode] = {}
    failed_pages: list[str] = []
    for url in listing_urls(fetch=fetch):
        try:
            page = fetch(url)
        except Exception as exc:  # a single bad page must not lose the whole run
            logger.warning("listing page %s failed: %s", url, exc)
            failed_pages.append(url)
            continue
        for episode in parse_listing_page(page):
            catalog.setdefault(episode.number, episode)

    for number in sorted(twit_lookup - set(catalog)):
        try:
            page = fetch(twit_url(number))
        except Exception as exc:
            logger.warning("ep %d: TWiT lookup failed: %s", number, exc)
            failed_pages.append(twit_url(number))
            continue
        episode = parse_twit_page(page, number)
        if episode:
            logger.info("ep %d: recovered from TWiT", number)
            catalog[number] = episode
        else:
            logger.warning("ep %d: no metadata on GRC or TWiT", number)
    return CatalogResult(episodes=catalog, failed_pages=failed_pages)
