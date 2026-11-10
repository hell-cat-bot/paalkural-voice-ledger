"""Probe one Whisper model size on representative clips (downloads on first use)."""
from __future__ import annotations

import statistics
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from server.asr import LocalASR, _enable_cuda_dlls  # noqa: E402
from server.audio import load_wav, process_chain, simulate_line  # noqa: E402
from server.benchmark import CLIPS, SLOT_KEYS  # noqa: E402
from server.parser import parse_transcript  # noqa: E402

CLIP_IDS = ["b02", "b04", "b06", "b07", "b09", "b11", "b16", "b23"]
CASES = [("clean", None, "raw"), ("5 dB", 5.0, "raw"), ("5 dB", 5.0, "band+gate")]
PROMPT = "சொசைட்டி நம்பர். லிட்டர். ஃபேட். ஷிஃப்ட்."


def main() -> int:
    model_name = sys.argv[1] if len(sys.argv) > 1 else "large-v3-turbo"
    asr = LocalASR(model_size=model_name)
    if asr.device == "cuda":
        _enable_cuda_dlls()
    print(f"loading {model_name} on {asr.device} ...", flush=True)
    t0 = time.perf_counter()
    asr.model  # noqa: B018 - force load/download
    print(f"loaded in {time.perf_counter() - t0:.1f}s", flush=True)
    rows = []
    for cond, snr, chain in CASES:
        hits = 0
        for clip_id in CLIP_IDS:
            clip = CLIPS[clip_id]
            clean, _ = load_wav(str(ROOT / "fixtures" / clip["audio"]))
            line = clean if snr is None else simulate_line(clean, clip.get("scene") or "society_hall", snr, seed=17)
            audio = line if chain == "raw" else process_chain(line, chain)[0]
            t1 = time.perf_counter()
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
            ms = (time.perf_counter() - t1) * 1000
            parsed = parse_transcript(text)
            pred = {k: v["value"] for k, v in parsed["slots"].items()}
            gt_keys = [k for k in SLOT_KEYS if clip.get(k) is not None]
            exact = all(pred.get(k) == clip.get(k) for k in gt_keys) and not (set(pred) - set(gt_keys))
            hits += int(exact)
            rows.append({"model": model_name, "condition": cond, "chain": chain, "clip": clip_id, "exact": exact, "pred": pred, "ms": round(ms), "text": text})
            print(f"{cond:5s} {chain:9s} {clip_id} {'EXACT' if exact else 'MISS '} {ms:6.0f}ms {pred}", flush=True)
        print(f"  -> {model_name} {cond} {chain}: {hits}/{len(CLIP_IDS)}", flush=True)
    sub = rows
    print(f"SUMMARY {model_name}: exact {sum(r['exact'] for r in sub)}/{len(sub)} p50 {statistics.median(r['ms'] for r in sub):.0f}ms", flush=True)
    import json
    out = ROOT / "data" / f"model_probe_{model_name}.json"
    out.write_text(json.dumps(rows, ensure_ascii=False, indent=1), encoding="utf-8")
    print(f"wrote {out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
