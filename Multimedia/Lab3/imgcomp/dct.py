"""Дискретне косинусне перетворення (DCT-II) блоками 8x8 у матричному вигляді.

Для блоку B розміром N x N:
    пряме   X = C @ B @ C.T
    обернене B = C.T @ X @ C
де C - ортонормована матриця DCT. Оскільки C ортогональна (C @ C.T = I),
обернена матриця дорівнює транспонованій, і перетворення зберігає енергію
(сума квадратів коефіцієнтів = сума квадратів пікселів).
"""
import numpy as np

BLOCK = 8
LEVEL_SHIFT = 128.0  # як у JPEG: пікселі 0..255 зсуваються до -128..127


def dct_matrix(n: int = BLOCK) -> np.ndarray:
    """C[k, i] = a(k) * cos(pi * (2i + 1) * k / 2n), a(0) = sqrt(1/n), a(k) = sqrt(2/n)."""
    k = np.arange(n).reshape(-1, 1)
    i = np.arange(n).reshape(1, -1)
    c = np.cos(np.pi * (2 * i + 1) * k / (2 * n))
    alpha = np.full((n, 1), np.sqrt(2.0 / n))
    alpha[0, 0] = np.sqrt(1.0 / n)
    return alpha * c


def to_blocks(img: np.ndarray, n: int = BLOCK) -> np.ndarray:
    """(H, W) -> (H/n, W/n, n, n): масив блоків."""
    h, w = img.shape
    if h % n or w % n:
        raise ValueError(f"розмір {w}x{h} має бути кратним {n}")
    return img.reshape(h // n, n, w // n, n).swapaxes(1, 2)


def from_blocks(blocks: np.ndarray) -> np.ndarray:
    """(H/n, W/n, n, n) -> (H, W)."""
    bh, bw, n, _ = blocks.shape
    return blocks.swapaxes(1, 2).reshape(bh * n, bw * n)


def forward(img: np.ndarray, n: int = BLOCK) -> np.ndarray:
    """Пряме DCT усіх блоків. Результат має розмір зображення:
    у кожному блоці n x n лежать його коефіцієнти (DC - у лівому верхньому куті)."""
    c = dct_matrix(n)
    blocks = to_blocks(np.asarray(img, dtype=np.float64) - LEVEL_SHIFT, n)
    return from_blocks(c @ blocks @ c.T)  # matmul застосовується до кожного блоку


def inverse(coeffs: np.ndarray, n: int = BLOCK) -> np.ndarray:
    """Обернене DCT усіх блоків (результат - дійсні значення, без обрізання до 0..255)."""
    c = dct_matrix(n)
    return from_blocks(c.T @ to_blocks(coeffs, n) @ c) + LEVEL_SHIFT


def zigzag_order(n: int = BLOCK) -> list[tuple[int, int]]:
    """Порядок обходу блоку зигзагом (від низьких частот до високих)."""
    cells = [(i, j) for i in range(n) for j in range(n)]
    return sorted(cells, key=lambda p: (p[0] + p[1], p[0] if (p[0] + p[1]) % 2 else p[1]))
