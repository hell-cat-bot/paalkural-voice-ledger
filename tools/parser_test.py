import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from server.parser import parse_transcript, validate

MEMBERS = {101: "Selvi M", 108: "Ravi K", 124: "Anitha R", 119: "Murugan S"}

CASES = [
    ("சொசைட்டி நம்பர் 101, ரெண்டு லிட்டர், பால், ஹேட் நாலு பாயிண்ட் ஐந்து. காலை ஷிஃப்ட்,",
     {"member_id": 101, "litres": 2.0, "fat": 4.5, "shift": "morning"}),
    ("நம்பர், 1, 2, 4, மூணு லிட்டர். இல்ல இல்ல, மூன்றரை லிட்டர். ஃபேட் நாலு பாயிண்ட் எட்டு. காலை.",
     {"member_id": 124, "litres": 3.5, "fat": 4.8, "shift": "morning"}),
    ("நூற்று இருபத்தி நாலு, மூணு லிட்டர். இல்லை இல்லை, மூன்றரை லிட்டர். ஃபேட் நாலு பாயிண்ட் எட்டு. காலை.",
     {"member_id": 124, "litres": 3.5, "fat": 4.8, "shift": "morning"}),
    ("நம்பர், ஒன் டூ ஃபோர். ஊந்தரை லிட்டர். காலை ஷிஃப்ட்.",
     {"member_id": 124, "litres": 1.5, "shift": "morning"}),
    ("நம்பர் 108. நாலு லிட்டர். ஃபேட் ஆறு. ஈவ்னிங் ஷிஃப்ட்.",
     {"member_id": 108, "litres": 4.0, "fat": 6.0, "shift": "evening"}),
    ("நம்பர், ஒன் ஜீரோ எட்டு. ஒன்றரை லிட்டர் பால். ஃபேட் மூணு பாயிண்ட் எட்டு. காலை.",
     {"member_id": 108, "litres": 1.5, "fat": 3.8, "shift": "morning"}),
    ("நம்பர், 1-2-4. ரெண்டு லிட்டர். ஃபேட் 4.5. காலை.",
     {"member_id": 124, "litres": 2.0, "fat": 4.5, "shift": "morning"}),
    ("நம்பர், ஒன் ஒன் னைன். ஐந்து லிட்டர் பால். ஃபேட் மூணு பாயிண்ட் ஐந்து. ஈவ்னிங்.",
     {"member_id": 119, "litres": 5.0, "fat": 3.5, "shift": "evening"}),
    ("சொசைட்டி நம்பர் 101. இரண்டி லிட்டர் பால். ஹேட் நாளு பாய்ந்த ஐந்தே. காலை ஷிஃப்ட்.",
     {"member_id": 101, "litres": 2.0, "fat": 4.5, "shift": "morning"}),
    ("நம்பர். 1, 2, 4. மூன்று லிட்டர். இல்லை இல்லை மூன்றுறை லிட்டர். காலை.",
     {"member_id": 124, "litres": 3.5, "shift": "morning"}),
    ("நம்பர் 156. ரெண்டு லிட்டர். இல்லை, இரண்டரை லிட்டர். செய்ட் மூன்னு, பாய்யன்ட் மூன்னு. ஏவனின்",
     {"member_id": 156, "litres": 2.5, "fat": 3.3, "shift": "evening"}),
    ("நம்பர் 156. இரண்டிலிட்டார். இல்லை, இரண்டிரை லிட்டார். பேட் மூன்று, பாயன் மூன்று. இவனி.",
     {"member_id": 156, "litres": 2.5, "fat": 3.3, "shift": "evening"}),
    ("நம்பர் 156. ரெண்டு லிக்கார். இல்லை, ரெண்டரை லிக்கார். பேச் மூன்று வாயின் மூன்று.",
     {"member_id": 156, "litres": 2.5, "fat": 3.3}),
    ("நம்பர் 156. ரெண்டிலிட்டர. இல்லை, ரெண்டரை லிட்டர். ஷெய்ட் மோனோ, பாய்யன்ட் மோனோ. ஏவனின்...",
     {"member_id": 156, "litres": 2.5, "fat": 3.3, "shift": "evening"}),
    ("நம்பர் 124. ஏற்று நாளு பாயன்ட் ஏட்டு. காலை.",
     {"member_id": 124, "fat": 4.8, "shift": "morning"}),
    ("நம்பர். 101. மூன் லிட்டர். ஃபேட் ஐந்து பாயங்ட் ஒன்றே. சாயங்காலம் ஷிஃப்ட்.",
     {"member_id": 101, "litres": 3.0, "fat": 5.1, "shift": "evening"}),
    ("நம்பர் நூற்று எட்டு. நாலு லிட்டர். ஃபேட் ஆறு. ஈவனின் ஷிஃப்ட்.",
     {"member_id": 108, "litres": 4.0, "fat": 6.0, "shift": "evening"}),
    ("நம்பர் ஒன் ஒன்னைன். ஆறை லிட்டர். ஃபேட் ஆறு பாயெண்ட் எட்டு. மார்ணிங்",
     {"member_id": 119, "litres": 0.5, "fat": 6.8, "shift": "morning"}),
    ("நம்பர் ஒன் ஒன் நெய்ன். ஹரை லிட்டர். ஃபேட் ஆறு பாயெண்டு எட்டு. மார்ணிங்",
     {"member_id": 119, "litres": 0.5, "fat": 6.8, "shift": "morning"}),
    ("நம்பர். 127. 4.5 லிட்டர். ஃபேட் மூன்று பாயின்ட் ஒன்பதே. மார்ணிங்",
     {"member_id": 127, "litres": 4.5, "fat": 3.9, "shift": "morning"}),
    ("நம்பர். 127. நாரரை விக்கர். ஃபேட் மூன்று பாயின் ஒன்பது. மாற்றின்",
     {"member_id": 127, "litres": 4.5, "fat": 3.9, "shift": "morning"}),
    ("நம்பர். 156. ஓர் லிட்டர் பால். ஃபேட் ஆறு பாயெண்ட் ஒன்பதே. மார்ணிங்",
     {"member_id": 156, "litres": 1.0, "fat": 6.9, "shift": "morning"}),
    ("நம்பர் 137. ஐந்தரை லிட்டர் பால். ஃபேட் மூன்று பாயெண்ட் ஏகு.",
     {"member_id": 137, "litres": 5.5, "fat": 3.7}),
]

failed = 0
for text, expected in CASES:
    parsed = parse_transcript(text)
    got = {k: v["value"] for k, v in parsed["slots"].items()}
    ok = all(got.get(k) == v for k, v in expected.items())
    val = validate(parsed, MEMBERS)
    print(("PASS" if ok else "FAIL"), "|", got, "| missing", parsed["missing"], "| valid", val["ok"])
    if not ok:
        failed += 1
        print("  text:", text)
        print("  expected:", expected)
        print("  flags:", [f["code"] for f in val["flags"]])
print("FAILED", failed, "of", len(CASES))
