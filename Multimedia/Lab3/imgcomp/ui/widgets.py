"""Віджети: перегляд зображення з синхронним масштабуванням і графік PSNR."""
import math

import numpy as np
from PySide6.QtCore import QObject, QPointF, QRectF, Qt, Signal
from PySide6.QtGui import QColor, QFont, QImage, QPainter, QPainterPath, QPen, QPixmap
from PySide6.QtWidgets import QFrame, QLabel, QVBoxLayout, QWidget

from .theme import DCT_COLOR, DWT_COLOR


def to_pixmap(img: np.ndarray) -> QPixmap:
    img = np.ascontiguousarray(img, dtype=np.uint8)
    h, w = img.shape
    qimg = QImage(img.data, w, h, w, QImage.Format.Format_Grayscale8)
    return QPixmap.fromImage(qimg.copy())


class ViewState(QObject):
    """Спільний масштаб і зсув для всіх трьох панелей (щоб порівнювати одну й ту саму ділянку).
    zoom = 0 означає «вписати у вікно»."""
    changed = Signal()

    def __init__(self):
        super().__init__()
        self.zoom = 0.0
        self.center = QPointF(0.5, 0.5)   # центр видимої ділянки у частках розміру зображення

    def set(self, zoom: float, center: QPointF) -> None:
        self.zoom = zoom
        self.center = QPointF(min(max(center.x(), 0.0), 1.0), min(max(center.y(), 0.0), 1.0))
        self.changed.emit()

    def reset(self) -> None:
        self.set(0.0, QPointF(0.5, 0.5))


class ImageView(QWidget):
    """Малює зображення з урахуванням ViewState. Колесо - масштаб, перетягування - зсув,
    подвійний клік - вписати у вікно."""

    def __init__(self, state: ViewState, parent=None):
        super().__init__(parent)
        self.state = state
        self.pixmap: QPixmap | None = None
        self.overlay: list[tuple[str, int, int, int, int]] = []   # підписи підсмуг DWT
        self._drag_pos = None
        self.setMinimumSize(200, 200)
        self.setCursor(Qt.CursorShape.OpenHandCursor)
        state.changed.connect(self.update)

    def set_image(self, img: np.ndarray, overlay=None) -> None:
        self.pixmap = to_pixmap(img)
        self.overlay = overlay or []
        self.update()

    def _scale(self) -> float:
        if not self.pixmap:
            return 1.0
        fit = min(self.width() / self.pixmap.width(), self.height() / self.pixmap.height())
        return fit if self.state.zoom == 0 else self.state.zoom

    def _target(self) -> QRectF:
        s = self._scale()
        w, h = self.pixmap.width() * s, self.pixmap.height() * s
        if self.state.zoom == 0:
            return QRectF((self.width() - w) / 2, (self.height() - h) / 2, w, h)
        cx, cy = self.state.center.x() * w, self.state.center.y() * h
        return QRectF(self.width() / 2 - cx, self.height() / 2 - cy, w, h)

    def paintEvent(self, _):
        p = QPainter(self)
        p.fillRect(self.rect(), QColor("#111214"))
        if not self.pixmap:
            return
        target = self._target()
        # при збільшенні - без згладжування, щоб було видно окремі пікселі й блоки 8x8
        p.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform, self._scale() < 1)
        p.drawPixmap(target, self.pixmap, QRectF(self.pixmap.rect()))
        if self.overlay:
            s = target.width() / self.pixmap.width()
            p.setPen(QPen(QColor(245, 165, 36, 170), 1))
            font = QFont(self.font())
            font.setPointSize(8)
            p.setFont(font)
            for name, y, x, h, w in self.overlay:
                r = QRectF(target.x() + x * s, target.y() + y * s, w * s, h * s)
                p.drawRect(r)
                if r.width() > 26 and r.height() > 14:
                    p.drawText(r.adjusted(3, 2, 0, 0), name)
        zoom_text = "вписано" if self.state.zoom == 0 else f"{self._scale() * 100:.0f}%"
        tw = self.fontMetrics().horizontalAdvance(zoom_text) + 12
        badge = QRectF(self.width() - tw - 6, self.height() - 24, tw, 18)
        p.fillRect(badge, QColor(17, 18, 20, 200))
        p.setPen(QColor("#a9abb3"))
        p.drawText(badge, Qt.AlignmentFlag.AlignCenter, zoom_text)

    def wheelEvent(self, event):
        if not self.pixmap:
            return
        old = self._scale()
        new = min(max(old * (1.25 if event.angleDelta().y() > 0 else 0.8), 0.1), 32.0)
        target = self._target()
        # точка під курсором залишається на місці
        pos = event.position()
        fx = (pos.x() - target.x()) / target.width()
        fy = (pos.y() - target.y()) / target.height()
        w, h = self.pixmap.width() * new, self.pixmap.height() * new
        cx = (fx * w - pos.x() + self.width() / 2) / w
        cy = (fy * h - pos.y() + self.height() / 2) / h
        self.state.set(new, QPointF(cx, cy))

    def mousePressEvent(self, event):
        self._drag_pos = event.position()
        self.setCursor(Qt.CursorShape.ClosedHandCursor)

    def mouseMoveEvent(self, event):
        if self._drag_pos is None or not self.pixmap:
            return
        if self.state.zoom == 0:
            self.state.zoom = self._scale()
        d = event.position() - self._drag_pos
        self._drag_pos = event.position()
        t = self._target()
        c = self.state.center
        self.state.set(self.state.zoom, QPointF(c.x() - d.x() / t.width(), c.y() - d.y() / t.height()))

    def mouseReleaseEvent(self, _):
        self._drag_pos = None
        self.setCursor(Qt.CursorShape.OpenHandCursor)

    def mouseDoubleClickEvent(self, _):
        self.state.reset()


class ImagePanel(QFrame):
    """Заголовок + зображення + PSNR і статистика."""

    def __init__(self, title: str, color: str, state: ViewState, parent=None):
        super().__init__(parent)
        self.setObjectName("Panel")
        self.title = QLabel(title)
        self.title.setObjectName("PanelTitle")
        self.title.setStyleSheet(f"color: {color};")
        self.view = ImageView(state)
        self.psnr = QLabel("")
        self.psnr.setObjectName("PanelPsnr")
        self.psnr.setStyleSheet(f"color: {color};")
        self.stats = QLabel("")
        self.stats.setObjectName("PanelStats")
        self.stats.setFixedHeight(self.stats.fontMetrics().lineSpacing() * 2 + 6)
        lay = QVBoxLayout(self)
        lay.setContentsMargins(10, 8, 10, 10)
        lay.setSpacing(6)
        lay.addWidget(self.title)
        lay.addWidget(self.view, 1)
        lay.addWidget(self.psnr)
        lay.addWidget(self.stats)


class PsnrChart(QWidget):
    """Графік PSNR від частки збережених коефіцієнтів (вісь X - логарифмічна).
    Лінії - режим «частка найбільших коефіцієнтів», точки - поточний результат."""

    X_MIN, X_MAX = 0.001, 1.0
    Y_MIN, Y_MAX = 10.0, 80.0

    def __init__(self, parent=None):
        super().__init__(parent)
        self.curves: dict[str, list[tuple[float, float]]] = {}
        self.points: dict[str, tuple[float, float]] = {}
        self.setMinimumSize(280, 220)

    def set_curves(self, curves) -> None:
        self.curves = curves
        self.update()

    def set_points(self, points) -> None:
        self.points = points
        self.update()

    def _plot_rect(self) -> QRectF:
        return QRectF(44, 14, self.width() - 58, self.height() - 52)

    def _map(self, r: QRectF, x: float, y: float) -> QPointF:
        lx = (math.log10(max(x, self.X_MIN)) - math.log10(self.X_MIN)) / (math.log10(self.X_MAX) - math.log10(self.X_MIN))
        y = min(max(y, self.Y_MIN), self.Y_MAX)
        ly = (y - self.Y_MIN) / (self.Y_MAX - self.Y_MIN)
        return QPointF(r.left() + lx * r.width(), r.bottom() - ly * r.height())

    def paintEvent(self, _):
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        r = self._plot_rect()
        font = QFont(self.font())
        font.setPointSize(8)
        p.setFont(font)
        grid, text = QColor("#2c2e33"), QColor("#8d9099")
        for y in range(int(self.Y_MIN), int(self.Y_MAX) + 1, 10):
            pt = self._map(r, self.X_MIN, y)
            p.setPen(grid)
            p.drawLine(QPointF(r.left(), pt.y()), QPointF(r.right(), pt.y()))
            p.setPen(text)
            p.drawText(QRectF(0, pt.y() - 8, r.left() - 6, 16), Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter, str(y))
        for x, label in ((0.001, "0.1%"), (0.01, "1%"), (0.1, "10%"), (1.0, "100%")):
            pt = self._map(r, x, self.Y_MIN)
            p.setPen(grid)
            p.drawLine(QPointF(pt.x(), r.top()), QPointF(pt.x(), r.bottom()))
            p.setPen(text)
            p.drawText(QRectF(pt.x() - 30, r.bottom() + 4, 60, 14), Qt.AlignmentFlag.AlignCenter, label)
        p.drawText(QRectF(r.left(), r.bottom() + 18, r.width(), 14), Qt.AlignmentFlag.AlignCenter,
                   "збережено коефіцієнтів (лог. шкала)")
        p.save()
        p.translate(10, r.center().y())
        p.rotate(-90)
        p.drawText(QRectF(-60, -8, 120, 14), Qt.AlignmentFlag.AlignCenter, "PSNR, дБ")
        p.restore()

        colors = {"DCT": QColor(DCT_COLOR), "DWT": QColor(DWT_COLOR)}
        p.setClipRect(r.adjusted(-6, -6, 6, 6))
        for name, pts in self.curves.items():
            path = QPainterPath()
            for i, (x, y) in enumerate(pts):
                q = self._map(r, x, y)
                path.moveTo(q) if i == 0 else path.lineTo(q)
            p.setPen(QPen(colors[name], 2))
            p.drawPath(path)
        for name, (x, y) in self.points.items():
            if math.isinf(y):
                y = self.Y_MAX
            q = self._map(r, x, y)
            p.setPen(QPen(QColor("#ffffff"), 2))
            p.setBrush(colors[name])
            p.drawEllipse(q, 5, 5)
        p.setClipping(False)
        # легенда
        p.setPen(text)
        x0 = r.left() + 8
        for i, name in enumerate(("DCT", "DWT")):
            y0 = r.top() + 8 + i * 16
            p.setPen(QPen(colors[name], 3))
            p.drawLine(QPointF(x0, y0 + 6), QPointF(x0 + 16, y0 + 6))
            p.setPen(QColor("#e8e8ea"))
            p.drawText(QPointF(x0 + 22, y0 + 10), name)
