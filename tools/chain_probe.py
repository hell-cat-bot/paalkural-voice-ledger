"""Compare front-end chains at low SNR on representative fixture clips."""
from __future__ import annotations

import statistics
import sys
import time
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from server.audio import load_wav, process_chain, simulate_line  # noqa: E402
from server.benchmark import CLIPS, SLOT_KEYS  # noqa: E402
from server.parser import parse_transcript  # noqa: E402

CLIP_IDS = ["b02", "b04", "b06", "b07", "b09", "b11", "b16", "b23"]
CHAINS = ["raw", "band", "band+gate", "full"]
CONDS = [("5 dB", 5.0), ("0 dB", 0.0)]
PROMPT = "சொசைட்டி நம்பர். லிட்டர். ஃபேட். ஷிஃப்ட்."


def main() -> int:
    from server.asr import LocalASR

    asr = LocalASR()
    print(asr.label, flush=True)
    rows = []
    for chain in CHAINS:
        for cond, snr in CONDS:
            hits = 0
            for clip_id in CLIP_IDS:
                clip = CLIPS[clip_id]
                clean, _ = load_wav(str(ROOT / "fixtures" / clip["audio"]))
                line = simulate_line(clean, clip.get("scene") or "society_hall", snr, seed=17)
                audio = line if chain == "raw" else process_chain(line, chain)[0]
                t0 = time.perf_counter()
                with asr._lock:
                    segs, _ = asr.model.transcribe(
                        audio,
                        language="ta",
                        beam_size=5,
                        temperature=[0.0, 0.2, 0.4, 0.6, 0.8, 1.0],
                        condition_on_previous_text=False,
                        vad_filter=False,
                        without_timestamps=True,
                        initial_prompt=PROMPT,
                    )
                    text = " ".join(s.text.strip() for s in segs).strip()
                ms = (time.perf_counter() - t0) * 1000
                parsed = parse_transcript(text)
                pred = {k: v["value"] for k, v in parsed["slots"].items()}
                gt_keys = [k for k in SLOT_KEYS if clip.get(k) is not None]
                exact = all(pred.get(k) == clip.get(k) for k in gt_keys) and not (set(pred) - set(gt_keys))
                hits += int(exact)
                rows.append({"chain": chain, "condition": cond, "clip": clip_id, "exact": exact, "pred": pred, "ms": round(ms)})
                mark = "EXACT" if exact else "MISS "
                print(f"{chain:10s} {cond:5s} {clip_id} {mark} {pred}", flush=True)
            print(f"  -> {chain} @ {cond}: {hits}/{len(CLIP_IDS)} exact", flush=True)
    for chain in CHAINS:
        sub = [r for r in rows if r["chain"] == chain]
        print(f"SUMMARY {chain:10s} exact {sum(r['exact'] for r in sub)}/{len(sub)} p50 {statistics.median(r['ms'] for r in sub):.0f}ms", flush=True)
    import json
    (ROOT / "data" / "chain_probe.json").write_text(json.dumps(rows, ensure_ascii=False, indent=1), encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
