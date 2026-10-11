from __future__ import annotations

from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QImage, QMouseEvent, QPixmap
from PySide6.QtMultimediaWidgets import QVideoWidget
from PySide6.QtWidgets import QLabel, QSlider, QStyle, QStyleOptionSlider, QVBoxLayout, QWidget

from ..utils import format_time


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


class InfoView(QWidget):
    doubleClicked = Signal()

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setObjectName("InfoView")
        self._cover_source: QImage | None = None

        self._cover = QLabel(alignment=Qt.AlignmentFlag.AlignCenter)
        self._cover.setObjectName("Cover")
        self._title = QLabel(alignment=Qt.AlignmentFlag.AlignCenter)
        self._title.setObjectName("InfoTitle")
        self._title.setWordWrap(True)
        self._subtitle = QLabel(alignment=Qt.AlignmentFlag.AlignCenter)
        self._subtitle.setObjectName("InfoSubtitle")
        self._subtitle.setWordWrap(True)

        layout = QVBoxLayout(self)
        layout.addStretch(1)
        layout.addWidget(self._cover)
        layout.addSpacing(12)
        layout.addWidget(self._title)
        layout.addWidget(self._subtitle)
        layout.addStretch(1)

        self.show_idle()

    def show_idle(self) -> None:
        self._set_cover(None, "▶")
        self._title.setText("Відкрийте медіафайл або URL")
        self._subtitle.setText(
            "Ctrl+O - файл,  Ctrl+U - посилання,  або перетягніть файли у вікно"
        )

    def show_audio(self, title: str, subtitle: str, cover: QImage | None) -> None:
        self._set_cover(cover, "♪")
        self._title.setText(title)
        self._subtitle.setText(subtitle)

    def show_loading(self, title: str) -> None:
        self._set_cover(None, "...")
        self._title.setText(title)
        self._subtitle.setText("Завантаження...")

    def _set_cover(self, image: QImage | None, placeholder: str) -> None:
        self._cover_source = image
        if image is None:
            self._cover.setPixmap(QPixmap())
            self._cover.setText(placeholder)
            self._cover.setProperty("placeholder", True)
        else:
            self._cover.setProperty("placeholder", False)
            self._rescale_cover()
        self._cover.style().unpolish(self._cover)
        self._cover.style().polish(self._cover)

    def _rescale_cover(self) -> None:
        if self._cover_source is None:
            return
        side = max(64, min(self.width(), self.height()) // 2)
        pixmap = QPixmap.fromImage(self._cover_source).scaled(
            side, side, Qt.AspectRatioMode.KeepAspectRatio,
            Qt.TransformationMode.SmoothTransformation,
        )
        self._cover.setPixmap(pixmap)

    def resizeEvent(self, event) -> None:
        super().resizeEvent(event)
        self._rescale_cover()

    def mouseDoubleClickEvent(self, event: QMouseEvent) -> None:
        self.doubleClicked.emit()
        event.accept()
