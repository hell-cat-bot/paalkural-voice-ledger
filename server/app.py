"""PaalKural local server: the line console, ledger, and evidence APIs."""
from __future__ import annotations

import base64
import csv
import io
import json
import mimetypes
import os
import re
import threading
import time
import uuid
import webbrowser
from datetime import datetime, timezone
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import unquote, urlparse

from . import store
from .asr import get_asr, provider_info
from .audio import decode_wav_bytes, load_wav, process_chain, simulate_line, wav_bytes, waveform
from .parser import parse_transcript, readback_text, validate
from .tts import synthesize

ROOT = Path(__file__).resolve().parents[1]
STATIC = ROOT / "static"
FIXTURES = ROOT / "fixtures"
TURNS = ROOT / "data" / "turns"
TURNS.mkdir(parents=True, exist_ok=True)

CHAIN = os.environ.get("DEMO_CHAIN", "band+gate")
MAX_BODY = 25 * 1024 * 1024
PENDING: dict[str, dict] = {}
PENDING_LOCK = threading.Lock()

MANIFEST = json.loads((FIXTURES / "manifest.json").read_text(encoding="utf-8"))
CLIPS = {c["id"]: c for c in MANIFEST["benchmark"] + MANIFEST["demo"]}

CSV_COLUMNS = (
    ("Receipt", lambda e: e["id"]),
    ("Time", lambda e: e["created_at"]),
    ("Member", lambda e: e["member_id"]),
    ("Name", lambda e: e["member_name"]),
    ("Shift", lambda e: e["shift"]),
    ("Litres", lambda e: e["litres"]),
    ("Fat", lambda e: e["fat"]),
    ("Rate", lambda e: e["rate"]),
    ("Amount", lambda e: e["amount"]),
    ("Status", lambda e: e["status"]),
    ("Source", lambda e: e["source"]),
    ("Corrected", lambda e: "yes" if e.get("override") else "no"),
    ("Audit hash", lambda e: e.get("hash", "")),
)


def ledger_csv(entries: list[dict]) -> str:
    buf = io.StringIO()
    writer = csv.writer(buf)
    writer.writerow([label for label, _ in CSV_COLUMNS])
    for entry in entries:
        writer.writerow([getter(entry) for _, getter in CSV_COLUMNS])
    return "\ufeff" + buf.getvalue()


def _now() -> str:
    return datetime.now(timezone.utc).astimezone().isoformat(timespec="seconds")


def _json_bytes(payload: dict) -> bytes:
    return json.dumps(payload, ensure_ascii=False).encode("utf-8")


def _missing_prompt(parsed: dict, val: dict) -> str:
    bits = []
    codes = {f["code"] for f in val["flags"]}
    if "member_id" in parsed["missing"] or "member_unknown" in codes:
        bits.append("சொசைட்டி நம்பர் சொல்லுங்கள்.")
    if "litres" in parsed["missing"] or "litres_range" in codes:
        bits.append("எத்தனை லிட்டர் சொல்லுங்கள்.")
    if "fat" in parsed["missing"] or "fat_range" in codes:
        bits.append("ஃபேட் எவ்வளவு சொல்லுங்கள்.")
    if "shift" in parsed["missing"]:
        bits.append("காலை அல்லது சாயங்காலம் சொல்லுங்கள்.")
    if "unit_mismatch" in codes:
        bits.append("லிட்டரில் சொல்லுங்கள்.")
    return " ".join(bits) or "மீண்டும் சொல்லுங்கள்."


def _speak(text: str) -> dict:
    t0 = time.perf_counter()
    out = synthesize(text)
    out["ms"] = round((time.perf_counter() - t0) * 1000)
    return out


def _member_preview(member_id: int | None) -> dict | None:
    if member_id is None or member_id not in store.MEMBERS:
        return None
    rows = store.history(member_id)[-3:]
    return {
        "id": member_id,
        "name": store.MEMBERS[member_id],
        "recent": [
            {
                "id": e["id"],
                "shift": e["shift"],
                "litres": e["litres"],
                "fat": e["fat"],
                "amount": e["amount"],
                "created_at": e["created_at"],
            }
            for e in rows
        ],
    }


def _preview(slots: dict) -> dict | None:
    litres = slots.get("litres", {}).get("value")
    fat = slots.get("fat", {}).get("value")
    if litres is None or fat is None:
        return None
    return {
        "rate": store.rate_for(fat),
        "amount": store.amount_for(litres, fat),
        "chart": "illustrative: ₹24 base + ₹4 per fat point",
    }


def decide_gate(raw_parsed: dict, raw_val: dict, mit_parsed: dict, mit_val: dict) -> dict:
    """Deterministic two-path gate. No audio or ASR side effects, so it is testable.

    Pre-fill is allowed only when both paths validate to identical slots, or
    when exactly one path validates. Everything else is readback/re-ask.
    """
    raw_slots = {k: v["value"] for k, v in raw_parsed["slots"].items()}
    mit_slots = {k: v["value"] for k, v in mit_parsed["slots"].items()}
    if raw_val["ok"] and mit_val["ok"]:
        agreement = "agree" if raw_slots == mit_slots else "disagree"
        chosen = "raw"
    elif raw_val["ok"]:
        agreement, chosen = "raw_only", "raw"
    elif mit_val["ok"]:
        agreement, chosen = "mit_only", "processed"
    else:
        agreement, chosen = "none", "raw"
    return {
        "agreement": agreement,
        "chosen": chosen,
        "raw_slots": raw_slots,
        "mit_slots": mit_slots,
        "differing": sorted(k for k in set(raw_slots) | set(mit_slots) if raw_slots.get(k) != mit_slots.get(k)),
    }


def _run_turn(payload: dict) -> dict:
    t_start = time.perf_counter()
    source = "upload"
    line_meta: dict = {"input": "microphone"}
    fixture_url = None
    clean = None
    recorded = None

    if payload.get("text"):
        source = "typed"
        transcript = str(payload["text"]).strip()
        audio_raw = None
        audio_mit = None
        asr_meta = {
            "text": transcript,
            "language": "ta",
            "language_probability": 1.0,
            "avg_logprob": 0.0,
            "duration_s": 0,
            "latency_ms": 0,
            "provider": "typed input (ASR bypassed)",
            "model": "none",
        }
        dsp = {"chain": "none", "stages": {}}
        line_meta = {"input": "typed"}
        agreement = "typed"
        secondary = None
        raw_res = mit_res = None
    else:
        if payload.get("fixture_id"):
            clip = CLIPS.get(str(payload["fixture_id"]))
            if not clip:
                raise ValueError("unknown fixture")
            clean, _ = load_wav(str(FIXTURES / clip["audio"]))
            scene = payload.get("scene") or clip.get("scene")
            snr = payload.get("snr")
            if scene and snr is not None:
                recorded = simulate_line(clean, scene, float(snr), seed=int(payload.get("seed", 17)))
                line_meta = {
                    "input": "fixture",
                    "fixture": clip["id"],
                    "scene": scene,
                    "snr_db": float(snr),
                    "line_8k": True,
                    "seed": int(payload.get("seed", 17)),
                }
            else:
                recorded = clean.copy()
                line_meta = {"input": "fixture", "fixture": clip["id"], "clean_studio": True}
            fixture_url = f"/api/fixture-audio/{clip['id']}.wav"
            source = "fixture"
        elif payload.get("audio_b64"):
            blob = base64.b64decode(str(payload["audio_b64"]), validate=True)
            recorded, _ = decode_wav_bytes(blob)
            if len(recorded) < 1600:
                raise ValueError("recording too short")
            line_meta = {"input": "microphone", "sample_rate_hz": 16000, "browser_pcm": True}
        else:
            raise ValueError("send text, fixture_id, or audio_b64")

        audio_raw = recorded.copy()
        audio_mit, dsp = process_chain(recorded, CHAIN)
        asr = get_asr()
        raw_res = asr.transcribe_array(audio_raw, language="ta")
        mit_res = asr.transcribe_array(audio_mit, language="ta")
        raw_parsed = parse_transcript(raw_res["text"])
        mit_parsed = parse_transcript(mit_res["text"])
        raw_val = validate(raw_parsed, store.MEMBERS)
        mit_val = validate(mit_parsed, store.MEMBERS)
        gate = decide_gate(raw_parsed, raw_val, mit_parsed, mit_val)
        agreement = gate["agreement"]
        chosen = gate["chosen"]
        raw_slots, mit_slots = gate["raw_slots"], gate["mit_slots"]
        chosen_parsed, chosen_val = (raw_parsed, raw_val) if chosen == "raw" else (mit_parsed, mit_val)
        asr_meta = raw_res if chosen == "raw" else mit_res
        secondary = {
            "path": "processed" if chosen == "raw" else "raw",
            "transcript": mit_res["text"] if chosen == "raw" else raw_res["text"],
            "slots": mit_slots if chosen == "raw" else raw_slots,
            "ok": mit_val["ok"] if chosen == "raw" else raw_val["ok"],
            "missing": mit_val["missing"] if chosen == "raw" else raw_val["missing"],
            "flags": [f["code"] for f in (mit_val["flags"] if chosen == "raw" else raw_val["flags"])],
            "differing": gate["differing"],
        }

    t_parse = time.perf_counter()
    if secondary is None:
        parsed = parse_transcript(asr_meta["text"])
        val = validate(parsed, store.MEMBERS)
    else:
        parsed, val = chosen_parsed, chosen_val
    parse_ms = round((time.perf_counter() - t_parse) * 1000, 1)

    member_id = parsed["slots"].get("member_id", {}).get("value")
    member = _member_preview(int(member_id)) if member_id is not None else None
    if member:
        read_ta, read_en = readback_text(parsed["slots"], member["name"])
    else:
        read_ta, read_en = readback_text(parsed["slots"], None)

    reask = None
    if parsed["missing"] or val["flags"]:
        reask_ta = _missing_prompt(parsed, val)
        reask = {"ta": reask_ta, "en": "Need one more detail; ask again.", **{"audio": _speak(reask_ta)}}
        if not parsed["slots"]:
            read_ta = "மீண்டும் சொல்லுங்கள்."
            read_en = "Please say it again."
    elif agreement == "disagree":
        reask_ta = "இரண்டு கேட்பும் வேறு வேறு சொல்கிறது. மீண்டும் சொல்லுங்கள்."
        reask = {
            "ta": reask_ta,
            "en": "The raw and conditioned listens disagree; ask again.",
            **{"audio": _speak(reask_ta)},
        }
    speech = _speak(read_ta)

    turn_id = "T-" + uuid.uuid4().hex[:6]
    raw_url = mit_url = None
    if audio_raw is not None:
        raw_path = TURNS / f"{turn_id}-raw.wav"
        mit_path = TURNS / f"{turn_id}-mit.wav"
        raw_path.write_bytes(wav_bytes(audio_raw))
        mit_path.write_bytes(wav_bytes(audio_mit))
        raw_url = f"/api/turn-audio/{turn_id}/raw"
        mit_url = f"/api/turn-audio/{turn_id}/mit"

    total_ms = round((time.perf_counter() - t_start) * 1000, 1)
    latency = {
        "asr_ms": asr_meta["latency_ms"],
        "asr_paths_ms": (raw_res["latency_ms"] + mit_res["latency_ms"]) if raw_res else 0,
        "dsp_ms": dsp["stages"].get("dsp_ms", 0),
        "parse_ms": parse_ms,
        "tts_ms": speech.get("ms", 0),
        "total_ms": total_ms,
    }
    turn = {
        "turn_id": turn_id,
        "created_at": _now(),
        "transcript": asr_meta["text"],
        "detected_language": asr_meta.get("language"),
        "language_probability": asr_meta.get("language_probability"),
        "avg_logprob": asr_meta.get("avg_logprob"),
        "slots": parsed["slots"],
        "missing": parsed["missing"],
        "validation": val,
        "readback": {"ta": read_ta, "en": read_en, "audio": speech},
        "reask": reask,
        "agreement": agreement,
        "second": secondary,
        "audio": {"raw_url": raw_url, "mitigated_url": mit_url, "fixture_url": fixture_url},
        "waveform": {
            "raw": waveform(audio_raw) if audio_raw is not None else [0.0] * 220,
            "mitigated": waveform(audio_mit) if audio_raw is not None else [0.0] * 220,
        },
        "line": line_meta,
        "member": member,
        "preview": _preview(parsed["slots"]),
        "provider": asr_meta["provider"],
        "engine": provider_info(),
        "asr": {"provider": asr_meta["provider"], "model": asr_meta["model"]},
        "dsp": dsp,
        "latency": latency,
        "source": source,
    }
    with PENDING_LOCK:
        now = time.time()
        for key in [k for k, v in PENDING.items() if now - v["stored_at"] > 1800]:
            PENDING.pop(key, None)
        PENDING[turn_id] = {"stored_at": now, "turn": turn}
    return turn


def _confirm(payload: dict) -> tuple[int, dict]:
    turn_id = str(payload.get("turn_id", ""))
    with PENDING_LOCK:
        held = PENDING.get(turn_id)
    if not held:
        return HTTPStatus.NOT_FOUND, {"error": "turn_expired", "message": "This turn expired. Record it again."}
    turn = held["turn"]
    corrections = payload.get("corrections") or {}
    slots = {k: v["value"] for k, v in turn["slots"].items()}
    merged = dict(slots)
    for key in ("member_id", "litres", "fat", "shift"):
        if key in corrections and corrections[key] not in (None, ""):
            try:
                merged[key] = float(corrections[key]) if key in ("litres", "fat") else (
                    int(corrections[key]) if key == "member_id" else str(corrections[key]).lower()
                )
            except (TypeError, ValueError):
                return HTTPStatus.BAD_REQUEST, {"error": "bad_correction", "message": f"Invalid {key}."}
    missing = [k for k in ("member_id", "litres", "fat", "shift") if k not in merged]
    if missing:
        return HTTPStatus.CONFLICT, {
            "error": "incomplete",
            "message": "Still missing " + ", ".join(missing) + ".",
            "missing": missing,
            "validation": turn["validation"],
        }
    if int(merged["member_id"]) not in store.MEMBERS:
        return HTTPStatus.CONFLICT, {"error": "member_unknown", "message": "That member is not in this society."}
    if not (0.2 <= float(merged["litres"]) <= 20.0):
        return HTTPStatus.CONFLICT, {"error": "litres_range", "message": "Litres must be 0.2–20."}
    if not (2.5 <= float(merged["fat"]) <= 9.0):
        return HTTPStatus.CONFLICT, {"error": "fat_range", "message": "Fat must be 2.5–9.0."}
    if merged["shift"] not in ("morning", "evening"):
        return HTTPStatus.CONFLICT, {"error": "shift_invalid", "message": "Shift must be morning or evening."}

    changed_slots = {
        k: merged[k] for k in ("member_id", "litres", "fat", "shift") if merged[k] != slots.get(k)
    }
    entry = store.commit(
        turn,
        corrections=changed_slots,
        override=bool(turn["validation"]["flags"]) or bool(changed_slots),
    )
    with PENDING_LOCK:
        PENDING.pop(turn_id, None)
    return HTTPStatus.OK, {
        "entry": entry,
        "receipt_url": f"/api/receipt/{entry['id']}",
        "corrections_applied": bool(changed_slots) or bool(turn["validation"]["flags"]),
    }


class Handler(BaseHTTPRequestHandler):
    server_version = "PaalKural/1.0"
    protocol_version = "HTTP/1.1"

    def log_message(self, fmt, *args):
        print(f"[{self.log_date_time_string()}] {fmt % args}", flush=True)

    def _send(self, status: int, body: bytes, ctype: str = "application/json; charset=utf-8", extra: dict | None = None):
        self.send_response(status)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        for key, value in (extra or {}).items():
            self.send_header(key, value)
        self.end_headers()
        try:
            self.wfile.write(body)
        except (BrokenPipeError, ConnectionResetError):
            pass

    def _json(self, status: int, payload: dict):
        self._send(status, _json_bytes(payload))

    def _file(self, path: Path, ctype: str | None = None):
        if not path.exists() or not path.is_file():
            self._json(HTTPStatus.NOT_FOUND, {"error": "not_found"})
            return
        ctype = ctype or mimetypes.guess_type(path.name)[0] or "application/octet-stream"
        self._send(HTTPStatus.OK, path.read_bytes(), ctype)

    def _body(self) -> dict:
        length = int(self.headers.get("Content-Length", "0"))
        if length <= 0:
            return {}
        if length > MAX_BODY:
            raise ValueError("body too large")
        raw = self.rfile.read(length)
        return json.loads(raw.decode("utf-8"))

    def do_GET(self):
        path = unquote(urlparse(self.path).path)
        try:
            if path in ("/", "/index.html"):
                self._file(STATIC / "index.html", "text/html; charset=utf-8")
            elif path.startswith("/static/"):
                parts = path[len("/static/"):].split("/")
                if not all(re.fullmatch(r"[A-Za-z0-9._-]+", p) for p in parts):
                    self._json(HTTPStatus.BAD_REQUEST, {"error": "bad_path"})
                    return
                target = STATIC.joinpath(*parts).resolve()
                if STATIC.resolve() not in target.parents:
                    self._json(HTTPStatus.BAD_REQUEST, {"error": "bad_path"})
                    return
                self._file(target)
            elif path == "/api/health":
                self._json(
                    HTTPStatus.OK,
                    {
                        "ok": True,
                        "provider": provider_info(),
                        "members": len(store.MEMBERS),
                        "chain": CHAIN,
                        "benchmark": (ROOT / "data" / "benchmark.json").exists(),
                        "provider_check": (ROOT / "data" / "benchmark-gnani.json").exists(),
                    },
                )
            elif path == "/api/ledger.csv":
                body = ledger_csv(store.summary()["entries"]).encode("utf-8")
                self._send(
                    HTTPStatus.OK,
                    body,
                    "text/csv; charset=utf-8",
                    {"Content-Disposition": 'attachment; filename="paalkural-ledger.csv"'},
                )
            elif path == "/api/ledger":
                self._json(HTTPStatus.OK, {**store.summary(), "provider": provider_info()})
            elif path == "/api/members":
                self._json(HTTPStatus.OK, {"members": [{"id": k, "name": v} for k, v in store.MEMBERS.items()]})
            elif path == "/api/fixtures":
                self._json(
                    HTTPStatus.OK,
                    {
                        "demo": MANIFEST["demo"],
                        "benchmark": [
                            {k: c[k] for k in ("id", "member_id", "litres", "fat", "shift", "scene")}
                            | {"audio_url": f"/api/fixture-audio/{c['id']}.wav"}
                            for c in MANIFEST["benchmark"]
                        ],
                        "synthetic": True,
                    },
                )
            elif path == "/api/benchmark":
                file = ROOT / "data" / "benchmark.json"
                if file.exists():
                    self._send(HTTPStatus.OK, file.read_bytes())
                else:
                    self._json(HTTPStatus.OK, {"status": "not_run", "message": "Run tools/benchmark.py to produce evidence."})
            elif path == "/api/benchmark-gnani":
                file = ROOT / "data" / "benchmark-gnani.json"
                if file.exists():
                    self._send(HTTPStatus.OK, file.read_bytes())
                else:
                    self._json(HTTPStatus.OK, {"status": "not_run", "message": "Run tools/gnani_benchmark.py to produce the provider check."})
            elif re.fullmatch(r"/api/fixture-audio/[a-z0-9]{3}\.wav", path):
                cid = path.rsplit("/", 1)[1][:-4]
                if cid not in CLIPS:
                    self._json(HTTPStatus.NOT_FOUND, {"error": "unknown_fixture"})
                    return
                self._file(FIXTURES / "audio" / f"{cid}.wav", "audio/wav")
            elif re.fullmatch(r"/api/turn-audio/T-[0-9a-f]{6}/(raw|mit)", path):
                turn_id, kind = path.rsplit("/", 2)[1:]
                self._file(TURNS / f"{turn_id}-{kind}.wav", "audio/wav")
            elif re.fullmatch(r"/api/tts-audio/[0-9a-f]{24}\.mp3", path):
                self._file(ROOT / "data" / "tts" / path.rsplit("/", 1)[1], "audio/mpeg")
            elif re.fullmatch(r"/api/receipt/E-[A-Z0-9]{4,8}", path):
                entry_id = path.rsplit("/", 1)[1]
                entry = next((e for e in store.summary()["entries"] if e["id"] == entry_id), None)
                if not entry:
                    self._json(HTTPStatus.NOT_FOUND, {"error": "unknown_receipt"})
                    return
                self._send(HTTPStatus.OK, store.receipt_html(entry).encode("utf-8"), "text/html; charset=utf-8")
            else:
                self._json(HTTPStatus.NOT_FOUND, {"error": "not_found"})
        except (BrokenPipeError, ConnectionResetError):
            pass
        except Exception as exc:  # pragma: no cover - last-resort API guard
            self._json(HTTPStatus.INTERNAL_SERVER_ERROR, {"error": "server_error", "message": str(exc)})

    def do_POST(self):
        path = urlparse(self.path).path
        try:
            payload = self._body()
            if path == "/api/turn":
                self._json(HTTPStatus.OK, _run_turn(payload))
            elif path == "/api/confirm":
                status, body = _confirm(payload)
                self._json(status, body)
            elif path == "/api/benchmark/replay":
                from .benchmark import replay

                result = replay(
                    payload.get("clip_id", "b01"),
                    payload.get("snr"),
                    payload.get("arm", "mitigated"),
                    get_asr(),
                )
                self._json(HTTPStatus.OK, result)
            else:
                self._json(HTTPStatus.NOT_FOUND, {"error": "not_found"})
        except ValueError as exc:
            self._json(HTTPStatus.BAD_REQUEST, {"error": "bad_request", "message": str(exc)})
        except (BrokenPipeError, ConnectionResetError):
            pass
        except Exception as exc:  # pragma: no cover
            import traceback

            traceback.print_exc()
            self._json(HTTPStatus.INTERNAL_SERVER_ERROR, {"error": "server_error", "message": str(exc)})


def _warm():
    try:
        from .benchmark import warm_captions

        warm_captions()
        asr = get_asr()
        if hasattr(asr, "model"):
            asr.model  # load the local Whisper model before the first caller arrives
        for text in (
            "மீண்டும் சொல்லுங்கள்.",
            "சொசைட்டி நம்பர் சொல்லுங்கள்.",
            "எத்தனை லிட்டர் சொல்லுங்கள்.",
            "ஃபேட் எவ்வளவு சொல்லுங்கள்.",
            "காலை அல்லது சாயங்காலம் சொல்லுங்கள்.",
            "இரண்டு கேட்பும் வேறு வேறு சொல்கிறது. மீண்டும் சொல்லுங்கள்.",
        ):
            synthesize(text)
        print("warmup complete", flush=True)
    except Exception as exc:  # pragma: no cover
        print(f"warmup skipped: {exc}", flush=True)


def main(port: int | None = None, open_browser: bool = False):
    host = os.environ.get("HOST", "127.0.0.1")
    port = port or int(os.environ.get("PORT", "7860"))
    server = ThreadingHTTPServer((host, port), Handler)
    print(f"PaalKural listening on http://{host}:{port} (chain={CHAIN})", flush=True)
    threading.Thread(target=_warm, daemon=True).start()
    if open_browser:
        threading.Timer(1.2, lambda: webbrowser.open(f"http://{host}:{port}")).start()
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\nstopping", flush=True)
    finally:
        server.server_close()


if __name__ == "__main__":
    main()
