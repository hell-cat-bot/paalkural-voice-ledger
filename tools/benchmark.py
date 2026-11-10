"""Run the PaalKural evidence benchmark and write data/benchmark.json.

    python tools/benchmark.py                 # 24 clips x 4 conditions x 2 arms
    python tools/benchmark.py --limit 3       # smoke run
    python tools/benchmark.py --conditions "clean,5" --arms mitigated
"""
from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from server.asr import LocalASR
from server.benchmark import CONDITIONS, MANIFEST, run_full

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "data" / "benchmark.json"


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--limit", type=int, default=0, help="use only the first N clips")
    parser.add_argument("--ids", default="", help="comma-separated clip ids")
    parser.add_argument("--conditions", default="", help="clean,15,5,0")
    parser.add_argument("--arms", default="", help="raw,mitigated")
    parser.add_argument("--out", type=Path, default=OUT)
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    clips = MANIFEST["benchmark"]
    if args.ids:
        wanted = {x.strip() for x in args.ids.split(",") if x.strip()}
        clips = [c for c in clips if c["id"] in wanted]
    if args.limit:
        clips = clips[: args.limit]
    conditions = CONDITIONS
    if args.conditions:
        wanted = {x.strip().lower() for x in args.conditions.split(",")}
        conditions = [c for c in CONDITIONS if c[0].lower().replace(" db", "") in wanted or c[0].lower() in wanted]
    arms = ("raw", "mitigated")
    if args.arms:
        arms = tuple(x.strip() for x in args.arms.split(",") if x.strip())

    # This tool produces the frozen local benchmark. Pin the local engine so a
    # loaded Gnani key cannot silently turn it into a provider run.
    asr = LocalASR()
    print(f"engine: {getattr(asr, 'label', 'local ASR')}", flush=True)
    print(f"clips={len(clips)} conditions={[c[0] for c in conditions]} arms={list(arms)}", flush=True)
    t0 = time.perf_counter()
    last = {"t": t0, "done": 0}

    def progress(done: int, total: int, row: dict) -> None:
        now = time.perf_counter()
        if done == total or done % 8 == 0:
            rate = (now - last["t"]) / max(1, done - last["done"])
            eta = rate * (total - done)
            mark = "exact" if row["all_exact"] else ("wrong+pass" if row["plausible_wrong"] else "miss")
            print(
                f"[{done:3d}/{total}] {row['clip']} {row['condition']:>5s} {row['arm']:<9s} "
                f"{mark:<10s} {row['asr_ms'] / 1000:5.1f}s  eta {eta / 60:4.1f} min",
                flush=True,
            )
            last.update(t=now, done=done)

    payload = run_full(asr, progress=progress, clips=clips, conditions=conditions, arms=arms)
    args.out.parent.mkdir(parents=True, exist_ok=True)
    tmp = args.out.with_suffix(".tmp")
    tmp.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    tmp.replace(args.out)
    print(f"\nwrote {args.out} ({payload['cells']} runs, {payload['elapsed_s']}s)", flush=True)
    print(payload["claim"], flush=True)
    for cell in payload["summary"]["cells"]:
        print(
            f"  {cell['condition']:>5s} {cell['arm']:<9s} exact {cell['exact']:2d}/{cell['n']} "
            f"({cell['exact_pct']:5.1f}%, CI {cell['exact_ci95'][0]:.0f}-{cell['exact_ci95'][1]:.0f}) "
            f"wer {cell['wer_pct']:5.1f}% gate {cell['validation_pct']:5.1f}% "
            f"wrong-pass {cell['plausible_wrong']}",
            flush=True,
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
