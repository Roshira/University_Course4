"""Метрики якості та стиснення."""
import zlib

import numpy as np


def mse(a: np.ndarray, b: np.ndarray) -> float:
    d = np.asarray(a, dtype=np.float64) - np.asarray(b, dtype=np.float64)
    return float(np.mean(d * d))


def psnr(original: np.ndarray, restored: np.ndarray, peak: float = 255.0) -> float:
    """PSNR = 10 * log10(peak^2 / MSE), дБ. Для однакових зображень - нескінченність."""
    e = mse(original, restored)
    return float("inf") if e == 0 else 10.0 * np.log10(peak * peak / e)


def coefficient_ratio(coeffs: np.ndarray) -> float:
    """Коефіцієнт стиснення за кількістю коефіцієнтів: усього / ненульових."""
    nz = int(np.count_nonzero(coeffs))
    return float("inf") if nz == 0 else coeffs.size / nz


def encoded_size(symbols: np.ndarray) -> int:
    """Оцінка реального розміру: цілі коефіцієнти записуються як int16 і стискаються zlib.
    Нулі стискаються дуже добре, тож розмір залежить і від кількості, і від
    розташування ненульових значень (а не лише від їх кількості)."""
    data = np.clip(symbols, -32768, 32767).astype("<i2").tobytes()
    return len(zlib.compress(data, 9))


def format_psnr(value: float) -> str:
    return "∞ дБ" if np.isinf(value) else f"{value:.2f} дБ"
