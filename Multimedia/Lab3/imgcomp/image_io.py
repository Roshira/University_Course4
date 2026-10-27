"""Читання/збереження зображень (Pillow) і підготовка розміру."""
from pathlib import Path

import numpy as np
from PIL import Image

SAMPLES_DIR = Path(__file__).resolve().parent.parent / "samples"


def load_gray(path: str | Path) -> np.ndarray:
    """Зображення у відтінках сірого, uint8 (кольорове переводиться в сіре)."""
    with Image.open(path) as im:
        return np.asarray(im.convert("L"), dtype=np.uint8)


def save_gray(img: np.ndarray, path: str | Path) -> None:
    Image.fromarray(np.asarray(img, dtype=np.uint8), mode="L").save(path)


def fit_size(img: np.ndarray, multiple: int) -> np.ndarray:
    """Обрізати по центру до розміру, кратного multiple (для блоків 8x8 і рівнів Хаара)."""
    h, w = img.shape
    nh, nw = h - h % multiple, w - w % multiple
    if nh == 0 or nw == 0:
        raise ValueError(f"зображення {w}x{h} замале")
    top, left = (h - nh) // 2, (w - nw) // 2
    return img[top:top + nh, left:left + nw]


def sample_images() -> list[Path]:
    return sorted(p for p in SAMPLES_DIR.glob("*.png"))
