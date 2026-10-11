from __future__ import annotations

import wave
from fractions import Fraction
from pathlib import Path

import av
import numpy as np

OUT = Path(__file__).resolve().parent
RATE = 48_000
DURATION = 20.0
FPS = 25
SIZE = (640, 360)

NOTES = [261.63, 329.63, 392.00, 523.25, 392.00, 329.63]


def melody(duration: float = DURATION) -> np.ndarray:
    t = np.arange(int(RATE * duration)) / RATE
    note_len = 0.4
    idx = (t // note_len).astype(int) % len(NOTES)
    freq = np.array(NOTES)[idx]
    local = t % note_len
    envelope = np.minimum(1.0, local * 40) * np.exp(-local * 4)
    signal = 0.6 * np.sin(2 * np.pi * freq * t) + 0.2 * np.sin(4 * np.pi * freq * t)
    return (signal * envelope * 0.8).astype(np.float32)


def frame_image(i: int) -> np.ndarray:
    w, h = SIZE
    t = i / FPS
    x = np.linspace(0, 1, w)[None, :]
    y = np.linspace(0, 1, h)[:, None]
    img = np.empty((h, w, 3), dtype=np.uint8)
    img[..., 0] = (127 + 100 * np.sin(2 * np.pi * (x + t / 5))).astype(np.uint8)
    img[..., 1] = (80 + 60 * np.sin(2 * np.pi * (y + t / 7))).astype(np.uint8)
    img[..., 2] = (150 + 90 * np.cos(2 * np.pi * (x * y + t / 3))).clip(0, 255).astype(np.uint8)

    cx = int(w / 2 + (w / 2 - 50) * np.sin(2 * np.pi * t / 4))
    cy = int(h / 2 + (h / 2 - 60) * np.cos(2 * np.pi * t / 3))
    yy, xx = np.ogrid[:h, :w]
    img[(xx - cx) ** 2 + (yy - cy) ** 2 < 30 ** 2] = (255, 255, 255)

    progress = int(w * t / DURATION)
    img[h - 12:h - 4, :progress] = (255, 210, 0)
    for s in range(int(t) + 1):
        x0 = 10 + (s % 20) * 30
        img[10:30, x0:x0 + 20] = (20, 20, 20)
    return img


def write_wav(path: Path, samples: np.ndarray) -> None:
    pcm = (samples * 32767).astype("<i2")
    with wave.open(str(path), "wb") as wf:
        wf.setnchannels(1)
        wf.setsampwidth(2)
        wf.setframerate(RATE)
        wf.writeframes(pcm.tobytes())


def encode(path: Path, audio_codec: str, video_codec: str | None = None,
           title: str = "Demo", audio_rate: int = RATE) -> None:
    samples = melody()
    with av.open(str(path), "w") as container:
        container.metadata["title"] = title
        container.metadata["artist"] = "Lab2 Sample Generator"

        vstream = None
        if video_codec:
            vstream = container.add_stream(video_codec, rate=FPS)
            vstream.width, vstream.height = SIZE
            vstream.pix_fmt = "yuv420p"

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
                frame = av.VideoFrame.from_ndarray(frame_image(i), format="rgb24")
                for packet in vstream.encode(frame):
                    container.mux(packet)
            for packet in vstream.encode(None):
                container.mux(packet)
    print("створено", path.name)


def main() -> None:
    write_wav(OUT / "melody.wav", melody())
    print("створено melody.wav")
    encode(OUT / "melody.mp3", "libmp3lame", title="Melody (MP3)", audio_rate=44_100)
    encode(OUT / "melody.ogg", "libopus", title="Melody (Ogg Opus)")
    encode(OUT / "melody.flac", "flac", title="Melody (FLAC)")
    encode(OUT / "demo.mp4", "aac", "libx264", title="Demo video (MP4)")
    encode(OUT / "demo.webm", "libopus", "libvpx-vp9", title="Demo video (WebM)")
    encode(OUT / "demo.mkv", "flac", "mpeg4", title="Demo video (MKV)")


if __name__ == "__main__":
    main()
