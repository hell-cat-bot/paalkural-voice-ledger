"""Small JSON ledger with an append-only audit record per entry."""
from __future__ import annotations

import hashlib
import html
import json
import threading
import uuid
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DATA = ROOT / "data"
LEDGER = DATA / "ledger.json"
LOCK = threading.RLock()

MEMBERS = {
    101: "Selvi M",
    108: "Ravi K",
    113: "Lakshmi P",
    119: "Murugan S",
    124: "Anitha R",
    127: "Kumar V",
    132: "Meena T",
    137: "Arumugam P",
    143: "Kavitha S",
    146: "Senthil N",
    151: "Vasanthi K",
    156: "Rajesh M",
}

SEED = {
    "society": "Kizhakku Colony Milk Society",
    "society_ta": "கிழக்கு காலனி பால் சொசைட்டி",
    "note": "All members, pours and prices are synthetic. Illustrative rate chart only.",
    "entries": [
        {
            "id": "E-1041",
            "member_id": 108,
            "member_name": "Ravi K",
            "shift": "evening",
            "litres": 3.0,
            "fat": 3.8,
            "rate": 39.2,
            "amount": 117.6,
            "created_at": "2026-11-09T17:42:00+05:30",
            "status": "confirmed",
            "source": "seed",
            "transcript": "நம்பர் ஒன் ஜீரோ எட்டு. மூணு லிட்டர். ஃபேட் மூணு பாயிண்ட் எட்டு. சாயங்காலம்.",
            "audio": "seed",
            "line": {"scene": "fan_cans", "snr_db": 10, "line_8k": True},
            "provider": "seed fixture (synthetic)",
            "latency_ms": 0,
            "flags": [],
            "hash": "seed-1041",
        },
        {
            "id": "E-1042",
            "member_id": 137,
            "member_name": "Arumugam P",
            "shift": "morning",
            "litres": 3.5,
            "fat": 4.9,
            "rate": 43.6,
            "amount": 152.6,
            "created_at": "2026-11-10T06:38:00+05:30",
            "status": "confirmed",
            "source": "seed",
            "transcript": "நூற்று முப்பத்தி ஏழு. மூன்றரை லிட்டர். ஃபேட் நாலு பாயிண்ட் ஒன்பது. மார்னிங்.",
            "audio": "seed",
            "line": {"scene": "society_hall", "snr_db": 5, "line_8k": True},
            "provider": "seed fixture (synthetic)",
            "latency_ms": 0,
            "flags": [],
            "hash": "seed-1042",
        },
        {
            "id": "E-1043",
            "member_id": 101,
            "member_name": "Selvi M",
            "shift": "morning",
            "litres": 2.0,
            "fat": 4.5,
            "rate": 42.0,
            "amount": 84.0,
            "created_at": "2026-11-10T06:52:00+05:30",
            "status": "confirmed",
            "source": "seed",
            "transcript": "சொசைட்டி நம்பர் நூற்று ஒன்று. ரெண்டு லிட்டர். ஃபேட் நாலு பாயிண்ட் ஐந்து. காலை.",
            "audio": "seed",
            "line": {"scene": "generator", "snr_db": 15, "line_8k": True},
            "provider": "seed fixture (synthetic)",
            "latency_ms": 0,
            "flags": [],
            "hash": "seed-1043",
        },
    ],
}


def _read() -> dict:
    with LOCK:
        if not LEDGER.exists():
            DATA.mkdir(parents=True, exist_ok=True)
            LEDGER.write_text(json.dumps(SEED, ensure_ascii=False, indent=2), encoding="utf-8")
        return json.loads(LEDGER.read_text(encoding="utf-8"))


def _write(data: dict) -> None:
    with LOCK:
        tmp = LEDGER.with_suffix(".tmp")
        tmp.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
        tmp.replace(LEDGER)


def rate_for(fat: float) -> float:
    return round(24.0 + 4.0 * float(fat), 2)


def amount_for(litres: float, fat: float) -> float:
    return round(float(litres) * rate_for(fat), 2)


def summary() -> dict:
    data = _read()
    entries = data["entries"]
    morning = [e for e in entries if e["shift"] == "morning"]
    evening = [e for e in entries if e["shift"] == "evening"]
    return {
        "society": data["society"],
        "society_ta": data["society_ta"],
        "note": data["note"],
        "entries": list(reversed(entries)),
        "totals": {
            "morning": {"litres": round(sum(e["litres"] for e in morning), 2), "amount": round(sum(e["amount"] for e in morning), 2), "count": len(morning)},
            "evening": {"litres": round(sum(e["litres"] for e in evening), 2), "amount": round(sum(e["amount"] for e in evening), 2), "count": len(evening)},
            "all": {"litres": round(sum(e["litres"] for e in entries), 2), "amount": round(sum(e["amount"] for e in entries), 2), "count": len(entries)},
        },
    }


def history(member_id: int) -> list[dict]:
    return [e for e in _read()["entries"] if e["member_id"] == member_id]


def commit(turn: dict, corrections: dict | None = None, override: bool = False) -> dict:
    data = _read()
    slots = turn["slots"]
    litres = float(corrections.get("litres", slots["litres"]["value"]) if corrections else slots["litres"]["value"])
    fat = float(corrections.get("fat", slots["fat"]["value"]) if corrections else slots["fat"]["value"])
    shift = str(corrections.get("shift", slots["shift"]["value"]) if corrections else slots["shift"]["value"])
    member_id = int(corrections.get("member_id", slots["member_id"]["value"]) if corrections else slots["member_id"]["value"])
    entry_id = "E-" + uuid.uuid4().hex[:6].upper()
    now = datetime.now(timezone.utc).astimezone()
    payload = {
        "id": entry_id,
        "member_id": member_id,
        "member_name": MEMBERS.get(member_id, "Unknown"),
        "shift": shift,
        "litres": round(litres, 2),
        "fat": round(fat, 2),
        "rate": rate_for(fat),
        "amount": amount_for(litres, fat),
        "created_at": now.isoformat(timespec="seconds"),
        "status": "confirmed",
        "source": "voice",
        "transcript": turn.get("transcript", ""),
        "audio": turn.get("turn_id"),
        "line": turn.get("line", {}),
        "provider": turn.get("provider", ""),
        "latency_ms": turn.get("latency", {}).get("total_ms", 0),
        "flags": turn.get("validation", {}).get("flags", []),
        "override": bool(override),
        "corrections": corrections or {},
    }
    payload["hash"] = hashlib.sha256(
        json.dumps(payload, sort_keys=True, ensure_ascii=False).encode("utf-8")
    ).hexdigest()[:12]
    data["entries"].append(payload)
    _write(data)
    return payload


def receipt_html(entry: dict) -> str:
    heard = html.escape(entry.get("transcript", ""))
    correction = ", ".join(
        f"{html.escape(str(k))} → {html.escape(str(v))}" for k, v in (entry.get("corrections") or {}).items()
    )
    said = f'<div class="said-label">Heard / கேட்டது</div><div class="said" lang="ta">{heard}</div>' if heard else ""
    corr = f'<div class="row"><span>Correction</span><span>{correction}</span></div>' if correction else ""
    return f"""<!doctype html>
<html lang="en"><head><meta charset="utf-8"><title>Receipt {entry['id']}</title>
<style>
  @import url('https://fonts.googleapis.com/css2?family=IBM+Plex+Mono:wght@400;600&family=Noto+Sans+Tamil:wght@400;600&display=swap');
  body {{ background:#ece9e1; margin:0; padding:32px; font-family:'IBM Plex Mono',monospace; color:#12211f; }}
  .slip {{ max-width:420px; margin:0 auto; background:#fffdf7; padding:28px 26px; border:1px solid #d7d2c4;
          box-shadow:0 18px 50px rgba(18,33,31,.12); position:relative; }}
  .slip:after {{ content:""; position:absolute; left:0; right:0; bottom:-8px; height:8px;
      background:linear-gradient(-45deg, transparent 4px, #fffdf7 0), linear-gradient(45deg, transparent 4px, #fffdf7 0);
      background-size:8px 8px; background-repeat:repeat-x; }}
  h1 {{ font-size:15px; letter-spacing:.16em; text-transform:uppercase; margin:0 0 2px; }}
  .ta {{ font-family:'Noto Sans Tamil',sans-serif; color:#52605c; font-size:12px; margin-bottom:18px; }}
  .said-label {{ font-size:9px; letter-spacing:.14em; text-transform:uppercase; color:#7d8a86; margin-top:14px; }}
  .said {{ font-family:'Noto Sans Tamil',sans-serif; font-size:13px; line-height:1.6; color:#3a4643;
         padding:6px 0 12px; border-bottom:1px dashed #ddd8ca; }}
  .row {{ display:flex; justify-content:space-between; padding:7px 0; border-bottom:1px dashed #ddd8ca; font-size:13px; }}
  .row span:first-child {{ color:#65736f; }}
  .big {{ font-size:26px; font-weight:600; padding-top:16px; }}
  .foot {{ margin-top:18px; font-size:10px; color:#7d8a86; line-height:1.6; }}
  .stamp {{ border:2px solid #1f7a5c; color:#1f7a5c; display:inline-block; padding:4px 8px; font-size:10px;
           letter-spacing:.12em; transform:rotate(-3deg); margin-top:10px; }}
  @media print {{ body {{ background:#fff; padding:0; }} .slip {{ box-shadow:none; border:0; }} }}
</style></head><body><div class="slip">
  <h1>PaalKural · Pour receipt</h1>
  <div class="ta">கிழக்கு காலனி பால் சொசைட்டி</div>
  <div class="row"><span>Receipt</span><span>{entry['id']}</span></div>
  <div class="row"><span>Member</span><span>{entry['member_id']} · {entry['member_name']}</span></div>
  {said}
  <div class="row"><span>Shift</span><span>{entry['shift'].title()}</span></div>
  <div class="row"><span>Litres</span><span>{entry['litres']:.2f} L</span></div>
  <div class="row"><span>Fat</span><span>{entry['fat']:.1f}%</span></div>
  <div class="row"><span>Rate</span><span>₹{entry['rate']:.2f}/L</span></div>
  <div class="row big"><span>Amount</span><span>₹{entry['amount']:.2f}</span></div>
  {corr}
  <div class="row"><span>Logged</span><span>{entry['created_at'][:16].replace('T', ' ')}</span></div>
  <div class="stamp">SYNTHETIC DEMO</div>
  <div class="foot">Illustrative rate chart. All names, pours and prices are synthetic.
  Audit hash {entry['hash']} · captured via {entry.get('provider','voice')}.</div>
</div></body></html>"""
