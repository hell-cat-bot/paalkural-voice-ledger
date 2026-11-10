"""Compare Whisper decoder configurations on the frozen fixture clips.

Scores decoded transcripts through the same slot compiler used by the line
console, so the winner is chosen by end-to-end exact match, not transcript
fluency. Writes data/decoder_sweep.json for the audit trail.
"""
from __future__ import annotations

import json
import statistics
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from server.audio import load_wav, process_chain, simulate_line  # noqa: E402
from server.benchmark import CLIPS, SLOT_KEYS, word_wer  # noqa: E402
from server.parser import parse_transcript  # noqa: E402

CLIP_IDS = ["b02", "b04", "b06", "b07", "b09", "b11", "b16", "b23"]
PROMPT = "சொசைட்டி நம்பர். லிட்டர். ஃபேட். ஷிஃப்ட்."
FALLBACK = [0.0, 0.2, 0.4, 0.6, 0.8, 1.0]
CONFIGS = {
    "prompt_beam5_t0": dict(initial_prompt=PROMPT, beam_size=5, temperature=0.0),
    "prompt_beam5_fallback": dict(initial_prompt=PROMPT, beam_size=5, temperature=FALLBACK),
    "prompt_beam5_rep105": dict(
        initial_prompt=PROMPT, beam_size=5, temperature=0.0,
        repetition_penalty=1.05, no_repeat_ngram_size=4,
    ),
    "prompt_greedy_fallback": dict(initial_prompt=PROMPT, beam_size=1, temperature=FALLBACK),
}
CASES = [("clean", None, "raw"), ("5 dB", 5.0, "mitigated")]


def decode(asr, audio, cfg):
    t0 = time.perf_counter()
    kwargs = dict(
        language="ta",
        temperature=0.0,
        condition_on_previous_text=False,
        vad_filter=False,
        without_timestamps=True,
    )
    kwargs.update(cfg)
    with asr._lock:
        segments, info = asr.model.transcribe(audio, **kwargs)
        segs = list(segments)
    return " ".join(s.text.strip() for s in segs).strip(), round((time.perf_counter() - t0) * 1000)


def main() -> int:
    from server.asr import LocalASR

    asr = LocalASR()
    print(asr.label, flush=True)
    rows = []
    for cfg_name, cfg in CONFIGS.items():
        for clip_id in CLIP_IDS:
            clip = CLIPS[clip_id]
            clean, _ = load_wav(str(ROOT / "fixtures" / clip["audio"]))
            for cond, snr, arm in CASES:
                line = clean if snr is None else simulate_line(clean, clip.get("scene") or "society_hall", snr, seed=17)
                audio = line if arm == "raw" else process_chain(line, "band+gate")[0]
                text, ms = decode(asr, audio, cfg)
                parsed = parse_transcript(text)
                pred = {k: v["value"] for k, v in parsed["slots"].items()}
                gt = {k: clip[k] for k in SLOT_KEYS if clip.get(k) is not None}
                gt_keys = [k for k in SLOT_KEYS if gt.get(k) is not None]
                exact = all(pred.get(k) == gt.get(k) for k in gt_keys) and not (set(pred) - set(gt_keys))
                row = {
                    "config": cfg_name,
                    "clip": clip_id,
                    "condition": cond,
                    "exact": exact,
                    "pred": pred,
                    "gt": gt,
                    "wer": round(word_wer(clip["text"], text), 4),
                    "ms": ms,
                    "text": text,
                }
                rows.append(row)
                mark = "EXACT" if exact else "MISS "
                print(f"{cfg_name:18s} {clip_id} {cond:5s} {mark} {ms:5d}ms {pred}", flush=True)
        done = [r for r in rows if r["config"] == cfg_name]
        n = len(done)
        print(
            f"  -> {cfg_name}: exact {sum(r['exact'] for r in done)}/{n}, "
            f"WER {statistics.mean(r['wer'] for r in done) * 100:.1f}%, "
            f"p50 {statistics.median(r['ms'] for r in done):.0f}ms",
            flush=True,
        )
    out = ROOT / "data" / "decoder_sweep.json"
    out.write_text(json.dumps({"engine": asr.label, "clips": CLIP_IDS, "rows": rows}, ensure_ascii=False, indent=1), encoding="utf-8")
    print(f"wrote {out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
