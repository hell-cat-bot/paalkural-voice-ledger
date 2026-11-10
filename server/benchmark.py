"""Evidence run: 24 frozen synthetic clips x 4 line conditions x 2 arms.

One variable changes between arms: the front-end (none vs bandlimit + gate).
The ASR model, decoder settings, fixtures and noise seeds are identical.
"""
from __future__ import annotations

import json
import math
import os
import platform
import statistics
import time
from datetime import datetime, timezone
from pathlib import Path

from .audio import load_wav, process_chain, simulate_line, waveform
from .parser import parse_transcript, readback_text, validate
from .store import MEMBERS

ROOT = Path(__file__).resolve().parents[1]
MANIFEST = json.loads((ROOT / "fixtures" / "manifest.json").read_text(encoding="utf-8"))
CLIPS = {c["id"]: c for c in MANIFEST["benchmark"] + MANIFEST["demo"]}
CONDITIONS = [("clean", None), ("15 dB", 15.0), ("5 dB", 5.0), ("0 dB", 0.0)]
ARMS = ("raw", "mitigated")
CHAIN = os.environ.get("DEMO_CHAIN", "band+gate")
SLOT_KEYS = ("member_id", "litres", "fat", "shift")


def normalize_words(text: str) -> list[str]:
    keep = []
    for ch in text.lower():
        if ch.isalnum() or ch.isspace():
            keep.append(ch)
        else:
            keep.append(" ")
    return "".join(keep).split()


def word_wer(ref: str, hyp: str) -> float:
    a, b = normalize_words(ref), normalize_words(hyp)
    if not a:
        return 0.0 if not b else 1.0
    prev = list(range(len(b) + 1))
    for i, wa in enumerate(a, 1):
        cur = [i]
        for j, wb in enumerate(b, 1):
            cur.append(min(prev[j] + 1, cur[j - 1] + 1, prev[j - 1] + (wa != wb)))
        prev = cur
    return prev[-1] / len(a)


def wilson(k: int, n: int, z: float = 1.96) -> list[float]:
    if n == 0:
        return [0.0, 0.0]
    p = k / n
    denom = 1 + z * z / n
    centre = p + z * z / (2 * n)
    margin = z * math.sqrt(p * (1 - p) / n + z * z / (4 * n * n))
    return [round(max(0.0, (centre - margin) / denom) * 100, 1), round(min(1.0, (centre + margin) / denom) * 100, 1)]


def _slot_values(parsed: dict) -> dict:
    return {k: v["value"] for k, v in parsed["slots"].items()}


def _compare(pred: dict, gt: dict) -> dict:
    return {k: (k in pred and gt.get(k) is not None and pred[k] == gt[k]) for k in SLOT_KEYS if gt.get(k) is not None}


def run_one(clip: dict, snr: float | None, arm: str, asr, chain: str | None = None) -> dict:
    clean, _ = load_wav(str(ROOT / "fixtures" / clip["audio"]))
    if snr is None:
        line = clean
        condition = "clean"
    else:
        line = simulate_line(clean, clip.get("scene") or "society_hall", snr, seed=17)
        condition = f"{snr:g} dB"
    if arm == "raw":
        audio = line
        dsp = {"chain": "raw", "stages": {}}
    else:
        audio, dsp = process_chain(line, chain or CHAIN)
    t0 = time.perf_counter()
    res = asr.transcribe_array(audio, language="ta")
    wall = round((time.perf_counter() - t0) * 1000, 1)
    parsed = parse_transcript(res["text"])
    val = validate(parsed, MEMBERS)
    pred = _slot_values(parsed)
    gt = {k: clip[k] for k in SLOT_KEYS if clip.get(k) is not None}
    matches = _compare(pred, gt)
    gt_keys = [k for k in SLOT_KEYS if gt.get(k) is not None]
    all_exact = (
        bool(gt_keys)
        and all(pred.get(k) == gt.get(k) for k in gt_keys)
        and not (set(pred) - set(gt_keys))
    )
    return {
        "clip": clip["id"],
        "condition": condition,
        "scene": clip.get("scene"),
        "arm": arm,
        "chain": dsp["chain"],
        "transcript": res["text"],
        "slots": pred,
        "gt": gt,
        "matches": matches,
        "all_exact": all_exact,
        "validation_ok": val["ok"],
        "plausible_wrong": val["ok"] and not all_exact,
        "reask": not val["ok"],
        "flags": [f["code"] for f in val["flags"]],
        "wer": round(word_wer(clip["text"], res["text"]), 4),
        "asr_ms": res["latency_ms"],
        "wall_ms": wall,
        "audio_s": res.get("duration_s"),
    }


def summarize(runs: list[dict], clips_n: int, conditions=None, arms=None) -> dict:
    conditions = conditions or CONDITIONS
    arms = arms or ARMS
    table = []
    for cond, _ in conditions:
        for arm in arms:
            cell = [r for r in runs if r["condition"] == cond and r["arm"] == arm]
            exact = sum(1 for r in cell if r["all_exact"])
            valid = sum(1 for r in cell if r["validation_ok"])
            wrong = sum(1 for r in cell if r["plausible_wrong"])
            slot_hits = {k: sum(1 for r in cell if r["matches"].get(k)) for k in SLOT_KEYS}
            table.append(
                {
                    "condition": cond,
                    "arm": arm,
                    "n": len(cell),
                    "exact": exact,
                    "exact_pct": round(exact / len(cell) * 100, 1) if cell else 0.0,
                    "exact_ci95": wilson(exact, len(cell)),
                    "validation_pct": round(valid / len(cell) * 100, 1) if cell else 0.0,
                    "plausible_wrong": wrong,
                    "plausible_wrong_pct": round(wrong / len(cell) * 100, 1) if cell else 0.0,
                    "reask_pct": round(sum(1 for r in cell if r["reask"]) / len(cell) * 100, 1) if cell else 0.0,
                    "wer_pct": round(statistics.mean(r["wer"] for r in cell) * 100, 1) if cell else 0.0,
                    "asr_ms_avg": round(statistics.mean(r["asr_ms"] for r in cell)) if cell else 0,
                    "asr_ms_p50": round(statistics.median(r["asr_ms"] for r in cell)) if cell else 0,
                    "slot_pct": {k: round(v / len(cell) * 100, 1) for k, v in slot_hits.items()} if cell else {},
                }
            )
    by = {(t["condition"], t["arm"]): t for t in table}
    deltas = {
        cond: {
            "exact_delta_pp": round(by[(cond, "mitigated")]["exact_pct"] - by[(cond, "raw")]["exact_pct"], 1),
            "wer_delta_pp": round(by[(cond, "mitigated")]["wer_pct"] - by[(cond, "raw")]["wer_pct"], 1),
        }
        for cond, _ in conditions
        if (cond, "mitigated") in by and (cond, "raw") in by
    }
    return {"clips": clips_n, "cells": table, "deltas": deltas}


def policy_for(runs: list[dict], conditions=None) -> dict:
    """Score the shipped two-path gate from the raw and conditioned runs.

    No extra decodes: for every clip and condition the pair of rows already
    exists. The gate pre-fills the sheet only when both paths validate to the
    same four values, or when exactly one path validates; everything else is
    sent to readback or re-ask.
    """
    conditions = conditions or CONDITIONS
    grouped: dict[tuple[str, str], dict[str, dict]] = {}
    for r in runs:
        grouped.setdefault((r["condition"], r["clip"]), {})[r["arm"]] = r
    cells = []
    for cond, _ in conditions:
        st = {"condition": cond, "n": 0, "agree": 0, "disagree": 0, "raw_only": 0,
              "mit_only": 0, "none": 0, "accepted": 0, "exact": 0,
              "plausible_wrong": 0, "reask": 0}
        for (c, _clip), pair in grouped.items():
            if c != cond or "raw" not in pair or "mitigated" not in pair:
                continue
            raw, mit = pair["raw"], pair["mitigated"]
            st["n"] += 1
            if raw["validation_ok"] and mit["validation_ok"]:
                if raw["slots"] == mit["slots"]:
                    st["agree"] += 1
                    pick = raw
                else:
                    st["disagree"] += 1
                    pick = None
            elif raw["validation_ok"]:
                st["raw_only"] += 1
                pick = raw
            elif mit["validation_ok"]:
                st["mit_only"] += 1
                pick = mit
            else:
                st["none"] += 1
                pick = None
            if pick is None:
                st["reask"] += 1
            else:
                st["accepted"] += 1
                if pick["all_exact"]:
                    st["exact"] += 1
                else:
                    st["plausible_wrong"] += 1
        n = st["n"]
        st["exact_pct"] = round(st["exact"] / n * 100, 1) if n else 0.0
        st["exact_ci95"] = wilson(st["exact"], n)
        st["accepted_pct"] = round(st["accepted"] / n * 100, 1) if n else 0.0
        cells.append(st)
    return {
        "definition": (
            "Both raw and conditioned decodes are parsed. The sheet is pre-filled "
            "when both validate to the same four values, or when exactly one "
            "validates; otherwise the turn goes to readback or re-ask."
        ),
        "derived": True,
        "cells": cells,
    }


def environment(asr=None) -> dict:
    engine = getattr(asr, "label", None) or "faster-whisper (not loaded)"
    return {
        "asr": {
            "model": engine,
            "compute": getattr(asr, "compute_type", ""),
            "device": getattr(asr, "device", ""),
            "beam_size": int(os.environ.get("DEMO_ASR_BEAM", "5")),
            "language": "ta",
            "initial_prompt": "சொசைட்டி நம்பர். லிட்டர். ஃபேட். ஷிஃப்ட்.",
            "temperature": "0.0 with fallback through 1.0; default compression-ratio and log-prob gates",
        },
        "tts": "edge-tts ta-IN-PallaviNeural (not used for scoring)",
        "chain": CHAIN,
        "snr_definition": "active-speech RMS / noise RMS, measured per clip before the 8 kHz mu-law roundtrip",
        "fixtures": {
            "count": 24,
            "voice": MANIFEST["voice"],
            "rate": MANIFEST["rate"],
            "source": "Microsoft Edge TTS, synthetic Tamil/Tanglish scripts",
            "seeds": 17,
        },
        "machine": {
            "platform": platform.platform(),
            "processor": platform.processor() or platform.machine(),
            "python": platform.python_version(),
        },
    }


def claim_for(summary: dict, policy: dict) -> str:
    cells = {(c["condition"], c["arm"]): c for c in summary["cells"]}
    pol = {c["condition"]: c for c in policy["cells"]}
    raw5, mit5 = cells[("5 dB", "raw")], cells[("5 dB", "mitigated")]
    raw0 = cells[("0 dB", "raw")]
    rawc, mitc = cells[("clean", "raw")], cells[("clean", "mitigated")]
    p5, p0, pc = pol["5 dB"], pol["0 dB"], pol["clean"]

    def silent(n: int) -> str:
        return f"{n} silent error" + ("" if n == 1 else "s")

    return (
        "On 24 synthetic Tamil/Tanglish clips a single spectral front-end did not consistently fix noise "
        f"({CHAIN} vs none: {mit5['exact']}/{mit5['n']} vs {raw5['exact']}/{raw5['n']} exact at 5 dB, "
        f"{mitc['exact']}/{mitc['n']} vs {rawc['exact']}/{rawc['n']} clean), so the shipped line listens twice: "
        f"it pre-filled {pc['exact']}/{pc['n']} clean pours correctly with {silent(pc['plausible_wrong'])}, "
        f"{p5['exact']}/{p5['n']} at 5 dB with {silent(p5['plausible_wrong'])} (raw alone: {raw5['exact']} correct, "
        f"{silent(raw5['plausible_wrong'])}), and {p0['exact']}/{p0['n']} at 0 dB with {silent(p0['plausible_wrong'])} "
        f"(raw: {raw0['exact']}, {silent(raw0['plausible_wrong'])}); everything else went to readback or re-ask "
        "(our own synthetic clips, not field data; n=24 per cell, Wilson 95% CIs in the table)."
    )


def run_full(asr, progress=None, clips=None, conditions=None, arms=None) -> dict:
    clips = clips if clips is not None else MANIFEST["benchmark"]
    conditions = conditions or CONDITIONS
    arms = arms or ARMS
    runs = []
    total = len(clips) * len(conditions) * len(arms)
    done = 0
    t0 = time.perf_counter()
    for clip in clips:
        for cond, snr in conditions:
            for arm in arms:
                row = run_one(clip, snr, arm, asr)
                runs.append(row)
                done += 1
                if progress:
                    progress(done, total, row)
    summary = summarize(runs, len(clips), conditions, arms)
    policy = policy_for(runs, conditions)
    full = len(clips) == len(MANIFEST["benchmark"]) and len(conditions) == len(CONDITIONS) and len(arms) == len(ARMS)
    payload = {
        "generated_at": datetime.now(timezone.utc).astimezone().isoformat(timespec="seconds"),
        "status": "complete" if full else "smoke",
        "synthetic": True,
        "n_per_cell": len(clips),
        "cells": len(runs),
        "elapsed_s": round(time.perf_counter() - t0, 1),
        "environment": environment(asr),
        "summary": summary,
        "policy": policy,
        "claim": claim_for(summary, policy) if full else "Smoke run: not enough cells for the published claim.",
        "caveats": [
            f"{len(clips)} synthetic clips per condition; each cell has n={len(clips)}, not independent samples.",
            "All voices are TTS, not real farmers; no field audio was collected.",
            "The slot compiler's variant lexicon was developed while inspecting ASR output from this fixture set.",
            f"Recorded before the participant supplied a Gnani key; the run uses {getattr(asr, 'label', 'a local model')}. A separate live-provider check over the same matrix is reported in the Evidence tab.",
            "SNR is measured on active speech and set before the 8 kHz mu-law roundtrip.",
            "The two-path gate is scored from the same raw and conditioned runs; it adds no third decode.",
            "The single-pass conditioned arm is reported even though it is not the shipped path.",
        ],
        "runs": runs,
    }
    return payload


def replay(clip_id: str, snr, arm: str, asr) -> dict:
    clip = CLIPS.get(clip_id)
    if not clip:
        raise ValueError("unknown clip")
    snr_value = None if snr in (None, "", "clean") else float(snr)
    result = run_one(clip, snr_value, "mitigated" if arm == "mitigated" else "raw", asr)
    clean, _ = load_wav(str(ROOT / "fixtures" / clip["audio"]))
    line = clean if snr_value is None else simulate_line(clean, clip.get("scene") or "society_hall", snr_value, seed=17)
    processed, dsp = process_chain(line, CHAIN) if result["arm"] == "mitigated" else (line, {"chain": "raw"})
    parsed = parse_transcript(result["transcript"])
    member = MEMBERS.get(parsed["slots"].get("member_id", {}).get("value"))
    ta, en = readback_text(parsed["slots"], member)
    return {
        **result,
        "clip_text": clip["text"],
        "readback": {"ta": ta, "en": en},
        "waveform": {"raw": waveform(line), "mitigated": waveform(processed)},
        "dsp": dsp,
        "ground_truth": {k: clip[k] for k in SLOT_KEYS},
    }


def warm_captions() -> None:
    from .tts import synthesize

    for clip in MANIFEST["demo"]:
        slots = {k: {"value": clip[k]} for k in SLOT_KEYS if clip.get(k) is not None}
        ta, _ = readback_text(slots, clip.get("member_name"))
        synthesize(ta)
