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


def _path_of(source: str) -> str:
    return unquote(urlparse(source).path) if is_url(source) else source


def suffix_of(source: str) -> str:
    name = Path(_path_of(source)).name
    if "." not in name:
        return ""
    return "." + name.rsplit(".", 1)[1].lower()


def media_kind(source: str) -> str | None:
    suffix = suffix_of(source)
    if suffix in AUDIO_EXTENSIONS:
        return "audio"
    if suffix in VIDEO_EXTENSIONS:
        return "video"
    return None


def is_supported_file(path: str) -> bool:
    return media_kind(path) is not None


def display_name(source: str) -> str:
    if is_url(source):
        path = Path(_path_of(source))
        name = path.name
        if not name or name.startswith("."):
            name = path.parent.name
        return name or urlparse(source).netloc
    return Path(source).name or source


def describe_source(source: str) -> str:
    remote = is_url(source)
    suffix = suffix_of(source)
    if remote and suffix in PLAYLIST_EXTENSIONS:
        return "Мережа, HLS-потік"
    kind = media_kind(source)
    ext = suffix.lstrip(".").upper()
    label = {"audio": "аудіо", "video": "відео"}.get(kind, "медіа")
    if remote:
        return f"Мережа, {label} {ext}".rstrip()
    return f"{label.capitalize()}, {ext}" if ext else label.capitalize()


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
