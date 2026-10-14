from PySide6.QtGui import QColor, QPalette
from PySide6.QtWidgets import QApplication

ACCENT = "#4f9cf9"

STYLESHEET = f"""
QMainWindow, QDockWidget {{ background: #17181b; }}
QMainWindow::separator {{ background: #17181b; width: 1px; }}
QMenuBar {{ background: #17181b; padding: 2px 6px; }}
QMenuBar::item {{ padding: 5px 10px; border-radius: 6px; }}
QMenuBar::item:selected {{ background: #2a2c31; }}
QMenu {{ background: #222428; border: 1px solid #33353b; border-radius: 8px; padding: 6px; }}
QMenu::item {{ padding: 6px 28px 6px 12px; border-radius: 6px; }}
QMenu::item:selected {{ background: #2d4a70; }}
QMenu::separator {{ height: 1px; background: #33353b; margin: 5px 8px; }}
QToolTip {{ background: #2a2c31; color: #e8e8ea; border: 1px solid #3a3d44; border-radius: 6px; padding: 4px 8px; }}

QDockWidget {{ titlebar-close-icon: none; }}
QDockWidget::title {{ background: #1c1d21; padding: 10px 12px; font-weight: 600; }}
#PlaylistCount {{ color: #7b7e87; padding: 2px 6px 6px 6px; }}

#ControlsPanel {{ background: #1f2024; border-top: 1px solid #2c2e33; }}
#NowPlaying {{ font-size: 16px; font-weight: 600; color: #f2f2f4; }}
#NowMeta {{ font-size: 12px; color: #8d9099; }}
#TimeLabel {{ color: #a9abb3; font-family: Consolas, monospace; font-size: 12px; }}

#InfoView {{
    background: qradialgradient(cx:0.5, cy:0.42, radius:0.75, fx:0.5, fy:0.42,
                                stop:0 #23263a, stop:1 #121316);
}}
#InfoTitle {{ font-size: 22px; font-weight: 600; color: #f2f2f4; }}
#InfoSubtitle {{ font-size: 13px; color: #8d9099; }}

QToolButton {{ border: none; border-radius: 8px; padding: 6px; color: #e8e8ea; }}
QToolButton:hover {{ background: #2c2e34; }}
QToolButton:pressed {{ background: #34373e; }}
QToolButton:checked, QToolButton[active="true"] {{ background: #22324a; }}
#PlayButton {{ background: {ACCENT}; border-radius: 26px; padding: 0; }}
#PlayButton:hover {{ background: #6aacfa; }}
#PlayButton:pressed {{ background: #3f86e0; }}
#PlayButton:disabled {{ background: #2f3d52; }}

QComboBox {{
    background: #2a2c31; border: 1px solid #36383e; border-radius: 8px;
    padding: 5px 10px; min-width: 52px; color: #e8e8ea;
}}
QComboBox:hover {{ border-color: #4a4d55; }}
QComboBox::drop-down {{ border: none; width: 18px; }}
QComboBox QAbstractItemView {{
    background: #222428; border: 1px solid #33353b; selection-background-color: #2d4a70; outline: none;
}}

QSlider {{ min-height: 20px; }}
QSlider::groove:horizontal {{ height: 4px; background: #34363c; border-radius: 2px; }}
QSlider::groove:horizontal:hover {{ height: 6px; border-radius: 3px; }}
QSlider::sub-page:horizontal {{
    background: qlineargradient(x1:0, y1:0, x2:1, y2:0, stop:0 {ACCENT}, stop:1 #8e5cf7);
    border-radius: 2px;
}}
QSlider::sub-page:horizontal:disabled {{ background: #34363c; }}
QSlider::handle:horizontal {{
    width: 12px; height: 12px; margin: -4px 0; border-radius: 6px; background: #ffffff;
}}
QSlider::handle:horizontal:hover {{ width: 16px; height: 16px; margin: -6px 0; border-radius: 8px; }}
QSlider::handle:horizontal:disabled {{ background: #4a4d55; }}
#VolumeSlider::sub-page:horizontal {{ background: #c9cbd1; }}

QListWidget {{ background: transparent; border: none; outline: none; }}
QScrollBar:vertical {{ background: transparent; width: 8px; margin: 2px; }}
QScrollBar::handle:vertical {{ background: #3a3d44; border-radius: 3px; min-height: 30px; }}
QScrollBar::handle:vertical:hover {{ background: #4a4d55; }}
QScrollBar::add-line, QScrollBar::sub-line {{ height: 0; }}
QScrollBar::add-page, QScrollBar::sub-page {{ background: none; }}

QStatusBar {{ background: #17181b; color: #8d9099; }}
QStatusBar::item {{ border: none; }}
QInputDialog QLineEdit, QComboBox QLineEdit {{ background: transparent; }}
QPushButton {{
    background: #2a2c31; border: 1px solid #36383e; border-radius: 8px; padding: 6px 16px; color: #e8e8ea;
}}
QPushButton:hover {{ background: #32353b; }}
QPushButton:default {{ background: {ACCENT}; border-color: {ACCENT}; color: #ffffff; }}
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
    for role in (QPalette.ColorRole.Text, QPalette.ColorRole.ButtonText, QPalette.ColorRole.WindowText):
        palette.setColor(QPalette.ColorGroup.Disabled, role, QColor("#5c5f66"))
    app.setPalette(palette)
    app.setStyleSheet(STYLESHEET)
