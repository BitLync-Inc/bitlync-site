#!/usr/bin/env python3
"""P5: homepage normalized-tickets table fields ⊆ Ticket ∪ VendorEnvelope.

No sandbox fetch. Uses only local index.html (+ preview/index.html) and
openapi.json. A schema change that drops a field still shown on the homepage
table fails CI until the table (or OpenAPI sync) is updated.
"""
from __future__ import annotations

import json
import re
import sys
from html.parser import HTMLParser
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
OPENAPI = ROOT / "openapi.json"
PAGES = [ROOT / "index.html", ROOT / "preview" / "index.html"]
FIX = (
    "FIX: Homepage normalized-tickets columns must be fields on OpenAPI "
    "Ticket or VendorEnvelope. Update the table in index.html / preview, "
    "or sync openapi.json from bitlync-core — do not invent fields. "
    "Wren only if marketing must change the field list."
)


def die(msg: str) -> None:
    print(f"::error::{msg}", file=sys.stderr)
    print(msg, file=sys.stderr)
    print(FIX, file=sys.stderr)
    raise SystemExit(1)


class TixTableParser(HTMLParser):
    """Find <th> text inside the normalized-tickets table (.tix / tix-head)."""

    def __init__(self) -> None:
        super().__init__()
        self.in_tix = False
        self.tix_depth = 0
        self.in_thead = False
        self.in_th = False
        self.th_buf: list[str] = []
        self.headers: list[str] = []
        self._div_depth_at_tix = 0
        self._saw_tix_head = False
        self._path: list[tuple[str, dict]] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        ad = {k: (v or "") for k, v in attrs}
        classes = set(ad.get("class", "").split())
        self._path.append((tag, ad))

        if tag == "div" and "tix" in classes:
            self.in_tix = True
            self.tix_depth = 1
            return
        if self.in_tix and tag == "div":
            self.tix_depth += 1

        if tag == "div" and "tix-head" in classes:
            self._saw_tix_head = True

        if self.in_tix and tag == "thead":
            self.in_thead = True
        if self.in_tix and self.in_thead and tag == "th":
            self.in_th = True
            self.th_buf = []

    def handle_endtag(self, tag: str) -> None:
        if self.in_th and tag == "th":
            text = re.sub(r"\s+", " ", "".join(self.th_buf)).strip().lower()
            if text:
                self.headers.append(text)
            self.in_th = False
            self.th_buf = []
        if self.in_thead and tag == "thead":
            self.in_thead = False
        if self.in_tix and tag == "div":
            self.tix_depth -= 1
            if self.tix_depth <= 0:
                self.in_tix = False
        if self._path and self._path[-1][0] == tag:
            self._path.pop()
        elif self._path:
            # mismatched HTML — pop best-effort
            for i in range(len(self._path) - 1, -1, -1):
                if self._path[i][0] == tag:
                    del self._path[i:]
                    break

    def handle_data(self, data: str) -> None:
        if self.in_th:
            self.th_buf.append(data)


def extract_headers(html: str) -> list[str]:
    # Prefer the table that follows the normalized-tickets tix-head marker.
    marker = "normalized tickets"
    idx = html.lower().find(marker)
    if idx < 0:
        return []
    chunk = html[idx : idx + 4000]
    ths = re.findall(r"<th[^>]*>(.*?)</th>", chunk, flags=re.I | re.S)
    headers = []
    for th in ths:
        text = re.sub(r"<[^>]+>", "", th)
        text = re.sub(r"\s+", " ", text).strip().lower()
        if text:
            headers.append(text)
    return headers


def schema_fields(doc: dict) -> set[str]:
    schemas = (doc.get("components") or {}).get("schemas") or {}
    allowed: set[str] = set()
    for name in ("Ticket", "VendorEnvelope"):
        props = (schemas.get(name) or {}).get("properties") or {}
        allowed.update(props.keys())
    return allowed


def check_page(path: Path, allowed: set[str]) -> None:
    if not path.is_file():
        die(f"missing {path.relative_to(ROOT)}")
    html = path.read_text(encoding="utf-8")
    headers = extract_headers(html)
    if not headers:
        die(
            f"{path.relative_to(ROOT)}: could not find normalized-tickets table headers "
            f"(expected tix-head 'normalized tickets' + <th> columns)."
        )
    unknown = [h for h in headers if h not in allowed]
    if unknown:
        die(
            f"{path.relative_to(ROOT)}: normalized-tickets fields {unknown} are not in "
            f"OpenAPI Ticket|VendorEnvelope properties {sorted(allowed)}. "
            f"Table headers were {headers}."
        )
    print(f"ok: {path.relative_to(ROOT)} headers {headers} ⊆ Ticket|VendorEnvelope")


def main() -> int:
    if not OPENAPI.is_file():
        die("missing openapi.json")
    doc = json.loads(OPENAPI.read_text(encoding="utf-8"))
    allowed = schema_fields(doc)
    if "Ticket" not in ((doc.get("components") or {}).get("schemas") or {}):
        die("openapi.json missing components.schemas.Ticket")
    if not allowed:
        die("Ticket/VendorEnvelope have no properties in openapi.json")
    for page in PAGES:
        check_page(page, allowed)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
