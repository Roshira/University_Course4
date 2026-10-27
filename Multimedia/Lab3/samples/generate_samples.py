"""Створює тестові зображення 512x512 у відтінках сірого (усі - власні, згенеровані програмно).

    python samples/generate_samples.py

landscape.png    - гірський пейзаж: небо з хмарами, сонце, гори (фрактальний шум), озеро з відображенням,
                   трава на передньому плані. Плавні ділянки + краї + текстура, як на фото.
city.png         - нічне місто: силуети будинків з вікнами, місяць, зорі. Багато різких країв і
                   періодичних структур.
marble.png       - мармур / дерево: дрібна природна текстура.
test_pattern.png - синтетична таблиця: градієнт, краї, тонкі лінії, смуги зростаючої частоти, текст, шум.

Генерація детермінована (фіксований seed), тому файли щоразу однакові.
"""
from pathlib import Path

import numpy as np
from PIL import Image, ImageDraw, ImageFilter, ImageFont

SIZE = 512
OUT = Path(__file__).resolve().parent


# ---------- шум ----------
def value_noise(shape, cell, rng):
    """Гладкий шум: випадкова решітка з кроком cell, бікубічна інтерполяція."""
    h, w = shape
    gh, gw = h // cell + 2, w // cell + 2
    grid = rng.random((gh, gw)).astype(np.float32)
    img = Image.fromarray(grid, mode="F").resize((gw * cell, gh * cell), Image.Resampling.BICUBIC)
    return np.asarray(img)[:h, :w]


def fbm(shape, rng, octaves=6, base=128, gain=0.5):
    """Фрактальний (броунівський) шум: сума октав зі зменшенням масштабу та амплітуди."""
    total = np.zeros(shape, np.float32)
    amp, norm, cell = 1.0, 0.0, base
    for _ in range(octaves):
        total += amp * value_noise(shape, max(cell, 1), rng)
        norm += amp
        amp *= gain
        cell //= 2
    return total / norm


def ridge_1d(n, rng, octaves=7, base=256):
    """Профіль гірського хребта (1D fBm)."""
    x = np.arange(n, dtype=np.float32)
    out = np.zeros(n, np.float32)
    amp, step = 1.0, base
    for _ in range(octaves):
        pts = rng.random(n // step + 2)
        out += amp * np.interp(x / step, np.arange(len(pts)), pts)
        amp *= 0.55
        step = max(step // 2, 1)
    return (out - out.min()) / (out.max() - out.min())


def to_image(a) -> Image.Image:
    return Image.fromarray(np.clip(a, 0, 255).astype(np.uint8), mode="L")


def font(size):
    for name in ("DejaVuSans-Bold.ttf", "arialbd.ttf", "Arial Bold.ttf"):
        try:
            return ImageFont.truetype(name, size)
        except OSError:
            pass
    return ImageFont.load_default()


# ---------- сцени ----------
def landscape() -> Image.Image:
    rng = np.random.default_rng(2026)
    y, x = np.mgrid[0:SIZE, 0:SIZE].astype(np.float32)
    horizon = 330

    # небо: градієнт + хмари + сонце з ореолом
    sky = 205 - 85 * (y / horizon)
    clouds = fbm((SIZE, SIZE), rng, octaves=6, base=128)
    clouds = np.clip((clouds - 0.52) * 3.2, 0, 1) * (1 - y / horizon).clip(0, 1) ** 0.5
    sky = sky + 60 * clouds
    sun_r = np.hypot(x - 360, y - 110)
    sky = sky + 70 * np.exp(-(sun_r / 70) ** 2) + np.where(sun_r < 26, 255, 0)
    img = sky.copy()

    # три плани гір: далекі світліші, близькі темніші, з текстурою схилів
    for top, height, shade, base in [(95, 150, 165, 256), (175, 120, 115, 128), (240, 90, 70, 64)]:
        ridge = top + height * (1 - ridge_1d(SIZE, rng, base=base))
        tex = fbm((SIZE, SIZE), rng, octaves=5, base=32)
        mountain = shade + 40 * (tex - 0.5) + 25 * (y - ridge) / height
        mask = (y >= ridge[None, :]) & (y < horizon)
        img = np.where(mask, mountain, img)

    # озеро: віддзеркалення з хвилями
    lake_top, lake_bottom = horizon, 430
    ripple = 3 * np.sin(y / 2.3 + 4 * fbm((SIZE, SIZE), rng, octaves=3, base=64))
    src_y = np.clip(2 * horizon - y + ripple, 0, horizon - 1).astype(int)
    src_x = np.clip(x + ripple * 1.5, 0, SIZE - 1).astype(int)
    reflection = 0.75 * img[src_y, src_x] + 15
    lake = (y >= lake_top) & (y < lake_bottom)
    img = np.where(lake, reflection, img)

    # передній план: берег і трава
    shore = lake_bottom + 6 * (fbm((1, SIZE), rng, octaves=4, base=64)[0] - 0.5)
    grass_tex = fbm((SIZE, SIZE), rng, octaves=4, base=8)
    ground = 60 + 55 * grass_tex + 20 * (SIZE - y) / (SIZE - lake_bottom)
    img = np.where(y >= shore[None, :], ground, img)

    im = to_image(img)
    d = ImageDraw.Draw(im)
    # травинки
    for _ in range(900):
        gx = rng.uniform(0, SIZE)
        gy = rng.uniform(lake_bottom + 5, SIZE)
        length = rng.uniform(6, 22) * (gy - lake_bottom) / (SIZE - lake_bottom) + 4
        d.line((gx, gy, gx + rng.uniform(-4, 4), gy - length), fill=int(rng.uniform(25, 120)), width=1)
    # дерево (ялина) на березі
    tx, ty = 85, 445
    for i in range(9):
        w = 8 + i * 6
        top = ty - 150 + i * 14
        d.polygon([(tx, top), (tx - w, top + 28), (tx + w, top + 28)], fill=28 + i)
    d.rectangle((tx - 4, ty - 20, tx + 4, ty + 6), fill=35)
    # птахи
    for bx, by in ((150, 70), (175, 85), (200, 62)):
        d.arc((bx - 8, by - 5, bx, by + 5), 200, 340, fill=40, width=2)
        d.arc((bx, by - 5, bx + 8, by + 5), 200, 340, fill=40, width=2)
    return im.filter(ImageFilter.GaussianBlur(0.4))


def city() -> Image.Image:
    rng = np.random.default_rng(7)
    y, x = np.mgrid[0:SIZE, 0:SIZE].astype(np.float32)
    sky = 18 + 55 * (y / SIZE) ** 1.5                      # світліше до горизонту (засвітка міста)
    moon = np.hypot(x - 410, y - 85)
    sky = sky + 50 * np.exp(-(moon / 45) ** 2)
    sky = np.where(moon < 30, 225 - 25 * fbm((SIZE, SIZE), rng, octaves=3, base=16), sky)
    im = to_image(sky)
    d = ImageDraw.Draw(im)
    for _ in range(140):                                    # зорі
        sx, sy = rng.uniform(0, SIZE), rng.uniform(0, 260)
        if np.hypot(sx - 410, sy - 85) > 60:
            v = int(rng.uniform(120, 255))
            d.point((sx, sy), fill=v)
            if v > 220:
                d.point([(sx + 1, sy), (sx, sy + 1)], fill=v - 60)

    def building(x0, width, height, shade, layer):
        top = SIZE - 40 - height
        d.rectangle((x0, top, x0 + width, SIZE), fill=shade)
        if rng.random() < 0.35:                             # дах-шпиль або антена
            d.polygon([(x0, top), (x0 + width / 2, top - rng.uniform(15, 40)), (x0 + width, top)], fill=shade)
        if layer == 0:
            return
        wx, wy = int(rng.integers(5, 9)), int(rng.integers(8, 13))
        for yy in range(int(top) + 8, SIZE - 50, wy + 5):
            for xx in range(int(x0) + 5, int(x0 + width) - wx - 3, wx + 5):
                if rng.random() < 0.45:
                    d.rectangle((xx, yy, xx + wx, yy + wy), fill=int(rng.uniform(150, 245)))

    x0 = -10
    while x0 < SIZE:                                        # дальній ряд - темні силуети
        w = rng.uniform(30, 70)
        building(x0, w, rng.uniform(120, 260), 32, 0)
        x0 += w + rng.uniform(-10, 5)
    x0 = -20
    while x0 < SIZE:                                        # ближній ряд - з вікнами
        w = rng.uniform(45, 95)
        building(x0, w, rng.uniform(80, 220), int(rng.uniform(40, 58)), 1)
        x0 += w + rng.uniform(4, 18)
    # набережна з ліхтарями та відображенням
    d.rectangle((0, SIZE - 40, SIZE, SIZE), fill=22)
    for lx in range(20, SIZE, 64):
        d.line((lx, SIZE - 40, lx, SIZE - 75), fill=70, width=2)
        d.ellipse((lx - 5, SIZE - 82, lx + 5, SIZE - 72), fill=250)
    d.text((14, 14), "NIGHT CITY 2026", fill=200, font=font(22))
    return im


def marble() -> Image.Image:
    rng = np.random.default_rng(42)
    y, x = np.mgrid[0:SIZE, 0:SIZE].astype(np.float32)
    turb = fbm((SIZE, SIZE), rng, octaves=7, base=128)
    veins = np.abs(np.sin((x * 0.6 + y * 0.35) / 22 + 9 * turb))
    img = 70 + 150 * veins ** 0.35
    img -= 90 * np.exp(-((veins - 0.02) / 0.05) ** 2) * (turb > 0.45)   # темні прожилки
    img += 18 * (fbm((SIZE, SIZE), rng, octaves=3, base=4) - 0.5)        # зерно
    # дерев'яна вставка в нижній третині (кільця + волокна)
    wood_r = np.hypot((x - 256) * 0.25, (y - 700)) + 6 * fbm((SIZE, SIZE), rng, octaves=4, base=32)
    wood = 105 + 45 * np.sin(wood_r / 3.2) + 20 * (fbm((SIZE, SIZE), rng, octaves=2, base=2) - 0.5)
    img = np.where(y > 380, wood, img)
    img[376:384] = 30                                                    # шов
    return to_image(img)


def test_pattern() -> Image.Image:
    y, x = np.mgrid[0:SIZE, 0:SIZE].astype(float)
    img = 40 + 150 * x / SIZE
    chirp = 128 + 100 * np.sin(2 * np.pi * (x / SIZE) ** 2 * 60)
    img[384:] = chirp[384:]
    r = np.hypot(x - 384, y - 128)
    mask = r < 120
    img[mask] = 128 + 110 * np.cos(r[mask] ** 2 / 180)
    rng = np.random.default_rng(0)
    img[256:384, 0:128] = np.clip(128 + rng.normal(0, 40, (128, 128)), 0, 255)
    im = to_image(img)
    d = ImageDraw.Draw(im)
    d.rectangle((40, 40, 200, 200), fill=230, outline=10, width=3)
    d.ellipse((90, 90, 150, 150), fill=20)
    for i in range(8):
        d.line((150 + i * 12, 260, 250 + i * 12, 370), fill=255 if i % 2 else 0, width=1 + i % 3)
    d.text((290, 280), "DCT vs DWT", fill=250, font=font(30))
    d.text((290, 320), "Haar 8x8", fill=10, font=font(30))
    return im


SCENES = {"landscape": landscape, "city": city, "marble": marble, "test_pattern": test_pattern}

if __name__ == "__main__":
    for name, make in SCENES.items():
        path = OUT / f"{name}.png"
        make().save(path)
        print("Збережено", path)
