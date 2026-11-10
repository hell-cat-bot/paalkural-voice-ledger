# PaalKural — submission entry

**Category fit:** Noise Canceller · Mixed Vibes (Tamil/Tanglish) · Main Character

**Entrant:** [your name] — solo
**Repo:** [link after pushing `C:\Hackathons\Gnani\paalkural`]
**Demo video:** `video/out/paalkural-demo.mp4` (72 s, 1080p, English narration, soft captions)
**Posts:** [LinkedIn URL] · [X URL]

---

## Written explanation

Most voice demos stop at a transcript. A milk collection line cannot. A wrong entry is money paid for milk that was never poured, and the line is loud.

PaalKural (பால்குரல்) is a working Tamil/Tanglish voice ledger for one fictional society. The operator loads a clip, speaks, or types. The same audio is decoded twice — once raw, once after a 260–3500 Hz bandlimit and a spectral gate — by **Gnani Prisma v3.0 live** (local faster-whisper is the no-key fallback). Each transcript is compiled into four slots (member, litres, fat, shift) and validated against a roster and range check. The sheet pre-fills only when both listens validate to the same four values, or when exactly one validates. If both validate but disagree, the sheet stamps CHECK and blocks the log until the operator resolves it. Every accepted turn is read back in Tamil through **Gnani Timbre v2.5 live** (edge-tts fallback) and requires a confirmation; the ledger stores an audit hash, and the receipt shows the heard transcript, the correction and the active provider.

The Evidence Lab keeps two separate books over the same 24 synthetic clips × 4 line conditions × 2 arms. Book one is the frozen local benchmark (192 runs; faster-whisper medium): the filtered front-end did **not** consistently beat the raw one (5 dB: 11/24 vs 12/24 exact; clean: 16/24 vs 22/24; our benchmark), so the product ships the two-path gate instead of selling the filter. The gate pre-filled 22/24 clean pours with 0 silent errors and 12/24 at 5 dB with 0 silent errors; at 0 dB it pre-filled 6/24 with 1 silent error, and sent everything else to readback or re-ask. Book two reruns the identical matrix through live Gnani Prisma: 192 calls, 0 errors, and the gate pre-filled 20/24 clean, 17/24 at 15 dB, 16/24 at 5 dB and 12/24 at 0 dB — **0 silent errors in every condition**. Prisma returns Tanglish, so WER against the Tamil scripts is not comparable and is excluded from the live claim. The two books are labelled separately in the UI, the README and the video; the frozen claim is never presented as a Gnani result.

This is a complete product, not a filter feature. It ships an operator console (clip / microphone / typed entry), a write-blocking agreement gate, a ledger with per-entry receipts, audit hashes and a CSV day book for the society's accounts, an Evidence Lab with frozen and live-provider artifacts, a live replay surface, provider-aware TTS caching, a health endpoint that states the active provider, and 26 automated tests covering parser variants from real transcripts, validation ranges, all five gate outcomes, provider-mode defaults, ledger export and evidence-copy guards. The stack is end to end: stdlib HTTP server, deterministic slot compiler, a fixed Tamil prompt with prompt-leak retry, JSON ledger, and a no-build vanilla front end with self-hosted fonts (no external CSS or CDN at runtime). A participant-supplied key switches the run to Prisma/Timbre; `DEMO_MODE=1` pins it local; the key is loaded from an ignored file and never printed, logged or committed.

## Models used

| Model | Where | Status |
| --- | --- | --- |
| **Gnani Prisma v3.0** STT | Live console + video + 192-call provider check (`data/benchmark-gnani.json`) | **live, used** |
| **Gnani Timbre v2.5** TTS | Tamil readback in the console and video | **live, used** |
| faster-whisper **medium** (CTranslate2), float16, CUDA, beam 5 | Frozen 192-run local benchmark; no-key fallback | local, used |
| edge-tts **ta-IN-PallaviNeural** at −6% | Readback fallback when no key is loaded | local, fallback |
| edge-tts **ta-IN-ValluvarNeural** at −18% | 24 synthetic fixture voices (Microsoft Edge TTS) | local, used |
| edge-tts **en-IN-NeerjaNeural** at −4% | Demo video narration | local, used |

The live provider check is a separate artifact. The frozen benchmark and its claim remain local faster-whisper runs so they can be reproduced without a key; the two results are never merged.

## Why this is a step beyond a typical entry

1. **A control arm, and a live-provider replication.** Every noise claim is scored raw vs filtered on the same seeded audio; the negative result is published, then the same matrix is rerun through the sponsor's model. The gate holds in both books.
2. **The gate is the product.** Disagreement between the two listens blocks the write. Silent-error rate is reported alongside exact match, because a confident wrong entry is the real failure — and the live run records 0 silent errors in every condition.
3. **Receipts carry provenance.** Heard Tamil/Tanglish transcript, correction, audit hash, amount and active provider — not just a number.
4. **Reproducible and tested.** `tools/benchmark.py` regenerates the frozen book; `tools/gnani_benchmark.py` regenerates the live book; the benchmark tool is pinned local so a loaded key cannot silently change it. 26 unit tests cover the gate, the ledger export and the evidence copy.
5. **Disclosed limits.** 24 synthetic clips, TTS voices, no field audio, and a compiler lexicon developed while inspecting this fixture set. Each claim is scoped to its own book and nothing more.

## Compliance

- Synthetic voices, names, member numbers and pours only; no real farmer, phone number, Aadhaar, PAN, account number or recorded call.
- No bought engagement, bots, paid promotion or engagement swaps.
- One entry; one award maximum acknowledged.
- A participant-supplied Gnani key powers the live UI, video and provider check. The key is never logged or committed. The frozen benchmark is local and is never described as Gnani-processed; the live provider check is reported separately with its own claim.
- Claim sentences are locked and reproduced verbatim in the app, the README and the submission; no bare accuracy claim is made without its 24-synthetic-clip scope.

## Contribution

Solo: research, product design, ASR/audio pipeline, provider integration, slot compiler, validation, ledger, UI, both benchmark books, tests and video. No third-party code beyond the listed models and libraries.
