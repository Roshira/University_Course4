import sys

from PySide6.QtWidgets import QApplication

from imgcomp.ui.main_window import MainWindow
from imgcomp.ui.theme import apply_dark_theme


def main() -> int:
    app = QApplication(sys.argv)
    app.setApplicationName("Стиснення зображень DCT/DWT")
    apply_dark_theme(app)
    window = MainWindow()
    if len(sys.argv) > 1:
        window.open_image(sys.argv[1])
    window.show()
    return app.exec()


if __name__ == "__main__":
    sys.exit(main())
