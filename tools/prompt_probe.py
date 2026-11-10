"""Compare prompt strategies on all clean benchmark clips."""
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from server.asr import LocalASR  # noqa: E402
from server.audio import load_wav  # noqa: E402
from server.benchmark import MANIFEST, SLOT_KEYS  # noqa: E402
from server.parser import parse_transcript  # noqa: E402

FULL = "சொசைட்டி நம்பர். லிட்டர். ஃபேட். ஷிஃப்ட்."
SHORT = "பால் சேகரிப்பு உரையாடல்."
CONFIGS = {
    "full_prompt": dict(initial_prompt=FULL),
    "no_prompt": dict(initial_prompt=None),
    "short_prompt": dict(initial_prompt=SHORT),
    "hotwords": dict(initial_prompt=None, hotwords=["சொசைட்டி", "நம்பர்", "லிட்டர்", "ஃபேட்", "ஷிஃப்ட்"]),
}


def main() -> int:
    asr = LocalASR()
    print(asr.label, flush=True)
    clips = MANIFEST["benchmark"]
    for name, cfg in CONFIGS.items():
        hits = 0
        leaks = 0
        for clip in clips:
            clean, _ = load_wav(str(ROOT / "fixtures" / clip["audio"]))
            with asr._lock:
                segs, _ = asr.model.transcribe(
                    clean,
                    language="ta",
                    beam_size=5,
                    temperature=[0.0, 0.2, 0.4, 0.6, 0.8, 1.0],
                    condition_on_previous_text=False,
                    vad_filter=False,
                    without_timestamps=True,
                    **cfg,
                )
                text = " ".join(s.text.strip() for s in segs).strip()
            leaked = text.replace(" ", "").strip(".") == FULL.replace(" ", "").strip(".")
            leaks += int(leaked)
            parsed = parse_transcript(text)
            pred = {k: v["value"] for k, v in parsed["slots"].items()}
            gt_keys = [k for k in SLOT_KEYS if clip.get(k) is not None]
            exact = all(pred.get(k) == clip.get(k) for k in gt_keys) and not (set(pred) - set(gt_keys))
            hits += int(exact)
            if not exact:
                print(f"  {name} {clip['id']} MISS leak={leaked} {pred} | {text[:70]}", flush=True)
        print(f"== {name}: exact {hits}/24, prompt leaks {leaks}", flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
