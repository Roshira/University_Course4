"""Дискретне вейвлет-перетворення Хаара (DWT), багаторівневе, двовимірне.

Один крок для пари сусідніх значень (a, b), ортонормований варіант:
    L = (a + b) / sqrt(2)   - середнє (низькі частоти)
    H = (a - b) / sqrt(2)   - різниця (високі частоти, деталі)
Обернений крок:
    a = (L + H) / sqrt(2),  b = (L - H) / sqrt(2)

2D-рівень: крок застосовується до всіх рядків, потім до всіх стовпців.
Отримуємо 4 підсмуги: LL (зменшена копія), LH, HL, HH (деталі).
Наступний рівень обробляє лише LL. Розташування після 2 рівнів:

    +-----+-----+-----------+
    | LL2 | HL2 |           |
    +-----+-----+    HL1    |
    | LH2 | HH2 |           |
    +-----+-----+-----------+
    |           |           |
    |    LH1    |    HH1    |
    |           |           |
    +-----------+-----------+
"""
import numpy as np

SQRT2 = np.sqrt(2.0)


def haar_matrix(n: int) -> np.ndarray:
    """Матриця одного кроку Хаара n x n: перші n/2 рядків - середні, наступні - різниці.
    Крок по рядках/стовпцях можна записати як W @ A @ W.T (використовується в тестах
    для перевірки, а в forward/inverse - швидша еквівалентна реалізація зрізами)."""
    if n % 2:
        raise ValueError("n має бути парним")
    w = np.zeros((n, n))
    for k in range(n // 2):
        w[k, 2 * k] = w[k, 2 * k + 1] = 1 / SQRT2
        w[n // 2 + k, 2 * k] = 1 / SQRT2
        w[n // 2 + k, 2 * k + 1] = -1 / SQRT2
    return w


def _step_rows(a: np.ndarray) -> np.ndarray:
    even, odd = a[:, 0::2], a[:, 1::2]
    return np.hstack(((even + odd) / SQRT2, (even - odd) / SQRT2))


def _inv_step_rows(a: np.ndarray) -> np.ndarray:
    half = a.shape[1] // 2
    low, high = a[:, :half], a[:, half:]
    out = np.empty_like(a)
    out[:, 0::2] = (low + high) / SQRT2
    out[:, 1::2] = (low - high) / SQRT2
    return out


def max_levels(shape: tuple[int, int]) -> int:
    """Скільки рівнів можна виконати (обидва розміри мають ділитися на 2^levels)."""
    h, w = shape
    levels = 0
    while h % 2 == 0 and w % 2 == 0 and min(h, w) >= 2:
        h, w, levels = h // 2, w // 2, levels + 1
    return levels


def forward(img: np.ndarray, levels: int = 3) -> np.ndarray:
    out = np.asarray(img, dtype=np.float64).copy()
    h, w = out.shape
    if levels > max_levels(out.shape):
        raise ValueError(f"для {w}x{h} можливо не більше {max_levels(out.shape)} рівнів")
    for _ in range(levels):
        sub = _step_rows(out[:h, :w])        # рядки
        sub = _step_rows(sub.T).T            # стовпці
        out[:h, :w] = sub
        h, w = h // 2, w // 2
    return out


def inverse(coeffs: np.ndarray, levels: int = 3) -> np.ndarray:
    out = np.asarray(coeffs, dtype=np.float64).copy()
    full_h, full_w = out.shape
    for level in reversed(range(levels)):
        h, w = full_h >> level, full_w >> level
        sub = _inv_step_rows(out[:h, :w].T).T   # стовпці
        sub = _inv_step_rows(sub)               # рядки
        out[:h, :w] = sub
    return out


def subband_rects(shape: tuple[int, int], levels: int) -> list[tuple[str, int, int, int, int]]:
    """Прямокутники підсмуг (назва, y, x, висота, ширина) - для підписів на карті коефіцієнтів."""
    h, w = shape
    rects = []
    for level in range(1, levels + 1):
        h2, w2 = h // 2, w // 2
        rects += [(f"HL{level}", 0, w2, h2, w2), (f"LH{level}", h2, 0, h2, w2), (f"HH{level}", h2, w2, h2, w2)]
        h, w = h2, w2
    rects.append((f"LL{levels}", 0, 0, h, w))
    return rects
