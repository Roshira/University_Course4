from __future__ import annotations

import numpy as np
from PySide6.QtCore import QModelIndex, QPointF, QRect, QRectF, QSize, Qt, QTimer, Signal
from PySide6.QtGui import (
    QBrush,
    QColor,
    QFont,
    QImage,
    QLinearGradient,
    QMouseEvent,
    QPainter,
    QPainterPath,
    QPen,
    QPixmap,
)
from PySide6.QtMultimediaWidgets import QVideoWidget
from PySide6.QtWidgets import (
    QLabel,
    QSlider,
    QStyle,
    QStyledItemDelegate,
    QStyleOptionSlider,
    QStyleOptionViewItem,
    QVBoxLayout,
    QWidget,
)

from ..spectrum import FFT_SIZE, band_levels
from ..utils import format_time
from . import icons

ROLE_INFO = Qt.ItemDataRole.UserRole + 1
ROLE_CURRENT = Qt.ItemDataRole.UserRole + 2


class SeekSlider(QSlider):
    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(Qt.Orientation.Horizontal, parent)
        self.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        self.setMouseTracking(True)

    def _value_at(self, x: float) -> int:
        opt = QStyleOptionSlider()
        self.initStyleOption(opt)
        groove = self.style().subControlRect(
            QStyle.ComplexControl.CC_Slider, opt, QStyle.SubControl.SC_SliderGroove, self
        )
        handle = self.style().subControlRect(
            QStyle.ComplexControl.CC_Slider, opt, QStyle.SubControl.SC_SliderHandle, self
        )
        span = groove.width() - handle.width()
        pos = int(x) - groove.x() - handle.width() // 2
        return QStyle.sliderValueFromPosition(self.minimum(), self.maximum(), pos, span)

    def mousePressEvent(self, event: QMouseEvent) -> None:
        if event.button() == Qt.MouseButton.LeftButton and self.isEnabled():
            self.setValue(self._value_at(event.position().x()))
            self.sliderMoved.emit(self.value())
        super().mousePressEvent(event)

    def mouseMoveEvent(self, event: QMouseEvent) -> None:
        if self.isEnabled() and self.maximum() > 0:
            self.setToolTip(format_time(self._value_at(event.position().x())))
        super().mouseMoveEvent(event)


class VideoView(QVideoWidget):
    doubleClicked = Signal()
    clicked = Signal()

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setStyleSheet("background: black;")

    def mouseDoubleClickEvent(self, event: QMouseEvent) -> None:
        self.doubleClicked.emit()
        event.accept()

    def mouseReleaseEvent(self, event: QMouseEvent) -> None:
        if event.button() == Qt.MouseButton.LeftButton:
            self.clicked.emit()
        super().mouseReleaseEvent(event)


class SpectrumView(QWidget):
    BANDS = 40
    DECAY = 0.045
    PEAK_DECAY = 0.012

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setMinimumHeight(90)
        self.setMaximumHeight(140)
        self._levels = np.zeros(self.BANDS)
        self._peaks = np.zeros(self.BANDS)
        self._history = np.zeros(0, dtype=np.float32)
        self._timer = QTimer(self)
        self._timer.setInterval(33)
        self._timer.timeout.connect(self._tick)
        self._timer.start()

    def feed(self, samples: np.ndarray, rate: int) -> None:
        self._history = np.concatenate([self._history, samples])[-FFT_SIZE:]
        new = band_levels(self._history, rate, self.BANDS)
        self._levels = np.maximum(new, self._levels)
        self._peaks = np.maximum(self._peaks, self._levels)

    def reset(self) -> None:
        self._history = np.zeros(0, dtype=np.float32)
        self._levels[:] = 0
        self._peaks[:] = 0
        self.update()

    def _tick(self) -> None:
        if not self.isVisible():
            return
        self._levels = np.maximum(self._levels - self.DECAY, 0)
        self._peaks = np.maximum(self._peaks - self.PEAK_DECAY, self._levels)
        self.update()

    def paintEvent(self, event) -> None:
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        w, h = self.width(), self.height()
        gap = 4
        bar_w = max(2.0, (w - gap * (self.BANDS - 1)) / self.BANDS)
        grad = QLinearGradient(0, h, 0, 0)
        grad.setColorAt(0.0, QColor(icons.ACCENT))
        grad.setColorAt(1.0, QColor("#b77cff"))
        for i in range(self.BANDS):
            x = i * (bar_w + gap)
            level = float(self._levels[i])
            bar_h = max(3.0, level * (h - 6))
            p.setPen(Qt.PenStyle.NoPen)
            p.setBrush(QColor(255, 255, 255, 14))
            p.drawRoundedRect(QRectF(x, 0, bar_w, h), 2, 2)
            p.setBrush(QBrush(grad))
            p.drawRoundedRect(QRectF(x, h - bar_h, bar_w, bar_h), 2, 2)
            peak_y = h - max(3.0, float(self._peaks[i]) * (h - 6)) - 4
            p.setBrush(QColor(255, 255, 255, 170))
            p.drawRoundedRect(QRectF(x, peak_y, bar_w, 2), 1, 1)
        p.end()


def make_cover(size: int, symbol: str, start: str = icons.ACCENT, end: str = "#8e5cf7") -> QPixmap:
    pm = QPixmap(size, size)
    pm.fill(Qt.GlobalColor.transparent)
    p = QPainter(pm)
    p.setRenderHint(QPainter.RenderHint.Antialiasing)
    grad = QLinearGradient(0, 0, size, size)
    grad.setColorAt(0, QColor(start))
    grad.setColorAt(1, QColor(end))
    path = QPainterPath()
    path.addRoundedRect(QRectF(0, 0, size, size), size * 0.12, size * 0.12)
    p.fillPath(path, QBrush(grad))
    inner = int(size * 0.42)
    p.drawPixmap(QRect((size - inner) // 2, (size - inner) // 2, inner, inner),
                 icons.pixmap(symbol, icons.ON_ACCENT, 128))
    p.end()
    return pm


def make_drop_target(size: int) -> QPixmap:
    pm = QPixmap(size, size)
    pm.fill(Qt.GlobalColor.transparent)
    p = QPainter(pm)
    p.setRenderHint(QPainter.RenderHint.Antialiasing)
    pen = QPen(QColor("#3b3e46"), 3, Qt.PenStyle.DashLine)
    pen.setDashPattern([4, 3])
    p.setPen(pen)
    p.setBrush(Qt.BrushStyle.NoBrush)
    p.drawRoundedRect(QRectF(3, 3, size - 6, size - 6), size * 0.14, size * 0.14)
    circle = size * 0.42
    c = QPointF(size / 2, size / 2)
    p.setPen(Qt.PenStyle.NoPen)
    p.setBrush(QColor(icons.ACCENT))
    p.drawEllipse(c, circle / 2, circle / 2)
    inner = int(circle * 0.5)
    p.drawPixmap(QRect(int(c.x() - inner / 2 + inner * 0.06), int(c.y() - inner / 2), inner, inner),
                 icons.pixmap("play", icons.ON_ACCENT, 128))
    p.end()
    return pm


class InfoView(QWidget):
    doubleClicked = Signal()
    COVER = 220

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setObjectName("InfoView")
        self.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
        self._cover_source: QImage | None = None

        self._cover = QLabel(alignment=Qt.AlignmentFlag.AlignCenter)
        self._title = QLabel(alignment=Qt.AlignmentFlag.AlignCenter)
        self._title.setObjectName("InfoTitle")
        self._title.setWordWrap(True)
        self._subtitle = QLabel(alignment=Qt.AlignmentFlag.AlignCenter)
        self._subtitle.setObjectName("InfoSubtitle")
        self._subtitle.setWordWrap(True)
        self.spectrum = SpectrumView()

        layout = QVBoxLayout(self)
        layout.setContentsMargins(48, 24, 48, 24)
        layout.addStretch(1)
        layout.addWidget(self._cover)
        layout.addSpacing(18)
        layout.addWidget(self._title)
        layout.addSpacing(4)
        layout.addWidget(self._subtitle)
        layout.addSpacing(22)
        layout.addWidget(self.spectrum)
        layout.addStretch(1)

        self.show_idle()

    def show_idle(self) -> None:
        self._cover_source = None
        self._cover.setPixmap(make_drop_target(self.COVER))
        self._title.setText("Відкрийте медіафайл або URL")
        self._subtitle.setText("Ctrl+O - файл,   Ctrl+U - посилання,   або перетягніть файли у вікно")
        self.spectrum.hide()

    def show_audio(self, title: str, subtitle: str, cover: QImage | None) -> None:
        self._cover_source = cover
        if cover is None:
            self._cover.setPixmap(make_cover(self.COVER, "note"))
        else:
            self._rescale_cover()
        self._title.setText(title)
        self._subtitle.setText(subtitle)
        self.spectrum.show()

    def show_loading(self, title: str) -> None:
        self._cover_source = None
        self._cover.setPixmap(make_cover(self.COVER, "note", "#3a3d45", "#2a2c32"))
        self._title.setText(title)
        self._subtitle.setText("Завантаження...")
        self.spectrum.reset()
        self.spectrum.hide()

    def show_error(self, message: str) -> None:
        self._cover_source = None
        self._cover.setPixmap(make_cover(self.COVER, "remove", "#d9534f", "#8e2c3a"))
        self._title.setText("Помилка відтворення")
        self._subtitle.setText(message)
        self.spectrum.hide()

    def _rescale_cover(self) -> None:
        if self._cover_source is None:
            return
        pixmap = QPixmap.fromImage(self._cover_source).scaled(
            self.COVER, self.COVER, Qt.AspectRatioMode.KeepAspectRatio,
            Qt.TransformationMode.SmoothTransformation,
        )
        self._cover.setPixmap(pixmap)

    def mouseDoubleClickEvent(self, event: QMouseEvent) -> None:
        self.doubleClicked.emit()
        event.accept()


class PlaylistDelegate(QStyledItemDelegate):
    HEIGHT = 50

    def sizeHint(self, option: QStyleOptionViewItem, index: QModelIndex) -> QSize:
        return QSize(option.rect.width(), self.HEIGHT)

    def paint(self, p: QPainter, option: QStyleOptionViewItem, index: QModelIndex) -> None:
        p.save()
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        r = option.rect.adjusted(4, 2, -4, -2)
        current = bool(index.data(ROLE_CURRENT))
        selected = bool(option.state & QStyle.StateFlag.State_Selected)
        hovered = bool(option.state & QStyle.StateFlag.State_MouseOver)

        if selected:
            bg = QColor("#2d4a70")
        elif current:
            bg = QColor("#262a33")
        elif hovered:
            bg = QColor("#24262b")
        else:
            bg = None
        if bg is not None:
            p.setPen(Qt.PenStyle.NoPen)
            p.setBrush(bg)
            p.drawRoundedRect(QRectF(r), 8, 8)
        if current:
            p.setBrush(QColor(icons.ACCENT))
            p.drawRoundedRect(QRectF(r.left(), r.top() + 10, 3, r.height() - 20), 1.5, 1.5)

        num_rect = QRect(r.left() + 10, r.top(), 26, r.height())
        if current:
            p.drawPixmap(QRect(num_rect.left() + 3, r.center().y() - 9, 18, 18),
                         icons.pixmap("play", icons.ACCENT, 36))
        else:
            p.setPen(QColor("#7b7e87"))
            p.drawText(num_rect, Qt.AlignmentFlag.AlignCenter, str(index.row() + 1))

        text_left = num_rect.right() + 8
        text_w = r.right() - text_left - 8
        title_font = QFont(option.font)
        title_font.setPointSizeF(option.font.pointSizeF() + 0.5)
        title_font.setBold(current)
        p.setFont(title_font)
        p.setPen(QColor("#ffffff" if current else "#e1e2e6"))
        title = p.fontMetrics().elidedText(index.data(), Qt.TextElideMode.ElideMiddle, text_w)
        p.drawText(QRect(text_left, r.top() + 6, text_w, 20), Qt.AlignmentFlag.AlignVCenter, title)

        info_font = QFont(option.font)
        info_font.setPointSizeF(max(7.0, option.font.pointSizeF() - 1))
        p.setFont(info_font)
        p.setPen(QColor(icons.ACCENT if current else "#7b7e87"))
        p.drawText(QRect(text_left, r.top() + 25, text_w, 18), Qt.AlignmentFlag.AlignVCenter,
                   index.data(ROLE_INFO) or "")
        p.restore()
