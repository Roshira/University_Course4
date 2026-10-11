from PySide6.QtGui import QColor, QPalette
from PySide6.QtWidgets import QApplication

ACCENT = "#4f9cf9"

STYLESHEET = f"""
QMainWindow, QDockWidget {{ background: #1e1f22; }}
#ControlsPanel {{ background: #26272b; border-top: 1px solid #34363b; }}
#NowPlaying {{ font-size: 14px; font-weight: 600; color: #e8e8ea; padding: 2px 0; }}
#TimeLabel {{ color: #a9abb3; font-family: Consolas, monospace; }}
#InfoView {{ background: #121316; }}
#Cover[placeholder="true"] {{ font-size: 96px; color: #3b3e46; }}
#InfoTitle {{ font-size: 20px; font-weight: 600; color: #e8e8ea; }}
#InfoSubtitle {{ font-size: 13px; color: #8d9099; }}
QToolButton {{ border-radius: 6px; padding: 4px; }}
QToolButton:hover {{ background: #34363b; }}
QToolButton:checked, QToolButton[active="true"] {{ background: #2d4a70; }}
QToolButton:disabled {{ opacity: 0.4; }}
#PlayButton {{ background: {ACCENT}; border-radius: 22px; padding: 6px; }}
#PlayButton:hover {{ background: #6aacfa; }}
QSlider::groove:horizontal {{ height: 6px; background: #3a3c42; border-radius: 3px; }}
QSlider::sub-page:horizontal {{ background: {ACCENT}; border-radius: 3px; }}
QSlider::sub-page:horizontal:disabled {{ background: #3a3c42; }}
QSlider::handle:horizontal {{
    width: 14px; height: 14px; margin: -4px 0; border-radius: 7px; background: #f2f2f4;
}}
QSlider::handle:horizontal:disabled {{ background: #55575e; }}
QListWidget {{ background: #1a1b1e; border: none; }}
QListWidget::item {{ padding: 5px 4px; }}
QListWidget::item:selected {{ background: #2d4a70; }}
QStatusBar {{ color: #a9abb3; }}
"""


def apply_dark_theme(app: QApplication) -> None:
    app.setStyle("Fusion")
    palette = QPalette()
    colors = {
        QPalette.ColorRole.Window: "#1e1f22",
        QPalette.ColorRole.WindowText: "#e8e8ea",
        QPalette.ColorRole.Base: "#1a1b1e",
        QPalette.ColorRole.AlternateBase: "#26272b",
        QPalette.ColorRole.ToolTipBase: "#26272b",
        QPalette.ColorRole.ToolTipText: "#e8e8ea",
        QPalette.ColorRole.Text: "#e8e8ea",
        QPalette.ColorRole.Button: "#2b2d31",
        QPalette.ColorRole.ButtonText: "#e8e8ea",
        QPalette.ColorRole.Highlight: ACCENT,
        QPalette.ColorRole.HighlightedText: "#ffffff",
        QPalette.ColorRole.PlaceholderText: "#7b7e87",
    }
    for role, color in colors.items():
        palette.setColor(role, QColor(color))
    for role in (QPalette.ColorRole.Text, QPalette.ColorRole.ButtonText, QPalette.ColorRole.WindowText):
        palette.setColor(QPalette.ColorGroup.Disabled, role, QColor("#6b6e76"))
    app.setPalette(palette)
    app.setStyleSheet(STYLESHEET)
