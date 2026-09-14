#!/usr/bin/env python3
"""Fail if this repo's openapi.json drifted from the bitlync-core pin lock.

Canonical owner: BitLync-Inc/bitlync-core (docs/openapi/bitlync-openapi-<ver>.json).
Consumers must not hand-edit openapi.json — sync via core's openapi-sync workflow
or scripts/openapi_sync_consumers.sh (opens a PR; never auto-pushes main).

Also requires preview/openapi.json to byte-match root openapi.json.

Optional: if BITLYNC_CORE_READ_TOKEN or GH_TOKEN can read private core, also
compare against the live pin on core@main (stronger cross-repo check).
"""
from __future__ import annotations

import hashlib
import json
import os
import sys
import urllib.error
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
OPENAPI = ROOT / "openapi.json"
PREVIEW = ROOT / "preview" / "openapi.json"
LOCK = ROOT / ".openapi-core-lock.json"
CORE_REPO = "BitLync-Inc/bitlync-core"
FIX = (
    "FIX: Do not hand-edit openapi.json (or preview/openapi.json). From bitlync-core run "
    "`bash scripts/openapi_sync_consumers.sh` or workflow_dispatch "
    "`OpenAPI sync` — that opens a PR on this repo. Never push the pin "
    "straight to main."
)


def die(msg: str) -> None:
    print(f"::error::{msg}", file=sys.stderr)
    print(msg, file=sys.stderr)
    print(FIX, file=sys.stderr)
    raise SystemExit(1)


def sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def load_lock() -> dict:
    if not LOCK.is_file():
        die(f"missing {LOCK.name} — {FIX}")
    return json.loads(LOCK.read_text(encoding="utf-8"))


def gh_get_raw(path: str, ref: str = "main") -> bytes | None:
    token = (
        os.environ.get("BITLYNC_CORE_READ_TOKEN")
        or os.environ.get("OPENAPI_SYNC_TOKEN")
        or os.environ.get("GH_TOKEN")
        or os.environ.get("GITHUB_TOKEN")
        or ""
    )
    if not token:
        return None
    url = f"https://api.github.com/repos/{CORE_REPO}/contents/{path}?ref={ref}"
    req = urllib.request.Request(
        url,
        headers={
            "Accept": "application/vnd.github.raw",
            "Authorization": f"Bearer {token}",
            "User-Agent": "bitlync-openapi-drift-ci",
        },
    )
    try:
        with urllib.request.urlopen(req, timeout=60) as resp:
            return resp.read()
    except urllib.error.HTTPError as e:
        print(f"note: live core fetch failed ({e.code}) for {path}; lock-only check", file=sys.stderr)
        return None


def main() -> int:
    if not OPENAPI.is_file():
        die(f"missing {OPENAPI.name}")
    if not PREVIEW.is_file():
        die(f"missing {PREVIEW.relative_to(ROOT)}")
    lock = load_lock()
    raw = OPENAPI.read_bytes()
    preview_raw = PREVIEW.read_bytes()
    if raw != preview_raw:
        die(
            "preview/openapi.json differs from openapi.json — keep both in lockstep "
            "via the core OpenAPI sync PR."
        )
    digest = sha256_bytes(raw)
    try:
        doc = json.loads(raw)
    except json.JSONDecodeError as e:
        die(f"openapi.json is not valid JSON: {e}")

    version = (doc.get("info") or {}).get("version")
    lock_ver = lock.get("version")
    lock_sha = lock.get("sha256")
    if not lock_ver or not lock_sha:
        die(f"{LOCK.name} missing version/sha256")

    if version != lock_ver:
        die(
            f"OpenAPI version drift: openapi.json info.version={version!r} but "
            f"{LOCK.name} version={lock_ver!r}."
        )
    if digest != lock_sha:
        die(
            f"OpenAPI content drift: sha256(openapi.json)={digest} but "
            f"{LOCK.name} sha256={lock_sha}. Someone edited the consumer copy "
            f"without syncing from bitlync-core."
        )

    pin_path = lock.get("pin_path") or f"docs/openapi/bitlync-openapi-{lock_ver}.json"
    live = gh_get_raw(pin_path)
    if live is not None:
        live_sha = sha256_bytes(live)
        if live_sha != digest:
            die(
                f"Cross-repo divergence: this openapi.json (sha256={digest}) != "
                f"{CORE_REPO} {pin_path} on main (sha256={live_sha})."
            )
        ver_py = gh_get_raw("api/dx/version.py")
        if ver_py is not None:
            tip = None
            for line in ver_py.decode("utf-8", errors="replace").splitlines():
                if line.startswith("__version__"):
                    tip = line.split("=", 1)[1].strip().strip("\"'")
                    break
            if tip and tip != version:
                die(
                    f"Consumer behind/ahead of core tip: openapi.json is {version}, "
                    f"bitlync-core api/dx/version.py is {tip}."
                )
        print(f"ok: openapi.json (+ preview) matches lock and live core pin {pin_path} ({version})")
    else:
        print(
            f"ok: openapi.json (+ preview) matches {LOCK.name} ({version}, sha256={digest[:12]}…). "
            "Live core compare skipped (no BITLYNC_CORE_READ_TOKEN)."
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
