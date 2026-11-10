"""Synthesize the demo narration with Gnani Timbre and build per-scene VTT/SRT.

One Timbre request per sentence gives exact sentence timing for captions and
lets the record config schedule UI actions against real speech. The key is
read through server.env and never printed.
"""
from __future__ import annotations

import hashlib
import json
import os
import re
import subprocess
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
from server.env import load_env  # noqa: E402

FFMPEG = Path(r"C:\Hackathons\Gnani\.tools\ffmpeg\ffmpeg-9.0.2-essentials_build\bin\ffmpeg.exe")
FFPROBE = FFMPEG.with_name("ffprobe.exe")
AUDIO = ROOT / "video" / "audio"
SENT = AUDIO / "_sent"
MODEL = "timbre-v2.5"
VOICE = "Nalini"
LANG = "en-IN"
GAP = 0.32
LEAD = 0.20
TAIL = 0.45
SPOKEN = {
    "PaalKural": "Paal Kural",
    "CSV": "C S V",
    "CHECK": "check",
    "4.0": "four point zero",
    "4.4": "four point four",
    "4.7": "four point seven",
    "127": "one hundred and twenty seven",
    "192": "one hundred and ninety two",
    "26": "twenty six",
}


def spoken(text: str) -> str:
    for src, dst in SPOKEN.items():
        text = re.sub(rf"(?<![A-Za-z0-9]){re.escape(src)}(?![A-Za-z0-9])", dst, text)
    return text


def parse_narration(path: Path) -> list[tuple[str, list[str]]]:
    scenes: list[tuple[str, list[str]]] = []
    current: list[str] | None = None
    for raw in path.read_text(encoding="utf-8").splitlines():
        line = raw.strip()
        if line.startswith("## "):
            match = re.match(r"##\s+(\S+)", line)
            if not match:
                continue
            current = []
            scenes.append((match.group(1), current))
        elif line and current is not None:
            current.append(line)
    return scenes


def probe(path: Path) -> float:
    out = subprocess.run(
        [str(FFPROBE), "-v", "error", "-show_entries", "format=duration", "-of", "default=nw=1:nk=1", str(path)],
        capture_output=True,
        text=True,
        check=True,
    )
    return float(out.stdout.strip())


def synth(text: str, path: Path, key: str) -> None:
    payload = json.dumps(
        {
            "text": text,
            "voice": VOICE,
            "model": MODEL,
            "language": LANG,
            "speed": 1.0,
            "audio_config": {"sample_rate": 44100, "container": "mp3"},
        }
    ).encode()
    req = urllib.request.Request(
        "https://api.vachana.ai/api/v1/tts/inference",
        data=payload,
        headers={
            "Content-Type": "application/json",
            "Accept": "audio/mpeg, application/json",
            "X-API-Key-ID": key,
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
            "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36",
        },
        method="POST",
    )
    for attempt in range(6):
        try:
            with urllib.request.urlopen(req, timeout=90) as resp:
                path.write_bytes(resp.read())
            return
        except urllib.error.HTTPError as exc:
            detail = exc.read()[:240].decode("utf-8", "replace")
            if exc.code == 429 and attempt < 5:
                time.sleep(3 * (attempt + 1))
                continue
            raise RuntimeError(f"TTS {exc.code}: {detail}") from None
        except (urllib.error.URLError, TimeoutError) as exc:
            if attempt < 5:
                time.sleep(2 * (attempt + 1))
                continue
            raise RuntimeError(f"TTS network: {exc}") from None


def silence(name: str, seconds: float) -> Path:
    path = AUDIO / f"_sil-{name}.mp3"
    if not path.exists() or abs(probe(path) - seconds) > 0.02:
        subprocess.run(
            [str(FFMPEG), "-y", "-v", "error", "-f", "lavfi", "-t", f"{seconds:.3f}",
             "-i", "anullsrc=r=44100:cl=mono", "-c:a", "libmp3lame", "-b:a", "192k", str(path)],
            check=True,
        )
    return path


def assemble(scene: str, clips: list[Path], out: Path) -> None:
    lead = silence("lead", LEAD)
    gap = silence("gap", GAP)
    tail = silence("tail", TAIL)
    inputs: list[Path] = [lead]
    for index, clip in enumerate(clips):
        inputs.append(clip)
        inputs.append(tail if index == len(clips) - 1 else gap)
    args = [str(FFMPEG), "-y", "-v", "error"]
    for item in inputs:
        args += ["-i", str(item)]
    graph = "".join(f"[{i}:a]" for i in range(len(inputs)))
    graph += f"concat=n={len(inputs)}:v=0:a=1,loudnorm=I=-16:TP=-1.5:LRA=11[a]"
    args += [
        "-filter_complex", graph, "-map", "[a]",
        "-ar", "44100", "-ac", "1", "-c:a", "libmp3lame", "-b:a", "192k", str(out),
    ]
    subprocess.run(args, check=True)


def stamp(seconds: float, comma: bool) -> str:
    ms = int(round(seconds * 1000))
    h, ms = divmod(ms, 3600000)
    m, ms = divmod(ms, 60000)
    s, ms = divmod(ms, 1000)
    return f"{h:02d}:{m:02d}:{s:02d}{',' if comma else '.'}{ms:03d}"


def main() -> None:
    load_env()
    key = os.environ.get("GNANI_API_KEY", "").strip()
    if not key:
        raise SystemExit("no Gnani key loaded")
    AUDIO.mkdir(parents=True, exist_ok=True)
    SENT.mkdir(parents=True, exist_ok=True)
    cache_path = SENT / "cache.json"
    cache = json.loads(cache_path.read_text(encoding="utf-8")) if cache_path.exists() else {}

    scenes = parse_narration(ROOT / "video" / "narration.md")
    durations: dict[str, int] = {}
    srt_rows: list[tuple[float, float, str]] = []
    cursor = 0.0

    for scene, sentences in scenes:
        clips: list[Path] = []
        cues: list[tuple[float, float, str]] = []
        t = LEAD
        for index, caption in enumerate(sentences):
            text = spoken(caption)
            digest = hashlib.sha256(f"{text}|{VOICE}|{MODEL}|{LANG}".encode()).hexdigest()[:20]
            clip = SENT / f"{digest}.mp3"
            if cache.get(digest) != clip.name or not clip.exists():
                synth(text, clip, key)
                cache[digest] = clip.name
                cache_path.write_text(json.dumps(cache, indent=0), encoding="utf-8")
                print(f"  tts {scene} {index + 1}/{len(sentences)} {probe(clip):.1f}s", flush=True)
                time.sleep(0.25)
            else:
                print(f"  cache {scene} {index + 1}/{len(sentences)}", flush=True)
            clips.append(clip)
            length = probe(clip)
            cues.append((t, t + length, caption))
            t += length + GAP

        out = AUDIO / f"{scene}.mp3"
        assemble(scene, clips, out)
        total = probe(out)
        durations[scene] = round(total * 1000)

        vtt = ["WEBVTT", ""]
        for start, end, caption in cues:
            vtt += [f"{stamp(start, False)} --> {stamp(min(end, total), False)}", caption, ""]
        (AUDIO / f"{scene}.vtt").write_text("\n".join(vtt), encoding="utf-8")
        for start, end, caption in cues:
            srt_rows.append((cursor + start, cursor + min(end, total), caption))
        cursor += total
        print(f"{scene}: {total:.1f}s, {len(sentences)} lines", flush=True)

    (AUDIO / "durations.json").write_text(json.dumps(durations, indent=2) + "\n", encoding="utf-8")
    srt = []
    for index, (start, end, caption) in enumerate(srt_rows, 1):
        srt += [str(index), f"{stamp(start, True)} --> {stamp(end, True)}", caption, ""]
    (ROOT / "video" / "out" / "paalkural-demo-3min.srt").write_text(
        "\n".join(srt), encoding="utf-8"
    )
    print(f"total {cursor:.1f}s -> {AUDIO / 'durations.json'}", flush=True)


if __name__ == "__main__":
    main()
