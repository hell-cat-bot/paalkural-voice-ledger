"""ASR adapters: local faster-whisper for the disclosed demo, Prisma when keyed."""
from __future__ import annotations

import json
import os
import secrets
import threading
import time
import urllib.error
import urllib.request
import uuid
from pathlib import Path

import numpy as np

from .audio import load_wav, wav_bytes
from .env import gnani_live

ROOT = Path(__file__).resolve().parents[1]
PROMPT = "சொசைட்டி நம்பர். லிட்டர். ஃபேட். ஷிஃப்ட்."
_DLL_HANDLES: list = []


def _squash(text: str) -> str:
    return "".join(ch for ch in text.lower() if ch.isalnum())


PROMPT_SQUASH = _squash(PROMPT)


def _enable_cuda_dlls() -> None:
    """Put the pip-installed CUDA 12 wheels on the DLL search path."""
    try:
        import nvidia

        base = Path(list(nvidia.__path__)[0])
    except Exception:
        return
    for sub in ("cublas", "cudnn", "cuda_runtime"):
        bin_dir = base / sub / "bin"
        if not bin_dir.is_dir():
            continue
        try:
            _DLL_HANDLES.append(os.add_dll_directory(str(bin_dir)))
        except (AttributeError, OSError):
            pass
        os.environ["PATH"] = str(bin_dir) + os.pathsep + os.environ.get("PATH", "")


class LocalASR:
    def __init__(self, model_size: str | None = None) -> None:
        self.model_size = model_size or os.environ.get("DEMO_ASR_MODEL", "medium")
        self.beam_size = int(os.environ.get("DEMO_ASR_BEAM", "5"))
        pref = os.environ.get("DEMO_ASR_DEVICE", "auto").strip().lower()
        if pref == "auto":
            try:
                import ctranslate2

                pref = "cuda" if ctranslate2.get_cuda_device_count() > 0 else "cpu"
            except Exception:
                pref = "cpu"
        self.device = pref
        self.compute_type = os.environ.get("DEMO_ASR_COMPUTE") or ("float16" if self.device == "cuda" else "int8")
        self._model = None
        self._lock = threading.Lock()
        self._init_lock = threading.Lock()

    @property
    def model(self):
        if self._model is None:
            with self._init_lock:
                if self._model is None:
                    from faster_whisper import WhisperModel

                    if self.device == "cuda":
                        _enable_cuda_dlls()
                    self._model = WhisperModel(self.model_size, device=self.device, compute_type=self.compute_type)
        return self._model

    @property
    def label(self) -> str:
        return f"faster-whisper {self.model_size} · {self.compute_type} · {self.device.upper()}"

    def _run(self, audio, language: str, prompt: str | None):
        segments, info = self.model.transcribe(
            audio,
            language=language,
            beam_size=self.beam_size,
            temperature=[0.0, 0.2, 0.4, 0.6, 0.8, 1.0],
            condition_on_previous_text=False,
            vad_filter=False,
            without_timestamps=True,
            initial_prompt=prompt,
        )
        segs = list(segments)
        text = " ".join(s.text.strip() for s in segs).strip()
        return text, segs, info

    def transcribe_wav(self, path: str, language: str = "ta") -> dict:
        t0 = time.perf_counter()
        audio, _ = load_wav(path)
        prompt_retry = False
        with self._lock:
            text, segs, info = self._run(audio, language, PROMPT)
            # On some inputs the decoder copies the prompt verbatim; that is a
            # known failure with high logprob, so the only safe response is a
            # second decode without any prompt.
            if text and _squash(text) in PROMPT_SQUASH:
                prompt_retry = True
                retry_text, retry_segs, retry_info = self._run(audio, language, None)
                if retry_text:
                    text, segs, info = retry_text, retry_segs, retry_info
        logprob = float(np.mean([s.avg_logprob for s in segs])) if segs else -3.0
        return {
            "text": text,
            "language": info.language,
            "language_probability": round(float(info.language_probability), 3),
            "avg_logprob": round(logprob, 3),
            "duration_s": round(float(info.duration), 2),
            "latency_ms": round((time.perf_counter() - t0) * 1000),
            "provider": self.label,
            "model": f"faster-whisper/{self.model_size}",
            "prompt_retry": prompt_retry,
        }

    def transcribe_array(self, audio: np.ndarray, language: str = "ta") -> dict:
        tmp = ROOT / "data" / "tmp"
        tmp.mkdir(parents=True, exist_ok=True)
        path = tmp / f"{uuid.uuid4().hex}.wav"
        with open(path, "wb") as fh:
            fh.write(wav_bytes(audio))
        try:
            return self.transcribe_wav(str(path), language)
        finally:
            try:
                path.unlink(missing_ok=True)
            except OSError:
                pass


def _multipart(fields: dict[str, str], file_field: str, filename: str, file_bytes: bytes) -> tuple[bytes, str]:
    boundary = "----paalkural" + secrets.token_hex(12)
    parts: list[bytes] = []
    for key, value in fields.items():
        parts.append(
            f"--{boundary}\r\nContent-Disposition: form-data; name=\"{key}\"\r\n\r\n{value}\r\n".encode()
        )
    parts.append(
        (
            f"--{boundary}\r\nContent-Disposition: form-data; name=\"{file_field}\"; "
            f"filename=\"{filename}\"\r\nContent-Type: audio/wav\r\n\r\n"
        ).encode()
    )
    parts.append(file_bytes)
    parts.append(f"\r\n--{boundary}--\r\n".encode())
    return b"".join(parts), f"multipart/form-data; boundary={boundary}"


class GnaniASR:
    URL = "https://api.vachana.ai/stt/v3"

    def __init__(self, api_key: str) -> None:
        self.api_key = api_key

    @property
    def label(self) -> str:
        return "Gnani Prisma v3.0 · live API"

    def transcribe_array(self, audio: np.ndarray, language: str = "ta") -> dict:
        t0 = time.perf_counter()
        body, ctype = _multipart(
            {
                "language_code": "ta-IN",
                "model": os.environ.get("GNANI_STT_MODEL", "prisma-v3.0"),
                "format": os.environ.get("GNANI_STT_FORMAT", "codemix"),
            },
            "audio_file",
            "pour.wav",
            wav_bytes(audio),
        )
        req = urllib.request.Request(
            self.URL,
            data=body,
            headers={
                "Content-Type": ctype,
                "Accept": "application/json",
                "X-API-Key-ID": self.api_key,
                "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                "(KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36",
            },
            method="POST",
        )
        for attempt in range(3):
            try:
                with urllib.request.urlopen(req, timeout=25) as resp:
                    payload = json.loads(resp.read().decode("utf-8"))
                break
            except urllib.error.HTTPError as exc:
                if exc.code in (429, 500, 502, 503, 504) and attempt < 2:
                    time.sleep(1.5 * (attempt + 1))
                    continue
                raise
            except (urllib.error.URLError, TimeoutError):
                if attempt < 2:
                    time.sleep(1.5 * (attempt + 1))
                    continue
                raise
        text = payload.get("transcript", "")
        return {
            "text": text,
            "language": payload.get("detected_language_code", "ta-IN"),
            "language_probability": 1.0,
            "avg_logprob": 0.0,
            "duration_s": None,
            "latency_ms": round((time.perf_counter() - t0) * 1000),
            "provider": f"Gnani Prisma · {payload.get('model', 'prisma-v3.0')}",
            "model": payload.get("model", "prisma-v3.0"),
            "request_id": payload.get("request_id"),
        }


_ASR = None
_ASR_LOCK = threading.Lock()


def get_asr():
    global _ASR
    with _ASR_LOCK:
        if _ASR is None:
            key = os.environ.get("GNANI_API_KEY", "").strip()
            _ASR = GnaniASR(key) if gnani_live() else LocalASR()
        return _ASR


def local_label() -> str:
    """Cheap description of the local engine without loading the model."""
    size = os.environ.get("DEMO_ASR_MODEL", "medium")
    pref = os.environ.get("DEMO_ASR_DEVICE", "auto").strip().lower()
    if pref == "auto":
        try:
            import ctranslate2

            pref = "cuda" if ctranslate2.get_cuda_device_count() > 0 else "cpu"
        except Exception:
            pref = "cpu"
    compute = os.environ.get("DEMO_ASR_COMPUTE") or ("float16" if pref == "cuda" else "int8")
    return f"faster-whisper {size} · {compute} · {pref.upper()}"


def provider_info() -> dict:
    key = bool(os.environ.get("GNANI_API_KEY", "").strip())
    live = gnani_live()
    if live:
        disclosure = (
            "Live Gnani Prisma STT and Timbre TTS are enabled with a participant-supplied key. "
            "The frozen 192-run benchmark and its claim remain local faster-whisper runs; "
            "the live provider check is reported separately."
        )
    elif key:
        disclosure = (
            "A Gnani key is loaded, but DEMO_MODE=1 keeps this run on local faster-whisper "
            "and edge-tts. The adapters were validated separately with the key."
        )
    else:
        disclosure = (
            "No Gnani key is loaded; this run uses local faster-whisper and edge-tts. "
            "The frozen benchmark is a local run."
        )
    return {
        "demo_mode": not live,
        "gnani_live": live,
        "gnani_key_present": key,
        "stt": "Gnani Prisma v3.0 · live" if live else f"{local_label()} (local demo)",
        "tts": "Gnani Timbre v2.5 · live" if live else "edge-tts ta-IN-Pallavi (local demo)",
        "routing": {
            "stt": "POST https://api.vachana.ai/stt/v3 · X-API-Key-ID",
            "tts": "POST https://api.vachana.ai/api/v1/tts/inference · X-API-Key-ID",
        },
        "disclosure": disclosure,
    }
