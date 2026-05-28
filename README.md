# ILSA Financial Reporting

Tooling for the **Imagination Library of San Antonio (ILSA)** treasurer. It turns
the raw bank and PayPal exports into:

- a typeset **fiscal report** (`report/ILSA-Financials.pdf`),
- a multi-sheet **planning workbook** (`ILSA_running_budget.xlsx`),
- a per-invoice **book-count summary** (`invoices/summary.csv`), and
- a **service-area map** of San Antonio ZIP zones.

Every number in the report and the workbook is derived from one consolidated
ledger by one shared model, so the report, the tables, the figures, and the
planning workbook always tell the same story.

---

## About ILSA

The **Imagination Library of San Antonio (ILSA)** is a 501(c)(3) nonprofit and
the local program partner of **Dolly Parton's Imagination Library (DPIL)**. Its
mission is simple and concrete: mail a free, high-quality, age-appropriate book
**every month to every enrolled child in San Antonio, from birth to age five** —
nurturing early literacy, kindergarten readiness, and a lifelong love of reading,
at no cost to families.

How the program works financially:

- **Enrollment & books.** Each enrolled child receives one book per month matched
  to their age group (Groups 1–6, in English or Spanish), a welcome book at
  sign-up, and a graduation book at age five.
- **Program cost.** DPIL bills a small per-child monthly fee (≈ \$2.60/child),
  invoiced through the Dollywood Foundation. This is ILSA's dominant, steadily
  rising expense — it scales directly with the number of children served.
- **Revenue.** Two streams fund the program: **recurring giving** (individual
  PayPal donations and subscriptions, plus Bonterra online gifts) and **episodic
  grants and major gifts** deposited at the bank.
- **Strategic goals.** *Universal Enrollment* (reach every eligible child in every
  ZIP code), *Community Investment* (grow sustainable recurring support), and
  *Educational Impact* (measurable gains in early-childhood reading readiness).

Because the program's cost grows with every child enrolled while recurring giving
grows more slowly, ILSA's central financial question is one of **sustainability**:
how long current reserves and giving can carry an expanding program, and how much
new fundraising is required to keep serving more children. This reporting tool
exists to answer that question honestly and repeatably.

The fiscal report is prepared by the ILSA Treasurer, Dr. Juan B. Gutiérrez.

## A gold standard for automated financial reporting

This toolchain treats the annual fiscal report not as a document someone types,
but as a **reproducible artifact built deterministically from primary financial
records** — the same discipline reproducible research applies to scientific
results. Three principles govern the design.

### 1. Transparency — every figure is traceable to a source

- **Single source of truth.** All analysis reads one consolidated ledger
  (`ILSA_full_ledger.xlsx`), assembled from the bank and PayPal exports. Nothing
  is computed from a side spreadsheet.
- **No hand-typed numbers in the report.** Every dollar figure and every data
  table row is generated into `report/ILSA-commands.tex`; the narrative
  (`FiscalReport.tex`) only *references* those macros. A number cannot appear in
  the prose unless the code produced it from the ledger.
- **Auditable classification.** How each transaction is categorized — donation,
  grant, program cost, bank fee, internal transfer — lives in readable code
  (`ilsa_ledger.classify_tcb`), not in private spreadsheet judgment, so any
  reviewer can inspect and challenge the rules.
- **No double-counting.** Internal PayPal→bank sweeps are detected and netted
  out, so a gift is counted once (when received), never again when funds move
  between accounts.
- **Primary-source invoices.** Book counts come from parsing the original DPIL
  invoice PDFs (`parse_invoices.py` → `invoices/summary.csv`), not from
  re-keyed figures.

An auditor can trace any number in the PDF backward: narrative → `ILSA-commands.tex`
→ the generating function → the ledger rows → the original bank/PayPal/invoice
record.

### 2. Rigor — defensible methodology

- **Reconciliation built in.** The consolidated cash model ties out: PayPal `Net`
  sums exactly to the reported PayPal ending balance; per-year closing reserves
  equal the next year's opening; the full-period figures equal cash on hand.
- **Honest income treatment.** Income is split into *recurring* (forecastable) and
  *episodic grants/major gifts* (shown discretely, never trended), so one-off
  windfalls don't distort the forward outlook.
- **One model, one story.** A single projection model
  (`ilsa_ledger.project_period` / `reserve_scenarios`) feeds the report figures,
  the report tables, the narrative, **and** the planning workbook — they are
  mathematically incapable of disagreeing.
- **Explicit, conservative assumptions.** Forward scenarios are a linear baseline
  fit to past data with a stated ±15%/yr band; every assumption is a named
  constant at the top of the code, not a buried magic number.
- **Reserves stated truthfully.** Cash position is reported inception-to-date
  (actual money on hand), kept distinct from period-scoped income and expense.

### 3. Reproducibility — anyone can regenerate the exact report

- **Deterministic.** Same inputs produce byte-comparable outputs on every run;
  there are no manual steps that cannot be replayed.
- **One pipeline, documented end to end** (see *Rebuild everything from scratch*).
  Re-running the scripts and compiling twice reproduces the full report.
- **Plain-text, diffable sources.** Python, LaTeX, and CSV can be version
  controlled; the exact difference between any two editions is visible in a diff.
- **Parameterized by period.** Any reporting window (`--year`, `--start/--end`)
  is reproducible from the same code, so historical editions can be regenerated
  on demand.
- **Generated vs. authored files are separated.** `ILSA-commands.tex` is machine
  generated and never hand-edited; `FiscalReport.tex` holds human-authored prose
  and is never overwritten — regeneration refreshes the numbers without touching
  the narrative.

---

## 1. Requirements

- **Python 3.10+** with: `pandas`, `numpy`, `matplotlib`, `openpyxl`,
  `PyMuPDF` (imported as `fitz`), `scikit-learn` *(optional; the projection uses
  `numpy`)*. The map utility (`zip.py`) additionally needs `folium` and
  `geopandas`.
- A **LaTeX distribution** with `pdflatex` (MiKTeX or TeX Live). Packages used:
  `scrextend`, `graphicx`, `fancyhdr`, `lastpage`, `hyperref`.

`ILSA.bat` activates the project's conda environment (`DataAnalytics`) on the
author's machine.

---

## 2. Quick start — produce the report

From the project root (`.../ILSA/data`):

```bash
# 1. Generate figures, the LaTeX command file, and refresh the invoice summary
python src/treasurer.py

# 2. Compile the report (run twice so the "Page x of N" count resolves)
cd report
pdflatex ILSA-Financials.tex
pdflatex ILSA-Financials.tex
```

Output: `report/ILSA-Financials.pdf`.

To rebuild the planning workbook:

```bash
python src/running_budget.py        # writes ILSA_running_budget.xlsx
```

---

## 3. How the pieces fit together

```
  RAW SOURCE (provenance)                 SINGLE SOURCE OF TRUTH
  TCB/*.csv, paypal/*.csv   ──hand-merged──►  ILSA_full_ledger.xlsx
                                              (sheets: TCB_Full_Ledger,
                                                       Paypal_Full_Ledger)
                                                       │
  invoices/*.pdf ──parse_invoices.py──► invoices/summary.csv
                                                       │
                                                       ▼
                                          src/ilsa_ledger.py
                              (load + consolidate ledger; net out internal
                               PayPal↔bank transfers; split recurring vs.
                               grant income; linear projection + ±band scenarios)
                                          │                         │
                   ┌──────────────────────┘                         └───────────────┐
                   ▼                                                                 ▼
        src/treasurer.py                                              src/running_budget.py
   • figures/*.png  (4 charts)                                   • ILSA_running_budget.xlsx
   • figures/monthly_summary.csv                                   (Dashboard, Budget Tracker,
   • figures/transactions_normalized.csv                           Income Tracker, Reserve
   • report/ILSA-commands.tex  (\newcommand defs)                  Scenarios, Fundraising
                   │                                               Planner, Instructions)
                   ▼
   report/ILSA-Financials.tex  (master)
     ├─ \input{0config}                 (preamble, styling, graphicspath)
     ├─ \input{ILSA-commands}           (generated numbers + table rows)
     ├─ \include{0FrontMatter}          (cover, uses \ilsaReportTitle/\ilsaPeriod)
     ├─ \include{1Introduction}         (board letter — static prose)
     └─ \include{2Report} → \input{FiscalReport}   (the financial report body)
                   │
                   ▼  pdflatex ×2
        report/ILSA-Financials.pdf

  Bexar_County_ZIP_Code_Areas.geojson ──src/zip.py──► san_antonio_zones_map.html
        (report/Areas.png is a static screenshot of this map)
```

### The scripts (`src/`)

| File | Role |
|------|------|
| `ilsa_ledger.py` | **Shared library** (not run directly). Loads `ILSA_full_ledger.xlsx`, consolidates TCB + PayPal, nets out internal transfers, builds the monthly table, and provides the **projection model** (`project_period`, `reserve_scenarios`). Imported by both `treasurer.py` and `running_budget.py` so they can never disagree. |
| `treasurer.py` | Builds the **report**: the four figures, the CSV summaries, and `report/ILSA-commands.tex`. Also refreshes `invoices/summary.csv` on each run. |
| `running_budget.py` | Builds the **planning workbook** `ILSA_running_budget.xlsx`. Starting reserves, program actuals, income rows, and the reserve scenarios all come from the shared model. |
| `parse_invoices.py` | Parses the Dollywood invoice PDFs into `invoices/summary.csv` (per age group 1–6, English/Spanish, quantity + amount, plus invoice month). |
| `zip.py` | Renders the San Antonio service-area ZIP map to HTML from the GeoJSON. |

### The report sources (`report/`)

| File | Edit? | Purpose |
|------|-------|---------|
| `ILSA-Financials.tex` | yes | Master document; sets title/author, includes everything. |
| `0config.tex` | yes | Preamble, fonts, headers/footers, `\graphicspath{{../figures/}{./}}`. |
| `0FrontMatter.tex` | yes | Cover page (logo, poster, title, period). |
| `1Introduction.tex` | yes | Board letter (static prose). |
| `2Report.tex` | yes | Thin wrapper that `\input`s `FiscalReport.tex`. |
| `FiscalReport.tex` | yes | **The report body** — prose, tables, figures. Inserts generated values via `\ilsa...` commands. Edit the wording here freely. |
| `ILSA-commands.tex` | **no** | **Generated** by `treasurer.py`. Holds every number and data-table row as `\newcommand`s. Do not hand-edit. |
| `Areas.png`, `Logo-*.png`, `Poster-1-ILSA.jpg` | — | Image assets. |

---

## 4. Configuration

| What | Where |
|------|-------|
| Projection horizon (`2029-12`) and annual scenario band (`±15%`) | `src/ilsa_ledger.py` → `SCENARIO_PROJECTION_END`, `SCENARIO_BAND` |
| Transaction categorization rules (Dollywood, grants, fees, transfers) | `src/ilsa_ledger.py` → `classify_tcb`, `PP_INTERNAL_TYPES` |
| Annual budget plan (budgeted kids + invoice per month) | `src/treasurer.py` → `ANNUAL_BUDGET`, `BUDGET_FY_LABEL` |
| Operational / marketing cost lines | `src/treasurer.py` → `OPERATIONAL_COSTS` |
| Report title on the cover | `--title` flag (default "Fiscal Report") |
| Fundraising goal (workbook) | `src/running_budget.py` → `FUNDRAISING_GOAL` |

---

## 5. Period-specific reports

`treasurer.py` is parameterized. Income and expenses are scoped to the chosen
period; reserves are always shown inception-to-date.

```bash
python src/treasurer.py                       # full history (default)
python src/treasurer.py --year 2025           # calendar year 2025
python src/treasurer.py --start 2025-01 --end 2025-06
python src/treasurer.py --year 2025 --title "Annual Report"
python src/treasurer.py --no-report           # figures only (skip ILSA-commands.tex)
python src/treasurer.py --no-invoices         # skip refreshing invoices/summary.csv
```

After any of these, recompile the report (step 2 above). One report exists at a
time; each run overwrites the figures and `ILSA-commands.tex`.

The workbook uses a fiscal-year start:

```bash
python src/running_budget.py --fy-start 2025-08
```

---

## 6. Rebuild everything from scratch

```bash
python src/parse_invoices.py     # invoices/summary.csv  (also run by treasurer)
python src/treasurer.py          # figures + ILSA-commands.tex + CSVs
python src/running_budget.py     # ILSA_running_budget.xlsx
python src/zip.py                # service-area map (optional)
cd report && pdflatex ILSA-Financials.tex && pdflatex ILSA-Financials.tex
```

---

## 7. Notes

- **Two-pass compile:** the footer's total page count uses `lastpage`, which
  needs two `pdflatex` runs (or `latexmk -pdf`) to resolve.
- **Internal transfers:** money swept from PayPal to the bank is detected and
  excluded from income/expense, so a donation is counted once.
- **Income split:** recurring giving (PayPal + Bonterra) is the forecastable
  stream; grants and major bank deposits are episodic and shown discretely.
- **Provenance:** `ILSA_full_ledger.xlsx` is assembled by hand from the raw
  exports in `TCB/` and `paypal/`. The pipeline reads only the consolidated
  workbook, not those raw files.
