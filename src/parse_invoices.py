"""Parse Dollywood / Imagination Library invoice PDFs into a summary table.

Each monthly invoice lists, per age group (Group 1-6) and language (English/
Spanish), the number of books mailed (Quantity) and the dollar Amount. It also
carries three non-group line items: welcome books (item code ``LETC``, sent to
newly enrolled children), graduation books (``GRAD``), and a per-piece mailing /
shipping charge (``Mailing``, quantity = total pieces = group + LETC + GRAD).
This module extracts all of them from every PDF and writes ``invoices/summary.csv``
with one row per invoice.

Columns:
    source, month,
    G1EN_Q .. G6ES_Q, G1EN_A .. G6ES_A,                       (group books)
    LETC_EN_Q, LETC_ES_Q, GRAD_EN_Q, GRAD_ES_Q, MAIL_EN_Q, MAIL_ES_Q,
    LETC_EN_A, LETC_ES_A, GRAD_EN_A, GRAD_ES_A, MAIL_EN_A, MAIL_ES_A,
    INVOICE_TOTAL
where, e.g., ``G1EN_Q`` is the quantity of Group-1 English books, ``LETC_EN_Q`` is
the welcome-book count, ``MAIL_EN_A`` is the mailing charge, and ``INVOICE_TOTAL``
is the printed invoice total used to validate that the parsed amounts tie out.

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
# Non-group line items: welcome (LETC), graduation (GRAD), per-piece mailing (MAIL).
EXTRA_KINDS = ("LETC", "GRAD", "MAIL")

# Column order: source, month, group Qs, group As, extra Qs, extra As, total.
GROUP_Q = [f"G{g}{code}_Q" for code, _ in LANGS for g in GROUPS]
GROUP_A = [f"G{g}{code}_A" for code, _ in LANGS for g in GROUPS]
EXTRA_Q = [f"{k}_{code}_Q" for k in EXTRA_KINDS for code, _ in LANGS]
EXTRA_A = [f"{k}_{code}_A" for k in EXTRA_KINDS for code, _ in LANGS]
Q_COLS = GROUP_Q + EXTRA_Q
A_COLS = GROUP_A + EXTRA_A
COLUMNS = ["source", "month", "invoice"] + GROUP_Q + GROUP_A + EXTRA_Q + EXTRA_A + ["INVOICE_TOTAL"]

_DATE_RE = re.compile(r"(\d{4})-(\d{2})-(\d{2})")
_GROUP_RE = re.compile(r"group\s+(\d)", re.IGNORECASE)
# Printed invoice total, e.g. "Total\n$634.81" (tolerant of the leading newline).
_TOTAL_RE = re.compile(r"\bTotal\b\s*\$\s*(-?[\d,]+\.\d{2})", re.IGNORECASE)


def _item_stem(code):
    """Map an invoice 'Item Code' cell to its summary-column stem, or None.

    Returns e.g. ``G3EN``, ``LETC_ES``, ``MAIL_EN``. Language tokens seen in the
    PDFs are eng/english and spa/esp/spanish; defaults to EN when none is present.
    """
    s = " ".join(str(code or "").split()).lower()  # collapse newlines/spaces
    if "promo" in s:
        return None  # promotional items / promo shipping are not program book cost
    if "spanish" in s or re.search(r"\b(spa|esp)\b", s):
        lang = "ES"
    else:
        lang = "EN"
    g = _GROUP_RE.search(s)
    if g:
        return f"G{g.group(1)}{lang}"
    if "letc" in s:
        return f"LETC_{lang}"
    if "grad" in s:
        return f"GRAD_{lang}"
    if "mailing" in s or "mail/" in s:
        return f"MAIL_{lang}"
    return None


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


def _invoice_from_tables(tables):
    """Return the DPIL invoice number from the Date/Invoice header table."""
    for rows in tables:
        if rows and rows[0] and "Date" in str(rows[0][0]) and any("Invoice" in str(c) for c in rows[0]):
            for r in rows[1:]:
                if r and len(r) > 1 and r[1]:
                    return str(r[1]).strip().strip("*").strip()
    return ""


def _invoice_from_name(path):
    """Fallback invoice id: the trailing token of the filename (export-batch agnostic)."""
    m = re.search(r"_([^_]+)\.pdf$", Path(path).name)
    return m.group(1) if m else Path(path).name


def parse_invoice(path):
    """Return a dict: invoice month, every group/LETC/GRAD/MAIL quantity and
    amount, and the printed invoice total (for validation)."""
    record = {"month": "", "invoice": ""}
    record.update({c: 0 for c in Q_COLS})
    record.update({c: 0.0 for c in A_COLS})
    record["INVOICE_TOTAL"] = 0.0

    doc = fitz.open(path)
    page = doc[0]
    tables = _extract_tables(page)
    text = page.get_text()
    doc.close()

    record["month"] = _month_from_tables(tables) or _month_from_name(path)
    record["invoice"] = _invoice_from_tables(tables) or _invoice_from_name(path)
    m = _TOTAL_RE.search(text or "")
    printed_total = round(_num(m.group(1)), 2) if m else None

    rows = _line_item_rows(tables)
    header = rows[0] if rows else []
    try:
        qi = next(i for i, c in enumerate(header) if c and "Quantity" in str(c))
        ci = next(i for i, c in enumerate(header) if c and "Item Code" in str(c))
        ai = next(i for i, c in enumerate(header) if c and "Amount" in str(c))
    except StopIteration:
        rows = []

    for row in rows[1:]:
        if max(qi, ci, ai) >= len(row):
            continue
        stem = _item_stem(row[ci])
        if stem is None:
            continue
        record[f"{stem}_Q"] += int(_num(row[qi]))
        record[f"{stem}_A"] = round(record[f"{stem}_A"] + _num(row[ai]), 2)

    # The printed total is an independent cross-check, but newer invoice layouts
    # omit it -- fall back to the sum of parsed line items so INVOICE_TOTAL is
    # always populated.
    line_sum = round(sum(record[c] for c in A_COLS), 2)
    record["INVOICE_TOTAL"] = printed_total if (printed_total and printed_total > 0) else line_sum
    return record


def build_summary(invoices_dir=INVOICES_DIR, out_path=None):
    """Parse every PDF in ``invoices_dir`` and write ``summary.csv``.

    Returns the number of invoices parsed.
    """
    invoices_dir = Path(invoices_dir)
    out_path = Path(out_path) if out_path else invoices_dir / "summary.csv"
    pdfs = sorted(invoices_dir.glob("*.pdf"))

    issues = []

    # The same DPIL invoice can be exported more than once (different filename
    # batch prefix, identical invoice number). Dedupe by invoice number, keeping
    # the most complete copy (highest total, then newest filename), so a re-export
    # never double-counts -- and a later corrected copy supersedes an earlier draft.
    by_invoice = {}
    for pdf in pdfs:
        rec = parse_invoice(pdf)
        key = rec["invoice"] or pdf.name
        by_invoice.setdefault(key, []).append((pdf.name, rec))

    chosen = []
    for key, items in by_invoice.items():
        items.sort(key=lambda nr: (nr[1]["INVOICE_TOTAL"], nr[0]))
        name, rec = items[-1]
        if len(items) > 1:
            dropped = ", ".join(n for n, _ in items[:-1])
            issues.append(f"  duplicate invoice {key}: kept {name}, dropped {dropped}")
        chosen.append((name, rec))

    chosen.sort(key=lambda nr: (nr[1]["month"], nr[1]["invoice"], nr[0]))

    with out_path.open("w", newline="", encoding="utf-8") as fh:
        writer = csv.DictWriter(fh, fieldnames=COLUMNS)
        writer.writeheader()
        for name, rec in chosen:
            parsed = round(sum(rec[c] for c in A_COLS), 2)
            has_books = any(rec[c] for c in Q_COLS)
            total = rec["INVOICE_TOTAL"]
            if total > 0 and not has_books and parsed == 0:
                issues.append(f"  {name} ({rec['month']}): non-book invoice "
                              f"(promotional/other), ${total:,.2f} excluded from book totals")
            elif total > 0 and abs(parsed - total) > 0.01:
                issues.append(f"  {name} ({rec['month']}): parsed amounts "
                              f"${parsed:,.2f} != printed total ${total:,.2f}")
            elif total == 0 and has_books:
                issues.append(f"  {name} ({rec['month']}): quantities present "
                              f"but $0 total (unbilled/draft?)")
            row = {"source": name}
            row.update(rec)
            writer.writerow(row)

    if issues:
        print("Invoice validation notes:")
        print("\n".join(issues))
    return len(chosen)


if __name__ == "__main__":
    count = build_summary()
    print(f"Parsed {count} invoices -> {INVOICES_DIR / 'summary.csv'}")
