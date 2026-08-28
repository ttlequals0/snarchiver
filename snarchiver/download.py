import logging
import pathlib
import time
import urllib.request

logger = logging.getLogger(__name__)

USER_AGENT = "snarchiver/1.0 (personal podcast archiver)"
_CHUNK = 1 << 16


def _default_opener(request, timeout):
    return urllib.request.urlopen(request, timeout=timeout)


def _request(url):
    return urllib.request.Request(url, headers={"User-Agent": USER_AGENT})


def _with_retries(action, *, retries, backoff, what):
    last = None
    for attempt in range(retries):
        try:
            return action()
        except Exception as exc:  # noqa: BLE001 - retried, then re-raised below
            last = exc
            if attempt + 1 < retries:
                delay = backoff * (2 ** attempt)
                logger.warning("%s failed (%s); retrying in %.1fs", what, exc, delay)
                time.sleep(delay)
    raise last


def get_text(url, *, retries=3, timeout=30, backoff=1.0, opener=_default_opener):
    def action():
        with opener(_request(url), timeout) as response:
            return response.read().decode("utf-8", "replace")

    return _with_retries(action, retries=retries, backoff=backoff, what=f"GET {url}")


def download_file(url, dest: pathlib.Path, *, retries=3, timeout=300,
                  backoff=1.0, opener=_default_opener) -> int:
    part = dest.with_name(dest.name + ".part")

    def action():
        written = 0
        with opener(_request(url), timeout) as response, part.open("wb") as handle:
            expected = response.headers.get("Content-Length")
            while True:
                chunk = response.read(_CHUNK)
                if not chunk:
                    break
                handle.write(chunk)
                written += len(chunk)
        if expected is not None and written != int(expected):
            part.unlink(missing_ok=True)
            raise IOError(f"{url}: expected {expected} bytes, got {written}")
        part.replace(dest)
        return written

    try:
        return _with_retries(action, retries=retries, backoff=backoff,
                             what=f"download {url}")
    finally:
        part.unlink(missing_ok=True)
