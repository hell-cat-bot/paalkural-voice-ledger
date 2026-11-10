import asyncio
import sys
import wave
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import av
import edge_tts
import numpy as np

from server.asr import LocalASR

ROOT = Path(__file__).resolve().parents[1]
TMP = ROOT / ".tmp"

TEXTS = {
    "tamil_id": "சொசைட்டி நம்பர், நூற்று ஒன்று. ரெண்டு லிட்டர் பால். ஃபேட் நாலு பாயிண்ட், ஐந்து. காலை ஷிஃப்ட்.",
    "digit_id": "சொசைட்டி நம்பர், ஒன் ஜீரோ ஒன். ரெண்டு லிட்டர் பால். ஃபேட் நாலு பாயிண்ட், ஐந்து. காலை ஷிஃப்ட்.",
    "numeric_id": "சொசைட்டி நம்பர் 101. ரெண்டு லிட்டர் பால். ஃபேட் 4.5. காலை ஷிஃப்ட்.",
    "split_fat": "சொசைட்டி நம்பர், நூற்று ஒன்று. ரெண்டு லிட்டர். ஃபேட், நாலு, பாயிண்ட், ஐந்து. காலை ஷிஃப்ட்.",
}


async def gen(name: str, text: str) -> Path:
    mp3 = TMP / f"v2_{name}.mp3"
    wav = TMP / f"v2_{name}.wav"
    await edge_tts.Communicate(text, "ta-IN-ValluvarNeural", rate="-18%").save(str(mp3))
    frames = []
    with av.open(str(mp3)) as container:
        stream = next(s for s in container.streams if s.type == "audio")
        rs = av.AudioResampler(format="s16", layout="mono", rate=16000)
        for frame in container.decode(stream):
            for out in rs.resample(frame):
                frames.append(out.to_ndarray().reshape(-1))
    audio = np.concatenate(frames).astype("int16")
    with wave.open(str(wav), "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(16000)
        w.writeframes(audio.tobytes())
    return wav


async def main() -> None:
    TMP.mkdir(exist_ok=True)
    asr = LocalASR()
    for name, text in TEXTS.items():
        wav = await gen(name, text)
        res = asr.transcribe_wav(str(wav), language="ta")
        print(f"\n{name}: {res['latency_ms']}ms\n{res['text']}")


asyncio.run(main())
