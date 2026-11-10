"""Audit frozen fixture audio against ground truth on the clean condition."""
from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from server.asr import LocalASR  # noqa: E402
from server.benchmark import CLIPS, SLOT_KEYS  # noqa: E402
from server.parser import parse_transcript  # noqa: E402


def main() -> int:
    asr = LocalASR()
    print(asr.label, flush=True)
    rows = []
    hits = 0
    for clip_id in sorted(CLIPS, key=lambda c: (c[0], c)):
        clip = CLIPS[clip_id]
        res = asr.transcribe_wav(str(ROOT / "fixtures" / clip["audio"]))
        text = res["text"]
        parsed = parse_transcript(text)
        pred = {k: v["value"] for k, v in parsed["slots"].items()}
        gt_keys = [k for k in SLOT_KEYS if clip.get(k) is not None]
        ok = all(pred.get(k) == clip.get(k) for k in gt_keys) and not (set(pred) - set(gt_keys))
        hits += int(ok)
        rows.append({"clip": clip_id, "ok": ok, "pred": pred, "gt": {k: clip.get(k) for k in SLOT_KEYS}, "text": text, "decoded": text})
        print(f"{clip_id} {'OK  ' if ok else 'MISS'} {pred} gt={{'member_id': {clip.get('member_id')}, 'litres': {clip.get('litres')}, 'fat': {clip.get('fat')}, 'shift': {clip.get('shift')}}}", flush=True)
        if not ok:
            print("   heard:", text, flush=True)
    print(f"clean exact {hits}/{len(rows)}")
    (ROOT / "data" / "fixture_audit.json").write_text(json.dumps(rows, ensure_ascii=False, indent=1), encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
