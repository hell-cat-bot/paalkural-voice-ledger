"""Live smoke test for the Gnani adapters.

Never prints the API key or request headers. Prints only transcripts,
latencies, validation outcomes and response metadata safe to share.
"""
from __future__ import annotations

import argparse
import json
import os
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from server.audio import load_wav, process_chain, simulate_line  # noqa: E402
from server.asr import GnaniASR  # noqa: E402
from server.parser import parse_transcript, validate  # noqa: E402
from server.store import MEMBERS  # noqa: E402


def _load_manifest() -> dict:
    return json.loads((ROOT / "fixtures" / "manifest.json").read_text(encoding="utf-8"))


def _clip(clip_id: str) -> dict:
    manifest = _load_manifest()
    clips = {c["id"]: c for c in manifest["benchmark"] + manifest["demo"]}
    if clip_id not in clips:
        raise SystemExit(f"unknown clip {clip_id}")
    return clips[clip_id]


def _run(asr: GnaniASR, audio, label: str, clip: dict) -> dict | None:
    try:
        res = asr.transcribe_array(audio, language="ta")
    except urllib.error.HTTPError as exc:
        body = exc.read().decode("utf-8", "replace")[:300]
        print(f"{label}: HTTP {exc.code} {exc.reason} :: {body}")
        return None
    except Exception as exc:  # network, timeout, parse
        print(f"{label}: {type(exc).__name__} :: {str(exc)[:300]}")
        return None
    parsed = parse_transcript(res["text"])
    val = validate(parsed, MEMBERS)
    slots = {k: v["value"] for k, v in parsed["slots"].items()}
    gt = {k: clip[k] for k in ("member_id", "litres", "fat", "shift") if clip.get(k) is not None}
    print(f"{label}: {res['latency_ms']} ms | {res['provider']} | {res['text']}")
    print(f"  slots={slots}")
    print(f"  gt={gt} exact={slots == gt} valid={val['ok']} missing={parsed['missing']} flags={[f['code'] for f in val['flags']]}")
    return {"res": res, "slots": slots, "gt": gt, "valid": val["ok"]}


def _tts(text: str) -> None:
    key = os.environ.get("GNANI_API_KEY", "").strip()
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
    t0 = time.perf_counter()
    try:
        with urllib.request.urlopen(req, timeout=30) as resp:
            body = resp.read()
            ctype = resp.headers.get("Content-Type", "")
            status = resp.status
    except urllib.error.HTTPError as exc:
        body = exc.read().decode("utf-8", "replace")[:300]
        print(f"tts: HTTP {exc.code} {exc.reason} :: {body}")
        return
    except Exception as exc:
        print(f"tts: {type(exc).__name__} :: {str(exc)[:300]}")
        return
    ms = round((time.perf_counter() - t0) * 1000)
    print(f"tts: {status} {ctype} {len(body)} bytes {ms} ms")
    if ctype.startswith("application/json") or body[:1] in (b"{", b"["):
        try:
            data = json.loads(body.decode("utf-8"))
            print("  json keys:", sorted(data)[:12])
            for field in ("audio", "audio_base64", "audioContent", "audio_content", "data"):
                if isinstance(data.get(field), str) and data[field]:
                    print(f"  {field}: base64-looking string, {len(data[field])} chars")
                    break
        except Exception:
            print("  json parse failed; first 120 bytes:", body[:120])
        return
    out = ROOT / "data" / "tts" / "gnani-smoke.mp3"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_bytes(body)
    print(f"  wrote {out} ({len(body)} bytes)")


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--clip", default="b12")
    ap.add_argument("--snr", type=float, default=5.0)
    ap.add_argument("--clean", action="store_true", help="use the studio clip, no line simulation")
    ap.add_argument("--tts", action="store_true", help="also test Timbre TTS")
    ap.add_argument("--text", default="சொசைட்டி நம்பர் நூற்று இருபத்தி ஏழு, மூன்று லிட்டர், ஃபேட் நாலு பாயிண்ட் நாலு, சாயங்காலம் ஷிஃப்ட். சரியா?")
    args = ap.parse_args()

    from server.env import load_env

    names = load_env()
    key = os.environ.get("GNANI_API_KEY", "").strip()
    print("env vars:", ", ".join(sorted(set(names))) or "none")
    print("key present:", bool(key), "| length:", len(key))
    if not key:
        return 2

    clip = _clip(args.clip)
    clean, _ = load_wav(str(ROOT / "fixtures" / clip["audio"]))
    if args.clean:
        line = clean.copy()
        print(f"clip {args.clip}: clean studio")
    else:
        scene = clip.get("scene") or "society_hall"
        line = simulate_line(clean, scene, args.snr, seed=17)
        print(f"clip {args.clip}: {scene} at {args.snr:g} dB, seed 17")
    mitigated, dsp = process_chain(line, os.environ.get("DEMO_CHAIN", "band+gate"))
    print("chain:", dsp["chain"])

    asr = GnaniASR(key)
    raw = _run(asr, line, "raw", clip)
    mit = _run(asr, mitigated, "mitigated", clip)
    if raw and mit:
        print("pair agrees:", raw["slots"] == mit["slots"])
    if args.tts:
        _tts(args.text)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
