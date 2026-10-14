from __future__ import annotations

import numpy as np

FFT_SIZE = 2048
MIN_FREQ = 40.0
MAX_FREQ = 16_000.0
FLOOR_DB = -65.0


def band_edges(bands: int, rate: int) -> np.ndarray:
    top = min(MAX_FREQ, rate / 2)
    return np.geomspace(MIN_FREQ, top, bands + 1)


def band_levels(samples: np.ndarray, rate: int, bands: int = 32) -> np.ndarray:
    if samples.size == 0:
        return np.zeros(bands)
    block = samples[-FFT_SIZE:]
    if block.size < FFT_SIZE:
        block = np.pad(block, (FFT_SIZE - block.size, 0))
    window = np.hanning(FFT_SIZE)
    spectrum = np.abs(np.fft.rfft(block * window)) / (window.sum() / 2)
    freqs = np.fft.rfftfreq(FFT_SIZE, 1 / rate)
    edges = band_edges(bands, rate)
    levels = np.zeros(bands)
    for i in range(bands):
        mask = (freqs >= edges[i]) & (freqs < edges[i + 1])
        if mask.any():
            peak = spectrum[mask].max()
        else:
            peak = spectrum[np.argmin(np.abs(freqs - (edges[i] + edges[i + 1]) / 2))]
        db = 20 * np.log10(max(peak, 1e-9))
        levels[i] = np.clip((db - FLOOR_DB) / -FLOOR_DB, 0.0, 1.0)
    return levels


def to_mono_float(data: bytes, sample_format: str, channels: int) -> np.ndarray:
    dtype, scale = {
        "float": (np.float32, 1.0),
        "int16": (np.int16, 32768.0),
        "int32": (np.int32, 2147483648.0),
        "uint8": (np.uint8, 128.0),
    }[sample_format]
    samples = np.frombuffer(data, dtype=dtype).astype(np.float32)
    if sample_format == "uint8":
        samples -= 128.0
    samples /= scale
    if channels > 1:
        usable = samples.size - samples.size % channels
        samples = samples[:usable].reshape(-1, channels).mean(axis=1)
    return samples
