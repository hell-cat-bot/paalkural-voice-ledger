"""TTS adapters: Timbre when keyed, edge-tts for the disclosed local demo."""
from __future__ import annotations

import asyncio
import hashlib
import json
import os
import urllib.request
from pathlib import Path

import edge_tts

from .env import gnani_live

ROOT = Path(__file__).resolve().parents[1]
CACHE = ROOT / "data" / "tts"
CACHE.mkdir(parents=True, exist_ok=True)
VOICE = os.environ.get("DEMO_TTS_VOICE", "ta-IN-PallaviNeural")


def _key(text: str, live: bool) -> str:
    """Provider is part of the key so a cached edge clip is never served as Timbre."""
    mode = "gnani" if live else "edge"
    return hashlib.sha256((text + "|" + VOICE + "|" + mode).encode("utf-8")).hexdigest()[:24]


async def _edge(text: str, out: Path) -> None:
    await edge_tts.Communicate(text, VOICE, rate="-6%").save(str(out))


def _timbre(text: str) -> bytes:
    key = os.environ["GNANI_API_KEY"].strip()
    payload = json.dumps(
        {
            "text": text,
            "voice": os.environ.get("GNANI_TTS_VOICE", "Nalini"),
            "model": os.environ.get("GNANI_TTS_MODEL", "timbre-v2.5"),
            "language": "ta-IN",
            "speed": 1.0,
            "audio_config": {"sample_rate": 16000, "container": "mp3"},
        }
    ).encode("utf-8")
    req = urllib.request.Request(
        "https://api.vachana.ai/api/v1/tts/inference",
        data=payload,
        headers={
            "Content-Type": "application/json",
            "Accept": "audio/mpeg, application/json",
            "X-API-Key-ID": key,
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
            "(KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36",
        },
        method="POST",
    )
    with urllib.request.urlopen(req, timeout=25) as resp:
        return resp.read()


def synthesize(text: str) -> dict:
    """Return a cache URL for spoken text. Falls back to local edge-tts."""
    live = gnani_live()
    digest = _key(text, live)
    ext = "mp3"
    path = CACHE / f"{digest}.{ext}"
    provider = "Gnani Timbre v2.5 · live" if live else "edge-tts · ta-IN-Pallavi (local demo)"
    if path.exists():
        return {"url": f"/api/tts-audio/{path.name}", "provider": provider, "cached": True}
    try:
        if live:
            path.write_bytes(_timbre(text))
        else:
            asyncio.run(_edge(text, path))
    except Exception:
        # A missing network must never take the call console down, and a
        # fallback must not be labelled as the provider that failed.
        provider = "edge-tts · fallback (Timbre unavailable)"
        try:
            asyncio.run(_edge(text, path))
        except Exception:
            return {"url": None, "provider": "browser speechSynthesis fallback", "cached": False}
    return {"url": f"/api/tts-audio/{path.name}", "provider": provider, "cached": False}


def prewarm(texts: list[str]) -> None:
    for text in texts:
        try:
            synthesize(text)
        except Exception:
            pass
