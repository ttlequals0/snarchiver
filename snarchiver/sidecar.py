import json
import pathlib

from snarchiver.naming import sn_title

SIDECAR_KEYS = {"title", "description", "published_at", "season", "episode"}
SEASON = 1


def description_text(episode) -> str:
    body = episode.description.strip()
    if episode.notes_url:
        body = f"{body}\n\nShow notes: {episode.notes_url}"
    return body


def write_sidecars(out_dir, stem: str, episode, published_at: str) -> None:
    out_dir = pathlib.Path(out_dir)
    body = description_text(episode)

    payload = {
        "title": sn_title(episode.number, episode.title),
        "description": body,
        "published_at": published_at,
        "season": SEASON,
        "episode": episode.number,
    }

    json_path = out_dir / f"{stem}.json"
    json_tmp = out_dir / f"{stem}.json.tmp"
    txt_path = out_dir / f"{stem}.txt"
    txt_tmp = out_dir / f"{stem}.txt.tmp"

    try:
        json_tmp.write_text(
            json.dumps(payload, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
        json_tmp.replace(json_path)
    except Exception:
        json_tmp.unlink(missing_ok=True)
        raise

    try:
        txt_tmp.write_text(body + "\n", encoding="utf-8")
        txt_tmp.replace(txt_path)
    except Exception:
        txt_tmp.unlink(missing_ok=True)
        raise
