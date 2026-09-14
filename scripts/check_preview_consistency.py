#!/usr/bin/env python3
"""Fail if preview/ drifted from repo root outside the documented allowlist.

preview/ is a subset mirror of the published site. Corresponding files must
byte-match unless listed in eng/preview-allowlist.yml. Root-only infra
(robots, CNAME, CI, scripts) is not mirrored.

No custom preview generator. Fix: open a PR that copies/regenerates
preview/ from root for the drifted paths.
"""
from __future__ import annotations

import fnmatch
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
PREVIEW = ROOT / "preview"
ALLOWLIST = ROOT / "eng" / "preview-allowlist.yml"
FIX = (
    "FIX: open a PR that copies/regenerates preview/ from root for drifted "
    "paths. Example: `cp logos/foo.png preview/logos/foo.png` then open the PR. "
    "Do not add a custom preview generator. Intentional preview-only diffs "
    "belong in eng/preview-allowlist.yml with a one-line reason."
)


def die(msg: str) -> None:
    print(f"::error::{msg}", file=sys.stderr)
    print(msg, file=sys.stderr)
    print(FIX, file=sys.stderr)
    raise SystemExit(1)


def _unquote(s: str) -> str:
    s = s.strip()
    if len(s) >= 2 and s[0] == s[-1] and s[0] in "'\"":
        return s[1:-1]
    return s


def load_allowlist(path: Path) -> dict:
    """Minimal YAML reader for this file's schema (stdlib only).

    Supports:
      top-level keys → list of strings, or list of {path, reason, require_preview_contains}
      empty lists as []
      single-line quoted/unquoted scalars
    """
    if not path.is_file():
        die(f"missing {path.relative_to(ROOT)}")
    data: dict = {
        "allow_content_diff": [],
        "root_only": [],
        "must_mirror": [],
        "preview_only": [],
    }
    section: str | None = None
    current: dict | None = None
    req_list = False

    for raw in path.read_text(encoding="utf-8").splitlines():
        if (not raw.strip()) or raw.lstrip().startswith("#"):
            continue
        stripped = raw.strip()
        indent = len(raw) - len(raw.lstrip(" "))

        if indent == 0 and not stripped.startswith("-") and ":" in stripped:
            key, rest = stripped.split(":", 1)
            key, rest = key.strip(), rest.strip()
            if key:
                section = key
                current = None
                req_list = False
                if section not in data:
                    die(f"{path.name}: unknown top-level key {section!r}")
                if rest == "[]":
                    continue
                if rest:
                    die(f"{path.name}: unexpected scalar for {section}: {rest}")
                continue

        if section is None:
            die(f"{path.name}: content before a top-level key: {stripped}")

        if stripped == "[]":
            continue

        if section == "must_mirror":
            if stripped.startswith("- "):
                data["must_mirror"].append(_unquote(stripped[2:]))
                continue
            die(f"{path.name}: expected list item under must_mirror: {stripped}")

        if stripped.startswith("- path:"):
            req_list = False
            current = {
                "path": _unquote(stripped.split(":", 1)[1]),
                "reason": "",
                "require_preview_contains": [],
            }
            data[section].append(current)
            continue

        if current is None:
            die(f"{path.name}: unexpected line under {section}: {stripped}")

        if stripped.startswith("reason:"):
            current["reason"] = _unquote(stripped.split(":", 1)[1])
            req_list = False
            continue

        if stripped == "require_preview_contains:":
            req_list = True
            continue

        if req_list and stripped.startswith("- "):
            current["require_preview_contains"].append(_unquote(stripped[2:]))
            continue

        die(f"{path.name}: could not parse: {raw}")

    return data


def iter_files(base: Path) -> list[Path]:
    if not base.is_dir():
        return []
    return sorted(p.relative_to(base) for p in base.rglob("*") if p.is_file())


def path_matches(rel: str, pattern: str) -> bool:
    rel_n = rel.replace("\\", "/")
    pat = pattern.replace("\\", "/").lstrip("./")
    if pat.endswith("/"):
        return rel_n == pat[:-1] or rel_n.startswith(pat)
    if any(ch in pat for ch in "*?["):
        return fnmatch.fnmatch(rel_n, pat)
    return rel_n == pat


def find_entry(entries: list, rel: str):
    for e in entries:
        pat = e if isinstance(e, str) else e["path"]
        if path_matches(rel, pat):
            return e
    return None


def expand_must_mirror(patterns: list[str]) -> list[str]:
    found: list[str] = []
    for pat in patterns:
        if pat.endswith("/"):
            d = ROOT / pat[:-1]
            if d.is_dir():
                for p in d.rglob("*"):
                    if p.is_file():
                        found.append(str(p.relative_to(ROOT)).replace("\\", "/"))
        else:
            p = ROOT / pat
            if p.is_file():
                found.append(pat.replace("\\", "/"))
    return found


def main() -> int:
    allow = load_allowlist(ALLOWLIST)
    if not PREVIEW.is_dir():
        die("missing preview/ directory")

    drifted: list[str] = []
    allow_diff = allow["allow_content_diff"]
    preview_only = allow["preview_only"]
    root_only = allow["root_only"]

    preview_files = [str(p).replace("\\", "/") for p in iter_files(PREVIEW)]
    for rel in preview_files:
        prev_p = PREVIEW / rel
        root_p = ROOT / rel
        if find_entry(preview_only, rel):
            print(f"ok: {rel} preview_only")
            continue
        entry = find_entry(allow_diff, rel)
        if entry:
            text = prev_p.read_text(encoding="utf-8", errors="replace")
            missing = [s for s in entry.get("require_preview_contains") or [] if s not in text]
            if missing:
                drifted.append(
                    f"{rel} (allowlisted but preview copy missing required marker(s): "
                    + "; ".join(missing)
                    + ")"
                )
                continue
            reason = (entry.get("reason") or "").strip()
            snippet = (reason[:77] + "…") if len(reason) > 80 else reason
            print(f"ok: {rel} allowlisted content-diff ({snippet})")
            continue
        if not root_p.is_file():
            drifted.append(
                f"{rel} (in preview/, no root counterpart; add to preview_only or delete)"
            )
            continue
        if prev_p.read_bytes() != root_p.read_bytes():
            drifted.append(f"{rel} (byte-diff vs root; not on allow_content_diff)")
        else:
            print(f"ok: {rel} matches root")

    for rel in expand_must_mirror(allow["must_mirror"]):
        if find_entry(root_only, rel):
            continue
        if not (PREVIEW / rel).is_file():
            drifted.append(f"{rel} (must_mirror at root, missing under preview/)")

    if drifted:
        print("PREVIEW DRIFT:", file=sys.stderr)
        for d in drifted:
            print(f"  - {d}", file=sys.stderr)
        die(f"{len(drifted)} drifted path(s) between preview/ and root.")

    print(
        f"ok: preview/ consistent with root "
        f"({len(preview_files)} preview files; "
        f"{len(allow_diff)} allow_content_diff)"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
