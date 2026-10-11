from __future__ import annotations

import random
from dataclasses import dataclass
from enum import Enum
from pathlib import Path

from .utils import display_name, is_url


class RepeatMode(Enum):
    OFF = "off"
    ALL = "all"
    ONE = "one"

    def next(self) -> "RepeatMode":
        order = list(RepeatMode)
        return order[(order.index(self) + 1) % len(order)]


@dataclass(frozen=True)
class MediaItem:
    source: str
    title: str

    @classmethod
    def from_source(cls, source: str, title: str | None = None) -> "MediaItem":
        source = source.strip()
        if not is_url(source):
            source = str(Path(source).resolve())
        return cls(source, title or display_name(source))

    @property
    def is_remote(self) -> bool:
        return is_url(self.source)


class Playlist:
    def __init__(self) -> None:
        self.items: list[MediaItem] = []
        self.current_index: int = -1
        self.repeat: RepeatMode = RepeatMode.OFF
        self.shuffle: bool = False

    def __len__(self) -> int:
        return len(self.items)

    @property
    def current(self) -> MediaItem | None:
        if 0 <= self.current_index < len(self.items):
            return self.items[self.current_index]
        return None

    def add(self, items: list[MediaItem]) -> int:
        first = len(self.items)
        self.items.extend(items)
        return first

    def remove(self, index: int) -> None:
        if not 0 <= index < len(self.items):
            raise IndexError(index)
        del self.items[index]
        if index < self.current_index:
            self.current_index -= 1
        elif index == self.current_index:
            self.current_index = -1

    def clear(self) -> None:
        self.items.clear()
        self.current_index = -1

    def set_current(self, index: int) -> MediaItem:
        if not 0 <= index < len(self.items):
            raise IndexError(index)
        self.current_index = index
        return self.items[index]

    def next_index(self, auto: bool = False) -> int | None:
        if not self.items:
            return None
        if auto and self.repeat is RepeatMode.ONE and self.current is not None:
            return self.current_index
        if self.shuffle and len(self.items) > 1:
            candidates = [i for i in range(len(self.items)) if i != self.current_index]
            return random.choice(candidates)
        nxt = self.current_index + 1
        if nxt < len(self.items):
            return nxt
        return 0 if self.repeat is not RepeatMode.OFF else None

    def previous_index(self) -> int | None:
        if not self.items:
            return None
        prev = self.current_index - 1
        if prev >= 0:
            return prev
        return len(self.items) - 1 if self.repeat is not RepeatMode.OFF else 0


    def save_m3u(self, path: str | Path) -> None:
        lines = ["#EXTM3U"]
        for item in self.items:
            lines.append(f"#EXTINF:-1,{item.title}")
            lines.append(item.source)
        Path(path).write_text("\n".join(lines) + "\n", encoding="utf-8")

    @staticmethod
    def load_m3u(path: str | Path) -> list[MediaItem]:
        path = Path(path)
        base = path.parent
        items: list[MediaItem] = []
        pending_title: str | None = None
        for raw in path.read_text(encoding="utf-8-sig", errors="replace").splitlines():
            line = raw.strip()
            if not line:
                continue
            if line.startswith("#EXTINF"):
                _, _, title = line.partition(",")
                pending_title = title.strip() or None
                continue
            if line.startswith("#"):
                continue
            source = line if is_url(line) else str((base / line).resolve())
            items.append(MediaItem.from_source(source, pending_title))
            pending_title = None
        return items
