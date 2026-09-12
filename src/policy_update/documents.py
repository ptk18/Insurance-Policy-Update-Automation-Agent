"""Attachment type checks and deterministic document inspection.

Document contents are untrusted evidence. Inspection only reads labeled fields and
records where they were found; no other text in the document has any effect.
Image inspection is not implemented until the hosted model adapter (A01) exists.
"""

import re
from io import BytesIO
from typing import Any

from pypdf import PdfReader

MAGIC = {
    b"%PDF-": "application/pdf",
    b"\x89PNG\r\n\x1a\n": "image/png",
    b"\xff\xd8\xff": "image/jpeg",
}
MAX_INSPECTED_PAGES = 20
NAME_LABELS = r"account holder|policyholder|customer name|name"
ADDRESS_LABELS = r"service address|mailing address|address"


def sniff_content_type(content: bytes) -> str | None:
    # Trust the bytes, never the client's declared type or filename extension.
    for magic, content_type in MAGIC.items():
        if content.startswith(magic):
            return content_type
    return None


def safe_filename(name: str | None) -> str:
    base = re.sub(r"[^A-Za-z0-9._-]", "_", (name or "").rsplit("/", 1)[-1].rsplit("\\", 1)[-1])
    base = base.strip("._")[:120]
    return base or "attachment"


def _find_field(pages: list[str], labels: str) -> tuple[list[str], int | None]:
    pattern = re.compile(rf"^\s*(?:{labels})\s*:\s*(.+?)\s*$", re.IGNORECASE | re.MULTILINE)
    values: list[str] = []
    first_page = None
    for number, text in enumerate(pages, start=1):
        for match in pattern.finditer(text):
            values.append(match.group(1))
            first_page = first_page or number
    return values, first_page


def inspect_document(content: bytes, content_type: str, source: dict[str, Any]) -> dict[str, Any]:
    """Return an evidence snapshot with the same shape as the fixture snapshots."""
    result: dict[str, Any] = {
        "name": "",
        "address": "",
        "readable": False,
        "certain": False,
        "reasons": [],
        "source": {**source, "kind": "attachment", "page": None, "pages": None},
    }
    if content_type != "application/pdf":
        result["reasons"].append(
            "Image documents cannot be inspected until the hosted model adapter exists."
        )
        return result
    try:
        reader = PdfReader(BytesIO(content))
        if reader.is_encrypted:
            result["reasons"].append("The PDF is encrypted and cannot be read.")
            return result
        pages = [page.extract_text() or "" for page in reader.pages[:MAX_INSPECTED_PAGES]]
        result["source"]["pages"] = len(reader.pages)
    except Exception:  # noqa: BLE001 - any parser failure is an unreadable document
        result["reasons"].append("The PDF could not be parsed.")
        return result
    if not any(text.strip() for text in pages):
        result["reasons"].append("The PDF has no readable text layer (scanned or empty).")
        return result
    result["readable"] = True
    names, name_page = _find_field(pages, NAME_LABELS)
    addresses, address_page = _find_field(pages, ADDRESS_LABELS)
    if not names:
        result["reasons"].append("No labeled account holder or policyholder name was found.")
    elif len(set(names)) > 1:
        result["reasons"].append("The document lists more than one account holder name.")
    if not addresses:
        result["reasons"].append("No labeled service or mailing address was found.")
    elif len(set(addresses)) > 1:
        result["reasons"].append("The document lists more than one address.")
    result["name"] = names[0] if names else ""
    result["address"] = addresses[0] if addresses else ""
    result["source"]["page"] = address_page or name_page
    result["certain"] = not result["reasons"]
    return result
