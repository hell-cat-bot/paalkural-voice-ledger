"""Drive the live console in Chrome and capture the demo states."""
from __future__ import annotations

import json
import sys
from pathlib import Path

from playwright.sync_api import sync_playwright

ROOT = Path(__file__).resolve().parents[1]
SHOTS = ROOT / "data" / "shots"
SHOTS.mkdir(parents=True, exist_ok=True)
BASE = "http://127.0.0.1:7860/"


def snap(page, name: str) -> None:
    page.screenshot(path=str(SHOTS / f"{name}.png"), full_page=True)
    print("shot", name, flush=True)


def run_clip(page, clip: str, snr: str = "5") -> None:
    page.select_option("#clip-select", clip)
    page.select_option("#snr-select", snr)
    page.click("#run-clip")
    page.wait_for_selector("#sheet-body:not([hidden])", timeout=60000)
    page.wait_for_timeout(400)


def main() -> int:
    errors: list[str] = []
    with sync_playwright() as pw:
        browser = pw.chromium.launch(channel="chrome", headless=True)
        page = browser.new_page(viewport={"width": 1440, "height": 1000}, device_scale_factor=1)
        page.on("pageerror", lambda exc: errors.append(str(exc)))
        page.on("console", lambda msg: errors.append("console: " + msg.text) if msg.type == "error" else None)
        page.goto(BASE, wait_until="networkidle")
        page.wait_for_timeout(800)
        snap(page, "line-idle")

        run_clip(page, "b12", "5")
        print("b12 agreement:", page.text_content("#second-status"), "| stamp:", page.text_content("#sheet-stamp"))
        print("b12 slots:", page.text_content("#slots").replace("\n", " ")[:180])
        snap(page, "line-agree")
        page.click("#confirm-btn")
        page.wait_for_selector("#receipt:not([hidden])", timeout=30000)
        page.wait_for_timeout(300)
        snap(page, "line-receipt-agree")

        page.click("#next-pour")
        page.wait_for_timeout(300)
        run_clip(page, "b09", "5")
        print("b09 agreement:", page.text_content("#second-status"), "| stamp:", page.text_content("#sheet-stamp"))
        print("b09 second:", page.text_content("#second-slots").replace("\n", " "))
        print("b09 gate:", page.text_content("#confirm-btn"), "|", page.text_content("#sheet-note"))
        snap(page, "line-disagree")

        page.click("#confirm-btn")
        page.wait_for_selector("#edit-dialog[open]", timeout=5000)
        print("edit note:", page.text_content("#edit-dialog .edit-note"))
        page.fill("#edit-litres", "3.5")
        snap(page, "line-edit")
        page.click("#edit-save")
        page.wait_for_selector("#receipt:not([hidden])", timeout=30000)
        page.wait_for_timeout(300)
        snap(page, "line-receipt-corrected")

        receipt_url = page.get_attribute("#receipt-link", "href")
        slip = browser.new_page(viewport={"width": 560, "height": 900}, device_scale_factor=2)
        slip.goto("http://127.0.0.1:7860" + receipt_url, wait_until="networkidle")
        slip.wait_for_timeout(300)
        slip.screenshot(path=str(SHOTS / "receipt-slip.png"), full_page=True)
        print("shot receipt-slip")
        slip.close()

        page.click("#tab-ledger")
        page.wait_for_timeout(800)
        snap(page, "ledger")

        page.click("#tab-evidence")
        page.wait_for_selector("#evidence-run:not([hidden])", timeout=30000)
        page.wait_for_timeout(600)
        print("claim:", page.text_content("#claim")[:220])
        print("policy:", page.text_content("#policy-rows").replace("\n", " ")[:300])
        snap(page, "evidence")

        page.click("#tab-line")
        page.wait_for_timeout(300)
        page.click("#next-pour")
        page.wait_for_timeout(300)
        page.click('.src[data-src="typed"]')
        page.fill("#typed-text", "நம்பர் 127. மூன்று லிட்டர். ஃபேட் நாலு பாயிண்ட் நாலு. சாயங்காலம்.")
        page.click("#run-typed")
        page.wait_for_selector("#sheet-body:not([hidden])", timeout=30000)
        page.wait_for_timeout(300)
        print("typed stamp:", page.text_content("#sheet-stamp"), "| agreement:", page.text_content("#transcript-meta"))
        snap(page, "line-typed")

        mobile = browser.new_page(viewport={"width": 390, "height": 844}, device_scale_factor=2, is_mobile=True)
        mobile.goto(BASE, wait_until="networkidle")
        mobile.select_option("#clip-select", "b09")
        mobile.select_option("#snr-select", "5")
        mobile.click("#run-clip")
        mobile.wait_for_selector("#sheet-body:not([hidden])", timeout=60000)
        mobile.wait_for_timeout(500)
        mobile.screenshot(path=str(SHOTS / "line-mobile.png"), full_page=True)
        print("shot line-mobile")
        mobile.close()

        browser.close()
    (ROOT / "data" / "ui_errors.json").write_text(json.dumps(errors, indent=1), encoding="utf-8")
    print("errors:", errors)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
