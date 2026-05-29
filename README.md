# ILSA Financial Reporting

Tooling for the **Imagination Library of San Antonio (ILSA)** treasurer. It turns
the raw bank and PayPal exports into:

- a typeset **fiscal report** (`report/ILSA-Financials.pdf`) — financials, an
  age-structured **enrollment-cohort projection**, and a **Methodology** appendix,
- a multi-sheet **planning workbook** (`ILSA_running_budget.xlsx`),
- a per-invoice **line-item summary** (`invoices/summary.csv`: age-group, welcome,
  graduation, and mailing quantities and amounts), and
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
- **Primary-source invoices.** Book counts *and* program cost come from parsing the
  original DPIL invoice PDFs (`parse_invoices.py` → `invoices/summary.csv`): per age
  group (1–6), welcome (`LETC`), graduation (`GRAD`), and per-piece mailing lines,
  with the printed invoice total retained for validation. Children served $=$
  group $+$ `LETC` $+$ `GRAD` $=$ the mailing piece count. Re-exported invoices are
  de-duplicated by invoice number, so a re-export can never double-count.

An auditor can trace any number in the PDF backward: narrative → `ILSA-commands.tex`
→ the generating function → the ledger rows → the original bank/PayPal/invoice
record.

### 2. Rigor — defensible methodology

- **Reconciliation built in.** The consolidated cash model ties out: PayPal `Net`
  sums exactly to the reported PayPal ending balance; per-year closing reserves
  equal the next year's opening; the full-period figures equal cash on hand.
- **Accrual vs. cash, reconciled.** Program cost is reported on an *accrual* basis
  (the invoiced amount in the invoice month) and reconciled to *cash* (bank
  payments, which clear about a month later); the running difference is the
  Dollywood payable. Reserves stay on the cash basis so they still tie to money on
  hand. The effective per-child cost (≈ \$2.38) is derived, not assumed.
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
  `scrextend`, `graphicx`, `fancyhdr`, `lastpage`, `hyperref`, `amsmath`, `amssymb`
  (Methodology equations), and `tcolorbox` (Key-Finding callout boxes).

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
     (line items: G1–6, LETC, GRAD, mailing, INVOICE_TOTAL;       │
      de-duplicated by invoice number)                            ▼
                                          src/ilsa_ledger.py   ──── shared model ────
              • consolidate ledger; net out internal PayPal↔bank transfers
              • split recurring vs. grant income
              • invoice_monthly(): invoiced (accrual) program cost + kids served
              • project_period() linear trend + reserve ±band scenarios
                                          │                         │
                   ┌──────────────────────┘                         └───────────────┐
                   ▼                                                                 ▼
        src/treasurer.py                                              src/running_budget.py
   • figures/*.png  (operating + projection charts, accrual basis)  • ILSA_running_budget.xlsx
   • src/cohort_explore.py → figures/cohort/*.png                     (Dashboard, Budget Tracker,
       (age structure, observed LETC/GRAD flows, runoff,             Income Tracker, Reserve
        enrollment + cost projection, horizon pyramids)              Scenarios, Fundraising
   • report/ILSA-commands.tex  (\newcommand defs: numbers + rows)    Planner, Instructions)
                   │
                   ▼
   report/ILSA-Financials.tex  (master)
     ├─ \input{0config}              (preamble, styling, math + Key-Finding boxes)
     ├─ \input{ILSA-commands}        (generated numbers + table rows)
     ├─ \include{0FrontMatter}       (cover)
     ├─ \include{1Introduction}      (board letter — static prose)
     ├─ \include{2Report} → \input{FiscalReport} + Enrollment-Cohort section
     └─ \appendix \include{3Appendix}   (Methodology — math formulations)
                   │
                   ▼  pdflatex ×2
        report/ILSA-Financials.pdf

  Bexar_County_ZIP_Code_Areas.geojson ──src/zip.py──► san_antonio_zones_map.html
        (report/Areas.png is a static screenshot of this map)
```

### The scripts (`src/`)

| File | Role |
|------|------|
| `ilsa_ledger.py` | **Shared library** (not run directly). Loads `ILSA_full_ledger.xlsx`, consolidates TCB + PayPal, nets out internal transfers, builds the monthly table and the invoice **accrual** model (`invoice_monthly`), and provides the **projection** (`project_period`, `reserve_scenarios`). Imported by every deliverable so they can never disagree. |
| `parse_invoices.py` | Parses the Dollywood invoice PDFs into `invoices/summary.csv`: per age group (1–6, EN/ES), welcome (`LETC`), graduation (`GRAD`), and per-piece mailing quantities/amounts, plus `INVOICE_TOTAL`. De-duplicates re-exported invoices by invoice number and validates parsed amounts against the printed total. |
| `treasurer.py` | Builds the **report**: figures (operating cost on the accrual basis), CSV summaries, the cohort assets (via `cohort_explore.build_for_report`), and `report/ILSA-commands.tex`. Kid counts and program cost come from the invoice model; cash vs. accrual is reconciled. Refreshes `invoices/summary.csv` on each run. |
| `cohort_explore.py` | **Age-structured cohort model.** Reads each Group 1–6 as an age cohort; uses the observed `LETC`/`GRAD` flows to project enrollment and program cost, the locked-in commitment runoff, and two intake-mix scenarios. Generates the Section 2.3 figures + macros (and runs standalone as a sandbox). |
| `running_budget.py` | Builds the **planning workbook** `ILSA_running_budget.xlsx`. Starting reserves, program **actuals** (invoiced kids + cost), income rows, and the reserve scenarios all come from the shared model — identical to the report. |
| `zip.py` | Renders the San Antonio service-area ZIP map to HTML from the GeoJSON. |

### The report sources (`report/`)

| File | Edit? | Purpose |
|------|-------|---------|
| `ILSA-Financials.tex` | yes | Master document; sets title/author, includes everything, switches to `\appendix`. |
| `0config.tex` | yes | Preamble, fonts, headers/footers, `\graphicspath{{../figures/}{./}}`, math packages, and the `keyfinding` callout-box style. |
| `0FrontMatter.tex` | yes | Cover page (logo, poster, title, period). |
| `1Introduction.tex` | yes | Board letter (static prose). |
| `2Report.tex` | yes | Financial-report wrapper: `\input`s `FiscalReport.tex` and adds the **Enrollment Cohorts and Forward Commitments** section (cohort figures). |
| `FiscalReport.tex` | yes | **The report body** — prose, tables, figures, and Key-Finding callout boxes. Inserts generated values via `\ilsa...` commands. Edit the wording here freely. |
| `3Appendix.tex` | yes | **Methodology appendix** — data model, classification, and the mathematical formulations (Section 8 below). |
| `ILSA-commands.tex` | **no** | **Generated** by `treasurer.py`. Holds every number and data-table row as `\newcommand`s. Do not hand-edit. |
| `Areas.png`, `Logo-*.png`, `Poster-1-ILSA.jpg` | — | Image assets. |

---

## 4. Configuration

| What | Where |
|------|-------|
| Reserve-projection horizon (`2029-12`) and annual scenario band (`±15%`) | `src/ilsa_ledger.py` → `SCENARIO_PROJECTION_END`, `SCENARIO_BAND` |
| Transaction categorization rules (Dollywood, grants, fees, transfers) | `src/ilsa_ledger.py` → `classify_tcb`, `PP_INTERNAL_TYPES` |
| Annual budget plan (budgeted kids + invoice per month) | `src/treasurer.py` → `ANNUAL_BUDGET`, `BUDGET_FY_LABEL` |
| Operational / marketing cost lines | `src/treasurer.py` → `OPERATIONAL_COSTS` |
| Cohort projection horizon, recruitment band (`±15%`), age classes (72) | `src/cohort_explore.py` → `PROJECTION_END`, `ENROLL_BAND`, `AGE_CLASSES` |
| Group → age-band labels and the welcome-rule convention | `src/cohort_explore.py` → `AGE_BAND`, `COUNT_CURRENT_GROUP` |
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
python src/treasurer.py          # report + cohort figures + ILSA-commands.tex + CSVs
python src/running_budget.py     # ILSA_running_budget.xlsx
python src/cohort_explore.py     # optional: cohort sandbox (figures + CSV tables)
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

---

## 8. The model and its mathematics

Every figure derives from one model: `src/ilsa_ledger.py` (consolidation,
invoice accrual, projection) and `src/cohort_explore.py` (the age-structured
cohort). The full derivation is in the report's **Methodology** appendix
(`report/3Appendix.tex`); the essentials follow.

### 8.1 Consolidation and reserves

Each month aggregates to income $I_t$ (recurring giving $+$ grants), expense
$E_t$ (program $+$ fees/chargebacks), net $N_t = I_t - E_t$, and the
inception-to-date cash position (reserves)

$$R_t = \sum_{j \le t} N_j = \sum_{j \le t} (I_j - E_j).$$

Internal PayPal↔bank transfers are excluded, so a gift is counted once.

### 8.2 Invoice line-item model and enrollment conservation

Each month's recipients are **disjoint** — a continuing child receives a group
book, a newly enrolled child a welcome book (`LETC`), and a graduating child a
graduation book (`GRAD`) — so children served equals the mailing piece count:

$$\mathrm{kids}(M) = \sum_{g=1}^{6} G_g(M) + \mathrm{LETC}(M) + \mathrm{GRAD}(M) = \mathrm{mailing}(M).$$

A new child enters their age group the month *after* enrolling, giving the
empirically-validated conservation law (residuals of a few children per month):

$$\sum_g G_g(M) = \sum_g G_g(M-1) + \mathrm{LETC}(M-1) - \mathrm{GRAD}(M).$$

### 8.3 Cash vs. accrual program cost

Program cost is the **invoiced** (accrual) amount in the invoice month; the bank
**payment** clears about a month later. The effective per-child cost and the
outstanding Dollywood payable are

$$c = \frac{\sum_M \mathrm{accrual}(M)}{\sum_M \mathrm{kids}(M)} \approx \$2.38, \qquad \mathrm{payable} = \sum_M \mathrm{invoiced}(M) - \sum_M \mathrm{paid}(M).$$

### 8.4 Trend estimation (ordinary least squares)

A forecastable monthly series $\{(t_i, y_i)\}_{i=0}^{n-1}$, $t_i = i$, is fit by
$\hat{y} = \beta_0 + \beta_1 t$ minimizing $\sum_i (y_i - \beta_0 - \beta_1 t_i)^2$:

$$\beta_1 = \frac{\sum_i (t_i - \bar{t})(y_i - \bar{y})}{\sum_i (t_i - \bar{t})^2}, \qquad \beta_0 = \bar{y} - \beta_1 \bar{t}, \qquad \hat{y}_t = \max(\beta_0 + \beta_1 t,\, 0).$$

This is applied to recurring giving, invoiced program cost, and the enrollment
inflow `LETC`.

### 8.5 Reserve projection and scenario bands

With current reserve $R_0$ and OLS extrapolations $\hat{I}_k, \hat{E}_k$, the
baseline path and the $\pm\beta$/year scenarios (with $\beta = 0.15$, elapsed
years $\tau_j = j/12$) are

$$R_k = R_0 + \sum_{j=1}^{k}(\hat{I}_j - \hat{E}_j), \qquad R_k^{\pm} = R_0 + \sum_{j=1}^{k}(\hat{I}_j - \hat{E}_j)(1 \pm \beta)^{\tau_j}.$$

The pessimistic case uses $(1 + \beta)$ (a widening deficit), optimistic
$(1 - \beta)$; no new grants are assumed.

### 8.6 Age-structured cohort model

Enrollment is a vector $\mathbf{n}(t) \in \mathbb{R}^{72}$ over monthly
age-of-enrollment classes (six annual groups $\times$ 12 months), seeded from the
current pyramid. Aging is a **Leslie progression matrix** $\mathbf{A}$ (a
sub-diagonal shift; class 71 graduates out) with exogenous recruitment $R(t)$ (the
`LETC` trend) distributed by an intake vector $\mathbf{w}$, $\sum_a w_a = 1$:

$$\mathbf{n}(t+1) = \mathbf{A}\,\mathbf{n}(t) + R(t)\,\mathbf{w}.$$

Total enrollment is $N(t) = \sum_a n_a(t)$ and monthly program cost is $c\,N(t)$.
Two intake mixes bracket the unobserved entry age: **today's mix**
($w_a = p_g/12$ for class $a$ in group $g$, with current stock shares $p_g$) and
**birth-fed** ($\mathbf{w} = \mathbf{e}_0$). Setting $R \equiv 0$ runs the existing
population off to graduation, giving the **locked-in commitment** — the cost of
finishing the children already enrolled, where a child in class $a$ owes $72 - a$
further monthly books:

$$\mathrm{Commitment} = c \sum_{a=0}^{71} (72 - a)\, n_a.$$
