# snarchiver

Archives the Security Now podcast from grc.com into a directory
[MinusPod](https://github.com/ttlequals0/MinusPod) can bulk-import as a local
feed, preserving each episode's real air date.

Python 3.11+, standard library only -- no runtime dependencies. `pdfimages`
(poppler) is optional and used only for artwork.

Run it with [uv](https://docs.astral.sh/uv/), which pins the interpreter so
every run is identical:

    uv run snarchiver --help

uv is configured with `python-preference = "only-managed"`, so it always uses
an interpreter it manages rather than whichever `python3` happens to be on
PATH. That matters: a discovered interpreter may lack a CA bundle, and every
HTTPS fetch then fails with `CERTIFICATE_VERIFY_FAILED`.

## Usage

    uv run snarchiver --from 1 --out /srv/minuspod/import/security-now

Later runs need no arguments; the state file resumes where the last one stopped:

    uv run snarchiver --out /srv/minuspod/import/security-now

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

Requires a Python 3.11+ interpreter with a working SSL trust store. Running
through `uv run` handles this: uv's managed interpreters ship with a usable
trust store. If you invoke a system interpreter directly and see
`CERTIFICATE_VERIFY_FAILED`, that interpreter has no CA bundle -- either use
`uv run`, or point it at one with `SSL_CERT_FILE=/etc/ssl/cert.pem`.

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

A full backfill is roughly **68 GB** and, at the default 2-second delay, a day
or two of wall clock. It is safely stoppable and resumable.

Note that the listing page's advertised sizes understate this. Those describe
GRC's own 64 kbps files, but the download URL redirects to a CDN serving a
higher-bitrate encoding -- episode 1092 is listed as 69 MB and arrives as
155 MB. Episodes up to roughly #1000 average about 57 MB; everything after
averages about 155 MB.

## Feed cover

`assets/sn-archive-cover.png` (3000x3000). Upload once:

    POST /api/v1/feeds/{slug}/artwork

## Tests

    uv run python -m unittest discover -s tests -v

No test touches the network; all parsing runs against frozen fixtures.
