"""Перевірка відображення повзунка на параметри (без запуску вікна)."""
import unittest

try:
    from imgcomp.ui.main_window import SLIDER_MAX, slider_to_value, value_to_slider
    from imgcomp.compress import Mode
except ImportError:  # PySide6 не встановлено
    Mode = None


@unittest.skipIf(Mode is None, "потрібен PySide6")
class SliderMappingTest(unittest.TestCase):
    def test_keep_range(self):
        self.assertAlmostEqual(slider_to_value(Mode.KEEP, 0), 0.001)
        self.assertAlmostEqual(slider_to_value(Mode.KEEP, SLIDER_MAX), 1.0)

    def test_roundtrip(self):
        for mode, value in ((Mode.KEEP, 0.05), (Mode.THRESHOLD, 20.0), (Mode.QUANT, 30.0)):
            self.assertAlmostEqual(slider_to_value(mode, value_to_slider(mode, value)), value, delta=value * 0.01)

    def test_quant_step_at_least_one(self):
        self.assertEqual(slider_to_value(Mode.QUANT, 0), 1.0)


if __name__ == "__main__":
    unittest.main()
