"""Серія експериментів без графічного інтерфейсу.

    python experiments.py                       # усі зображення з samples/
    python experiments.py photo.png --levels 4  # своє зображення

Для кожного зображення і кожного механізму стиснення виконується кілька рівнів стиснення
для DCT і DWT. Результати зберігаються в results/:
    results.csv / results.md         - таблиці (частка коефіцієнтів, PSNR, коеф. стиснення, розмір)
    <ім'я>_keep_<частка>.png         - Original | DCT | DWT з підписами PSNR
    levels.md                        - вплив кількості рівнів Хаара на PSNR
    <ім'я>_psnr.png                  - графік PSNR від частки збережених коефіцієнтів (потрібен matplotlib)
"""
import argparse
import csv
from pathlib import Path

import numpy as np
from PIL import Image, ImageDraw, ImageFont

from imgcomp.compress import (DEFAULT_LEVELS, MODE_TITLES, Mode, compress_dct, compress_dwt,
                              transform_dct, transform_dwt)
from imgcomp.image_io import fit_size, load_gray, sample_images
from imgcomp.metrics import format_psnr

LEVELS = {
    Mode.KEEP: [0.20, 0.10, 0.05, 0.02, 0.01],   # частка збережених коефіцієнтів
    Mode.THRESHOLD: [5, 10, 20, 40],             # поріг
    Mode.QUANT: [5, 10, 20, 40],                 # крок квантування
}

ROOT = Path(__file__).resolve().parent


def value_label(mode: Mode, value: float) -> str:
    if mode is Mode.KEEP:
        return f"{value * 100:g}%"
    return f"T={value:g}" if mode is Mode.THRESHOLD else f"q={value:g}"


def _font(size: int):
    for name in ("DejaVuSans.ttf", "arial.ttf", "segoeui.ttf"):
        try:
            return ImageFont.truetype(name, size)
        except OSError:
            pass
    return ImageFont.load_default()


def comparison_image(original, results, title: str) -> Image.Image:
    """Original | DCT | DWT в один рядок з підписами."""
    h, w = original.shape
    pad, head, foot = 10, 34, 48
    canvas = Image.new("L", (3 * w + 4 * pad, h + head + foot + pad), 255)
    d = ImageDraw.Draw(canvas)
    d.text((pad, 8), title, fill=0, font=_font(18))
    panels = [("Original", original, "")] + [
        (r.method, r.image, f"PSNR {format_psnr(r.psnr)}   {r.kept_fraction * 100:.2f}% коеф.") for r in results]
    for i, (name, img, caption) in enumerate(panels):
        x = pad + i * (w + pad)
        canvas.paste(Image.fromarray(img), (x, head))
        d.text((x, head + h + 6), name, fill=0, font=_font(16))
        d.text((x, head + h + 26), caption, fill=60, font=_font(14))
    return canvas


def run(path: Path, levels: int, out: Path) -> list[dict]:
    img = fit_size(load_gray(path), max(8, 2 ** levels))
    dct_coeffs, dwt_coeffs = transform_dct(img), transform_dwt(img, levels)
    rows = []
    for mode, values in LEVELS.items():
        for value in values:
            r_dct = compress_dct(img, mode, value, coeffs=dct_coeffs)
            r_dwt = compress_dwt(img, mode, value, levels, coeffs=dwt_coeffs)
            for r in (r_dct, r_dwt):
                rows.append({
                    "image": path.stem, "mode": mode.value, "value": value_label(mode, value), "method": r.method,
                    "kept": r.kept, "kept_pct": round(r.kept_fraction * 100, 3), "psnr": round(r.psnr, 2),
                    "ratio": round(r.ratio, 2), "bytes": r.encoded_bytes,
                    "size_ratio": round(img.size / r.encoded_bytes, 2),
                })
            if mode is not Mode.KEEP:     # картинки порівняння - лише для основного режиму
                continue
            title = f"{path.stem}: {MODE_TITLES[mode]}, {value_label(mode, value)}"
            name = f"{path.stem}_{mode.value}_{value_label(mode, value).replace('%', 'pct').replace('=', '')}.png"
            comparison_image(img, [r_dct, r_dwt], title).save(out / name)
    plot_curves(img, levels, dct_coeffs, dwt_coeffs, out / f"{path.stem}_psnr.png", path.stem)
    return rows


def plot_curves(img, levels, dct_coeffs, dwt_coeffs, target: Path, name: str) -> None:
    try:
        import matplotlib
        matplotlib.use("Agg")
        import matplotlib.pyplot as plt
    except ImportError:
        print("  (matplotlib не встановлено - графік пропущено)")
        return
    fractions = np.geomspace(0.002, 0.5, 30)
    p_dct = [compress_dct(img, Mode.KEEP, f, coeffs=dct_coeffs).psnr for f in fractions]
    p_dwt = [compress_dwt(img, Mode.KEEP, f, levels, coeffs=dwt_coeffs).psnr for f in fractions]
    fig, ax = plt.subplots(figsize=(6.4, 4))
    ax.plot(fractions * 100, p_dct, marker="o", ms=3, label="DCT 8x8")
    ax.plot(fractions * 100, p_dwt, marker="s", ms=3, label=f"DWT Хаара, {levels} рівні")
    ax.set_xscale("log")
    ax.set_xlabel("Збережено коефіцієнтів, %")
    ax.set_ylabel("PSNR, дБ")
    ax.set_title(f"{name}: PSNR від частки коефіцієнтів")
    ax.grid(True, which="both", alpha=0.3)
    ax.legend()
    fig.tight_layout()
    fig.savefig(target, dpi=120)
    plt.close(fig)


LEVEL_STUDY_FRACTIONS = [0.01, 0.02, 0.05, 0.10]


def levels_study(images: list[Path], out: Path) -> None:
    """PSNR DWT залежно від кількості рівнів (при фіксованій частці коефіцієнтів)."""
    head = " | ".join(f"{f * 100:g}%" for f in LEVEL_STUDY_FRACTIONS)
    lines = ["# Вплив кількості рівнів Хаара на PSNR (режим: частка найбільших коефіцієнтів)\n"]
    for path in images:
        img = fit_size(load_gray(path), 2 ** 7)
        lines += [f"\n### {path.stem}\n", f"| Метод | {head} |", "|---" * (len(LEVEL_STUDY_FRACTIONS) + 1) + "|"]
        c = transform_dct(img)
        lines.append("| DCT 8x8 | " + " | ".join(
            f"{compress_dct(img, Mode.KEEP, f, coeffs=c).psnr:.2f}" for f in LEVEL_STUDY_FRACTIONS) + " |")
        for levels in range(1, 8):
            c = transform_dwt(img, levels)
            lines.append(f"| DWT, {levels} рів. | " + " | ".join(
                f"{compress_dwt(img, Mode.KEEP, f, levels, coeffs=c).psnr:.2f}" for f in LEVEL_STUDY_FRACTIONS) + " |")
    (out / "levels.md").write_text("\n".join(lines) + "\n", encoding="utf-8")


def write_tables(rows: list[dict], out: Path) -> None:
    with open(out / "results.csv", "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)
    lines = []
    for image in dict.fromkeys(r["image"] for r in rows):
        for mode in Mode:
            part = [r for r in rows if r["image"] == image and r["mode"] == mode.value]
            lines += [f"\n### {image} - {MODE_TITLES[mode]}\n",
                      "| Рівень | Метод | Збережено коеф. | PSNR, дБ | Коеф. стиснення (коеф.) | Розмір zlib, Б | Коеф. стиснення (розмір) |",
                      "|---|---|---|---|---|---|---|"]
            lines += [f"| {r['value']} | {r['method']} | {r['kept']} ({r['kept_pct']}%) | {r['psnr']} | "
                      f"{r['ratio']} | {r['bytes']} | {r['size_ratio']} |" for r in part]
    (out / "results.md").write_text("\n".join(lines).lstrip() + "\n", encoding="utf-8")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("images", nargs="*", type=Path, help="зображення (за замовчуванням - samples/*.png)")
    parser.add_argument("--levels", type=int, default=DEFAULT_LEVELS,
                        help=f"кількість рівнів Хаара (за замовчуванням {DEFAULT_LEVELS})")
    parser.add_argument("--out", type=Path, default=ROOT / "results")
    args = parser.parse_args()

    args.out.mkdir(parents=True, exist_ok=True)
    images = args.images or sample_images()
    rows = []
    for path in images:
        print("Обробка", path.name)
        rows += run(path, args.levels, args.out)
    write_tables(rows, args.out)
    levels_study(images, args.out)
    print(f"Готово: {len(rows)} результатів у {args.out}")


if __name__ == "__main__":
    main()
