"""Telephone-line simulation, synthetic noise, and the mitigation chain.

SNR is defined as active-speech RMS / noise RMS, measured per clip. The clean
speech is never used by the ASR; it is only used to set noise gain and to score.
"""
from __future__ import annotations

import io
import wave
from dataclasses import dataclass
from typing import Literal

import numpy as np
import soxr

try:
    import audioop  # Python 3.12 only; used for the 8-bit mu-law roundtrip
except DeprecationWarning:  # pragma: no cover
    audioop = None

SR = 16000
LINE_SR = 8000
Scene = Literal["society_hall", "fan_cans", "generator"]


def load_wav(path: str) -> tuple[np.ndarray, int]:
    with open(path, "rb") as fh:
        return decode_wav_bytes(fh.read())


def decode_wav_bytes(data: bytes) -> tuple[np.ndarray, int]:
    with wave.open(io.BytesIO(data), "rb") as w:
        sr = w.getframerate()
        channels = w.getnchannels()
        width = w.getsampwidth()
        raw = w.readframes(w.getnframes())
    if width != 2:
        raise ValueError(f"expected 16-bit PCM, got {width * 8}-bit")
    audio = np.frombuffer(raw, dtype="<i2").astype(np.float32) / 32768.0
    if channels > 1:
        audio = audio.reshape(-1, channels).mean(axis=1)
    if sr != SR:
        audio = resample(audio, sr, SR)
    return np.clip(audio, -1.0, 1.0), SR


def wav_bytes(audio: np.ndarray, sr: int = SR) -> bytes:
    pcm = (np.clip(audio, -1.0, 1.0) * 32767).astype("<i2")
    buf = io.BytesIO()
    with wave.open(buf, "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(sr)
        w.writeframes(pcm.tobytes())
    return buf.getvalue()


def save_wav(path: str, audio: np.ndarray, sr: int = SR) -> None:
    with open(path, "wb") as fh:
        fh.write(wav_bytes(audio, sr))


def resample(audio: np.ndarray, src_sr: int, dst_sr: int) -> np.ndarray:
    if src_sr == dst_sr:
        return audio.astype(np.float32, copy=False)
    return soxr.resample(audio, src_sr, dst_sr).astype(np.float32)


def mulaw_roundtrip(audio: np.ndarray, sr: int = SR) -> np.ndarray:
    """Push audio through a narrowband 8 kHz mu-law channel and back."""
    if audioop is None:
        raise RuntimeError("audioop unavailable")
    pcm8 = resample(audio, sr, LINE_SR)
    pcm16 = (np.clip(pcm8, -1.0, 1.0) * 32767).astype("<i2")
    encoded = audioop.lin2ulaw(pcm16.tobytes(), 2)
    decoded = audioop.ulaw2lin(encoded, 2)
    pcm8 = np.frombuffer(decoded, dtype="<i2").astype(np.float32) / 32768.0
    return resample(pcm8, LINE_SR, sr)


def active_rms(audio: np.ndarray, frame: int = 320, hop: int = 160) -> float:
    """RMS over frames that plausibly contain speech, not silence."""
    if len(audio) < frame:
        return float(np.sqrt(np.mean(audio**2) + 1e-12))
    rms = np.array(
        [np.sqrt(np.mean(audio[i : i + frame] ** 2) + 1e-12) for i in range(0, len(audio) - frame, hop)]
    )
    floor = float(np.percentile(rms, 10))
    threshold = max(floor * 2.5, 0.008)
    mask = np.zeros(len(audio), dtype=bool)
    for idx in np.where(rms > threshold)[0]:
        mask[idx * hop : idx * hop + frame] = True
    active = audio[mask]
    if active.size < frame:
        return float(np.sqrt(np.mean(audio**2) + 1e-12))
    return float(np.sqrt(np.mean(active**2) + 1e-12))


def _pink(n: int, rng: np.random.Generator) -> np.ndarray:
    white = rng.standard_normal(n)
    spec = np.fft.rfft(white)
    freqs = np.fft.rfftfreq(n, 1 / SR)
    spec[1:] /= np.sqrt(freqs[1:])
    spec[0] = 0
    out = np.fft.irfft(spec, n)
    return out / (np.max(np.abs(out)) + 1e-9)


def _brown(n: int, rng: np.random.Generator) -> np.ndarray:
    out = np.cumsum(rng.standard_normal(n))
    out -= np.linspace(out[0], out[-1], n)
    return out / (np.max(np.abs(out)) + 1e-9)


def _clanks(n: int, rng: np.random.Generator, density: float = 0.55) -> np.ndarray:
    out = np.zeros(n, dtype=np.float32)
    t = np.arange(int(SR * 0.18)) / SR
    for _ in range(max(2, int(n / SR * density))):
        start = int(rng.uniform(0, max(1, n - len(t))))
        freq = rng.uniform(900, 3600)
        decay = rng.uniform(18, 42)
        burst = np.sin(2 * np.pi * freq * t) * np.exp(-t * decay) * rng.uniform(0.25, 0.8)
        out[start : start + len(t)] += burst.astype(np.float32)
    return out


def make_noise(scene: str, n: int, seed: int) -> np.ndarray:
    rng = np.random.default_rng(seed)
    t = np.arange(n) / SR
    if scene == "society_hall":
        voices = np.zeros(n, dtype=np.float32)
        for _ in range(7):
            base = _pink(n, rng).astype(np.float32)
            am = 0.55 + 0.45 * np.sin(2 * np.pi * rng.uniform(0.4, 2.8) * t + rng.uniform(0, 6.28))
            voices += base * am.astype(np.float32) * rng.uniform(0.2, 0.7)
        mix = voices / 4 + _clanks(n, rng) * 0.8
    elif scene == "fan_cans":
        hum = sum(0.16 * np.sin(2 * np.pi * f * t + p) for f, p in [(100, 0), (200, 1.1), (300, 2.2)])
        am = 0.75 + 0.25 * np.sin(2 * np.pi * 11.5 * t)
        mix = _pink(n, rng) * am.astype(np.float32) + hum.astype(np.float32) * 0.4 + _clanks(n, rng, 0.35)
    elif scene == "generator":
        hum = sum(a * np.sin(2 * np.pi * 50 * k * t + k) for k, a in [(1, 0.35), (2, 0.2), (3, 0.12), (5, 0.06)])
        mix = hum.astype(np.float32) + _brown(n, rng).astype(np.float32) * 0.9 + _pink(n, rng).astype(np.float32) * 0.25
    else:
        raise ValueError(f"unknown scene: {scene}")
    mix = mix.astype(np.float32)
    return mix / (np.sqrt(np.mean(mix**2)) + 1e-9)


def simulate_line(speech: np.ndarray, scene: str | None, snr_db: float | None, seed: int) -> np.ndarray:
    """Add synthetic scene noise at a measured SNR, then pass the 8 kHz channel."""
    if scene is None or snr_db is None:
        return speech.copy()
    noise = make_noise(scene, len(speech), seed)
    speech_rms = active_rms(speech)
    noise_rms = speech_rms / (10 ** (snr_db / 20))
    mixed = speech + noise * noise_rms
    peak = float(np.max(np.abs(mixed)) + 1e-9)
    if peak > 0.98:
        mixed = mixed * (0.98 / peak)
    return mulaw_roundtrip(mixed.astype(np.float32))


def bandlimit(audio: np.ndarray, low: float = 260.0, high: float = 3500.0) -> np.ndarray:
    spec = np.fft.rfft(audio)
    freqs = np.fft.rfftfreq(len(audio), 1 / SR)
    lo = 1 / (1 + np.exp(-(freqs - low) / 35.0))
    hi = 1 / (1 + np.exp((freqs - high) / 55.0))
    return np.fft.irfft(spec * lo * hi, n=len(audio)).astype(np.float32)


def vad_trim(audio: np.ndarray, frame: int = 320, hop: int = 160) -> tuple[np.ndarray, dict]:
    if len(audio) < frame:
        return audio, {"trimmed_ms": 0, "frames_active": 0}
    rms = np.array(
        [np.sqrt(np.mean(audio[i : i + frame] ** 2) + 1e-12) for i in range(0, len(audio) - frame, hop)]
    )
    floor = float(np.percentile(rms, 12))
    threshold = max(floor * 2.2, 0.006)
    active = np.where(rms > threshold)[0]
    if len(active) == 0:
        return audio, {"trimmed_ms": 0, "frames_active": 0}
    pad = 12
    start = max(0, (active[0] - pad) * hop)
    end = min(len(audio), (active[-1] + pad) * hop + frame)
    if end - start < SR * 0.35:
        return audio, {"trimmed_ms": 0, "frames_active": int(len(active))}
    return audio[start:end], {
        "trimmed_ms": round((len(audio) - (end - start)) / SR * 1000),
        "frames_active": int(len(active)),
    }


def spectral_gate(audio: np.ndarray, strength: float = 1.35, floor: float = 0.07) -> np.ndarray:
    """Wiener-style noise suppression with a minimum-statistics floor."""
    frame, hop = 400, 160
    if len(audio) < frame * 2:
        return audio
    window = np.hanning(frame).astype(np.float32)
    n_frames = 1 + (len(audio) - frame) // hop
    idx = np.arange(frame)[None, :] + hop * np.arange(n_frames)[:, None]
    frames = audio[idx] * window
    spec = np.fft.rfft(frames, axis=1)
    mag = np.abs(spec)
    noise = np.percentile(mag, 18, axis=0)
    power = mag**2
    gain = np.maximum(power - strength * noise**2, 0) / (power + 1e-12)
    gain = np.clip(gain, floor, 1.0)
    # smooth gain across time and frequency to avoid musical noise
    gain = (gain + np.roll(gain, 1, axis=0) + np.roll(gain, -1, axis=0)) / 3.0
    gain = (gain + np.roll(gain, 1, axis=1) + np.roll(gain, -1, axis=1)) / 3.0
    cleaned = np.fft.irfft(spec * gain, n=frame, axis=1) * window
    out = np.zeros(len(audio), dtype=np.float32)
    norm = np.zeros(len(audio), dtype=np.float32)
    for i in range(n_frames):
        out[i * hop : i * hop + frame] += cleaned[i].astype(np.float32)
        norm[i * hop : i * hop + frame] += window**2
    return out / np.maximum(norm, 1e-8)


def waveform(audio: np.ndarray, buckets: int = 220) -> list[float]:
    if len(audio) == 0:
        return [0.0] * buckets
    chunk = max(1, len(audio) // buckets)
    peaks = [float(np.max(np.abs(audio[i : i + chunk]))) for i in range(0, len(audio), chunk)]
    if len(peaks) > buckets:
        peaks = peaks[:buckets]
    peaks += [0.0] * (buckets - len(peaks))
    return [round(min(1.0, p), 4) for p in peaks]


@dataclass
class Mitigation:
    raw: np.ndarray
    processed: np.ndarray
    stages: dict
    waveform_raw: list[float]
    waveform_processed: list[float]


def mitigate(line_audio: np.ndarray) -> Mitigation:
    import time

    stages: dict[str, float | int] = {}
    t0 = time.perf_counter()
    banded = bandlimit(line_audio)
    stages["bandlimit_ms"] = round((time.perf_counter() - t0) * 1000, 1)
    t1 = time.perf_counter()
    gated = spectral_gate(banded)
    stages["denoise_ms"] = round((time.perf_counter() - t1) * 1000, 1)
    t2 = time.perf_counter()
    trimmed, vad = vad_trim(gated)
    stages["vad_ms"] = round((time.perf_counter() - t2) * 1000, 1)
    stages.update(vad)
    return Mitigation(
        raw=line_audio,
        processed=trimmed,
        stages=stages,
        waveform_raw=waveform(line_audio),
        waveform_processed=waveform(trimmed),
    )


def process_chain(audio: np.ndarray, chain: str = "band+gate") -> tuple[np.ndarray, dict]:
    """Named processing variants used by the console and the evidence run."""
    import time

    if chain == "raw":
        return audio, {"chain": "raw", "stages": {}}
    if chain == "band":
        t0 = time.perf_counter()
        out = bandlimit(audio)
        return out, {"chain": "bandlimit 260-3500 Hz", "stages": {"dsp_ms": round((time.perf_counter() - t0) * 1000, 1)}}
    if chain == "band+gate":
        t0 = time.perf_counter()
        out = spectral_gate(bandlimit(audio))
        return out, {
            "chain": "bandlimit 260-3500 Hz + spectral gate",
            "stages": {"dsp_ms": round((time.perf_counter() - t0) * 1000, 1)},
        }
    if chain == "full":
        mit = mitigate(audio)
        return mit.processed, {"chain": "bandlimit + spectral gate + VAD", "stages": mit.stages}
    raise ValueError(f"unknown chain: {chain}")
