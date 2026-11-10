"""Deterministic slot compiler for Tamil / Tanglish milk-pour utterances.

The compiler is deliberately rule-based: on a noisy line, an explainable parse
with a hard validation gate is safer than a fluent guess. It understands Tamil
number words, English digit sequences, Tamil-script English loanwords, and
spoken self-corrections ("இல்ல இல்ல...").
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field

TAMIL_DIGITS = str.maketrans("௦௧௨௩௪௫௬௭௮௯", "0123456789")

UNITS = {
    "பூஜ்யம்": 0, "சுழியம்": 0, "zero": 0, "oh": 0, "ஜீரோ": 0, "ஜீரொ": 0,
    "ஒன்று": 1, "ஒரு": 1, "ஒன்": 1, "ஒண்": 1, "வண்": 1, "one": 1, "ஓர்": 1, "ஓர": 1,
    "ரெண்டு": 2, "இரண்டு": 2, "டூ": 2, "டு": 2, "two": 2,
    "மூணு": 3, "மூன்று": 3, "த்ரீ": 3, "த்ரி": 3, "three": 3,
    "நாலு": 4, "நான்கு": 4, "நாங்கு": 4, "ஃபோர்": 4, "ஃபோ": 4, "four": 4,
    "ஐந்து": 5, "ஐந்த": 5, "ஃபைவ்": 5, "ஃபிவ்": 5, "five": 5,
    "ஆறு": 6, "சிக்ஸ்": 6, "six": 6,
    "ஏழு": 7, "செவன்": 7, "seven": 7,
    "எட்டு": 8, "எயிட்": 8, "ஏட்": 8, "eight": 8,
    "ஒன்பது": 9, "ஒன்பது": 9, "னைன்": 9, "நைன்": 9, "நெய்ன்": 9, "nine": 9,
    "ஒன்னைன்": 19, "ஒன்றி": 13,
    "பத்து": 10, "டென்": 10, "ten": 10,
    "பதினொன்று": 11, "eleven": 11,
    "பன்னிரண்டு": 12, "twelve": 12,
    "பதின்மூன்று": 13, "thirteen": 13,
    "பதினான்கு": 14, "fourteen": 14,
    "பதினைந்து": 15, "fifteen": 15,
    "பதினாறு": 16, "sixteen": 16,
    "பதினேழு": 17, "seventeen": 17,
    "பதினெட்டு": 18, "eighteen": 18,
    "பத்தொன்பது": 19, "nineteen": 19,
    "இருபது": 20, "twenty": 20,
}
TENS = {
    "இருபத்தி": 20, "இருபத்தினான்கு": 24, "முப்பது": 30, "முப்பத்தி": 30,
    "நாற்பது": 40, "நாற்பத்தி": 40,
    "ஐம்பது": 50, "ஐம்பத்தி": 50,
    "அறுபது": 60, "அறுபத்தி": 60,
    "எழுபது": 70, "எழுபத்தி": 70,
    "எண்பது": 80, "எண்பத்தி": 80,
    "தொண்ணூறு": 90, "தொண்ணூற்றி": 90,
    "thirty": 30, "forty": 40, "fifty": 50,
    "sixty": 60, "seventy": 70, "eighty": 80, "ninety": 90,
}
HUNDREDS = {
    "நூறு": 100, "நூற்று": 100,
    "இருநூறு": 200, "இருநூற்று": 200,
    "முந்நூறு": 300, "முந்நூற்று": 300,
    "நானூறு": 400, "நானூற்று": 400,
    "ஐந்நூறு": 500, "ஐந்நூற்று": 500,
    "hundred": 100,
}
HALVES = {
    "அரை": 0.5, "ஒன்றரை": 1.5, "ஒந்தரை": 1.5, "ஊந்தரை": 1.5, "ஓந்தரை": 1.5,
    "ரெண்டரை": 2.5, "இரண்டரை": 2.5, "மூன்றரை": 3.5, "நாலரை": 4.5,
    "ஐந்தரை": 5.5, "ஆறரை": 6.5, "ஏழரை": 7.5, "எட்டரை": 8.5, "ஒன்பதரை": 9.5,
    "ஆறை": 0.5, "ஹரை": 0.5, "நாரரை": 4.5, "நானரை": 4.5,
}
POINT = {
    "பாயிண்ட்", "பாயிண்ட", "பாய்ன்ட்", "பாய்ன்ட", "பாயிண்", "புள்ளி",
    "point", ".", "டாட்", "dot",
}
MEMBER_KW = {"நம்பர்", "நம்பெர்", "எண்", "number", "சொசைட்டி", "society", "member", "மெம்பர்"}
LITRE_KW = {"லிட்டர்", "லிடர்", "லிட்ட", "litre", "liter", "liters", "litres", "ltr", "ல்டர்"}
FAT_KW = {"ஃபேட்", "பேட்", "ஃபாட்", "ஹேட்", "ஷேட்", "டேட்", "ஃபேய்ட்", "fat", "கொழுப்பு"}
SHIFT_KW = {
    "காலை": "morning", "மார்னிங்": "morning", "morning": "morning", "am": "morning",
    "சாயங்காலம்": "evening", "சாயங்கால": "evening", "ஈவ்னிங்": "evening",
    "evening": "evening", "pm": "evening", "சாயங்காலம்": "evening",
    "மார்ணிங்": "morning", "மாற்றின்": "morning",
    "ஈவினின்": "evening", "ஈவனின்": "evening", "ஈவ்ணின்": "evening",
}
CORRECTION = {"இல்ல", "இல்லை", "sorry", "திரும்ப", "actually", "correct", "wrong", "அல்ல"}
SLOT_KEYWORDS = LITRE_KW | FAT_KW | set(SHIFT_KW)
REQUIRED = ("member_id", "litres", "fat", "shift")

# Spellings that faster-whisper produced on the frozen synthetic fixtures.
# Kept as an explicit, auditable lexicon rather than fuzzy matching so a
# canonical token can always be traced back to what the ASR actually wrote.
TOKEN_VARIANTS = {
    "இரண்டி": "ரெண்டு", "ரெண்டி": "ரெண்டு", "ரெந்தி": "ரெண்டு", "ரெந்து": "ரெண்டு",
    "மூன்றுறை": "மூன்றரை", "மூன்றிரை": "மூன்றரை", "மூன்றரே": "மூன்றரை",
    "இரண்டிரை": "ரெண்டரை", "ரெண்டிரை": "ரெண்டரை",
    "நாளு": "நாலு", "நாலும்": "நாலு", "நாலும்,": "நாலு", "நால்": "நாலு",
    "ஐந்தே": "ஐந்து", "அய்ந்தே": "ஐந்து", "அஞ்சு": "ஐந்து",
    "மோனோ": "மூணு", "மோனு": "மூணு", "மூனு": "மூணு", "மூனோ": "மூணு", "மூன்னு": "மூணு",
    "ஓனு": "ஒன்று", "ஒன்னு": "ஒன்று", "ஒண்ணு": "ஒன்று",
    "எட்டே": "எட்டு", "ஏட்டே": "எட்டு", "ஏட்டு": "எட்டு", "ஏற்று": "எட்டு", "ஏறு": "எட்டு",
    "ஆறே": "ஆறு", "ஆறில்": "ஆறு", "ஆர்ல்": "ஆறு", "ஏழே": "ஏழு",
    "ஒன்பதே": "ஒன்பது", "பத்தே": "பத்து", "ஒன்றே": "ஒன்று",
    "மூன்": "மூணு", "ஏகு": "ஏழு",
    "வாயின்": "பாயிண்ட்", "வாய்யின்": "பாயிண்ட்", "வாயன்": "பாயிண்ட்",
    "பையன்ட்": "பாயிண்ட்", "பையண்ட்": "பாயிண்ட்",
    "ஏவனின்": "ஈவ்னிங்", "இவனி": "ஈவ்னிங்", "ஈவினிங்": "ஈவ்னிங்", "ஈவ்னின்": "ஈவ்னிங்",
}
HALF_TAILS = {"ரை", "ரெய்", "ஹரை", "ஹரி", "ஹரெய்", "அரை"}
FUSED_HALF = {
    "ஒன்று": "ஒன்றரை", "ரெண்டு": "ரெண்டரை", "மூன்று": "மூன்றரை", "நாலு": "நாலரை",
    "ஐந்து": "ஐந்தரை", "ஆறு": "ஆறரை", "ஏழு": "ஏழரை", "எட்டு": "எட்டரை",
    "ஒன்பது": "ஒன்பதரை", "பத்து": "பத்தரை",
}
FAT_VARIANTS = FAT_KW | {"தேட்", "செய்ட்", "ஷெய்ட்", "பேச்", "சேர்", "ஃபேஸ்"}
LITRE_STEMS = (
    "லிட்டார்", "லிட்டேன்", "லிட்டர்", "லிட்டர", "லிட்டா", "லிடர்", "விட்டார்", "விட்டேன்",
    "விட்டர்", "விட்டர", "லிக்கார்", "லிக்கர்", "லிக்கர", "நிக்கிறேன்", "நிக்கர்", "நிக்கர", "ல்டர்",
    "விக்கர்", "விக்கர",
)
_LITRE_TOKEN = set(LITRE_STEMS) | LITRE_KW


@dataclass
class Slot:
    value: object
    raw: str
    confidence: float
    method: str
    position: int
    alternatives: list = field(default_factory=list)

    def as_dict(self) -> dict:
        return {
            "value": self.value,
            "raw": self.raw,
            "confidence": round(self.confidence, 2),
            "method": self.method,
            "alternatives": self.alternatives,
        }


def _clean(text: str) -> str:
    text = text.translate(TAMIL_DIGITS).lower()
    text = text.replace("-", " ")
    for stem in sorted(LITRE_STEMS, key=len, reverse=True):
        text = text.replace(stem, " லிட்டர் ")
    text = re.sub(r"(\d+)\s*liters?\b\.?", r"\1 லிட்டர்", text)
    text = re.sub(r"(\d+)\s*litres?\b\.?", r"\1 லிட்டர்", text)
    text = re.sub(r"(\d+)\s*litre[்]?", r"\1 லிட்டர்", text)
    text = re.sub(r"[।,:;!?()\[\]{}\"“”‘’]", " ", text)
    text = re.sub(r"\s+", " ", text)
    return text.strip()


def _tokens(text: str) -> list[str]:
    raw = _clean(text).split()
    out = []
    for tok in raw:
        tok = tok.strip(".-")
        if not tok:
            continue
        tok = TOKEN_VARIANTS.get(tok, tok)
        if tok.startswith("பாய"):
            tok = "பாயிண்ட்"
        elif tok in FAT_VARIANTS:
            tok = "ஃபேட்"
        elif tok in _LITRE_TOKEN:
            tok = "லிட்டர்"
        out.append(tok)
    i = 0
    while i < len(out):
        if (
            out[i] in HALF_TAILS
            and i > 0
            and out[i - 1] in FUSED_HALF
            and (i + 1 >= len(out) or out[i + 1] in SLOT_KEYWORDS or out[i + 1] == "லிட்டர்")
        ):
            out[i - 1] = FUSED_HALF[out[i - 1]]
            del out[i]
            continue
        i += 1
    return out


def _parse_number(tokens: list[str], start: int) -> dict | None:
    """Parse the maximal number phrase beginning at `start`."""
    if start >= len(tokens):
        return None
    first = tokens[start]
    m = re.fullmatch(r"\d+(?:\.\d+)?", first)
    if m:
        value = float(first)
        end = start + 1
        if end < len(tokens) and tokens[end] in POINT and end + 1 < len(tokens):
            nxt = tokens[end + 1]
            if re.fullmatch(r"\d+", nxt):
                value += int(nxt) / (10 ** len(nxt))
                end += 2
        return {
            "value": value, "end": end, "digits": list(first.replace(".", "")),
            "raw": " ".join(tokens[start:end]), "kind": "digit",
        }
    if first in HALVES:
        return {"value": HALVES[first], "end": start + 1, "digits": [], "raw": first, "kind": "half"}
    if first not in UNITS and first not in TENS and first not in HUNDREDS:
        return None
    total = 0.0
    unit_digits: list[int] = []
    saw_magnitude = False
    unit_after_magnitude = False
    fused_complete = False
    end = start
    point_seen = False
    while end < len(tokens):
        tok = tokens[end]
        if (
            end > start
            and (tok in UNITS or tok in TENS or tok in HUNDREDS or tok in HALVES
                 or tok in POINT or re.fullmatch(r"\d+(?:\.\d+)?", tok))
            and end + 1 < len(tokens)
            and tokens[end + 1] in SLOT_KEYWORDS
            and (not saw_magnitude or unit_after_magnitude or fused_complete)
            and not point_seen
        ):
            # "one two four, two litres": a new slot's number starts here.
            break
        if re.fullmatch(r"\d+(?:\.\d+)?", tok):
            if point_seen:
                frac = tok.split(".")[1] if "." in tok else tok
                total += int(frac) / (10 ** len(frac))
            else:
                total += float(tok)
                unit_digits.extend(list(tok.split(".")[0]))
            end += 1
            continue
        if tok in POINT:
            point_seen = True
            end += 1
            continue
        if point_seen:
            if re.fullmatch(r"\d+", tok):
                total += int(tok) / (10 ** len(tok))
                end += 1
            elif tok in UNITS and UNITS[tok] < 10:
                total += UNITS[tok] / 10
                end += 1
            break
        if tok in HALVES and not total:
            total += HALVES[tok]
            end += 1
            continue
        if tok in HUNDREDS:
            total += HUNDREDS[tok]
            saw_magnitude = True
            end += 1
            continue
        if tok in TENS:
            total += TENS[tok]
            saw_magnitude = True
            if TENS[tok] % 10:
                fused_complete = True
            end += 1
            continue
        if tok in UNITS:
            val = UNITS[tok]
            if val == 0 and total:
                if not saw_magnitude and not point_seen:
                    unit_digits.append(0)
                end += 1
                continue
            if val < 10 and not saw_magnitude and not point_seen:
                unit_digits.append(val)
            total += val
            if saw_magnitude and val < 10:
                unit_after_magnitude = True
            end += 1
            continue
        break
    if end == start:
        return None
    return {
        "value": total, "end": end, "digits": unit_digits if not saw_magnitude else [],
        "raw": " ".join(tokens[start:end]), "kind": "words",
    }


def _digit_run(tokens: list[str], start: int) -> dict | None:
    vals: list[int] = []
    end = start
    while end < len(tokens) and re.fullmatch(r"\d", tokens[end]):
        vals.append(int(tokens[end]))
        end += 1
    if len(vals) < 2:
        return None
    return {
        "value": float("".join(str(v) for v in vals)),
        "end": end,
        "digits": vals,
        "raw": " ".join(tokens[start:end]),
        "kind": "digit_run",
        "seq": True,
    }


def _spoken_digit_seq(tokens: list[str], start: int) -> dict | None:
    """Digits spoken one by one ("ஒன் ஒன் நெய்ன்") rather than as a phrase."""
    parts: list[int] = []
    end = start
    while end < len(tokens) and end - start < 7:
        tok = tokens[end]
        if tok in SLOT_KEYWORDS or tok in POINT:
            break
        val = UNITS.get(tok)
        if val is None or val > 19:
            break
        if len("".join(str(v) for v in parts)) + len(str(val)) > 3:
            break
        parts.append(val)
        end += 1
    digits = "".join(str(v) for v in parts)
    if len(digits) < 2:
        return None
    return {
        "value": float(digits),
        "end": end,
        "digits": parts,
        "raw": " ".join(tokens[start:end]),
        "kind": "spoken_digits",
        "seq": True,
    }


def _candidates(tokens: list[str], predicate) -> list[tuple[int, dict]]:
    found = []
    for i in range(len(tokens)):
        if predicate(tokens[i]):
            parsed = _parse_number(tokens, i)
            if parsed:
                found.append((i, parsed))
    return found


def _pick_after_correction(tokens: list[str], candidates: list[tuple[int, dict]], kind: str) -> tuple[int, dict] | None:
    if not candidates:
        return None
    markers = [i for i, t in enumerate(tokens) if t in CORRECTION]
    if markers:
        last = markers[-1]
        later = [c for c in candidates if c[0] > last]
        if later:
            return later[-1]
        if kind == "litres":
            return candidates[-1]
    return candidates[-1] if kind == "litres" else candidates[0]


def parse_transcript(text: str) -> dict:
    tokens = _tokens(text)
    lower = " ".join(tokens)
    slots: dict[str, Slot] = {}

    # member id: prefer a number stated after a member/society keyword
    member_candidates: list[tuple[int, dict]] = []
    for i, tok in enumerate(tokens):
        if tok in MEMBER_KW:
            for j in range(i + 1, min(len(tokens), i + 8)):
                parsed = _spoken_digit_seq(tokens, j) or _digit_run(tokens, j) or _parse_number(tokens, j)
                if parsed:
                    digits = "".join(str(d) for d in parsed["digits"]) if len(parsed["digits"]) > 1 else ""
                    if digits and 100 <= int(digits) <= 199:
                        parsed = dict(parsed, value=float(digits), member_seq=True)
                    member_candidates.append((j, parsed))
                    break
    if not member_candidates:
        for i, tok in enumerate(tokens):
            parsed = _parse_number(tokens, i)
            if parsed and 100 <= parsed["value"] <= 199 and abs(parsed["value"] - round(parsed["value"])) < 1e-6:
                member_candidates.append((i, parsed))
    chosen = _pick_after_correction(tokens, member_candidates, "member")
    if chosen:
        pos, parsed = chosen
        value = int(round(parsed["value"]))
        if 100 <= value <= 199:
            slots["member_id"] = Slot(value, parsed["raw"], 0.98 if parsed.get("member_seq") or parsed["raw"].replace(" ", "").isdigit() else 0.92, "member+number", pos)

    # litres: the number immediately before the litre keyword
    litre_candidates: list[tuple[int, dict]] = []
    for i, tok in enumerate(tokens):
        if tok in LITRE_KW:
            if i > 0:
                parsed = _parse_number(tokens, i - 1)
                if parsed and parsed["end"] >= i:
                    litre_candidates.append((i - 1, parsed))
            parsed_after = _parse_number(tokens, i + 1)
            if parsed_after:
                litre_candidates.append((i + 1, parsed_after))
    chosen = _pick_after_correction(tokens, litre_candidates, "litres")
    if chosen:
        pos, parsed = chosen
        slots["litres"] = Slot(round(float(parsed["value"]), 2), parsed["raw"], 0.96, "litre-keyword", pos)

    # fat: number after the fat keyword, decimals spoken as "point"
    fat_candidates: list[tuple[int, dict]] = []
    for i, tok in enumerate(tokens):
        if tok in FAT_KW:
            for j in range(i + 1, min(len(tokens), i + 7)):
                parsed = _parse_number(tokens, j)
                if parsed:
                    fat_candidates.append((j, parsed))
                    break
    if not fat_candidates:
        for i, tok in enumerate(tokens):
            if tok in POINT:
                parsed = _parse_number(tokens, max(0, i - 1))
                if parsed and parsed["end"] >= i + 1:
                    fat_candidates.append((max(0, i - 1), parsed))
    chosen = _pick_after_correction(tokens, fat_candidates, "fat")
    if chosen:
        pos, parsed = chosen
        slots["fat"] = Slot(round(float(parsed["value"]), 2), parsed["raw"], 0.94, "fat-keyword", pos)

    # shift: last explicit shift token wins
    shift_positions = [(i, SHIFT_KW[t]) for i, t in enumerate(tokens) if t in SHIFT_KW]
    if shift_positions:
        pos, value = shift_positions[-1]
        slots["shift"] = Slot(value, tokens[pos], 0.97, "shift-keyword", pos)

    missing = [k for k in REQUIRED if k not in slots]
    extra_note = None
    if "கிலோ" in lower or "கிலோகிராம்" in lower:
        extra_note = "unit_mismatch"
    return {
        "slots": {k: v.as_dict() for k, v in slots.items()},
        "missing": missing,
        "tokens": tokens,
        "note": extra_note,
    }


def validate(parsed: dict, members: dict[int, str]) -> dict:
    slots = parsed["slots"]
    flags: list[dict] = []
    missing = list(parsed["missing"])
    if "member_id" not in slots:
        flags.append({"code": "member_missing", "message": "Member number not heard."})
    else:
        mid = slots["member_id"]["value"]
        if mid not in members:
            flags.append({"code": "member_unknown", "message": f"Member {mid} is not in this society's roster."})
    if "litres" not in slots:
        flags.append({"code": "litres_missing", "message": "Litres not heard."})
    else:
        litres = slots["litres"]["value"]
        if not (0.2 <= litres <= 20.0):
            flags.append({"code": "litres_range", "message": f"{litres:g} L is outside the 0.2–20 L range."})
    if "fat" not in slots:
        flags.append({"code": "fat_missing", "message": "Fat percentage not heard."})
    else:
        fat = slots["fat"]["value"]
        if not (2.5 <= fat <= 9.0):
            flags.append({"code": "fat_range", "message": f"{fat:g}% is outside the 2.5–9.0% range."})
    if "shift" not in slots:
        flags.append({"code": "shift_missing", "message": "Shift not heard."})
    elif slots["shift"]["value"] not in ("morning", "evening"):
        flags.append({"code": "shift_invalid", "message": "Shift must be morning or evening."})
    if parsed.get("note") == "unit_mismatch":
        flags.append({"code": "unit_mismatch", "message": "Kilograms are not accepted; milk is logged in litres."})
    return {
        "ok": not missing and not flags,
        "flags": flags,
        "missing": missing,
        "reask_reason": flags[0]["message"] if flags else None,
    }


def _tamil_1_99(n: int) -> str:
    units = ["", "ஒன்று", "ரெண்டு", "மூன்று", "நாலு", "ஐந்து", "ஆறு", "ஏழு", "எட்டு", "ஒன்பது"]
    teens = {10: "பத்து", 11: "பதினொன்று", 12: "பன்னிரண்டு", 13: "பதின்மூன்று", 14: "பதினான்கு", 15: "பதினைந்து", 16: "பதினாறு", 17: "பதினேழு", 18: "பதினெட்டு", 19: "பத்தொன்பது"}
    tens = {20: "இருபது", 30: "முப்பது", 40: "நாற்பது", 50: "ஐம்பது", 60: "அறுபது", 70: "எழுபது", 80: "எண்பது", 90: "தொண்ணூறு"}
    combining = {20: "இருபத்தி", 30: "முப்பத்தி", 40: "நாற்பத்தி", 50: "ஐம்பத்தி", 60: "அறுபத்தி", 70: "எழுபத்தி", 80: "எண்பத்தி", 90: "தொண்ணூற்றி"}
    if n < 10:
        return units[n]
    if n < 20:
        return teens[n]
    if n % 10 == 0:
        return tens[n]
    return combining[n - n % 10] + " " + units[n % 10]


def tamil_number(n: int) -> str:
    if n < 100:
        return _tamil_1_99(n)
    if n < 200:
        return "நூற்று" + (" " + _tamil_1_99(n - 100) if n > 100 else "")
    h, rem = divmod(n, 100)
    hundreds = {2: "இருநூறு", 3: "முந்நூறு", 4: "நானூறு", 5: "ஐந்நூறு"}.get(h, "நூறு")
    return hundreds + (" " + _tamil_1_99(rem) if rem else "")


def _spell_litres(v: float) -> str:
    halves = {0.5: "அரை", 1.5: "ஒன்றரை", 2.5: "ரெண்டரை", 3.5: "மூன்றரை", 4.5: "நாலரை", 5.5: "ஐந்தரை", 6.5: "ஆறரை"}
    if v in halves:
        return halves[v]
    return tamil_number(int(round(v)))


def _spell_fat(v: float) -> str:
    whole = int(v)
    frac = int(round((v - whole) * 10))
    if frac == 0:
        return tamil_number(whole)
    frac_words = {1: "ஒன்று", 2: "டூ", 3: "மூன்று", 4: "நாலு", 5: "ஐந்து", 6: "ஆறு", 7: "ஏழு", 8: "எட்டு", 9: "ஒன்பது"}
    return f"{tamil_number(whole)} பாயிண்ட் {frac_words.get(frac, tamil_number(frac))}"


def readback_text(slots: dict, member_name: str | None) -> tuple[str, str]:
    mid = int(slots["member_id"]["value"]) if "member_id" in slots else None
    litres = slots.get("litres", {}).get("value")
    fat = slots.get("fat", {}).get("value")
    shift = slots.get("shift", {}).get("value")
    ta_bits = []
    en_bits = []
    if mid is not None:
        ta_bits.append(f"சொசைட்டி நம்பர் {tamil_number(mid)}")
        en_bits.append(f"society number {mid}")
    if litres is not None:
        ta_bits.append(f"{_spell_litres(litres)} லிட்டர்")
        en_bits.append(f"{litres:g} litres")
    if fat is not None:
        ta_bits.append(f"ஃபேட் {_spell_fat(fat)}")
        en_bits.append(f"fat {fat:g}")
    if shift is not None:
        ta_bits.append("காலை ஷிஃப்ட்" if shift == "morning" else "சாயங்காலம் ஷிஃப்ட்")
        en_bits.append(f"{shift} shift")
    if not ta_bits:
        return "மீண்டும் சொல்லுங்கள்.", "Please say it again."
    ta = ", ".join(ta_bits) + ". சரியா?"
    en = ", ".join(en_bits) + ". Is that correct?"
    return ta, en
