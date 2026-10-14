from __future__ import annotations

from functools import lru_cache

from PySide6.QtCore import QByteArray, QRectF, Qt
from PySide6.QtGui import QIcon, QPainter, QPixmap
from PySide6.QtSvg import QSvgRenderer

TEXT = "#e8e8ea"
DISABLED = "#5c5f66"
ACCENT = "#4f9cf9"
ON_ACCENT = "#ffffff"

_FILL = 'fill="{c}" stroke="none"'
_STROKE = 'fill="none" stroke="{c}" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"'

SHAPES = {
    "play": f'<path {_FILL} d="M8 5.5v13a1 1 0 0 0 1.5.86l10.4-6.5a1 1 0 0 0 0-1.72L9.5 4.64A1 1 0 0 0 8 5.5z"/>',
    "pause": f'<rect {_FILL} x="6" y="5" width="4" height="14" rx="1.2"/><rect {_FILL} x="14" y="5" width="4" height="14" rx="1.2"/>',
    "stop": f'<rect {_FILL} x="6" y="6" width="12" height="12" rx="2"/>',
    "prev": f'<rect {_FILL} x="5" y="5" width="2.4" height="14" rx="1"/><path {_FILL} d="M19 6.3v11.4a1 1 0 0 1-1.55.83L9.3 13.1a1.3 1.3 0 0 1 0-2.2l8.15-5.43A1 1 0 0 1 19 6.3z"/>',
    "next": f'<rect {_FILL} x="16.6" y="5" width="2.4" height="14" rx="1"/><path {_FILL} d="M5 6.3v11.4a1 1 0 0 0 1.55.83l8.15-5.43a1.3 1.3 0 0 0 0-2.2L6.55 5.47A1 1 0 0 0 5 6.3z"/>',
    "back": f'<path {_STROKE} d="M4 12a8 8 0 1 0 2.35-5.65"/><path {_STROKE} d="M4 4v4.5h4.5"/><text x="12" y="15.3" font-size="7.5" font-family="Segoe UI, Arial" font-weight="700" text-anchor="middle" fill="{{c}}">10</text>',
    "forward": f'<path {_STROKE} d="M20 12a8 8 0 1 1-2.35-5.65"/><path {_STROKE} d="M20 4v4.5h-4.5"/><text x="12" y="15.3" font-size="7.5" font-family="Segoe UI, Arial" font-weight="700" text-anchor="middle" fill="{{c}}">10</text>',
    "folder": f'<path {_STROKE} d="M3.5 7.5a2 2 0 0 1 2-2h3.6l2 2.2h7.4a2 2 0 0 1 2 2v7.8a2 2 0 0 1-2 2h-13a2 2 0 0 1-2-2z"/>',
    "link": f'<circle {_STROKE} cx="12" cy="12" r="8.5"/><path {_STROKE} d="M3.5 12h17"/><path {_STROKE} d="M12 3.5c2.6 2.4 3.8 5.2 3.8 8.5s-1.2 6.1-3.8 8.5c-2.6-2.4-3.8-5.2-3.8-8.5s1.2-6.1 3.8-8.5z"/>',
    "volume": f'<path {_FILL} d="M4 9.2h3.3L12 5.3v13.4l-4.7-3.9H4z"/><path {_STROKE} d="M15.5 9a4 4 0 0 1 0 6"/><path {_STROKE} d="M18 6.3a7.6 7.6 0 0 1 0 11.4"/>',
    "volume_low": f'<path {_FILL} d="M4 9.2h3.3L12 5.3v13.4l-4.7-3.9H4z"/><path {_STROKE} d="M15.5 9a4 4 0 0 1 0 6"/>',
    "mute": f'<path {_FILL} d="M4 9.2h3.3L12 5.3v13.4l-4.7-3.9H4z"/><path {_STROKE} d="M15.5 9.5l5 5M20.5 9.5l-5 5"/>',
    "fullscreen": f'<path {_STROKE} d="M4 9V5a1 1 0 0 1 1-1h4M15 4h4a1 1 0 0 1 1 1v4M20 15v4a1 1 0 0 1-1 1h-4M9 20H5a1 1 0 0 1-1-1v-4"/>',
    "repeat": f'<path {_STROKE} d="M4.5 11V9.5a3 3 0 0 1 3-3H19"/><path {_STROKE} d="M16 3.5l3 3-3 3"/><path {_STROKE} d="M19.5 13v1.5a3 3 0 0 1-3 3H5"/><path {_STROKE} d="M8 20.5l-3-3 3-3"/>',
    "shuffle": f'<path {_STROKE} d="M4 7h2.5c4.5 0 6.5 10 11 10H20"/><path {_STROKE} d="M4 17h2.5c4.5 0 6.5-10 11-10H20"/><path {_STROKE} d="M17.5 4.5L20 7l-2.5 2.5M17.5 14.5L20 17l-2.5 2.5"/>',
    "remove": f'<path {_STROKE} d="M6 12h12"/><circle {_STROKE} cx="12" cy="12" r="8.5"/>',
    "trash": f'<path {_STROKE} d="M5 7h14M10 7V5h4v2M7 7l.9 12a1 1 0 0 0 1 .9h6.2a1 1 0 0 0 1-.9L17 7"/>',
    "save": f'<path {_STROKE} d="M5 5a1 1 0 0 1 1-1h10.5L20 7.5V19a1 1 0 0 1-1 1H6a1 1 0 0 1-1-1z"/><path {_STROKE} d="M8.5 4v4.5h6V4M8 20v-5.5h8V20"/>',
    "note": f'<path {_FILL} d="M10 17.5a3 3 0 1 1-2-2.83V5.6a1 1 0 0 1 .78-.98l9-2a1 1 0 0 1 1.22.98v11.9a3 3 0 1 1-2-2.83V7.4l-7 1.56z"/>',
    "video": f'<rect {_STROKE} x="3" y="6" width="13" height="12" rx="2"/><path {_STROKE} d="M16 10.5l5-3v9l-5-3"/>',
}


def svg(name: str, color: str) -> bytes:
    body = SHAPES[name].format(c=color)
    return f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24">{body}</svg>'.encode()


@lru_cache(maxsize=None)
def pixmap(name: str, color: str = TEXT, size: int = 48) -> QPixmap:
    renderer = QSvgRenderer(QByteArray(svg(name, color)))
    pm = QPixmap(size, size)
    pm.fill(Qt.GlobalColor.transparent)
    painter = QPainter(pm)
    painter.setRenderHint(QPainter.RenderHint.Antialiasing)
    renderer.render(painter, QRectF(0, 0, size, size))
    painter.end()
    return pm


def icon(name: str, color: str = TEXT, checked_color: str | None = ACCENT) -> QIcon:
    result = QIcon()
    result.addPixmap(pixmap(name, color), QIcon.Mode.Normal, QIcon.State.Off)
    result.addPixmap(pixmap(name, DISABLED), QIcon.Mode.Disabled, QIcon.State.Off)
    if checked_color:
        result.addPixmap(pixmap(name, checked_color), QIcon.Mode.Normal, QIcon.State.On)
    return result
