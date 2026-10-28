"""Citeste un PDF: text, metadate si text ascuns (alb pe alb sau font minuscul).

Foloseste PyMuPDF daca e instalat, altfel pypdf. Ambele dau acelasi format.
"""
import re
from datetime import datetime, timedelta, timezone


def _parse_pdf_date(value) -> str | None:
    """'D:20261020120000+02'00'' -> ISO 8601. Returneaza None daca nu poate."""
    if not value:
        return None
    if isinstance(value, datetime):
        return value.isoformat()
    m = re.match(r"D?:?(\d{4})(\d{2})(\d{2})(\d{2})?(\d{2})?(\d{2})?([Zz+\-])?(\d{2})?'?(\d{2})?", str(value))
    if not m:
        return None
    y, mo, d, h, mi, s, sign, oh, om = m.groups()
    tz = timezone.utc
    if sign in ("+", "-") and oh:
        delta = timedelta(hours=int(oh), minutes=int(om or 0))
        tz = timezone(delta if sign == "+" else -delta)
    dt = datetime(int(y), int(mo), int(d), int(h or 0), int(mi or 0), int(s or 0), tzinfo=tz)
    return dt.isoformat()


def _is_white(rgb) -> bool:
    return all(c >= 0.95 for c in rgb)


def _read_pymupdf(path: str, min_font: float) -> dict:
    try:
        import pymupdf as fitz  # versiunile noi
    except ImportError:
        import fitz  # versiunile vechi

    doc = fitz.open(path)
    text_parts, hidden = [], []
    for page in doc:
        text_parts.append(page.get_text())
        for block in page.get_text("dict")["blocks"]:
            for line in block.get("lines", []):
                for span in line.get("spans", []):
                    t = span.get("text", "").strip()
                    if not t:
                        continue
                    c = span.get("color", 0)
                    rgb = (((c >> 16) & 255) / 255, ((c >> 8) & 255) / 255, (c & 255) / 255)
                    if _is_white(rgb) or span.get("size", 12) < min_font:
                        hidden.append(t)
    md = doc.metadata or {}
    return {
        "text": "\n".join(text_parts),
        "pages": doc.page_count,
        "metadata": {
            "producer": md.get("producer") or "",
            "creator": md.get("creator") or "",
            "created": _parse_pdf_date(md.get("creationDate")),
            "modified": _parse_pdf_date(md.get("modDate")),
        },
        "hidden_text": hidden,
        "engine": "pymupdf",
    }


def _read_pypdf(path: str, min_font: float) -> dict:
    from pypdf import PdfReader

    reader = PdfReader(path)
    text_parts, hidden = [], []
    for page in reader.pages:
        state = {"fill": (0.0, 0.0, 0.0)}

        def before(op, args, cm, tm, state=state):
            if op == b"rg" and len(args) == 3:
                state["fill"] = tuple(float(a) for a in args)
            elif op == b"g" and len(args) == 1:
                state["fill"] = (float(args[0]),) * 3

        def visit(text, cm, tm, font_dict, font_size, state=state):
            t = (text or "").strip()
            if not t:
                return
            scale = abs(tm[0]) if tm and tm[0] else 1
            size = (font_size or 12) * scale
            if _is_white(state["fill"]) or size < min_font:
                hidden.append(t)

        text_parts.append(page.extract_text(visitor_operand_before=before, visitor_text=visit) or "")
    md = reader.metadata or {}
    return {
        "text": "\n".join(text_parts),
        "pages": len(reader.pages),
        "metadata": {
            "producer": str(md.get("/Producer", "") or ""),
            "creator": str(md.get("/Creator", "") or ""),
            "created": _parse_pdf_date(md.get("/CreationDate")),
            "modified": _parse_pdf_date(md.get("/ModDate")),
        },
        "hidden_text": hidden,
        "engine": "pypdf",
    }


def read_pdf(path: str, min_font: float = 3.0) -> dict:
    try:
        return _read_pymupdf(path, min_font)
    except ImportError:
        return _read_pypdf(path, min_font)
