import asyncio
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import edge_tts

from server.asr import LocalASR
from server.audio import load_wav

ROOT = Path(__file__).resolve().parents[1]
TMP = ROOT / ".tmp"
TEXT = (
    "சொசைட்டி நம்பர் நூற்று ஒன்று. "
    "ரெண்டு லிட்டர் பால். "
    "ஃபேட் நாலு பாயிண்ட் ஐந்து. "
    "காலை ஷிஃப்ட்."
)

VARIANTS = [
    ("pallavi_normal", "ta-IN-PallaviNeural", "+0%"),
    ("pallavi_slow", "ta-IN-PallaviNeural", "-18%"),
    ("valluvar_slow", "ta-IN-ValluvarNeural", "-12%"),
]


async def main() -> None:
    TMP.mkdir(exist_ok=True)
    for name, voice, rate in VARIANTS:
        out = TMP / f"variant_{name}.mp3"
        await edge_tts.Communicate(TEXT, voice, rate=rate).save(str(out))
        print("generated", name)
    asr = LocalASR()
    for name, _, _ in VARIANTS:
        wav = TMP / f"variant_{name}.wav"
        # decode with av here to keep the test independent of fixture tooling
        import av
        import numpy as np
        import wave

        frames = []
        with av.open(str(TMP / f"variant_{name}.mp3")) as container:
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
        res = asr.transcribe_wav(str(wav), language="ta")
        print(f"\n{name}: {res['latency_ms']}ms\n{res['text']}")


asyncio.run(main())
