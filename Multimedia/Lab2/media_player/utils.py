from __future__ import annotations

from pathlib import Path
from urllib.parse import unquote, urlparse

AUDIO_EXTENSIONS = (".mp3", ".wav", ".flac", ".ogg", ".opus", ".m4a", ".aac", ".wma")
VIDEO_EXTENSIONS = (".mp4", ".mkv", ".webm", ".avi", ".mov", ".wmv", ".m4v")
PLAYLIST_EXTENSIONS = (".m3u", ".m3u8")

_URL_SCHEMES = ("http", "https", "rtsp", "rtmp", "ftp")


def format_time(ms: int) -> str:
    total = max(0, int(ms)) // 1000
    hours, rest = divmod(total, 3600)
    minutes, seconds = divmod(rest, 60)
    if hours:
        return f"{hours}:{minutes:02d}:{seconds:02d}"
    return f"{minutes}:{seconds:02d}"


def is_url(text: str) -> bool:
    parsed = urlparse(text.strip())
    return parsed.scheme.lower() in _URL_SCHEMES and bool(parsed.netloc)


def media_kind(source: str) -> str | None:
    path = urlparse(source).path if is_url(source) else source
    suffix = Path(path).suffix.lower()
    if suffix in AUDIO_EXTENSIONS:
        return "audio"
    if suffix in VIDEO_EXTENSIONS:
        return "video"
    return None


def is_supported_file(path: str) -> bool:
    return media_kind(path) is not None


def display_name(source: str) -> str:
    if is_url(source):
        parsed = urlparse(source)
        name = unquote(Path(parsed.path).name)
        return name or parsed.netloc
    return Path(source).name or source


def open_file_filter() -> str:
    def mask(exts: tuple[str, ...]) -> str:
        return " ".join(f"*{e}" for e in exts)

    all_media = AUDIO_EXTENSIONS + VIDEO_EXTENSIONS
    return ";;".join(
        (
            f"Усі медіафайли ({mask(all_media)})",
            f"Аудіо ({mask(AUDIO_EXTENSIONS)})",
            f"Відео ({mask(VIDEO_EXTENSIONS)})",
            f"Списки відтворення ({mask(PLAYLIST_EXTENSIONS)})",
            "Усі файли (*)",
        )
    )
