"""Provider check: the same frozen matrix, decoded by live Gnani Prisma.

This does not replace the local benchmark. It answers one question: does the
shipped gate still work when the ASR is the sponsor's model? Every call is
made with the participant-supplied key, which is never printed.
"""
from __future__ import annotations

import argparse
import json
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from server.asr import GnaniASR  # noqa: E402
from server.benchmark import (  # noqa: E402
    ARMS,
    CONDITIONS,
    MANIFEST,
    claim_for,
    environment,
    policy_for,
    run_one,
    summarize,
)


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--clips", default="", help="comma-separated clip ids (default: all 24)")
    ap.add_argument("--conditions", default="", help="comma-separated conditions: clean,15,5,0")
    ap.add_argument("--out", default="data/benchmark-gnani.json")
    args = ap.parse_args()

    from server.env import load_env

    load_env()
    import os

    key = os.environ.get("GNANI_API_KEY", "").strip()
    if not key:
        print("no key loaded; cannot run the provider check")
        return 2
    asr = GnaniASR(key)
    print(f"provider: {asr.label}")

    clips = MANIFEST["benchmark"]
    if args.clips:
        wanted = {c.strip() for c in args.clips.split(",") if c.strip()}
        clips = [c for c in clips if c["id"] in wanted]
    conditions = CONDITIONS
    if args.conditions:
        wanted = {c.strip().lower() for c in args.conditions.split(",") if c.strip()}
        conditions = [
            (name, snr)
            for name, snr in CONDITIONS
            if name.lower().replace(" db", "") in wanted or (snr is None and "clean" in wanted)
        ]

    total = len(clips) * len(conditions) * len(ARMS)
    runs: list[dict] = []
    errors: list[dict] = []
    consecutive = 0
    t0 = time.perf_counter()
    for clip in clips:
        for cond, snr in conditions:
            for arm in ARMS:
                try:
                    row = run_one(clip, snr, arm, asr)
                    runs.append(row)
                    consecutive = 0
                except Exception as exc:  # keep a partial record instead of losing the run
                    errors.append({
                        "clip": clip["id"], "condition": cond, "arm": arm,
                        "error": f"{type(exc).__name__}: {str(exc)[:200]}",
                    })
                    consecutive += 1
                    print(f"ERROR {clip['id']} {cond} {arm}: {type(exc).__name__}")
                    if consecutive >= 5:
                        print("five consecutive provider errors; stopping so the partial stays usable")
                        break
                done = len(runs) + len(errors)
                if done % 12 == 0:
                    print(f"  {done}/{total} rows, {round(time.perf_counter() - t0, 1)}s", flush=True)
                time.sleep(0.12)
            if consecutive >= 5:
                break
        if consecutive >= 5:
            break

    full = len(runs) == len(MANIFEST["benchmark"]) * len(CONDITIONS) * len(ARMS) and not errors
    summary = summarize(runs, len({r["clip"] for r in runs}), conditions) if runs else {"clips": 0, "cells": []}
    policy = policy_for(runs, conditions) if runs else {"cells": []}
    payload = {
        "generated_at": datetime.now(timezone.utc).astimezone().isoformat(timespec="seconds"),
        "status": "complete" if full else "partial",
        "provider": {
            "name": asr.label,
            "model": "prisma-v3.0",
            "endpoint": "POST https://api.vachana.ai/stt/v3",
            "key": "participant-supplied, not logged",
            "tts": "Gnani Timbre v2.5 (live, smoke-tested separately)",
        },
        "synthetic": True,
        "n_per_cell": len({r["clip"] for r in runs}) if runs else 0,
        "cells": len(runs),
        "errors": errors,
        "elapsed_s": round(time.perf_counter() - t0, 1),
        "environment": environment(asr),
        "summary": summary,
        "policy": policy,
        "claim": (
            "Live Gnani Prisma v3.0 decoded the same frozen matrix. "
            + claim_for(summary, policy)
            + " Slot exactness is the comparable metric here; WER against the Tamil scripts is not comparable to Tanglish transcripts and is not used in this claim."
            if full and summary.get("cells") and policy.get("cells")
            else "Provider check incomplete; no claim is made from it."
        ),
        "caveats": [
            "Live provider check only; the shipped 192-run benchmark and its claim remain the local faster-whisper run.",
            "24 synthetic TTS clips per condition; no field or real-farmer audio.",
            "Prisma returns Tanglish; the slot compiler is applied unchanged, so exactness measures parse+validation, not raw verbatim ASR.",
            "WER against the Tamil reference is script-mismatched and is not a headline metric for this arm.",
            "Calls are metered and were made with a participant-supplied key; no key material is stored in this file.",
        ],
        "runs": runs,
    }
    env = payload["environment"]
    env["asr"]["model"] = asr.label
    env["tts"] = "Gnani Timbre v2.5 (live, not used for scoring)"
    out = ROOT / args.out
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(payload, ensure_ascii=False, indent=1), encoding="utf-8")
    print(f"wrote {out} | status={payload['status']} | rows={len(runs)} errors={len(errors)} | {payload['elapsed_s']}s")
    if payload["status"] == "complete":
        print("claim:", payload["claim"])
    return 0 if payload["status"] == "complete" else 1


if __name__ == "__main__":
    raise SystemExit(main())
