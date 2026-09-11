from __future__ import annotations

import json
from pathlib import Path
from typing import Iterable

from .models import ConflictEpisode


class EpisodeLog:
    """Append-only JSONL store for refusal snapshots."""

    def __init__(self, path: str | Path) -> None:
        self.path = Path(path)

    def append(self, episode: ConflictEpisode) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with self.path.open("a", encoding="utf-8") as stream:
            json.dump(episode.to_dict(), stream, sort_keys=True)
            stream.write("\n")

    def write(self, episodes: Iterable[ConflictEpisode]) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with self.path.open("w", encoding="utf-8") as stream:
            for episode in episodes:
                json.dump(episode.to_dict(), stream, sort_keys=True)
                stream.write("\n")

    def read(self) -> list[ConflictEpisode]:
        episodes: list[ConflictEpisode] = []
        with self.path.open(encoding="utf-8") as stream:
            for line in stream:
                if line.strip():
                    episodes.append(ConflictEpisode.from_dict(json.loads(line)))
        return episodes
