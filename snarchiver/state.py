import datetime
import json
import logging
import pathlib
from dataclasses import dataclass, field

logger = logging.getLogger(__name__)

# Kept out of --out on purpose: MinusPod rejects dotfiles and lists every
# unrecognized file in its dry-run plan.
DEFAULT_STATE_PATH = "snarchiver-state.json"
STATE_VERSION = 1


@dataclass
class State:
    last_complete: int = 0
    pending: set[int] = field(default_factory=set)

    def floor(self) -> int:
        return self.last_complete + 1

    def mark_complete(self, number: int) -> None:
        self.last_complete = max(self.last_complete, number)
        self.pending.discard(number)

    def mark_pending(self, number: int) -> None:
        self.pending.add(number)


def load_state(path) -> State:
    path = pathlib.Path(path)
    if not path.exists():
        return State()
    try:
        data = json.loads(path.read_text(encoding="utf-8"))

        # State file must be a JSON object (dict), not array or scalar.
        if not isinstance(data, dict):
            raise ValueError(f"state file must be object, got {type(data).__name__}")

        # Validate last_complete is an integer.
        last_complete = data.get("last_complete", 0)
        if not isinstance(last_complete, int):
            raise ValueError(f"last_complete must be int, got {type(last_complete).__name__}")

        # Validate pending is a list of integers.
        pending_raw = data.get("pending", [])
        if not isinstance(pending_raw, list):
            raise ValueError(f"pending must be list, got {type(pending_raw).__name__}")
        pending = set()
        for item in pending_raw:
            if not isinstance(item, int):
                raise ValueError(f"pending items must be int, got {type(item).__name__}")
            pending.add(item)

        return State(last_complete=last_complete, pending=pending)
    except (OSError, ValueError, TypeError, KeyError) as exc:
        logger.warning("state file %s unreadable (%s); starting fresh", path, exc)
        return State()


def save_state(path, state: State) -> None:
    path = pathlib.Path(path)
    payload = {
        "version": STATE_VERSION,
        "last_complete": state.last_complete,
        "pending": sorted(state.pending),
        "updated": datetime.datetime.now(datetime.timezone.utc)
                   .strftime("%Y-%m-%dT%H:%M:%SZ"),
    }
    tmp = path.with_name(path.name + ".tmp")
    tmp.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
    tmp.replace(path)
