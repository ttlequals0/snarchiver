import datetime
import json
import logging
import pathlib
from dataclasses import dataclass, field

logger = logging.getLogger(__name__)

# Kept out of --out on purpose: MinusPod rejects dotfiles and lists every
# unrecognized file in its dry-run plan.
DEFAULT_STATE_PATH = "snarchiver-state.json"
STATE_VERSION = 2


@dataclass
class State:
    # Every episode number actually archived, not a high-water mark: a mark
    # like "last_complete=500" cannot distinguish "1-499 are done" from
    # "1-499 were never attempted", which is what made an earlier
    # partial-catalog defect unrecoverable.
    completed: set[int] = field(default_factory=set)
    pending: set[int] = field(default_factory=set)

    def floor(self) -> int:
        """Lowest positive integer not yet completed."""
        n = 1
        while n in self.completed:
            n += 1
        return n

    @property
    def last_complete(self) -> int:
        """Top of the first contiguous completed range, for humans only."""
        return self.floor() - 1

    def mark_complete(self, number: int) -> None:
        self.completed.add(number)
        self.pending.discard(number)

    def mark_pending(self, number: int) -> None:
        self.pending.add(number)


def _ranges_to_set(ranges) -> set[int]:
    completed: set[int] = set()
    for pair in ranges:
        if (not isinstance(pair, list) or len(pair) != 2):
            raise ValueError(f"completed range must be a [start, end] pair, got {pair!r}")
        start, end = pair
        for bound in (start, end):
            if not isinstance(bound, int) or isinstance(bound, bool):
                raise ValueError(f"completed range bounds must be int, got {bound!r}")
        if start < 1 or end < start:
            raise ValueError(f"completed range must satisfy 1 <= start <= end, got {pair!r}")
        completed.update(range(start, end + 1))
    return completed


def _set_to_ranges(numbers: set[int]) -> list[list[int]]:
    ranges: list[list[int]] = []
    for n in sorted(numbers):
        if ranges and n == ranges[-1][1] + 1:
            ranges[-1][1] = n
        else:
            ranges.append([n, n])
    return ranges


def _validate_pending(pending_raw) -> set[int]:
    if not isinstance(pending_raw, list):
        raise ValueError(f"pending must be list, got {type(pending_raw).__name__}")
    pending = set()
    for item in pending_raw:
        if not isinstance(item, int) or isinstance(item, bool):
            raise ValueError(f"pending items must be int, got {type(item).__name__}")
        pending.add(item)
    return pending


def load_state(path) -> State:
    path = pathlib.Path(path)
    if not path.exists():
        return State()
    try:
        data = json.loads(path.read_text(encoding="utf-8"))

        # State file must be a JSON object (dict), not array or scalar.
        if not isinstance(data, dict):
            raise ValueError(f"state file must be object, got {type(data).__name__}")

        version = data.get("version", 1)
        pending = _validate_pending(data.get("pending", []))

        if version == 1:
            # Migrate: a bare last_complete=N means 1..N are complete.
            last_complete = data.get("last_complete", 0)
            if not isinstance(last_complete, int) or isinstance(last_complete, bool):
                raise ValueError(
                    f"last_complete must be int, got {type(last_complete).__name__}")
            if last_complete < 0:
                raise ValueError(f"last_complete must not be negative, got {last_complete}")
            completed = set(range(1, last_complete + 1))
        else:
            ranges = data.get("completed", [])
            if not isinstance(ranges, list):
                raise ValueError(f"completed must be list, got {type(ranges).__name__}")
            completed = _ranges_to_set(ranges)

        return State(completed=completed, pending=pending)
    except (OSError, ValueError, TypeError, KeyError) as exc:
        logger.warning("state file %s unreadable (%s); starting fresh", path, exc)
        return State()


def save_state(path, state: State) -> None:
    path = pathlib.Path(path)
    payload = {
        "version": STATE_VERSION,
        "completed": _set_to_ranges(state.completed),
        # Derived, for humans skimming the file; not read back on load.
        "last_complete": state.last_complete,
        "pending": sorted(state.pending),
        "updated": datetime.datetime.now(datetime.timezone.utc)
                   .strftime("%Y-%m-%dT%H:%M:%SZ"),
    }
    tmp = path.with_name(path.name + ".tmp")
    try:
        tmp.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
        tmp.replace(path)
    except Exception:
        tmp.unlink(missing_ok=True)
        raise
