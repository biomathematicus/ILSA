"""Parse Dollywood / Imagination Library invoice PDFs into a summary table.

Each monthly invoice lists, per age group (Group 1-6) and language (English/
Spanish), the number of books mailed (Quantity) and the dollar Amount. This
module extracts those figures from every PDF in the invoices folder and writes
``invoices/summary.csv`` with one row per invoice.

Columns (per the treasurer's spec):
    source, G1EN_Q .. G6EN_Q, G1ES_Q .. G6ES_Q, G1EN_A .. G6EN_A, G1ES_A .. G6ES_A
where, e.g., ``G1EN_Q`` is the quantity of Group-1 (age 1) English books and
``G1EN_A`` is the corresponding dollar amount.

The fiscal-report generator (treasurer.py) calls ``build_summary()`` on each run
so the CSV always reflects the latest invoices.
"""

import csv
import re
from pathlib import Path

import fitz  # PyMuPDF

from ilsa_ledger import INVOICES_DIR

GROUPS = range(1, 7)
LANGS = (("EN", "eng"), ("ES", "spa"))

# Column order: source, month, then all quantities, then all amounts.
Q_COLS = [f"G{g}{code}_Q" for code, _ in LANGS for g in GROUPS]
A_COLS = [f"G{g}{code}_A" for code, _ in LANGS for g in GROUPS]
COLUMNS = ["source", "month"] + Q_COLS + A_COLS

# "Group 6 eng", "Group 1 spa", tolerant of full language words.
_ITEM_RE = re.compile(r"group\s+(\d)\s+(eng|spa|english|spanish)", re.IGNORECASE)
_LANG_CODE = {"eng": "EN", "english": "EN", "spa": "ES", "spanish": "ES"}
_DATE_RE = re.compile(r"(\d{4})-(\d{2})-(\d{2})")


def _num(text):
    """Parse a numeric cell, tolerating $, commas, and stray text."""
    if text is None:
        return 0.0
    cleaned = re.sub(r"[^\d.\-]", "", str(text))
    try:
        return float(cleaned) if cleaned not in ("", "-", ".") else 0.0
    except ValueError:
        return 0.0


def _extract_tables(page):
    """Return every table on the page as a list of extracted row-lists."""
    try:
        return [t.extract() for t in page.find_tables().tables]
    except Exception:
        return []


def _line_item_rows(tables):
    """Return the invoice's line-item table rows, or []."""
    for rows in tables:
        if rows and any(cell and "Item Code" in str(cell) for cell in rows[0]):
            return rows
    return []


def _month_from_tables(tables):
    """Return the invoice month as 'YYYY-MM' from the Date/Invoice header table."""
    for rows in tables:
        if rows and rows[0] and "Date" in str(rows[0][0]) and any("Invoice" in str(c) for c in rows[0]):
            for r in rows[1:]:
                m = _DATE_RE.search(str(r[0] or "")) if r else None
                if m:
                    return f"{m.group(1)}-{m.group(2)}"
    return ""


def _month_from_name(path):
    """Fallback: parse 'YYYY-MM' from the invoice-number portion of the filename."""
    m = re.search(r"_(\d{2})(\d{2})3737", Path(path).name)
    return f"20{m.group(2)}-{m.group(1)}" if m else ""


def parse_invoice(path):
    """Return a dict: invoice month plus the 24 group quantity/amount values."""
    record = {"month": ""}
    record.update({c: 0 for c in Q_COLS})
    record.update({c: 0.0 for c in A_COLS})

    doc = fitz.open(path)
    tables = _extract_tables(doc[0])
    doc.close()

    record["month"] = _month_from_tables(tables) or _month_from_name(path)

    rows = _line_item_rows(tables)
    if not rows:
        return record

    header = rows[0]
    try:
        qi = next(i for i, c in enumerate(header) if c and "Quantity" in str(c))
        ci = next(i for i, c in enumerate(header) if c and "Item Code" in str(c))
        ai = next(i for i, c in enumerate(header) if c and "Amount" in str(c))
    except StopIteration:
        return record

    for row in rows[1:]:
        if ci >= len(row):
            continue
        m = _ITEM_RE.search(str(row[ci] or ""))
        if not m:
            continue
        group, lang = m.group(1), _LANG_CODE[m.group(2).lower()]
        record[f"G{group}{lang}_Q"] = int(_num(row[qi]))
        record[f"G{group}{lang}_A"] = round(_num(row[ai]), 2)
    return record


def build_summary(invoices_dir=INVOICES_DIR, out_path=None):
    """Parse every PDF in ``invoices_dir`` and write ``summary.csv``.

    Returns the number of invoices parsed.
    """
    invoices_dir = Path(invoices_dir)
    out_path = Path(out_path) if out_path else invoices_dir / "summary.csv"
    pdfs = sorted(invoices_dir.glob("*.pdf"))

    with out_path.open("w", newline="", encoding="utf-8") as fh:
        writer = csv.DictWriter(fh, fieldnames=COLUMNS)
        writer.writeheader()
        for pdf in pdfs:
            row = {"source": pdf.name}
            row.update(parse_invoice(pdf))
            writer.writerow(row)
    return len(pdfs)


if __name__ == "__main__":
    count = build_summary()
    print(f"Parsed {count} invoices -> {INVOICES_DIR / 'summary.csv'}")
