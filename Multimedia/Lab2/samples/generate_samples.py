from __future__ import annotations

import math
import sys
import wave
from fractions import Fraction
from pathlib import Path

import av
import numpy as np
from PySide6.QtCore import QPointF, QRectF, Qt
from PySide6.QtGui import (
    QBrush,
    QColor,
    QFont,
    QGuiApplication,
    QImage,
    QLinearGradient,
    QPainter,
    QPainterPath,
    QPen,
    QRadialGradient,
)

OUT = Path(__file__).resolve().parent
sys.path.insert(0, str(OUT.parent))
from media_player.spectrum import FFT_SIZE, band_levels

RATE = 48_000
DURATION = 20.0
FPS = 25
W, H = 960, 540

NOTES = [261.63, 329.63, 392.00, 523.25, 392.00, 329.63]
BASS = [130.81, 130.81, 174.61, 196.00]


def melody(duration: float = DURATION) -> np.ndarray:
    t = np.arange(int(RATE * duration)) / RATE
    note_len = 0.4
    idx = (t // note_len).astype(int) % len(NOTES)
    freq = np.array(NOTES)[idx]
    local = t % note_len
    envelope = np.minimum(1.0, local * 40) * np.exp(-local * 4)
    lead = (0.6 * np.sin(2 * np.pi * freq * t) + 0.2 * np.sin(4 * np.pi * freq * t)) * envelope
    bass_idx = (t // (note_len * 6)).astype(int) % len(BASS)
    bass_freq = np.array(BASS)[bass_idx]
    bass_local = t % (note_len * 6)
    bass = 0.35 * np.sin(2 * np.pi * bass_freq * t) * np.exp(-bass_local * 1.2)
    return ((lead + bass) * 0.7).astype(np.float32)


def qimage_to_array(img: QImage) -> np.ndarray:
    img = img.convertToFormat(QImage.Format.Format_RGB888)
    data = np.frombuffer(img.constBits(), dtype=np.uint8)
    return data.reshape(img.height(), img.bytesPerLine())[:, : img.width() * 3].reshape(
        img.height(), img.width(), 3
    ).copy()


def canvas() -> tuple[QImage, QPainter]:
    img = QImage(W, H, QImage.Format.Format_RGB32)
    p = QPainter(img)
    p.setRenderHint(QPainter.RenderHint.Antialiasing)
    p.setRenderHint(QPainter.RenderHint.TextAntialiasing)
    return img, p


def font(size: float, bold: bool = False) -> QFont:
    f = QFont("Segoe UI")
    f.setPixelSize(int(size))
    f.setBold(bold)
    return f


def caption(p: QPainter, title: str, t: float) -> None:
    p.setPen(QColor(255, 255, 255, 230))
    p.setFont(font(30, True))
    p.drawText(QRectF(36, 26, W - 72, 44), Qt.AlignmentFlag.AlignLeft, title)
    p.setFont(font(20))
    p.setPen(QColor(255, 255, 255, 170))
    p.drawText(QRectF(36, H - 56, W - 72, 30), Qt.AlignmentFlag.AlignRight,
               f"00:{int(t):02d} / 00:{int(DURATION):02d}")
    p.setPen(Qt.PenStyle.NoPen)
    p.setBrush(QColor(255, 255, 255, 40))
    p.drawRoundedRect(QRectF(36, H - 18, W - 72, 4), 2, 2)
    p.setBrush(QColor("#ffd34d"))
    p.drawRoundedRect(QRectF(36, H - 18, (W - 72) * t / DURATION, 4), 2, 2)


STARS = np.random.default_rng(7).random((160, 3))
PLANETS = [
    ("Меркурій", 70, 5, 4.1, "#b9b2a8"),
    ("Венера", 105, 8, 1.6, "#e6c27a"),
    ("Земля", 145, 9, 1.0, "#4f9cf9"),
    ("Марс", 185, 7, 0.53, "#e0603c"),
    ("Юпітер", 245, 18, 0.084, "#d9a066"),
]


def frame_solar(i: int, samples: np.ndarray) -> np.ndarray:
    t = i / FPS
    img, p = canvas()
    bg = QRadialGradient(QPointF(W / 2, H / 2), W * 0.7)
    bg.setColorAt(0, QColor("#141a33"))
    bg.setColorAt(1, QColor("#05060c"))
    p.fillRect(img.rect(), QBrush(bg))
    for sx, sy, ph in STARS:
        alpha = int(120 + 120 * math.sin(t * 2 + ph * 10))
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(QColor(255, 255, 255, max(30, alpha)))
        p.drawEllipse(QPointF(sx * W, sy * H), 1.2, 1.2)

    c = QPointF(W / 2, H / 2 + 20)
    glow = QRadialGradient(c, 90)
    glow.setColorAt(0, QColor(255, 210, 90, 255))
    glow.setColorAt(0.35, QColor(255, 170, 40, 200))
    glow.setColorAt(1, QColor(255, 140, 0, 0))
    p.setBrush(QBrush(glow))
    p.drawEllipse(c, 90, 90)
    p.setBrush(QColor("#ffd34d"))
    p.drawEllipse(c, 30, 30)

    for name, radius, size, speed, color in PLANETS:
        p.setPen(QPen(QColor(255, 255, 255, 40), 1))
        p.setBrush(Qt.BrushStyle.NoBrush)
        p.drawEllipse(c, radius * 1.6, radius * 0.75)
        angle = t * speed * 1.2 + radius
        pos = QPointF(c.x() + radius * 1.6 * math.cos(angle), c.y() + radius * 0.75 * math.sin(angle))
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(QColor(color))
        p.drawEllipse(pos, size, size)
        p.setPen(QColor(255, 255, 255, 190))
        p.setFont(font(14))
        p.drawText(QPointF(pos.x() + size + 6, pos.y() + 5), name)

    caption(p, "Сонячна система", t)
    p.end()
    return qimage_to_array(img)


def frame_spectrum(i: int, samples: np.ndarray) -> np.ndarray:
    t = i / FPS
    img, p = canvas()
    bg = QLinearGradient(0, 0, 0, H)
    bg.setColorAt(0, QColor("#1b1036"))
    bg.setColorAt(1, QColor("#070a18"))
    p.fillRect(img.rect(), QBrush(bg))

    end = int(t * RATE)
    window = samples[max(0, end - FFT_SIZE):end]
    bands = 48
    levels = band_levels(window, RATE, bands)
    left, right, base = 60, W - 60, H - 110
    gap = 5
    bar_w = (right - left - gap * (bands - 1)) / bands
    grad = QLinearGradient(0, base, 0, base - 300)
    grad.setColorAt(0, QColor("#4f9cf9"))
    grad.setColorAt(0.6, QColor("#8e5cf7"))
    grad.setColorAt(1, QColor("#ff5fa2"))
    for b in range(bands):
        x = left + b * (bar_w + gap)
        h = max(4.0, levels[b] * 300)
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(QBrush(grad))
        p.drawRoundedRect(QRectF(x, base - h, bar_w, h), 3, 3)
        p.setBrush(QColor(143, 92, 247, 60))
        p.drawRoundedRect(QRectF(x, base + 6, bar_w, h * 0.25), 3, 3)

    wave_block = samples[max(0, end - 1200):end]
    if wave_block.size > 2:
        path = QPainterPath()
        step = (right - left) / (wave_block.size - 1)
        for k, v in enumerate(wave_block):
            pt = QPointF(left + k * step, 120 + float(v) * 60)
            if k == 0:
                path.moveTo(pt)
            else:
                path.lineTo(pt)
        p.setPen(QPen(QColor(255, 255, 255, 170), 2))
        p.setBrush(Qt.BrushStyle.NoBrush)
        p.drawPath(path)

    caption(p, "Спектр мелодії (FFT)", t)
    p.end()
    return qimage_to_array(img)


def frame_countdown(i: int, samples: np.ndarray) -> np.ndarray:
    t = i / FPS
    img, p = canvas()
    hue = (t / DURATION * 300 + 200) % 360
    bg = QLinearGradient(0, 0, W, H)
    bg.setColorAt(0, QColor.fromHsv(int(hue), 160, 90))
    bg.setColorAt(1, QColor.fromHsv(int(hue + 60) % 360, 200, 35))
    p.fillRect(img.rect(), QBrush(bg))

    c = QPointF(W / 2, H / 2 + 10)
    beat = t % 1.0
    for k in range(3):
        r = 120 + (beat + k / 3) % 1.0 * 260
        alpha = int(90 * (1 - (beat + k / 3) % 1.0))
        p.setPen(QPen(QColor(255, 255, 255, alpha), 2))
        p.setBrush(Qt.BrushStyle.NoBrush)
        p.drawEllipse(c, r, r)

    ring = QRectF(c.x() - 150, c.y() - 150, 300, 300)
    p.setPen(QPen(QColor(255, 255, 255, 50), 14))
    p.drawEllipse(ring)
    pen = QPen(QColor("#ffffff"), 14)
    pen.setCapStyle(Qt.PenCapStyle.RoundCap)
    p.setPen(pen)
    p.drawArc(ring, 90 * 16, -int(360 * 16 * (1 - t / DURATION)))

    left = max(0, math.ceil(DURATION - t))
    p.setFont(font(150, True))
    p.setPen(QColor("#ffffff"))
    p.drawText(ring, Qt.AlignmentFlag.AlignCenter, str(left))
    caption(p, "Зворотний відлік", t)
    p.end()
    return qimage_to_array(img)


def write_wav(path: Path, samples: np.ndarray) -> None:
    pcm = (samples * 32767).astype("<i2")
    with wave.open(str(path), "wb") as wf:
        wf.setnchannels(1)
        wf.setsampwidth(2)
        wf.setframerate(RATE)
        wf.writeframes(pcm.tobytes())


def encode(path: Path, audio_codec: str, video_codec: str | None = None, frames=None,
           title: str = "Demo", audio_rate: int = RATE, video_bitrate: int | None = None) -> None:
    samples = melody()
    with av.open(str(path), "w") as container:
        container.metadata["title"] = title
        container.metadata["artist"] = "Lab2 Sample Generator"

        vstream = None
        if video_codec:
            vstream = container.add_stream(video_codec, rate=FPS)
            vstream.width, vstream.height = W, H
            vstream.pix_fmt = "yuv420p"
            if video_bitrate:
                vstream.bit_rate = video_bitrate

        astream = container.add_stream(audio_codec, rate=audio_rate)
        astream.layout = "mono"

        chunk = 1024
        pts = 0
        for start in range(0, len(samples), chunk):
            block = samples[start:start + chunk]
            frame = av.AudioFrame.from_ndarray(block[None, :], format="flt", layout="mono")
            frame.sample_rate = RATE
            frame.pts = pts
            frame.time_base = Fraction(1, RATE)
            pts += len(block)
            for packet in astream.encode(frame):
                container.mux(packet)
        for packet in astream.encode(None):
            container.mux(packet)

        if vstream is not None:
            for i in range(int(DURATION * FPS)):
                frame = av.VideoFrame.from_ndarray(frames(i, samples), format="rgb24")
                for packet in vstream.encode(frame):
                    container.mux(packet)
            for packet in vstream.encode(None):
                container.mux(packet)
    print("створено", path.name)


def main() -> None:
    app = QGuiApplication.instance() or QGuiApplication(sys.argv)
    write_wav(OUT / "melody.wav", melody())
    print("створено melody.wav")
    encode(OUT / "melody.mp3", "libmp3lame", title="Melody (MP3)", audio_rate=44_100)
    encode(OUT / "melody.ogg", "libopus", title="Melody (Ogg Opus)")
    encode(OUT / "melody.flac", "flac", title="Melody (FLAC)")
    encode(OUT / "demo.mp4", "aac", "libx264", frame_solar, title="Сонячна система (MP4)")
    encode(OUT / "demo.webm", "libopus", "libvpx-vp9", frame_spectrum, title="Спектр мелодії (WebM)",
           video_bitrate=1_500_000)
    encode(OUT / "demo.mkv", "flac", "mpeg4", frame_countdown, title="Зворотний відлік (MKV)",
           video_bitrate=4_000_000)
    del app


if __name__ == "__main__":
    main()
