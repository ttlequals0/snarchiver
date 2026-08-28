# snarchiver

Archives the Security Now podcast from grc.com into a directory
[MinusPod](https://github.com/ttlequals0/MinusPod) can bulk-import as a local
feed, preserving each episode's real air date.

Python 3.11+, standard library only. `pdfimages` (poppler) is optional and used
only for artwork.

## Usage

    python3 -m snarchiver --from 1 --out /srv/minuspod/import/security-now

Later runs need no arguments; the state file resumes where the last one stopped:

    python3 -m snarchiver --out /srv/minuspod/import/security-now

| Flag | Meaning |
|---|---|
| `--from N` | First episode; overrides the state floor |
| `--to N` | Last episode |
| `--out DIR` | Output directory (default `episodes`) |
| `--delay SEC` | Pause between episodes (default 2) |
| `--state PATH` | State file (default `snarchiver-state.json`) |
| `--artwork` | Extract episode art from notes PDFs |
| `--dry-run` | Report the plan, write nothing |
| `--force` | Re-download episodes already on disk |
| `-v`, `--verbose` | Debug-level logging |

Requires a Python 3.11+ interpreter with a working SSL trust store. A broken
store surfaces as `CERTIFICATE_VERIFY_FAILED` on every fetch; point `python3`
at an interpreter with valid certificates (e.g. Homebrew's) if you see it.

## Output

Four files per episode, sharing a byte-identical stem:

    s01e0001 - As the Worm Turns.mp3
    s01e0001 - As the Worm Turns.txt
    s01e0001 - As the Worm Turns.json
    s01e0001 - As the Worm Turns.jpg    (optional)

The JSON sidecar carries the real air date. Without it MinusPod synthesizes
publish dates stepping back one day per episode from import time, which would
compress 21 years into a 1093-day window.

## Scale

A full backfill is roughly 45-55 GB and, at the default 2-second delay, a day
or two of wall clock. It is safely stoppable and resumable.

## Feed cover

`assets/sn-archive-cover.png` (3000x3000). Upload once:

    POST /api/v1/feeds/{slug}/artwork

## Tests

    python3 -m unittest discover -s tests -v

No test touches the network; all parsing runs against frozen fixtures.
