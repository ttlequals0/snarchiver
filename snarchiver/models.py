import datetime
from dataclasses import dataclass


@dataclass
class Episode:
    number: int
    title: str
    description: str
    air_date: datetime.date
    audio_url: str | None
    notes_url: str | None
    source: str

    @property
    def is_complete(self) -> bool:
        return bool(self.audio_url) and bool(self.description.strip())
