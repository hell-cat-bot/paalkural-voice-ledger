"""Freeze the synthetic voice fixtures used by the product and the evidence lab.

Every clip is synthetic (edge-tts), never a real call. Ground-truth slots are
authored by hand so scoring is exact. Output: fixtures/audio/*.wav (16 kHz mono)
and fixtures/manifest.json.
"""
from __future__ import annotations

import asyncio
import json
import wave
from pathlib import Path

import av
import edge_tts
import numpy as np

ROOT = Path(__file__).resolve().parents[1]
AUDIO = ROOT / "fixtures" / "audio"
MANIFEST = ROOT / "fixtures" / "manifest.json"
VOICE = "ta-IN-ValluvarNeural"
RATE = "-18%"
SR = 16000

MEMBERS = {
    101: "Selvi M",
    108: "Ravi K",
    113: "Lakshmi P",
    119: "Murugan S",
    124: "Anitha R",
    127: "Kumar V",
    132: "Meena T",
    137: "Arumugam P",
    143: "Kavitha S",
    146: "Senthil N",
    151: "Vasanthi K",
    156: "Rajesh M",
}

# (id, member, litres, fat, shift, scene, text)
BENCH = [
    ("b01", 101, 2.0, 4.5, "morning", "society_hall",
     "சொசைட்டி நம்பர், ஒன் ஜீரோ ஒன். ரெண்டு லிட்டர் பால். ஃபேட் நாலு பாயிண்ட், ஐந்து. காலை ஷிஃப்ட்."),
    ("b02", 101, 3.0, 5.1, "evening", "fan_cans",
     "நம்பர், ஒன் ஜீரோ ஒன். மூணு லிட்டர். ஃபேட் ஐந்து பாயிண்ட், ஒன்று. சாயங்காலம் ஷிஃப்ட்."),
    ("b03", 108, 1.5, 3.8, "morning", "society_hall",
     "சொசைட்டி நம்பர், ஒன் ஜீரோ எட்டு. ஒன்றரை லிட்டர் பால். ஃபேட் மூணு பாயிண்ட், எட்டு. காலை."),
    ("b04", 108, 4.0, 6.0, "evening", "generator",
     "நம்பர் 108. நாலு லிட்டர். ஃபேட் ஆறு. ஈவ்னிங் ஷிஃப்ட்."),
    ("b05", 113, 2.5, 4.7, "morning", "fan_cans",
     "நம்பர், ஒன் ஒன் த்ரீ. ரெண்டரை லிட்டர். ஃபேட் நாலு பாயிண்ட், ஏழு. காலை."),
    ("b06", 113, 3.5, 5.5, "evening", "society_hall",
     "நம்பர், ஒன் ஒன் த்ரீ. மூன்றரை லிட்டர் பால். ஃபேட் ஐந்து பாயிண்ட், ஐந்து. சாயங்காலம்."),
    ("b07", 119, 0.5, 6.8, "morning", "generator",
     "நம்பர், ஒன் ஒன் னைன். அரை லிட்டர். ஃபேட் ஆறு பாயிண்ட், எட்டு. மார்னிங்."),
    ("b08", 119, 5.0, 3.5, "evening", "fan_cans",
     "நம்பர், ஒன் ஒன் னைன். ஐந்து லிட்டர் பால். ஃபேட் மூணு பாயிண்ட், ஐந்து. ஈவ்னிங் ஷிஃப்ட்."),
    ("b09", 124, 3.5, 4.8, "morning", "society_hall",
     "நம்பர், ஒன் டூ ஃபோர். மூணு லிட்டர். இல்ல இல்ல, மூன்றரை லிட்டர். ஃபேட் நாலு பாயிண்ட், எட்டு. காலை."),
    ("b10", 124, 2.0, 5.1, "evening", "generator",
     "நம்பர் 124. ரெண்டு லிட்டர். ஃபேட் ஐந்து பாயிண்ட், ஒன்று. சாயங்காலம்."),
    ("b11", 127, 4.5, 3.9, "morning", "fan_cans",
     "நம்பர், ஒன் டூ செவன். நாலரை லிட்டர். ஃபேட் மூணு பாயிண்ட், ஒன்பது. மார்னிங்."),
    ("b12", 127, 3.0, 4.4, "evening", "society_hall",
     "நம்பர், ஒன் டூ செவன். மூணு லிட்டர் பால். ஃபேட் நாலு பாயிண்ட், நாலு. ஈவ்னிங் ஷிஃப்ட்."),
    ("b13", 132, 1.5, 5.8, "morning", "generator",
     "நம்பர், ஒன் த்ரீ டூ. ஒன்றரை லிட்டர். ஃபேட் ஐந்து பாயிண்ட், எட்டு. காலை."),
    ("b14", 132, 2.0, 6.2, "evening", "fan_cans",
     "நம்பர், ஒன் த்ரீ டூ. ரெண்டு லிட்டர். ஃபேட் ஆறு பாயிண்ட், டூ. சாயங்காலம்."),
    ("b15", 137, 3.5, 4.9, "morning", "society_hall",
     "நம்பர், ஒன் த்ரீ செவன். மூன்றரை லிட்டர். ஃபேட் நாலு பாயிண்ட், ஒன்பது. மார்னிங்."),
    ("b16", 137, 5.5, 3.7, "evening", "generator",
     "நம்பர் 137. ஐந்தரை லிட்டர் பால். ஃபேட் மூணு பாயிண்ட், ஏழு. ஈவ்னிங் ஷிஃப்ட்."),
    ("b17", 143, 2.0, 5.3, "morning", "fan_cans",
     "நம்பர், ஒன் ஃபோர் த்ரீ. ரெண்டு லிட்டர். ஃபேட் ஐந்து பாயிண்ட், மூணு. காலை."),
    ("b18", 143, 4.0, 4.1, "evening", "society_hall",
     "நம்பர், ஒன் ஃபோர் த்ரீ. நாலு லிட்டர். ஃபேட் நாலு பாயிண்ட், ஒன்று. சாயங்காலம்."),
    ("b19", 146, 1.5, 6.5, "morning", "generator",
     "நம்பர், ஒன் ஃபோர் சிக்ஸ். ஒன்றரை லிட்டர் பால். ஃபேட் ஆறு பாயிண்ட், ஐந்து. மார்னிங்."),
    ("b20", 146, 3.0, 3.4, "evening", "fan_cans",
     "நம்பர், ஒன் ஃபோர் சிக்ஸ். மூணு லிட்டர். ஃபேட் மூணு பாயிண்ட், நாலு. ஈவ்னிங் ஷிஃப்ட்."),
    ("b21", 151, 2.5, 5.6, "morning", "society_hall",
     "நம்பர், ஒன் ஃபைவ் ஒன். ரெண்டரை லிட்டர். ஃபேட் ஐந்து பாயிண்ட், ஆறு. காலை."),
    ("b22", 151, 4.5, 4.2, "evening", "generator",
     "நம்பர் 151. நாலரை லிட்டர். ஃபேட் நாலு பாயிண்ட், டூ. சாயங்காலம்."),
    ("b23", 156, 1.0, 6.9, "morning", "fan_cans",
     "நம்பர், ஒன் ஃபைவ் சிக்ஸ். ஒரு லிட்டர் பால். ஃபேட் ஆறு பாயிண்ட், ஒன்பது. மார்னிங்."),
    ("b24", 156, 2.5, 3.3, "evening", "society_hall",
     "நம்பர், ஒன் ஃபைவ் சிக்ஸ். ரெண்டு லிட்டர். இல்ல, ரெண்டரை லிட்டர். ஃபேட் மூணு பாயிண்ட், மூணு. ஈவ்னிங் ஷிஃப்ட்."),
]

DEMO = [
    ("d01", 124, 2.0, 4.5, "morning",
     "சொசைட்டி நம்பர், ஒன் டூ ஃபோர். ரெண்டு லிட்டர். ஃபேட் நாலு பாயிண்ட், ஐந்து. காலை ஷிஃப்ட்."),
    ("d02", 124, 3.5, 4.8, "morning",
     "நம்பர், ஒன் டூ ஃபோர். மூணு லிட்டர். இல்ல இல்ல, மூன்றரை லிட்டர். ஃபேட் நாலு பாயிண்ட், எட்டு. காலை."),
    ("d03", 124, 1.5, None, "morning",
     "நம்பர், ஒன் டூ ஃபோர். ஒன்றரை லிட்டர். காலை ஷிஃப்ட்."),
    ("d04", 119, 4.0, 6.1, "evening",
     "நம்பர், ஒன் ஒன் னைன். நாலு லிட்டர். ஃபேட் ஆறு பாயிண்ட், ஒன்று. சாயங்காலம் ஷிஃப்ட்."),
]


def decode_mp3(path: Path) -> np.ndarray:
    frames: list[np.ndarray] = []
    with av.open(str(path)) as container:
        stream = next(s for s in container.streams if s.type == "audio")
        resampler = av.AudioResampler(format="s16", layout="mono", rate=SR)
        for frame in container.decode(stream):
            for out in resampler.resample(frame):
                frames.append(out.to_ndarray().reshape(-1))
        for out in resampler.resample(None):
            frames.append(out.to_ndarray().reshape(-1))
    return np.concatenate(frames).astype(np.int16)


def write_wav(path: Path, audio: np.ndarray) -> None:
    with wave.open(str(path), "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(SR)
        w.writeframes(audio.tobytes())


async def synth(text: str, out_mp3: Path) -> None:
    await edge_tts.Communicate(text, VOICE, rate=RATE).save(str(out_mp3))


async def main() -> None:
    AUDIO.mkdir(parents=True, exist_ok=True)
    tmp = ROOT / ".tmp"
    tmp.mkdir(exist_ok=True)
    sem = asyncio.Semaphore(2)

    async def one(clip_id: str, text: str) -> Path:
        mp3 = tmp / f"{clip_id}.mp3"
        wav = AUDIO / f"{clip_id}.wav"
        async with sem:
            for attempt in range(4):
                try:
                    if mp3.exists() and mp3.stat().st_size < 1000:
                        mp3.unlink()
                    if not mp3.exists():
                        await synth(text, mp3)
                    write_wav(wav, decode_mp3(mp3))
                    return wav
                except Exception as exc:
                    if attempt == 3:
                        raise RuntimeError(f"{clip_id}: {exc}") from exc
                    await asyncio.sleep(2 + attempt * 2)
        return wav

    jobs = [(c[0], c[-1]) for c in BENCH] + [(c[0], c[-1]) for c in DEMO]
    await asyncio.gather(*(one(cid, text) for cid, text in jobs))

    manifest = {
        "voice": VOICE,
        "rate": RATE,
        "sample_rate": SR,
        "source": "synthetic edge-tts; hand-authored Tamil with English loanwords and digit sequences",
        "synthetic": True,
        "benchmark": [
            {
                "id": cid, "audio": f"audio/{cid}.wav", "member_id": member,
                "member_name": MEMBERS[member], "litres": litres, "fat": fat,
                "shift": shift, "scene": scene, "text": text,
            }
            for cid, member, litres, fat, shift, scene, text in BENCH
        ],
        "demo": [
            {
                "id": cid, "audio": f"audio/{cid}.wav", "member_id": member,
                "member_name": MEMBERS[member], "litres": litres, "fat": fat,
                "shift": shift, "text": text,
            }
            for cid, member, litres, fat, shift, text in DEMO
        ],
        "members": [{"id": k, "name": v} for k, v in MEMBERS.items()],
    }
    MANIFEST.write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"FIXTURES_READY {len(jobs)} clips -> {MANIFEST}")


if __name__ == "__main__":
    asyncio.run(main())
