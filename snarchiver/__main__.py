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
    wanted |= {n for n in state.pending if n in catalog}
    return [catalog[n] for n in sorted(wanted)]


def archive_episode(episode, published_at, out_dir, state, *, artwork, force,
                    downloader=download.download_file):
    if not episode.is_complete:
        logger.warning("ep %d: missing audio or description; skipped",
                       episode.number)
        state.mark_pending(episode.number)
        return "incomplete"

    out_dir = pathlib.Path(out_dir)
    stem = episode_stem(episode.number, episode.title)
    audio_path = out_dir / f"{stem}.mp3"

    if audio_path.exists() and not force:
        # Audio-only reordering (sidecars written after download) means a
        # kill between the two can strand an .mp3 with no .json/.txt; that
        # would otherwise never self-heal once last_complete passes it.
        txt_path = out_dir / f"{stem}.txt"
        json_path = out_dir / f"{stem}.json"
        if not txt_path.exists() or not json_path.exists():
            write_sidecars(out_dir, stem, episode, published_at)
            state.mark_complete(episode.number)
            return "repaired"
        state.mark_complete(episode.number)
        return "skipped"

    # Download before writing sidecars: this writes into MinusPod's live
    # import directory, and a failed download must leave no .txt/.json
    # orphans for MinusPod to reject on its next scan.
    try:
        downloader(episode.audio_url, audio_path)
    except Exception as exc:  # one bad episode must not end the run
        logger.warning("ep %d: download failed: %s", episode.number, exc)
        state.mark_pending(episode.number)
        return "failed"

    write_sidecars(out_dir, stem, episode, published_at)

    if artwork and episode.notes_url and episode.notes_url.lower().endswith(".pdf"):
        _try_artwork(episode, out_dir, stem)

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
        catalog = catalog_mod.build_catalog()
    except Exception as exc:
        logger.error("could not build catalog: %s", exc)
        return 1
    if not catalog:
        logger.error("no episodes found; is grc.com reachable?")
        return 1

    published = assign_publish_dates(catalog.values())
    targets = select_targets(catalog, state, args.from_, args.to)
    logger.info("%d episodes in catalog, %d selected", len(catalog), len(targets))

    if args.dry_run:
        for episode in targets:
            logger.info("would archive ep %d: %s", episode.number, episode.title)
        return 0

    out_dir.mkdir(parents=True, exist_ok=True)
    for index, episode in enumerate(targets):
        result = archive_episode(episode, published[episode.number], out_dir,
                                 state, artwork=use_artwork, force=args.force)
        logger.info("ep %d: %s", episode.number, result)
        save_state(state_path, state)
        if args.delay and index + 1 < len(targets):
            time.sleep(args.delay)
    return 0


if __name__ == "__main__":
    sys.exit(main())
