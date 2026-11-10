"""Grid over front-end variants at 5 dB and 0 dB, scored end to end."""
from __future__ import annotations

import json
import statistics
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from server.audio import bandlimit, load_wav, simulate_line, spectral_gate  # noqa: E402
from server.benchmark import CLIPS, SLOT_KEYS  # noqa: E402
from server.parser import parse_transcript  # noqa: E402

CLIP_IDS = ["b01", "b02", "b04", "b06", "b07", "b08", "b09", "b11", "b13", "b16", "b20", "b23"]
CONDS = [("5 dB", 5.0), ("0 dB", 0.0)]
VARIANTS = {
    "raw": None,
    "260-3500_g1.35_f0.07": ("band_gate", 260, 3500, 1.35, 0.07),
    "120-3800_g1.35_f0.07": ("band_gate", 120, 3800, 1.35, 0.07),
    "120-3800_g1.00_f0.15": ("band_gate", 120, 3800, 1.0, 0.15),
    "120-3800_bandonly": ("band", 120, 3800, 0, 0),
    "gateonly_g1.35_f0.07": ("gate", 0, 0, 1.35, 0.07),
}


def build(line, spec):
    if spec is None:
        return line
    kind, low, high, strength, floor = spec
    if kind == "band":
        return bandlimit(line, low, high)
    if kind == "gate":
        return spectral_gate(line, strength, floor)
    return spectral_gate(bandlimit(line, low, high), strength, floor)


def main() -> int:
    from server.asr import LocalASR

    asr = LocalASR()
    print(asr.label, flush=True)
    rows = []
    for name, spec in VARIANTS.items():
        for cond, snr in CONDS:
            hits = 0
            times: list[float] = []
            for clip_id in CLIP_IDS:
                clip = CLIPS[clip_id]
                clean, _ = load_wav(str(ROOT / "fixtures" / clip["audio"]))
                line = simulate_line(clean, clip.get("scene") or "society_hall", snr, seed=17)
                audio = build(line, spec)
                res = asr.transcribe_array(audio, language="ta")
                times.append(res["latency_ms"])
                parsed = parse_transcript(res["text"])
                pred = {k: v["value"] for k, v in parsed["slots"].items()}
                gt_keys = [k for k in SLOT_KEYS if clip.get(k) is not None]
                exact = all(pred.get(k) == clip.get(k) for k in gt_keys) and not (set(pred) - set(gt_keys))
                hits += int(exact)
                rows.append({"variant": name, "condition": cond, "clip": clip_id, "exact": exact, "pred": pred, "ms": res["latency_ms"], "text": res["text"]})
            print(f"{name:24s} {cond}: {hits:2d}/{len(CLIP_IDS)} exact, p50 {statistics.median(times):.0f}ms", flush=True)
    (ROOT / "data" / "chain_grid.json").write_text(json.dumps(rows, ensure_ascii=False, indent=1), encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
