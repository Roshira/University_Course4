"""Головне вікно: Original | DCT | DWT, керування стисненням, графік і таблиця експериментів."""
import csv
import math
from pathlib import Path

import numpy as np
from PySide6.QtCore import Qt, QTimer
from PySide6.QtGui import QAction, QColor, QKeySequence
from PySide6.QtWidgets import (QComboBox, QDockWidget, QFileDialog, QHBoxLayout, QHeaderView, QLabel,
                               QMainWindow, QMessageBox, QPushButton, QSlider, QSpinBox, QTableWidget,
                               QTableWidgetItem, QVBoxLayout, QWidget)

from .. import dct, haar
from ..compress import (DEFAULT_LEVELS, MODE_TITLES, Mode, Result, compress_dct, compress_dwt,
                        transform_dct, transform_dwt)
from ..image_io import fit_size, load_gray, sample_images, save_gray
from ..metrics import format_psnr
from ..visualize import coefficient_map, difference_map
from .theme import DCT_COLOR, DWT_COLOR
from .widgets import ImagePanel, PsnrChart, ViewState

SLIDER_MAX = 1000
KEEP_MIN = 0.001          # 0.1 %

# що показувати в панелях
VIEW_IMAGE, VIEW_COEFFS, VIEW_DIFF = range(3)


def slider_to_value(mode: Mode, pos: int) -> float:
    """Позиція повзунка (0..1000) -> параметр стиснення."""
    if mode is Mode.KEEP:     # 0.1 % .. 100 %, логарифмічно
        return 10 ** (math.log10(KEEP_MIN) * (1 - pos / SLIDER_MAX))
    if mode is Mode.THRESHOLD:  # поріг 0 .. 200
        return pos / 5
    return max(1.0, pos / 5)    # крок квантування 1 .. 200


def value_to_slider(mode: Mode, value: float) -> int:
    if mode is Mode.KEEP:
        return round(SLIDER_MAX * (1 - math.log10(value) / math.log10(KEEP_MIN)))
    return round(value * 5)


def describe_value(mode: Mode, value: float) -> str:
    if mode is Mode.KEEP:
        return f"зберегти {value * 100:.2f} % коефіцієнтів"
    if mode is Mode.THRESHOLD:
        return f"обнулити |c| < {value:.1f}"
    return f"крок квантування q = {value:.1f}"


SHORT_TITLES = {Mode.KEEP: "Частка", Mode.THRESHOLD: "Поріг", Mode.QUANT: "Квантування"}


def short_value(mode: Mode, value: float) -> str:
    if mode is Mode.KEEP:
        return f"{value * 100:g} %"
    return f"T = {value:g}" if mode is Mode.THRESHOLD else f"q = {value:g}"


DEFAULT_VALUES = {Mode.KEEP: 0.05, Mode.THRESHOLD: 20.0, Mode.QUANT: 20.0}


class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("Стиснення зображень: DCT і DWT")
        self.resize(1400, 820)

        self.source: np.ndarray | None = None   # завантажене зображення
        self.image: np.ndarray | None = None    # обрізане до потрібного розміру
        self.image_name = ""
        self.dct_coeffs = self.dwt_coeffs = None
        self.results: tuple[Result, Result] | None = None
        self.values = dict(DEFAULT_VALUES)

        self.view_state = ViewState()
        self.panels = [
            ImagePanel("Original", "#e8e8ea", self.view_state),
            ImagePanel("DCT 8x8", DCT_COLOR, self.view_state),
            ImagePanel("DWT Хаара", DWT_COLOR, self.view_state),
        ]
        self._update_timer = QTimer(self, singleShot=True, interval=25, timeout=self.recompute)

        self._build_menu()
        self._build_central()
        self._build_docks()

        samples = sample_images()
        default = next((p for p in samples if p.stem == "landscape"), samples[0] if samples else None)
        if default:
            self.open_image(default)

    # ---------- побудова інтерфейсу ----------
    def _build_menu(self):
        file_menu = self.menuBar().addMenu("Файл")
        act = QAction("Відкрити зображення...", self, shortcut=QKeySequence.StandardKey.Open)
        act.triggered.connect(self.choose_image)
        file_menu.addAction(act)
        samples_menu = file_menu.addMenu("Тестові зображення")
        for path in sample_images():
            a = QAction(path.stem, self)
            a.triggered.connect(lambda _=False, p=path: self.open_image(p))
            samples_menu.addAction(a)
        act = QAction("Зберегти результати...", self, shortcut=QKeySequence.StandardKey.Save)
        act.triggered.connect(self.save_results)
        file_menu.addAction(act)
        file_menu.addSeparator()
        act = QAction("Вихід", self, shortcut=QKeySequence.StandardKey.Quit)
        act.triggered.connect(self.close)
        file_menu.addAction(act)

    def _build_central(self):
        central = QWidget()
        root = QVBoxLayout(central)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)

        panels = QHBoxLayout()
        panels.setContentsMargins(10, 10, 10, 10)
        panels.setSpacing(10)
        for p in self.panels:
            panels.addWidget(p, 1)
        root.addLayout(panels, 1)

        controls = QWidget()
        controls.setObjectName("ControlsPanel")
        rows = QVBoxLayout(controls)
        rows.setContentsMargins(14, 10, 14, 10)
        rows.setSpacing(8)
        row1, row2 = QHBoxLayout(), QHBoxLayout()
        row1.setSpacing(10)
        row2.setSpacing(10)
        rows.addLayout(row1)
        rows.addLayout(row2)

        def caption(text):
            lbl = QLabel(text)
            lbl.setObjectName("ControlCaption")
            return lbl

        self.mode_box = QComboBox()
        for mode in Mode:
            self.mode_box.addItem(MODE_TITLES[mode], mode)
        self.mode_box.currentIndexChanged.connect(self._mode_changed)

        self.slider = QSlider(Qt.Orientation.Horizontal)
        self.slider.setRange(0, SLIDER_MAX)
        self.slider.valueChanged.connect(self._slider_moved)
        self.value_label = QLabel()
        self.value_label.setObjectName("ValueLabel")

        self.levels_box = QSpinBox()
        self.levels_box.setRange(1, 7)
        self.levels_box.setValue(DEFAULT_LEVELS)
        self.levels_box.valueChanged.connect(self._levels_changed)

        self.view_box = QComboBox()
        self.view_box.addItems(["Відновлене зображення", "Коефіцієнти після стиснення", "Різниця з оригіналом ×5"])
        self.view_box.currentIndexChanged.connect(self.refresh_views)

        add_btn = QPushButton("Додати в таблицю")
        add_btn.clicked.connect(self.add_to_table)

        row1.addWidget(caption("Механізм стиснення:"))
        row1.addWidget(self.mode_box)
        row1.addSpacing(6)
        row1.addWidget(caption("Рівень:"))
        row1.addWidget(self.slider, 1)
        row1.addWidget(self.value_label)
        row2.addWidget(caption("Рівні Хаара:"))
        row2.addWidget(self.levels_box)
        row2.addSpacing(12)
        row2.addWidget(caption("Показати:"))
        row2.addWidget(self.view_box)
        row2.addStretch(1)
        row2.addWidget(add_btn)
        root.addWidget(controls)

        hint = QLabel("Колесо миші - масштаб (синхронно в усіх панелях), перетягування - зсув, подвійний клік - вписати")
        hint.setObjectName("Hint")
        self.statusBar().addPermanentWidget(hint)
        self.setCentralWidget(central)
        self._set_slider_for_mode()

    def _build_docks(self):
        self.chart = PsnrChart()
        dock = QDockWidget("PSNR від частки коефіцієнтів", self)
        dock.setObjectName("ChartDock")
        dock.setWidget(self.chart)
        dock.setFeatures(QDockWidget.DockWidgetFeature.DockWidgetMovable)
        self.addDockWidget(Qt.DockWidgetArea.RightDockWidgetArea, dock)

        box = QWidget()
        lay = QVBoxLayout(box)
        lay.setContentsMargins(6, 6, 6, 6)
        self.table = QTableWidget(0, 6)
        self.table.setHorizontalHeaderLabels(["Механізм", "Параметр", "Метод", "Коеф.", "PSNR, дБ", "Стисн."])
        self.table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.ResizeToContents)
        self.table.verticalHeader().setVisible(False)
        self.table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        buttons = QHBoxLayout()
        b_presets = QPushButton("3 рівні стиснення")
        b_presets.setToolTip("Додати в таблицю результати для 10 %, 5 % і 1 % коефіцієнтів")
        b_presets.clicked.connect(self.add_presets)
        b_csv = QPushButton("Експорт CSV")
        b_csv.clicked.connect(self.export_csv)
        b_clear = QPushButton("Очистити")
        b_clear.clicked.connect(lambda: self.table.setRowCount(0))
        for b in (b_presets, b_csv, b_clear):
            buttons.addWidget(b)
        lay.addWidget(self.table, 1)
        lay.addLayout(buttons)
        dock = QDockWidget("Експерименти", self)
        dock.setObjectName("TableDock")
        dock.setWidget(box)
        dock.setFeatures(QDockWidget.DockWidgetFeature.DockWidgetMovable)
        self.addDockWidget(Qt.DockWidgetArea.RightDockWidgetArea, dock)
        self.resizeDocks([dock], [430], Qt.Orientation.Horizontal)

    # ---------- дані ----------
    @property
    def mode(self) -> Mode:
        return self.mode_box.currentData()

    @property
    def levels(self) -> int:
        return self.levels_box.value()

    def choose_image(self):
        path, _ = QFileDialog.getOpenFileName(self, "Відкрити зображення", "",
                                              "Зображення (*.png *.jpg *.jpeg *.bmp *.tif *.tiff *.gif *.webp)")
        if path:
            self.open_image(Path(path))

    def open_image(self, path: Path):
        try:
            self.source = load_gray(path)
        except Exception as exc:  # noqa: BLE001 - показати будь-яку помилку читання
            QMessageBox.warning(self, "Помилка", f"Не вдалося відкрити {path}:\n{exc}")
            return
        self.image_name = Path(path).stem
        h, w = self.source.shape
        max_levels = max(1, min(7, int(math.log2(max(min(h, w), 16) / 8))))
        self.levels_box.blockSignals(True)
        self.levels_box.setMaximum(max_levels)
        self.levels_box.blockSignals(False)
        self.view_state.reset()
        self._prepare()

    def _prepare(self):
        """Обрізати зображення під блоки 8x8 і рівні Хаара, порахувати коефіцієнти і криві."""
        if self.source is None:
            return
        self.image = fit_size(self.source, max(dct.BLOCK, 2 ** self.levels))
        self.dct_coeffs = transform_dct(self.image)
        self.dwt_coeffs = transform_dwt(self.image, self.levels)
        h, w = self.image.shape
        crop = "" if self.image.shape == self.source.shape else f" (обрізано з {self.source.shape[1]}x{self.source.shape[0]})"
        self.statusBar().showMessage(f"{self.image_name}: {w}x{h}{crop}, {w * h} коефіцієнтів, "
                                     f"{(h // 8) * (w // 8)} блоків 8x8, Хаар {self.levels} рів.")
        fractions = np.geomspace(KEEP_MIN, 1.0, 28)
        self.chart.set_curves({
            "DCT": [(f, compress_dct(self.image, Mode.KEEP, f, coeffs=self.dct_coeffs).psnr) for f in fractions],
            "DWT": [(f, compress_dwt(self.image, Mode.KEEP, f, self.levels, coeffs=self.dwt_coeffs).psnr)
                    for f in fractions],
        })
        self.recompute()

    def compute(self, mode: Mode, value: float) -> tuple[Result, Result]:
        return (compress_dct(self.image, mode, value, coeffs=self.dct_coeffs),
                compress_dwt(self.image, mode, value, self.levels, coeffs=self.dwt_coeffs))

    def recompute(self):
        if self.image is None:
            return
        self.results = self.compute(self.mode, self.values[self.mode])
        for panel, r in zip(self.panels[1:], self.results):
            panel.psnr.setText(f"PSNR {format_psnr(r.psnr)}")
            panel.stats.setText(
                f"Коефіцієнтів: {r.kept} з {r.total} ({r.kept_fraction * 100:.2f} %), {r.ratio:.1f}:1\n"
                f"Розмір (оцінка zlib): {r.encoded_bytes / 1024:.1f} КБ, "
                f"{self.image.size / r.encoded_bytes:.1f}:1")
        h, w = self.image.shape
        self.panels[0].psnr.setText(f"{w}x{h}")
        self.panels[0].stats.setText(f"{self.image_name}, відтінки сірого\n"
                                     f"8 біт/піксель, {self.image.size / 1024:.0f} КБ")
        self.chart.set_points({r.method: (max(r.kept_fraction, KEEP_MIN), r.psnr) for r in self.results})
        self.refresh_views()

    def refresh_views(self):
        if self.results is None:
            return
        view = self.view_box.currentIndex()
        self.panels[0].view.set_image(self.image)
        r_dct, r_dwt = self.results
        if view == VIEW_COEFFS:
            self.panels[1].view.set_image(coefficient_map(r_dct.reduced))
            self.panels[2].view.set_image(coefficient_map(r_dwt.reduced),
                                          haar.subband_rects(self.image.shape, self.levels))
        elif view == VIEW_DIFF:
            self.panels[1].view.set_image(difference_map(self.image, r_dct.image))
            self.panels[2].view.set_image(difference_map(self.image, r_dwt.image))
        else:
            self.panels[1].view.set_image(r_dct.image)
            self.panels[2].view.set_image(r_dwt.image)

    # ---------- керування ----------
    def _set_slider_for_mode(self):
        self.slider.blockSignals(True)
        self.slider.setValue(value_to_slider(self.mode, self.values[self.mode]))
        self.slider.blockSignals(False)
        self.value_label.setText(describe_value(self.mode, self.values[self.mode]))

    def _mode_changed(self):
        self._set_slider_for_mode()
        self.recompute()

    def _slider_moved(self, pos: int):
        self.values[self.mode] = slider_to_value(self.mode, pos)
        self.value_label.setText(describe_value(self.mode, self.values[self.mode]))
        self._update_timer.start()

    def _levels_changed(self):
        self._prepare()

    def set_parameters(self, mode: Mode, value: float, levels: int | None = None, view: int | None = None):
        """Встановити параметри програмно (для демонстрації і знімків екрана)."""
        self.values[mode] = value
        if levels is not None and levels != self.levels:
            self.levels_box.setValue(levels)
        if view is not None:
            self.view_box.setCurrentIndex(view)
        if self.mode is mode:
            self._set_slider_for_mode()
            self.recompute()
        else:
            self.mode_box.setCurrentIndex(list(Mode).index(mode))

    # ---------- таблиця і збереження ----------
    def _add_rows(self, mode: Mode, value: float, results):
        for r in results:
            row = self.table.rowCount()
            self.table.insertRow(row)
            cells = [SHORT_TITLES[mode], short_value(mode, value), r.method, f"{r.kept_fraction * 100:.2f} %",
                     format_psnr(r.psnr).replace(" дБ", ""), f"{r.ratio:.1f}:1"]
            for col, text in enumerate(cells):
                item = QTableWidgetItem(text)
                if col == 2:
                    item.setForeground(QColor(DCT_COLOR if r.method == "DCT" else DWT_COLOR))
                self.table.setItem(row, col, item)
        self.table.scrollToBottom()

    def add_to_table(self):
        if self.results:
            self._add_rows(self.mode, self.values[self.mode], self.results)

    def add_presets(self):
        if self.image is None:
            return
        for f in (0.10, 0.05, 0.01):
            self._add_rows(Mode.KEEP, f, self.compute(Mode.KEEP, f))

    def export_csv(self):
        if self.table.rowCount() == 0:
            return
        path, _ = QFileDialog.getSaveFileName(self, "Експорт CSV", "experiments.csv", "CSV (*.csv)")
        if not path:
            return
        with open(path, "w", newline="", encoding="utf-8-sig") as f:
            writer = csv.writer(f, delimiter=";")
            writer.writerow([self.table.horizontalHeaderItem(c).text() for c in range(self.table.columnCount())])
            for row in range(self.table.rowCount()):
                writer.writerow([self.table.item(row, c).text() for c in range(self.table.columnCount())])

    def save_results(self):
        if not self.results:
            return
        folder = QFileDialog.getExistingDirectory(self, "Папка для результатів")
        if not folder:
            return
        tag = f"{self.image_name}_{self.mode.value}_{self.values[self.mode]:g}"
        save_gray(self.image, Path(folder) / f"{self.image_name}_original.png")
        for r in self.results:
            save_gray(r.image, Path(folder) / f"{tag}_{r.method}.png")
        self.grab().save(str(Path(folder) / f"{tag}_screen.png"))
        self.statusBar().showMessage(f"Збережено в {folder}", 5000)
