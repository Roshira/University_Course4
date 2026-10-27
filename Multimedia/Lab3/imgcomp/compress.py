"""Зменшення кількості значущих коефіцієнтів і повний цикл стиснення.

Обидва перетворення ортонормовані, тому похибка в коефіцієнтах дорівнює похибці
в пікселях (теорема Парсеваля), і однакові механізми стиснення можна чесно
порівнювати для DCT і DWT.
"""
from dataclasses import dataclass
from enum import Enum

import numpy as np

from . import dct, haar
from .metrics import coefficient_ratio, encoded_size, psnr

DEFAULT_LEVELS = 5


class Mode(Enum):
    KEEP = "keep"            # зберегти частку найбільших за модулем коефіцієнтів
    THRESHOLD = "threshold"  # обнулити коефіцієнти з |c| < поріг
    QUANT = "quant"          # рівномірне квантування з кроком q


MODE_TITLES = {
    Mode.KEEP: "Частка найбільших коефіцієнтів",
    Mode.THRESHOLD: "Поріг (thresholding)",
    Mode.QUANT: "Квантування",
}


def keep_largest(coeffs: np.ndarray, fraction: float) -> np.ndarray:
    """Залишити round(fraction * N) найбільших за модулем коефіцієнтів, решту обнулити."""
    flat = coeffs.ravel()
    k = int(round(np.clip(fraction, 0.0, 1.0) * flat.size))
    out = np.zeros_like(flat)
    if k > 0:
        idx = np.argpartition(np.abs(flat), flat.size - k)[flat.size - k:]
        out[idx] = flat[idx]
    return out.reshape(coeffs.shape)


def threshold(coeffs: np.ndarray, t: float) -> np.ndarray:
    return np.where(np.abs(coeffs) >= t, coeffs, 0.0)


def quantize(coeffs: np.ndarray, step: float) -> tuple[np.ndarray, np.ndarray]:
    """Повертає (індекси квантування, відновлені коефіцієнти = індекс * крок)."""
    step = max(float(step), 1e-9)
    q = np.round(coeffs / step)
    return q, q * step


def reduce(coeffs: np.ndarray, mode: Mode, value: float) -> tuple[np.ndarray, np.ndarray]:
    """Застосувати механізм стиснення. Повертає (коефіцієнти після обробки,
    цілі числа, які були б записані у файл - для оцінки розміру)."""
    if mode is Mode.KEEP:
        kept = keep_largest(coeffs, value)
        return kept, np.round(kept)
    if mode is Mode.THRESHOLD:
        kept = threshold(coeffs, value)
        return kept, np.round(kept)
    q, rec = quantize(coeffs, value)
    return rec, q


@dataclass
class Result:
    method: str                 # "DCT" або "DWT"
    coeffs: np.ndarray          # коефіцієнти до стиснення
    reduced: np.ndarray         # коефіцієнти після стиснення
    image: np.ndarray           # відновлене зображення uint8
    kept: int                   # кількість ненульових коефіцієнтів
    total: int
    psnr: float
    ratio: float                # total / kept
    encoded_bytes: int          # оцінка розміру (zlib від цілих коефіцієнтів)

    @property
    def kept_fraction(self) -> float:
        return self.kept / self.total


def _finish(method, img, coeffs, reduced, symbols, restored) -> Result:
    image = np.clip(np.round(restored), 0, 255).astype(np.uint8)
    kept = int(np.count_nonzero(reduced))
    return Result(
        method=method, coeffs=coeffs, reduced=reduced, image=image,
        kept=kept, total=reduced.size,
        psnr=psnr(img, image), ratio=coefficient_ratio(reduced),
        encoded_bytes=encoded_size(symbols),
    )


def transform_dct(img: np.ndarray) -> np.ndarray:
    """DCT 8x8 (зсув на -128 виконується всередині dct.forward)."""
    return dct.forward(img)


def transform_dwt(img: np.ndarray, levels: int) -> np.ndarray:
    """DWT Хаара з таким самим зсувом -128, як у DCT: тоді обнулений коефіцієнт
    наближення дає сірий (128), а не чорний колір, і методи порівнюються чесно."""
    return haar.forward(np.asarray(img, dtype=np.float64) - dct.LEVEL_SHIFT, levels)


def compress_dct(img: np.ndarray, mode: Mode, value: float, coeffs: np.ndarray | None = None) -> Result:
    if coeffs is None:
        coeffs = transform_dct(img)
    reduced, symbols = reduce(coeffs, mode, value)
    return _finish("DCT", img, coeffs, reduced, symbols, dct.inverse(reduced))


def compress_dwt(img: np.ndarray, mode: Mode, value: float, levels: int = DEFAULT_LEVELS,
                 coeffs: np.ndarray | None = None) -> Result:
    if coeffs is None:
        coeffs = transform_dwt(img, levels)
    reduced, symbols = reduce(coeffs, mode, value)
    restored = haar.inverse(reduced, levels) + dct.LEVEL_SHIFT
    return _finish("DWT", img, coeffs, reduced, symbols, restored)
