import argparse
import logging
import pathlib
import sys
import tempfile
import time

from snarchiver import artwork as artwork_mod
from snarchiver import catalog as catalog_mod
from snarchiver import download
from snarchiver.dates import assign_publish_dates
from snarchiver.naming import episode_stem
from snarchiver.sidecar import write_sidecars
from snarchiver.state import DEFAULT_STATE_PATH, load_state, save_state

logger = logging.getLogger("snarchiver")


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="snarchiver",
                                     description="Archive Security Now for MinusPod import")
    parser.add_argument("--from", dest="from_", type=int,
                        help="first episode (default: one past the state file)")
    parser.add_argument("--to", type=int, help="last episode")
    parser.add_argument("--out", default="episodes", help="output directory")
    parser.add_argument("--delay", type=float, default=2.0,
                        help="seconds between episodes (default 2)")
    parser.add_argument("--state", default=DEFAULT_STATE_PATH)
    parser.add_argument("--artwork", action="store_true",
                        help="extract episode art from notes PDFs")
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--force", action="store_true",
                        help="re-download episodes already on disk")
    parser.add_argument("-v", "--verbose", action="store_true")
    return parser


def select_targets(catalog, state, from_, to):
    floor = state.floor() if from_ is None else from_
    wanted = {n for n in catalog if n >= floor and (to is None or n <= to)}
    # Pending is retried regardless of floor (that's the point of pending),
    # but --to still bounds it like everything else.
    wanted |= {n for n in state.pending
              if n in catalog and (to is None or n <= to)}
    return [catalog[n] for n in sorted(wanted)]


# Results that involved a network round trip; only these justify --delay.
NETWORK_RESULTS = {"downloaded", "failed"}


def _wants_artwork(artwork_enabled, episode):
    return (artwork_enabled and episode.notes_url
            and episode.notes_url.lower().endswith(".pdf"))


def archive_episode(episode, published_at, out_dir, state, *, artwork, force,
                    downloader=None):
    # Looked up dynamically (not bound as a default) so tests can patch
    # download.download_file and have main()'s un-parameterized call see it.
    downloader = downloader or download.download_file
    if not episode.is_complete:
        logger.warning("ep %d: missing audio or description; skipped",
                       episode.number)
        state.mark_pending(episode.number)
        return "incomplete"

    out_dir = pathlib.Path(out_dir)
    try:
        stem = episode_stem(episode.number, episode.title)
    except Exception as exc:  # a malformed title must not kill the run
        logger.error("ep %d: naming failed: %s", episode.number, exc)
        state.mark_pending(episode.number)
        return "failed"

    audio_path = out_dir / f"{stem}.mp3"
    temp_audio_path = out_dir / f"{stem}.mp3.part"

    if audio_path.exists() and not force:
        # Audio-only reordering (sidecars written after download) means a
        # kill between the two can strand an .mp3 with no .json/.txt; that
        # would otherwise never self-heal once last_complete passes it.
        txt_path = out_dir / f"{stem}.txt"
        json_path = out_dir / f"{stem}.json"
        art_path = out_dir / f"{stem}.jpg"
        repaired = False
        try:
            if not txt_path.exists() or not json_path.exists():
                write_sidecars(out_dir, stem, episode, published_at)
                repaired = True
            if _wants_artwork(artwork, episode) and not art_path.exists():
                _try_artwork(episode, out_dir, stem)
                repaired = repaired or art_path.exists()
        except Exception as exc:  # full disk, permissions, etc: retry later
            logger.error("ep %d: repair failed: %s", episode.number, exc)
            state.mark_pending(episode.number)
            return "failed"
        state.mark_complete(episode.number)
        return "repaired" if repaired else "skipped"

    # Download to a name MinusPod ignores (.part), then write sidecars,
    # then rename the audio into place last. A kill at any point leaves
    # either nothing, or an ignored temp file plus sidecars, never a
    # finished .mp3 with no .json, which is what makes MinusPod synthesize
    # a wrong date.
    try:
        downloader(episode.audio_url, temp_audio_path)
    except Exception as exc:  # one bad episode must not end the run
        logger.warning("ep %d: download failed: %s", episode.number, exc)
        temp_audio_path.unlink(missing_ok=True)
        state.mark_pending(episode.number)
        return "failed"

    try:
        write_sidecars(out_dir, stem, episode, published_at)
        if _wants_artwork(artwork, episode):
            _try_artwork(episode, out_dir, stem)
        temp_audio_path.replace(audio_path)
    except Exception as exc:  # full disk, permissions, etc: retry later
        logger.error("ep %d: archiving failed: %s", episode.number, exc)
        state.mark_pending(episode.number)
        return "failed"

    state.mark_complete(episode.number)
    return "downloaded"


def _try_artwork(episode, out_dir, stem):
    # The notes PDF is staged outside out_dir: MinusPod scans that directory
    # and would report a stray .pdf as a rejected file mid-run.
    with tempfile.TemporaryDirectory() as work:
        pdf = pathlib.Path(work) / "notes.pdf"
        try:
            download.download_file(episode.notes_url, pdf)
            if artwork_mod.extract_cover(pdf, out_dir / f"{stem}.jpg"):
                logger.info("ep %d: artwork extracted", episode.number)
        except Exception as exc:
            logger.info("ep %d: no artwork (%s)", episode.number, exc)


def _gap_floor(catalog) -> int | None:
    """Highest episode number safe to treat as a complete floor.

    None if the catalog has no hole below its highest number: every number
    from 1 up to the max is present, so any absence above that is a
    genuine upstream skip, not a fetch artifact.
    """
    if not catalog:
        return None
    highest = max(catalog)
    for number in range(1, highest + 1):
        if number not in catalog:
            return number - 1
    return None


def main(argv=None) -> int:
    args = build_parser().parse_args(argv)
    logging.basicConfig(level=logging.DEBUG if args.verbose else logging.INFO,
                        format="%(levelname)s %(message)s", stream=sys.stderr)

    use_artwork = args.artwork
    if use_artwork and not artwork_mod.have_pdfimages():
        logger.warning("pdfimages not found; artwork extraction disabled")
        use_artwork = False

    out_dir = pathlib.Path(args.out)
    state_path = pathlib.Path(args.state)
    state = load_state(state_path)

    try:
        catalog_result = catalog_mod.build_catalog()
    except Exception as exc:
        logger.error("could not build catalog: %s", exc)
        return 1
    catalog = catalog_result.episodes
    if not catalog:
        logger.error("no episodes found; is grc.com reachable?")
        return 1

    exit_code = 0
    if not catalog_result.complete:
        # A page-fetch failure can hide episode numbers that are really
        # upstream. Leave any resulting hole out of state.completed rather
        # than capping anything: floor() already stops at the first
        # incomplete number on its own, and completed entries from a prior
        # run are never touched here, so a later run with a working fetch
        # can still discover and fill the hole.
        floor_cap = _gap_floor(catalog)
        gap_msg = (f"; catalog has a hole starting at episode {floor_cap + 1}"
                  if floor_cap is not None else "; no hole below the current max")
        logger.error("catalog incomplete: failed pages %s%s",
                     catalog_result.failed_pages, gap_msg)
        exit_code = 1
    else:
        # The fetch was fully successful, so any number missing below the
        # max is a genuine, permanent upstream skip, not a fetch artifact:
        # there is nothing to archive, so mark it complete now rather than
        # stalling the floor on it forever.
        for number in range(1, max(catalog) + 1):
            if number not in catalog:
                state.mark_complete(number)

    published = assign_publish_dates(catalog.values())
    targets = select_targets(catalog, state, args.from_, args.to)
    logger.info("%d episodes in catalog, %d selected", len(catalog), len(targets))

    if args.dry_run:
        for episode in targets:
            logger.info("would archive ep %d: %s", episode.number, episode.title)
        return exit_code

    out_dir.mkdir(parents=True, exist_ok=True)
    incomplete = []
    for index, episode in enumerate(targets):
        result = archive_episode(episode, published[episode.number], out_dir,
                                 state, artwork=use_artwork, force=args.force)
        if result == "incomplete":
            incomplete.append(episode.number)
        logger.info("ep %d: %s", episode.number, result)
        try:
            save_state(state_path, state)
        except Exception as exc:  # full disk, permissions, etc: keep archiving
            logger.error("could not save state: %s", exc)
            exit_code = 1
        if args.delay and result in NETWORK_RESULTS and index + 1 < len(targets):
            time.sleep(args.delay)
    if incomplete:
        # Each incomplete episode already logged a warning mid-run; that
        # scrolls away over an hours-long run, so summarize at the end too.
        logger.warning("%d episode(s) skipped as incomplete: %s",
                       len(incomplete), ", ".join(str(n) for n in incomplete))
    return exit_code


if __name__ == "__main__":
    sys.exit(main())
