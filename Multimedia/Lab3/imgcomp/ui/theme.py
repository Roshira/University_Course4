from PySide6.QtGui import QColor, QPalette
from PySide6.QtWidgets import QApplication

ACCENT = "#4f9cf9"
DCT_COLOR = "#4f9cf9"
DWT_COLOR = "#f5a524"

STYLESHEET = f"""
QMainWindow, QDockWidget {{ background: #17181b; }}
QMainWindow::separator {{ background: #17181b; width: 1px; height: 1px; }}
QMenuBar {{ background: #17181b; padding: 2px 6px; }}
QMenuBar::item {{ padding: 5px 10px; border-radius: 6px; }}
QMenuBar::item:selected {{ background: #2a2c31; }}
QMenu {{ background: #222428; border: 1px solid #33353b; border-radius: 8px; padding: 6px; }}
QMenu::item {{ padding: 6px 28px 6px 12px; border-radius: 6px; }}
QMenu::item:selected {{ background: #2d4a70; }}
QMenu::separator {{ height: 1px; background: #33353b; margin: 5px 8px; }}
QToolTip {{ background: #2a2c31; color: #e8e8ea; border: 1px solid #3a3d44; border-radius: 6px; padding: 4px 8px; }}
QDockWidget::title {{ background: #1c1d21; padding: 10px 12px; font-weight: 600; }}

#Panel {{ background: #1f2024; border: 1px solid #2c2e33; border-radius: 10px; }}
#PanelTitle {{ font-size: 15px; font-weight: 600; color: #f2f2f4; }}
#PanelPsnr {{ font-size: 20px; font-weight: 600; }}
#PanelStats {{ color: #a9abb3; font-size: 12px; }}
#ControlsPanel {{ background: #1f2024; border-top: 1px solid #2c2e33; }}
#ControlCaption {{ color: #8d9099; font-size: 12px; }}
#ValueLabel {{ color: #f2f2f4; font-weight: 600; min-width: 190px; }}
#Hint {{ color: #7b7e87; font-size: 11px; }}

QComboBox, QSpinBox {{
    background: #2a2c31; border: 1px solid #36383e; border-radius: 8px;
    padding: 5px 10px; color: #e8e8ea;
}}
QComboBox:hover, QSpinBox:hover {{ border-color: #4a4d55; }}
QComboBox::drop-down {{ border: none; width: 18px; }}
QComboBox QAbstractItemView {{
    background: #222428; border: 1px solid #33353b; selection-background-color: #2d4a70; outline: none;
}}
QSlider {{ min-height: 22px; }}
QSlider::groove:horizontal {{ height: 4px; background: #34363c; border-radius: 2px; }}
QSlider::sub-page:horizontal {{
    background: qlineargradient(x1:0, y1:0, x2:1, y2:0, stop:0 {ACCENT}, stop:1 #8e5cf7);
    border-radius: 2px;
}}
QSlider::handle:horizontal {{ width: 14px; height: 14px; margin: -5px 0; border-radius: 7px; background: #ffffff; }}
QPushButton {{
    background: #2a2c31; border: 1px solid #36383e; border-radius: 8px; padding: 6px 14px; color: #e8e8ea;
}}
QPushButton:hover {{ background: #32353b; }}
QPushButton:checked {{ background: #2d4a70; border-color: {ACCENT}; }}
QTableWidget {{ background: #1d1e22; border: none; gridline-color: #2c2e33; }}
QHeaderView::section {{ background: #24262b; color: #a9abb3; border: none; padding: 5px; }}
QScrollBar:vertical, QScrollBar:horizontal {{ background: transparent; width: 8px; height: 8px; margin: 2px; }}
QScrollBar::handle {{ background: #3a3d44; border-radius: 3px; min-height: 30px; min-width: 30px; }}
QScrollBar::add-line, QScrollBar::sub-line {{ height: 0; width: 0; }}
QStatusBar {{ background: #17181b; color: #8d9099; }}
"""


def apply_dark_theme(app: QApplication) -> None:
    app.setStyle("Fusion")
    palette = QPalette()
    colors = {
        QPalette.ColorRole.Window: "#17181b",
        QPalette.ColorRole.WindowText: "#e8e8ea",
        QPalette.ColorRole.Base: "#1d1e22",
        QPalette.ColorRole.AlternateBase: "#24262b",
        QPalette.ColorRole.ToolTipBase: "#2a2c31",
        QPalette.ColorRole.ToolTipText: "#e8e8ea",
        QPalette.ColorRole.Text: "#e8e8ea",
        QPalette.ColorRole.Button: "#2a2c31",
        QPalette.ColorRole.ButtonText: "#e8e8ea",
        QPalette.ColorRole.Highlight: ACCENT,
        QPalette.ColorRole.HighlightedText: "#ffffff",
        QPalette.ColorRole.PlaceholderText: "#7b7e87",
    }
    for role, color in colors.items():
        palette.setColor(role, QColor(color))
    app.setPalette(palette)
    app.setStyleSheet(STYLESHEET)
