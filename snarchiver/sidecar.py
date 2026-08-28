import json
import pathlib

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

    (out_dir / f"{stem}.txt").write_text(body + "\n", encoding="utf-8")

    payload = {
        "title": episode.title,
        "description": body,
        "published_at": published_at,
        "season": SEASON,
        "episode": episode.number,
    }
    (out_dir / f"{stem}.json").write_text(
        json.dumps(payload, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
