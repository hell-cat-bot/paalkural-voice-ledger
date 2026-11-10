import asyncio
from pathlib import Path

import edge_tts

OUT = Path(__file__).resolve().parents[1] / ".tmp" / "tts_test.mp3"
TEXT = "நூற்று இருபத்தி நாலு, காலை ஷிஃப்ட், ரெண்டு லிட்டர், ஃபேட் நாலு பாயிண்ட் ஐந்து. சரியா?"


async def main() -> None:
    OUT.parent.mkdir(parents=True, exist_ok=True)
    await edge_tts.Communicate(TEXT, "ta-IN-PallaviNeural").save(str(OUT))
    print("TTS_OK", OUT.stat().st_size)


asyncio.run(main())
