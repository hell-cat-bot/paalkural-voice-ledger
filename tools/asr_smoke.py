import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from server.asr import LocalASR
from server.audio import load_wav, mitigate, simulate_line
from server.parser import parse_transcript, readback_text, validate

ROOT = Path(__file__).resolve().parents[1]
manifest = json.loads((ROOT / "fixtures" / "manifest.json").read_text(encoding="utf-8"))
members = {m["id"]: m["name"] for m in manifest["members"]}
asr = LocalASR()

for cid, member, litres, fat, shift, scene, text in [
    ("b01", 101, 2.0, 4.5, "morning", "society_hall", ""),
    ("b09", 124, 3.5, 4.8, "morning", "society_hall", ""),
    ("d03", 124, 1.5, None, "morning", "society_hall", ""),
]:
    clean, _ = load_wav(str(ROOT / "fixtures" / "audio" / f"{cid}.wav"))
    variants = [("clean", clean)]
    for snr in (5, 0):
        line = simulate_line(clean, scene, snr, seed=17)
        variants.append((f"{snr}dB-raw", line))
        variants.append((f"{snr}dB-mit", mitigate(line).processed))
    for label, audio in variants:
        res = asr.transcribe_array(audio, language="ta")
        parsed = parse_transcript(res["text"])
        val = validate(parsed, members)
        rb = readback_text(parsed["slots"], None)
        print(f"\n[{cid} {label}] {res['latency_ms']}ms logp={res['avg_logprob']}")
        print("TEXT:", res["text"])
        print("SLOTS:", {k: v["value"] for k, v in parsed["slots"].items()}, "MISSING:", parsed["missing"], "OK:", val["ok"])
        if val["flags"]:
            print("FLAGS:", [f["code"] for f in val["flags"]])
        print("READBACK:", rb[0])
