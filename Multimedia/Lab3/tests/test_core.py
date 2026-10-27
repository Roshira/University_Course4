import math
import unittest

import numpy as np

from imgcomp import dct, haar
from imgcomp.compress import Mode, compress_dct, compress_dwt, keep_largest, quantize, threshold
from imgcomp.image_io import fit_size
from imgcomp.metrics import coefficient_ratio, encoded_size, psnr
from imgcomp.visualize import coefficient_map, difference_map

RNG = np.random.default_rng(1)


def naive_dct2(block: np.ndarray) -> np.ndarray:
    """DCT-II за формулою з подвійною сумою (еталон для перевірки матричної версії)."""
    n = block.shape[0]
    out = np.zeros((n, n))
    for u in range(n):
        for v in range(n):
            au = math.sqrt(1 / n) if u == 0 else math.sqrt(2 / n)
            av = math.sqrt(1 / n) if v == 0 else math.sqrt(2 / n)
            s = 0.0
            for x in range(n):
                for y in range(n):
                    s += block[x, y] * math.cos((2 * x + 1) * u * math.pi / (2 * n)) \
                                     * math.cos((2 * y + 1) * v * math.pi / (2 * n))
            out[u, v] = au * av * s
    return out


def test_image(h=64, w=96) -> np.ndarray:
    y, x = np.mgrid[0:h, 0:w]
    img = 128 + 60 * np.sin(x / 7) * np.cos(y / 11) + RNG.normal(0, 10, (h, w))
    return np.clip(img, 0, 255).astype(np.uint8)


class DctTest(unittest.TestCase):
    def test_matrix_is_orthonormal(self):
        c = dct.dct_matrix(8)
        np.testing.assert_allclose(c @ c.T, np.eye(8), atol=1e-12)

    def test_matches_formula(self):
        block = RNG.uniform(-128, 127, (8, 8))
        c = dct.dct_matrix(8)
        np.testing.assert_allclose(c @ block @ c.T, naive_dct2(block), atol=1e-9)

    def test_constant_block_has_only_dc(self):
        coeffs = dct.forward(np.full((8, 8), 200.0))
        self.assertAlmostEqual(coeffs[0, 0], 8 * (200 - 128))
        self.assertAlmostEqual(np.abs(coeffs).sum() - abs(coeffs[0, 0]), 0, places=9)

    def test_perfect_reconstruction(self):
        img = test_image()
        np.testing.assert_allclose(dct.inverse(dct.forward(img)), img, atol=1e-9)

    def test_blocks_roundtrip(self):
        img = RNG.uniform(0, 255, (16, 24))
        blocks = dct.to_blocks(img)
        self.assertEqual(blocks.shape, (2, 3, 8, 8))
        np.testing.assert_array_equal(blocks[1, 2], img[8:16, 16:24])
        np.testing.assert_array_equal(dct.from_blocks(blocks), img)

    def test_zigzag(self):
        z = dct.zigzag_order(8)
        self.assertEqual(z[:6], [(0, 0), (0, 1), (1, 0), (2, 0), (1, 1), (0, 2)])
        self.assertEqual(len(set(z)), 64)

    def test_bad_size(self):
        with self.assertRaises(ValueError):
            dct.forward(np.zeros((10, 16)))


class HaarTest(unittest.TestCase):
    def test_matrix_is_orthonormal(self):
        w = haar.haar_matrix(8)
        np.testing.assert_allclose(w @ w.T, np.eye(8), atol=1e-12)

    def test_one_level_equals_matrix_form(self):
        img = RNG.uniform(0, 255, (8, 16))
        expected = haar.haar_matrix(8) @ img @ haar.haar_matrix(16).T
        np.testing.assert_allclose(haar.forward(img, 1), expected, atol=1e-9)

    def test_simple_values(self):
        out = haar.forward(np.array([[4.0, 2.0], [6.0, 8.0]]), 1)
        # LL = сума / 2, HL = різниця по рядках, LH = по стовпцях, HH = діагональна
        np.testing.assert_allclose(out, [[10, 0], [-4, 2]], atol=1e-12)

    def test_perfect_reconstruction_all_levels(self):
        img = test_image(64, 64)
        for levels in range(1, haar.max_levels(img.shape) + 1):
            np.testing.assert_allclose(haar.inverse(haar.forward(img, levels), levels), img, atol=1e-9)

    def test_energy_preserved(self):
        img = test_image().astype(float)
        self.assertAlmostEqual(np.sum(haar.forward(img, 3) ** 2) / np.sum(img ** 2), 1.0, places=12)

    def test_constant_image_only_ll(self):
        coeffs = haar.forward(np.full((32, 32), 50.0), 2)
        self.assertEqual(np.count_nonzero(np.abs(coeffs) > 1e-9), 64)  # лише LL2 8x8
        np.testing.assert_allclose(coeffs[:8, :8], 50.0 * 4)

    def test_max_levels(self):
        self.assertEqual(haar.max_levels((512, 512)), 9)
        self.assertEqual(haar.max_levels((48, 64)), 4)
        with self.assertRaises(ValueError):
            haar.forward(np.zeros((48, 64)), 5)

    def test_subbands_cover_image(self):
        area = sum(h * w for _, _, _, h, w in haar.subband_rects((64, 64), 3))
        self.assertEqual(area, 64 * 64)


class CompressionTest(unittest.TestCase):
    def test_keep_largest(self):
        c = np.array([[5.0, -9.0], [1.0, 0.5]])
        np.testing.assert_array_equal(keep_largest(c, 0.5), [[5, -9], [0, 0]])
        np.testing.assert_array_equal(keep_largest(c, 1.0), c)
        self.assertEqual(np.count_nonzero(keep_largest(c, 0.0)), 0)

    def test_threshold_and_quantize(self):
        c = np.array([3.0, -3.0, 2.9, -10.4])
        np.testing.assert_array_equal(threshold(c, 3), [3, -3, 0, -10.4])
        q, rec = quantize(c, 4)
        np.testing.assert_array_equal(q, [1, -1, 1, -3])
        np.testing.assert_array_equal(rec, [4, -4, 4, -12])

    def test_more_coefficients_better_quality(self):
        img = test_image()
        for fn in (compress_dct, compress_dwt):
            values = [fn(img, Mode.KEEP, f).psnr for f in (0.02, 0.1, 0.4)]
            self.assertEqual(values, sorted(values), fn.__name__)

    def test_keep_fraction_counts(self):
        img = test_image()
        r = compress_dwt(img, Mode.KEEP, 0.1, levels=3)
        self.assertEqual(r.total, img.size)
        self.assertLessEqual(r.kept, round(0.1 * img.size))
        self.assertAlmostEqual(r.ratio, r.total / r.kept)

    def test_lossless_without_reduction(self):
        img = test_image()
        self.assertEqual(compress_dct(img, Mode.KEEP, 1.0).psnr, float("inf"))
        self.assertEqual(compress_dwt(img, Mode.THRESHOLD, 0.0).psnr, float("inf"))

    def test_parseval_error(self):
        # для ортонормованих перетворень MSE у пікселях = MSE у коефіцієнтах (до округлення)
        img = test_image().astype(float)
        coeffs = dct.forward(img)
        kept = keep_largest(coeffs, 0.05)
        err_pixels = np.mean((dct.inverse(kept) - img) ** 2)
        err_coeffs = np.mean((kept - coeffs) ** 2)
        self.assertAlmostEqual(err_pixels, err_coeffs, places=8)

    def test_coarser_quantization_smaller_file(self):
        img = test_image()
        sizes = [compress_dct(img, Mode.QUANT, q).encoded_bytes for q in (2, 10, 50)]
        self.assertEqual(sizes, sorted(sizes, reverse=True))


class MetricsTest(unittest.TestCase):
    def test_psnr(self):
        a = np.zeros((4, 4))
        self.assertEqual(psnr(a, a), float("inf"))
        self.assertAlmostEqual(psnr(a, a + 1), 20 * math.log10(255), places=9)
        self.assertAlmostEqual(psnr(a, a + 255), 0.0, places=9)

    def test_ratio_and_size(self):
        self.assertEqual(coefficient_ratio(np.array([0, 0, 3, 0])), 4.0)
        self.assertLess(encoded_size(np.zeros(10000)), encoded_size(RNG.integers(-50, 50, 10000)))

    def test_fit_size(self):
        img = np.arange(30 * 21).reshape(30, 21)
        out = fit_size(img, 8)
        self.assertEqual(out.shape, (24, 16))
        np.testing.assert_array_equal(out, img[3:27, 2:18])


class VisualizeTest(unittest.TestCase):
    def test_coefficient_map(self):
        m = coefficient_map(np.array([[0.0, -100.0], [10.0, 1.0]]))
        self.assertEqual(m.dtype, np.uint8)
        self.assertEqual(m[0, 0], 0)
        self.assertEqual(m[0, 1], 255)
        self.assertTrue(0 < m[1, 1] < m[1, 0] < 255)
        self.assertEqual(coefficient_map(np.zeros((2, 2))).max(), 0)

    def test_difference_map(self):
        a = np.array([[10, 200]], dtype=np.uint8)
        b = np.array([[12, 100]], dtype=np.uint8)
        np.testing.assert_array_equal(difference_map(a, b), [[10, 255]])


class DwtLevelShiftTest(unittest.TestCase):
    def test_dropping_all_coefficients_gives_gray(self):
        # при нульових коефіцієнтах обидва методи відновлюють сіре зображення (128)
        img = test_image(64, 64)
        self.assertTrue(np.all(compress_dct(img, Mode.KEEP, 0.0).image == 128))
        self.assertTrue(np.all(compress_dwt(img, Mode.KEEP, 0.0, levels=3).image == 128))


if __name__ == "__main__":
    unittest.main()
