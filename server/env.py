"""Load local key files without ever logging their values.

Supports a simple KEY=VALUE file, including the challenge drop at
``../.env.txt``. Values are written into ``os.environ`` only when the
variable is not already set, so an explicit shell export always wins.
"""
from __future__ import annotations

import os
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
CANDIDATES = (ROOT / ".env.txt", ROOT.parent / ".env.txt", ROOT / ".env")

_ALIASES = ("GNANI_KEY", "GNANI_API_KEY_ID", "GNANI_STT_KEY", "API_KEY", "X_API_KEY_ID")


def _parse(path: Path) -> dict[str, str]:
    out: dict[str, str] = {}
    for raw in path.read_text(encoding="utf-8", errors="replace").splitlines():
        line = raw.strip()
        if not line or line.startswith("#"):
            continue
        if line.lower().startswith("export "):
            line = line[7:].strip()
        if "=" not in line:
            # A bare token file (the challenge drop) is treated as the key.
            if len(line) >= 20 and " " not in line:
                out.setdefault("GNANI_API_KEY", line)
            continue
        name, value = line.split("=", 1)
        name = name.strip()
        value = value.strip().strip('"').strip("'")
        if name:
            out[name] = value
    return out


def gnani_live() -> bool:
    """True when a key is loaded and the run is not forced to local models.

    ``DEMO_MODE=1`` is an explicit local override; ``DEMO_MODE=0`` forces the
    live provider when a key exists. With no flag, a loaded key means live.
    """
    key = bool(os.environ.get("GNANI_API_KEY", "").strip())
    return key and os.environ.get("DEMO_MODE") != "1"


def load_env(force: bool = False) -> list[str]:
    names: list[str] = []
    for path in CANDIDATES:
        if not path.is_file():
            continue
        for name, value in _parse(path).items():
            if force or not os.environ.get(name):
                os.environ[name] = value
            names.append(name)
    if not os.environ.get("GNANI_API_KEY"):
        for alias in _ALIASES:
            value = os.environ.get(alias, "").strip()
            if value:
                os.environ["GNANI_API_KEY"] = value
                names.append(f"GNANI_API_KEY<-{alias}")
                break
    # Never echo values. Names only, and only when explicitly requested.
    if os.environ.get("PAAKURAL_ENV_DEBUG") == "1":
        print("env loaded:", ", ".join(sorted(set(names))) or "none", flush=True)
    return names
