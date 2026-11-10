"""Score a library noise reducer (noisereduce) against the current chain.

Same clips, seeds, adapter and parser as the published benchmark, so the
comparison isolates the front-end.
"""
from __future__ import annotations

import json
import statistics
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

import noisereduce as nr  # noqa: E402

from server.audio import bandlimit, load_wav, simulate_line, spectral_gate  # noqa: E402
from server.benchmark import CLIPS, SLOT_KEYS, word_wer  # noqa: E402
from server.parser import parse_transcript, validate  # noqa: E402
from server.store import MEMBERS  # noqa: E402

CLIP_IDS = [c["id"] for c in json.loads((ROOT / "fixtures" / "manifest.json").read_text(encoding="utf-8"))["benchmark"]]
CONDS = [("5 dB", 5.0), ("0 dB", 0.0)]
VARIANTS = {
    "raw": None,
    "band+gate": ("band_gate", 0.0),
    "band+nr0.7": ("band_nr", 0.7),
    "band+nr0.85": ("band_nr", 0.85),
    "nr0.85": ("nr", 0.85),
}


def build(line, spec):
    if spec is None:
        return line
    kind, prop = spec
    if kind == "band_gate":
        return spectral_gate(bandlimit(line))
    if kind == "band_nr":
        return nr.reduce_noise(y=bandlimit(line), sr=16000, stationary=False, prop_decrease=prop)
    if kind == "nr":
        return nr.reduce_noise(y=line, sr=16000, stationary=False, prop_decrease=prop)
    raise ValueError(kind)


def main() -> int:
    from server.asr import LocalASR

    asr = LocalASR()
    print(asr.label, flush=True)
    rows = []
    for name, spec in VARIANTS.items():
        for cond, snr in CONDS:
            hits = wrong = valid = 0
            times: list[float] = []
            wers: list[float] = []
            for clip_id in CLIP_IDS:
                clip = CLIPS[clip_id]
                clean, _ = load_wav(str(ROOT / "fixtures" / clip["audio"]))
                line = simulate_line(clean, clip.get("scene") or "society_hall", snr, seed=17)
                audio = build(line, spec)
                res = asr.transcribe_array(audio, language="ta")
                times.append(res["latency_ms"])
                parsed = parse_transcript(res["text"])
                val = validate(parsed, MEMBERS)
                pred = {k: v["value"] for k, v in parsed["slots"].items()}
                gt_keys = [k for k in SLOT_KEYS if clip.get(k) is not None]
                exact = all(pred.get(k) == clip.get(k) for k in gt_keys) and not (set(pred) - set(gt_keys))
                hits += int(exact)
                valid += int(val["ok"])
                wrong += int(val["ok"] and not exact)
                wers.append(word_wer(clip["text"], res["text"]))
                rows.append({
                    "variant": name, "condition": cond, "clip": clip_id,
                    "exact": exact, "valid": val["ok"], "pred": pred,
                    "ms": res["latency_ms"], "wer": round(wers[-1], 4), "text": res["text"],
                })
            print(
                f"{name:12s} {cond}: exact {hits:2d}/{len(CLIP_IDS)}  valid {valid:2d}  "
                f"wrong-pass {wrong:2d}  wer {statistics.mean(wers) * 100:5.1f}%  "
                f"p50 {statistics.median(times):.0f}ms",
                flush=True,
            )
    out = ROOT / "data" / "noisereduce_probe.json"
    out.write_text(json.dumps(rows, ensure_ascii=False, indent=1), encoding="utf-8")
    print("wrote", out, flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
