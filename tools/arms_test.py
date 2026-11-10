import json
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from server.asr import LocalASR
from server.audio import bandlimit, load_wav, simulate_line, spectral_gate, vad_trim
from server.parser import parse_transcript, validate

ROOT = Path(__file__).resolve().parents[1]
manifest = json.loads((ROOT / "fixtures" / "manifest.json").read_text(encoding="utf-8"))
members = {m["id"]: m["name"] for m in manifest["members"]}
clips = {c["id"]: c for c in manifest["benchmark"] + manifest["demo"]}
asr = LocalASR()

IDS = ["b01", "b09", "b24", "d03"]

ARMS = {
    "raw": lambda a: a,
    "band": lambda a: bandlimit(a),
    "band+gate": lambda a: spectral_gate(bandlimit(a)),
    "band+vad": lambda a: vad_trim(bandlimit(a))[0],
    "full": lambda a: vad_trim(spectral_gate(bandlimit(a)))[0],
}


def score(cid, slots):
    gt = clips[cid]
    keys = ["member_id", "litres", "fat", "shift"]
    hit = sum(1 for k in keys if slots.get(k) == gt[k])
    return f"{hit}/4"


t0 = time.perf_counter()
rows = []
for cid in IDS:
    clean, _ = load_wav(str(ROOT / "fixtures" / "audio" / f"{cid}.wav"))
    conditions = [("clean", clean)]
    for snr in (5, 0):
        scene = clips[cid].get("scene")
        if scene:
            conditions.append((f"{snr}dB", simulate_line(clean, scene, snr, seed=17)))
    for cond, audio in conditions:
        for name, fn in ARMS.items():
            res = asr.transcribe_array(fn(audio), language="ta")
            parsed = parse_transcript(res["text"])
            slots = {k: v["value"] for k, v in parsed["slots"].items()}
            val = validate(parsed, members)
            rows.append(
                {
                    "clip": cid,
                    "cond": cond,
                    "arm": name,
                    "score": score(cid, slots),
                    "valid": val["ok"],
                    "lat": res["latency_ms"],
                    "slots": slots,
                    "text": res["text"][:220],
                }
            )
            print(
                f"{cid:4} {cond:6} {name:9} {rows[-1]['score']:4} valid={str(val['ok']):5} "
                f"{res['latency_ms']:5}ms slots={slots}",
                flush=True,
            )
            print(f"     {res['text'][:220]}", flush=True)

elapsed = time.perf_counter() - t0
print(f"\nTOTAL {elapsed:.1f}s")
(ROOT / "data" / "arms_test.json").write_text(json.dumps(rows, ensure_ascii=False, indent=1), encoding="utf-8")

print("\nSUMMARY (slot hits / 4)")
for cond in ["clean", "5dB", "0dB"]:
    for name in ARMS:
        subset = [r for r in rows if r["cond"] == cond and r["arm"] == name]
        hits = sum(int(r["score"].split("/")[0]) for r in subset)
        valid = sum(1 for r in subset if r["valid"])
        print(f"{cond:6} {name:9} hits={hits:2}/{len(subset)*4} valid={valid}/{len(subset)} lat_avg={sum(r['lat'] for r in subset)//len(subset)}ms")
