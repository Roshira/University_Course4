"""Зображення для відображення (без Qt): карти коефіцієнтів і різниця."""
import numpy as np


def coefficient_map(coeffs: np.ndarray) -> np.ndarray:
    """Модулі коефіцієнтів у логарифмічному масштабі -> 0..255 (нулі - чорні)."""
    mag = np.log1p(np.abs(coeffs))
    top = mag.max()
    return np.zeros(coeffs.shape, np.uint8) if top == 0 else np.round(255 * mag / top).astype(np.uint8)


def difference_map(original: np.ndarray, restored: np.ndarray, gain: float = 5.0) -> np.ndarray:
    """|оригінал - відновлене| * gain, обрізане до 0..255."""
    d = np.abs(original.astype(np.int16) - restored.astype(np.int16)) * gain
    return np.clip(d, 0, 255).astype(np.uint8)
