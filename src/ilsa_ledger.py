"""Shared ledger model for ILSA financial tooling.

This module is the single source of truth for reading and consolidating the raw
bank (Texas Community Bank) and PayPal exports in ``ILSA_full_ledger.xlsx``.
Both ``treasurer.py`` (the fiscal report) and ``running_budget.py`` (the planning
workbook) import from here so their numbers can never drift apart.

Key behaviors:
* Internal PayPal <-> TCB transfers are categorized and excluded from income and
  expense, so a donation is counted once (when received), not again when the
  PayPal balance is swept to the bank.
* Income splits into recurring giving (PayPal + Bonterra) and episodic grants /
  major gifts (bank deposits).
* All paths resolve against the project root (the parent of ``src/``), so scripts
  run correctly from anywhere.
"""

from pathlib import Path

import numpy as np
import pandas as pd

# --------------------------------------------------------------------------- #
# Paths (project root is the parent of this src/ directory)
# --------------------------------------------------------------------------- #
ROOT = Path(__file__).resolve().parent.parent
DATA_FILE = ROOT / "ILSA_full_ledger.xlsx"
FIG_DIR = ROOT / "figures"
REPORT_DIR = ROOT / "report"
INVOICES_DIR = ROOT / "invoices"

TCB_SHEET = "TCB_Full_Ledger"
PP_SHEET = "Paypal_Full_Ledger"

# PayPal transaction types that move money between PayPal and the bank rather
# than representing external giving. Netted out of the analysis.
PP_INTERNAL_TYPES = {"User Initiated Withdrawal", "Bank Deposit to PP Account"}

# Consolidated transaction categories.
CAT_RECURRING = "recurring_income"   # PayPal giving + Bonterra (forecastable)
CAT_GRANT = "grant_income"           # bank deposits: grants & major gifts
CAT_PROGRAM = "program_expense"      # Dollywood / Imagination Library mailings
CAT_FEE = "bank_fee"                 # bank service charges, postage
CAT_REVERSAL = "income_reversal"     # chargebacks (donor reversed a gift)
CAT_INTERNAL = "internal_transfer"   # PayPal <-> TCB sweeps (excluded)

INCOME_CATS = {CAT_RECURRING, CAT_GRANT}
EXPENSE_CATS = {CAT_PROGRAM, CAT_FEE, CAT_REVERSAL}


# --------------------------------------------------------------------------- #
# Normalization
# --------------------------------------------------------------------------- #
def to_numeric(series):
    """Strip currency symbols/commas and coerce to float."""
    return pd.to_numeric(
        series.astype(str).str.replace(r"[\$,]", "", regex=True), errors="coerce"
    )


def classify_tcb(description):
    """Map a TCB transaction description to a consolidated category."""
    u = str(description).upper()
    if "PAYPAL" in u or "INST XFER" in u:
        return CAT_INTERNAL
    if "DOLLYWOOD" in u:
        return CAT_PROGRAM
    if "CHARGEBACK" in u:
        return CAT_REVERSAL
    if "FEE" in u or "SERVICE CHARGE" in u:
        return CAT_FEE
    if "BONTERRA" in u:
        return CAT_RECURRING
    if "DDA" in u or "DEPOSIT" in u:
        return CAT_GRANT
    return "uncategorized"


def normalize_tcb(df):
    """Return a tidy TCB ledger: date, source, description, category, amount, gross."""
    df = df.copy()
    df.columns = df.columns.str.strip()
    df["date"] = pd.to_datetime(df["Processed Date"], errors="coerce")
    magnitude = to_numeric(df["Amount"]).abs()
    direction = df["Credit or Debit"].astype(str).str.strip().str.lower()
    sign = np.where(direction.eq("credit"), 1.0, -1.0)
    df["amount"] = magnitude * sign
    df["gross"] = df["amount"]  # bank entries have no separate fee
    df["category"] = df["Description"].map(classify_tcb)
    df["source"] = "TCB"
    df["description"] = df["Description"].astype(str).str.strip()
    return df[["date", "source", "description", "category", "amount", "gross"]]


def normalize_paypal(df):
    """Return a tidy PayPal ledger. ``amount`` is Net (fees included); ``gross`` is
    the pre-fee gift amount."""
    df = df.copy()
    df.columns = df.columns.str.strip()
    df["date"] = pd.to_datetime(df["Date"], errors="coerce")
    df["amount"] = to_numeric(df["Net"])
    df["gross"] = to_numeric(df["Gross"])
    status = df["Status"].astype(str).str.strip().str.lower()
    ptype = df["Type"].astype(str).str.strip()

    is_internal = (
        ptype.isin(PP_INTERNAL_TYPES)
        | ((ptype == "Website Payment") & (df["amount"] < 0))
        | status.eq("pending")  # the only pending row is the $41 bank-link wash
    )
    df["category"] = np.where(is_internal, CAT_INTERNAL, CAT_RECURRING)
    df["source"] = "PayPal"
    df["description"] = ptype
    return df[["date", "source", "description", "category", "amount", "gross"]]


def load_ledger(path=DATA_FILE):
    """Load both sheets and return one consolidated, normalized ledger.

    Columns: date, source, description, category, amount (signed net), gross
    (signed pre-fee), month (Period[M]). Rows are sorted by date.
    """
    tcb_raw = pd.read_excel(path, sheet_name=TCB_SHEET)
    pp_raw = pd.read_excel(path, sheet_name=PP_SHEET)

    ledger = pd.concat(
        [normalize_tcb(tcb_raw), normalize_paypal(pp_raw)], ignore_index=True
    )
    ledger = ledger.dropna(subset=["date"]).sort_values("date").reset_index(drop=True)
    ledger["month"] = ledger["date"].dt.to_period("M")

    unknown = ledger[ledger["category"] == "uncategorized"]
    if not unknown.empty:
        print("WARNING: uncategorized transactions (treated as neither income nor expense):")
        print(unknown[["date", "source", "description", "amount"]].to_string(index=False))

    return ledger


# --------------------------------------------------------------------------- #
# Monthly aggregation (inception-to-date)
# --------------------------------------------------------------------------- #
def build_monthly(ledger):
    """Aggregate the full ledger into a continuous monthly table.

    Internal transfers are excluded. Returns a DataFrame indexed by a gap-free
    monthly PeriodIndex with positive-magnitude income/expense columns, net flow,
    and the consolidated cumulative cash position (reserves) from inception.
    """
    active = ledger[ledger["category"] != CAT_INTERNAL]
    pivot = (
        active.pivot_table(
            index="month", columns="category", values="amount", aggfunc="sum"
        )
        .fillna(0.0)
    )

    full_index = pd.period_range(pivot.index.min(), pivot.index.max(), freq="M")
    pivot = pivot.reindex(full_index, fill_value=0.0)

    m = pd.DataFrame(index=pivot.index)
    m.index.name = "month"
    m["recurring_income"] = pivot.get(CAT_RECURRING, 0.0)
    m["grant_income"] = pivot.get(CAT_GRANT, 0.0)
    m["total_income"] = m["recurring_income"] + m["grant_income"]
    # Expense columns are stored as negative signed amounts -> flip to magnitudes.
    m["program_expense"] = -pivot.get(CAT_PROGRAM, 0.0)
    m["other_expense"] = -(pivot.get(CAT_FEE, 0.0) + pivot.get(CAT_REVERSAL, 0.0))
    m["total_expense"] = m["program_expense"] + m["other_expense"]
    m["net"] = m["total_income"] - m["total_expense"]
    m["cash_position"] = m["net"].cumsum()  # inception-to-date reserves
    return m


# --------------------------------------------------------------------------- #
# Forward projection model (shared by the report and the dashboard so every
# deliverable tells one story). The BASELINE is the linear regression of
# recurring income and program cost on past data; optimistic/pessimistic vary the
# baseline net cash flow by +/- SCENARIO_BAND per year.
# --------------------------------------------------------------------------- #
PROJECTION_MONTHS = 24                 # minimum projection horizon
SCENARIO_PROJECTION_END = "2029-12"    # projection horizon (year-end)
SCENARIO_BAND = 0.15                   # annual +/- variation around the baseline


def fit_line(values):
    """Least-squares line over sequential indices; returns (slope, intercept)."""
    values = np.asarray(values, dtype=float)
    slope, intercept = np.polyfit(np.arange(len(values)), values, 1)
    return float(slope), float(intercept)


def future_months(last_period, n):
    return [last_period + i for i in range(1, n + 1)]


def horizon_to_end(last_period, end=SCENARIO_PROJECTION_END):
    """Months from ``last_period`` to the projection end (at least PROJECTION_MONTHS)."""
    return max(PROJECTION_MONTHS, (pd.Period(end, "M") - last_period).n)


def project_period(monthly_period, horizon=PROJECTION_MONTHS):
    """Baseline linear projection of recurring income, program cost, and reserves.

    Returns None if there are too few months to fit a trend.
    """
    rec = monthly_period["recurring_income"].values
    prog = monthly_period["program_expense"].values
    n = len(rec)
    if n < 2:
        return None
    inc_slope, inc_int = fit_line(rec)
    exp_slope, exp_int = fit_line(prog)
    t_future = np.arange(n, n + horizon)
    inc_proj = np.maximum(inc_slope * t_future + inc_int, 0.0)
    exp_proj = np.maximum(exp_slope * t_future + exp_int, 0.0)
    start_cash = float(monthly_period["cash_position"].iloc[-1])
    cash_path = start_cash + np.cumsum(inc_proj - exp_proj)
    return {
        "inc_slope": inc_slope,
        "exp_slope": exp_slope,
        "inc_proj": inc_proj,
        "exp_proj": exp_proj,
        "cash_path": cash_path,
        "future": future_months(monthly_period.index[-1], horizon),
    }


def reserve_scenarios(monthly, proj, band=SCENARIO_BAND):
    """Reserve trajectories: baseline plus +/-band/yr scenarios.

    Returns (future_periods, baseline, pessimistic, optimistic). Optimistic scales
    each month's net cash flow by (1-band)^years, pessimistic by (1+band)^years.
    """
    r0 = float(monthly["cash_position"].iloc[-1])
    net = proj["inc_proj"] - proj["exp_proj"]
    years = np.array([(i + 1) / 12.0 for i in range(len(net))])
    baseline = r0 + np.cumsum(net)
    pessimistic = r0 + np.cumsum(net * (1 + band) ** years)
    optimistic = r0 + np.cumsum(net * (1 - band) ** years)
    return proj["future"], baseline, pessimistic, optimistic


# --------------------------------------------------------------------------- #
# LaTeX-safe formatting helpers (shared so currency renders consistently)
# --------------------------------------------------------------------------- #
def money(x):
    """Format a number as LaTeX currency, e.g. \\$1,234 or -\\$1,234."""
    return f"-\\${abs(x):,.0f}" if x < 0 else f"\\${x:,.0f}"


def pct(x):
    """Format a number as a LaTeX percent, e.g. 4.3\\%."""
    return f"{x:.1f}\\%"
