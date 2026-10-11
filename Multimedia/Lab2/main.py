import os
import sys

os.environ.setdefault("QT_LOGGING_RULES", "qt.multimedia.ffmpeg*=false")

from PySide6.QtWidgets import QApplication

from media_player.ui.main_window import MainWindow
from media_player.ui.theme import apply_dark_theme


def main() -> int:
    app = QApplication(sys.argv)
    app.setApplicationName("Медіаплеєр")
    apply_dark_theme(app)

    window = MainWindow()
    window.show()
    if len(sys.argv) > 1:
        window.add_sources(sys.argv[1:], play=True)
    return app.exec()


if __name__ == "__main__":
    sys.exit(main())
