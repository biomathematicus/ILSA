"""ILSA Treasurer - fiscal-report figures and LaTeX command definitions.

Reads the consolidated ledger (via ``ilsa_ledger``), produces the report figures
and CSV summaries, refreshes the invoice summary, and writes
``report/ILSA-commands.tex`` -- a file of ``\\newcommand`` definitions for every
number and table that varies with the data. The report prose itself lives in the
static, hand-editable ``report/FiscalReport.tex``, which simply inserts these
commands. This keeps the narrative editable while the numbers stay generated.

Income is split into recurring giving (PayPal + Bonterra, forecastable) and
episodic grants / major gifts (bank deposits, shown discretely). The reporting
period is selectable; income/expenses are period-scoped while the cash position
is shown inception-to-date (true accumulated reserves).

Usage:
    python treasurer.py                      # full history
    python treasurer.py --year 2025          # calendar year 2025
    python treasurer.py --start 2025-01 --end 2025-06
    python treasurer.py --year 2025 --no-report   # figures only
"""

import argparse

import matplotlib

matplotlib.use("Agg")  # batch-safe: never opens a blocking window

import matplotlib.pyplot as plt
import numpy as np
import pandas as pd

import ilsa_ledger as L
from ilsa_ledger import (
    CAT_GRANT,
    CAT_INTERNAL,
    CAT_PROGRAM,
    FIG_DIR,
    REPORT_DIR,
    SCENARIO_BAND,
    build_monthly,
    horizon_to_end,
    invoice_monthly,
    load_ledger,
    money,
    pct,
    project_period,
    reserve_scenarios,
)

try:
    import parse_invoices
except Exception:  # parsing is optional; report still builds without it
    parse_invoices = None

try:
    import cohort_explore  # age-structure cohort figures + commands (Section 2.x)
except Exception:
    cohort_explore = None

# --------------------------------------------------------------------------- #
# Forward budget plan (edit as the plan changes; actuals come from the ledger).
# --------------------------------------------------------------------------- #
BUDGET_FY_LABEL = "August 2025 -- July 2026"
# (month label, ledger period, budgeted kids, budgeted invoice $).
# Actual kids come from the parsed invoices (invoices/summary.csv); actual invoice
# comes from the ledger's Dollywood payments.
ANNUAL_BUDGET = [
    ("Aug", "2025-08", 370, 900),
    ("Sep", "2025-09", 425, 1000),
    ("Oct", "2025-10", 490, 1200),
    ("Nov", "2025-11", 560, 1350),
    ("Dec", "2025-12", 650, 1580),
    ("Jan", "2026-01", 750, 1800),
    ("Feb", "2026-02", 850, 2100),
    ("Mar", "2026-03", 980, 2400),
    ("Apr", "2026-04", 1120, 2750),
    ("May", "2026-05", 1300, 3200),
    ("Jun", "2026-06", 1500, 3650),
    ("Jul", "2026-07", 1700, 4200),
]

# Operational & marketing costs (item, budgeted $, frequency, notes).
# NOTE: only "Mail Box" was visible in the source workbook; add the rest here.
OPERATIONAL_COSTS = [
    ("Mail Box", 350, "yearly", ""),
]

# Forward projection (Figures 2.2-3 and 2.2-4 and the scenario table).
# The BASELINE is the linear regression of recurring income and program cost on
# past data (the same trend shown in the income/expense projection). Optimistic
# and pessimistic vary the baseline net cash flow by +/- SCENARIO_BAND per year,
# so every projection in the report tells one consistent story.
SCENARIO_PROJECTION_END = "2029-12"   # projection horizon (year-end)
SCENARIO_BAND = 0.15                  # annual +/- variation around the baseline


# --------------------------------------------------------------------------- #
# Reporting period
# --------------------------------------------------------------------------- #
def resolve_period(monthly, year=None, start=None, end=None):
    """Resolve the reporting window against available data."""
    idx = monthly.index
    if year is not None:
        start_p = pd.Period(f"{year}-01", "M")
        end_p = pd.Period(f"{year}-12", "M")
    else:
        start_p = pd.Period(start, "M") if start else idx.min()
        end_p = pd.Period(end, "M") if end else idx.max()

    start_p = max(start_p, idx.min())
    end_p = min(end_p, idx.max())
    if start_p > end_p:
        raise ValueError("Requested period is outside the available data range.")

    monthly_period = monthly.loc[start_p:end_p].copy()
    prior = monthly.loc[monthly.index < start_p]
    opening_reserves = float(prior["cash_position"].iloc[-1]) if len(prior) else 0.0

    label = f"{start_p.strftime('%B %Y')}--{end_p.strftime('%B %Y')}"
    return {
        "start": start_p,
        "end": end_p,
        "label": label,
        "monthly": monthly_period,
        "opening_reserves": opening_reserves,
    }


# --------------------------------------------------------------------------- #
# Plotting helpers (the projection model lives in ilsa_ledger)
# --------------------------------------------------------------------------- #
def _month_labels(periods):
    return [p.strftime("%Y-%m") for p in periods]


def _thin_xticks(ax, labels, max_ticks=16):
    step = max(1, len(labels) // max_ticks)
    positions = list(range(0, len(labels), step))
    ax.set_xticks(positions)
    ax.set_xticklabels([labels[i] for i in positions], rotation=45, ha="right")


# --------------------------------------------------------------------------- #
# Figures
# --------------------------------------------------------------------------- #
def plot_income_expense_actual(monthly, label, out_dir):
    labels = _month_labels(monthly.index)
    x = np.arange(len(labels))
    width = 0.42

    fig, (ax1, ax2) = plt.subplots(2, 1, figsize=(12, 10))

    ax1.bar(x - width / 2, monthly["recurring_income"], width,
            label="Recurring giving (PayPal + Bonterra)", color="#2a9d8f")
    ax1.bar(x + width / 2, monthly["program_accrual"], width,
            label="Program expense (Imagination Library, invoiced)", color="#e76f51")
    ax1.set_title("Monthly Operating Income vs. Expense", fontsize=13, fontweight="bold")
    ax1.set_ylabel("Amount ($)")
    ax1.legend()
    ax1.grid(True, axis="y", alpha=0.3)
    ax1.axhline(0, color="black", linewidth=0.8)
    _thin_xticks(ax1, labels)

    ax2.bar(x, monthly["grant_income"], width=0.6, color="#264653",
            label="Grants & major gifts (bank deposits)")
    for xi, val in zip(x, monthly["grant_income"]):
        if val > 0:
            ax2.annotate(f"${val:,.0f}", xy=(xi, val), xytext=(0, 3),
                         textcoords="offset points", ha="center", fontsize=7)
    ax2.set_title("Grants & Major Gifts (episodic)", fontsize=13, fontweight="bold")
    ax2.set_xlabel("Month")
    ax2.set_ylabel("Amount ($)")
    ax2.legend()
    ax2.grid(True, axis="y", alpha=0.3)
    _thin_xticks(ax2, labels)

    fig.suptitle(f"Monthly Income and Expense Analysis ({label.replace('--', ' to ')})",
                 fontsize=15, fontweight="bold")
    fig.tight_layout()
    fig.savefig(out_dir / "ILSA-Income-Debit-Actual.png", dpi=300, bbox_inches="tight")
    plt.close(fig)


def plot_cash_position_actual(monthly, label, opening_reserves, out_dir):
    labels = _month_labels(monthly.index)
    x = np.arange(len(labels))

    fig, ax = plt.subplots(figsize=(12, 6))
    ax.plot(x, monthly["cash_position"], marker="o", linewidth=2.5, color="#1d3557",
            label="Accumulated reserves (all income - expenses, since inception)")

    grant_months = monthly[monthly["grant_income"] > 0]
    for month, row in grant_months.iterrows():
        pos = labels.index(month.strftime("%Y-%m"))
        ax.annotate(f"+${row['grant_income']:,.0f}",
                    xy=(pos, monthly.loc[month, "cash_position"]),
                    xytext=(0, 10), textcoords="offset points",
                    fontsize=7, ha="center", color="#264653")

    ax.set_title(f"Accumulated Reserves ({label.replace('--', ' to ')})",
                 fontsize=14, fontweight="bold")
    ax.set_xlabel("Month")
    ax.set_ylabel("Reserves ($)")
    ax.legend()
    ax.grid(True, alpha=0.3)
    ax.axhline(0, color="black", linestyle="--", alpha=0.5)
    _thin_xticks(ax, labels)

    opening = opening_reserves
    closing = monthly["cash_position"].iloc[-1]
    ax.annotate(f"Opening: ${opening:,.0f}    Closing: ${closing:,.0f}",
                xy=(0.02, 0.95), xycoords="axes fraction",
                bbox=dict(boxstyle="round,pad=0.3", facecolor="lightblue", alpha=0.7))

    fig.tight_layout()
    fig.savefig(out_dir / "ILSA-Cash-Flow-Actual.png", dpi=300, bbox_inches="tight")
    plt.close(fig)


def plot_income_expense_projection(monthly, proj, label, out_dir):
    hist_labels = _month_labels(monthly.index)
    future_labels = _month_labels(proj["future"])
    all_labels = hist_labels + future_labels
    x_hist = np.arange(len(hist_labels))
    x_future = np.arange(len(hist_labels), len(all_labels))

    fig, (ax1, ax2) = plt.subplots(2, 1, figsize=(12, 10))

    ax1.plot(x_hist, monthly["recurring_income"], marker="o", color="#2a9d8f",
             linewidth=2, label="Historical recurring giving")
    ax1.plot(x_future, proj["inc_proj"], marker="s", markersize=3, color="#e76f51",
             linewidth=2, linestyle="--", label="Projected recurring giving")
    ax1.set_title("Recurring-Giving Projection (baseline; episodic grants excluded -- see Fig. 1)",
                  fontsize=13, fontweight="bold")
    ax1.set_ylabel("Monthly Income ($)")
    ax1.legend(fontsize=9)
    ax1.grid(True, alpha=0.3)
    ax1.axhline(0, color="black", linestyle="--", alpha=0.5)
    _thin_xticks(ax1, all_labels)

    ax2.plot(x_hist, monthly["program_accrual"], marker="o", color="#e76f51",
             linewidth=2, label="Historical program expense (invoiced)")
    ax2.plot(x_future, proj["exp_proj"], marker="s", color="#9d0208", linewidth=2,
             linestyle="--", label="Projected program expense")
    ax2.fill_between(x_hist, monthly["program_accrual"], alpha=0.25, color="#e76f51")
    ax2.fill_between(x_future, proj["exp_proj"], alpha=0.25, color="#9d0208")
    ax2.set_title("Program Expense Projection (Imagination Library mailings)",
                  fontsize=13, fontweight="bold")
    ax2.set_xlabel("Month")
    ax2.set_ylabel("Monthly Expense ($)")
    ax2.legend(fontsize=9)
    ax2.grid(True, alpha=0.3)
    _thin_xticks(ax2, all_labels)

    fig.suptitle(f"Income and Expense Projections (from {label.split('--')[-1]})",
                 fontsize=14, fontweight="bold")
    fig.tight_layout()
    fig.savefig(out_dir / "ILSA-Income-Debit-Projections.png", dpi=300, bbox_inches="tight")
    plt.close(fig)


def plot_cash_position_projection(monthly, proj, out_dir):
    """Projected reserves: baseline (linear trend) with +/-band/yr scenarios."""
    n = len(monthly)
    future, base, pess, opt = reserve_scenarios(monthly, proj)
    band_pct = f"{SCENARIO_BAND * 100:.0f}"

    hist_labels = _month_labels(monthly.index)
    all_labels = hist_labels + _month_labels(future)
    x_hist = np.arange(n)
    x_future = np.arange(n, n + len(future))

    fig, ax = plt.subplots(figsize=(12, 6))
    ax.plot(x_hist, monthly["cash_position"], marker="o", linewidth=2.5,
            color="#1d3557", label="Historical reserves")
    ax.fill_between(x_future, pess, opt, color="#9bb4c9", alpha=0.30)
    ax.plot(x_future, base, linewidth=2.5, linestyle="--", color="#1d3557",
            label="Baseline (linear trend)")
    ax.plot(x_future, opt, linewidth=1.8, linestyle="--", color="#2a9d8f",
            label=f"Optimistic (+{band_pct}%/yr)")
    ax.plot(x_future, pess, linewidth=1.8, linestyle="--", color="#e63946",
            label=f"Pessimistic (-{band_pct}%/yr)")

    ax.set_title(f"Projected Reserves to {future[-1].strftime('%Y')}: "
                 f"Baseline with +/-{band_pct}%/yr Scenarios",
                 fontsize=14, fontweight="bold")
    ax.set_xlabel("Month")
    ax.set_ylabel("Reserves ($)")
    ax.legend(fontsize=9)
    ax.grid(True, alpha=0.3)
    ax.axhline(0, color="black", linestyle="-", linewidth=1, alpha=0.7)
    _thin_xticks(ax, all_labels)

    start_cash = float(monthly["cash_position"].iloc[-1])
    ax.annotate(f"Reserves at period end: ${start_cash:,.0f}",
                xy=(0.02, 0.95), xycoords="axes fraction",
                bbox=dict(boxstyle="round,pad=0.3", facecolor="yellow", alpha=0.7))

    fig.tight_layout()
    fig.savefig(out_dir / "ILSA-Cash-Flow-Projections.png", dpi=300, bbox_inches="tight")
    plt.close(fig)


# --------------------------------------------------------------------------- #
# Command values (numbers + sentences)
# --------------------------------------------------------------------------- #
def metric_commands(ledger, period, proj, title):
    """Return a {LaTeX-command-name: value} dict for the headline figures."""
    monthly = period["monthly"]
    start_p, end_p = period["start"], period["end"]
    lp = ledger[(ledger["month"] >= start_p) & (ledger["month"] <= end_p)]

    n_months = len(monthly)
    recurring_total = monthly["recurring_income"].sum()
    grant_total = monthly["grant_income"].sum()
    total_income = monthly["total_income"].sum()
    program_total = monthly["program_expense"].sum()
    program_accrual_total = monthly["program_accrual"].sum()
    other_total = monthly["other_expense"].sum()
    total_expense = program_total + other_total
    net_change = monthly["net"].sum()
    reserves_end = float(monthly["cash_position"].iloc[-1])
    reserves_start = period["opening_reserves"]
    # Operating result compares recurring giving to program cost incurred (accrual),
    # consistent with the invoiced program figure reported above.
    op_result = recurring_total - program_accrual_total

    grant_rows = lp[lp["category"] == CAT_GRANT]
    program_rows = lp[lp["category"] == CAT_PROGRAM]
    if not grant_rows.empty:
        top = grant_rows.loc[grant_rows["amount"].idxmax()]
        largest_gift = money(top["amount"])
        largest_gift_month = top["month"].strftime("%B %Y")
    else:
        largest_gift, largest_gift_month = "n/a", "n/a"

    if op_result >= 0:
        op_sentence = (f"covered this cost in full, producing an operating surplus of "
                       f"{money(op_result)} for the period.")
    else:
        op_sentence = (f"did not fully cover this cost, leaving an operating deficit of "
                       f"{money(abs(op_result))} that was funded from grants and "
                       f"accumulated reserves.")

    cmd = {
        "ilsaReportTitle": title,
        "ilsaPeriod": period["label"],
        "ilsaNMonths": str(n_months),
        "ilsaTotalIncome": money(total_income),
        "ilsaIncomeMonthly": money(total_income / n_months),
        "ilsaRecurringTotal": money(recurring_total),
        "ilsaRecurringMonthly": money(recurring_total / n_months),
        "ilsaRecurringPct": pct(recurring_total / total_income * 100 if total_income else 0),
        "ilsaGrantTotal": money(grant_total),
        "ilsaGrantPct": pct(grant_total / total_income * 100 if total_income else 0),
        "ilsaGrantCount": str(len(grant_rows)),
        "ilsaLargestGift": largest_gift,
        "ilsaLargestGiftMonth": largest_gift_month,
        "ilsaProgramTotal": money(program_total),
        "ilsaProgramMonthly": money(program_total / n_months),
        "ilsaProgramCount": str(len(program_rows)),
        "ilsaOtherTotal": money(other_total),
        "ilsaTotalExpense": money(total_expense),
        "ilsaNetChange": money(net_change),
        "ilsaReservesStart": money(reserves_start),
        "ilsaReservesEnd": money(reserves_end),
        "ilsaOpSentence": op_sentence,
    }

    if proj is not None:
        cmd["ilsaRecurringSlope"] = money(proj["inc_slope"])
        cmd["ilsaProgramSlope"] = money(proj["exp_slope"])
        cmd["ilsaProjCashOneYr"] = money(proj["cash_path"][11]) if len(proj["cash_path"]) >= 12 else "n/a"
        cmd["ilsaProjCashTwoYr"] = money(proj["cash_path"][23]) if len(proj["cash_path"]) >= 24 else "n/a"
        cmd["ilsaProjEndOneYr"] = (end_p + 12).strftime("%B %Y")
        cmd["ilsaProjEndTwoYr"] = (end_p + 24).strftime("%B %Y")
    else:
        for k in ("ilsaRecurringSlope", "ilsaProgramSlope", "ilsaProjCashOneYr",
                  "ilsaProjCashTwoYr", "ilsaProjEndOneYr", "ilsaProjEndTwoYr"):
            cmd[k] = "n/a"
    return cmd


# --------------------------------------------------------------------------- #
# Command values (table rows)
# --------------------------------------------------------------------------- #
def _budget_rows(invoice_m):
    """Budget vs. actual rows. Actual kids = children served that month
    (group + welcome + graduation books mailed); actual cost = the invoiced
    (accrual) amount for that invoice month. Both come from invoices/summary.csv."""
    rows = []
    tot_bi = 0
    tot_ai = 0.0
    for label, per, bk, bi in ANNUAL_BUDGET:
        p = pd.Period(per, "M")
        in_data = p in invoice_m.index
        ak = int(invoice_m.loc[p, "kids"]) if in_data else 0
        ac = float(invoice_m.loc[p, "accrual_cost"]) if in_data else float("nan")
        has_actual = ak > 0 and pd.notna(ac)
        ak_str = f"{ak:,}" if ak else "---"
        ai_str = money(ac) if has_actual else "---"
        var_str = money(bi - ac) if has_actual else "---"
        rows.append(f"{label} & {bk:,} & {ak_str} & \\${bi:,} & {ai_str} & {var_str} \\\\")
        tot_bi += bi
        if has_actual:
            tot_ai += ac
    # Kid columns are a monthly stock, not a flow -- no meaningful total.
    total = (f"\\textbf{{Total}} & --- & --- & "
             f"\\textbf{{\\${tot_bi:,}}} & \\textbf{{{money(tot_ai)}}} & \\\\")
    return "\n".join(rows), total


def _opex_rows():
    return "\n".join(f"{item} & \\${amt:,} & {freq} & {notes} \\\\"
                     for item, amt, freq, notes in OPERATIONAL_COSTS)


def scenario_reserve_commands(monthly, proj):
    """Year-end reserve projections under baseline and +/-band/yr scenarios.

    Uses the same trajectories as the Projected Reserves figure, so the table and
    the plot are guaranteed to agree.
    """
    future, base, pess, opt = reserve_scenarios(monthly, proj)
    band_pct = f"{SCENARIO_BAND * 100:.0f}\\%"
    rows = []
    last_idx_by_year = {}
    for i, p in enumerate(future):
        last_idx_by_year[p.year] = i  # last available month index for each year
    for year in sorted(last_idx_by_year):
        i = last_idx_by_year[year]
        rows.append(f"{future[i].strftime('%b %Y')} & {money(pess[i])} & "
                    f"{money(base[i])} & {money(opt[i])} \\\\")
    return {
        "ilsaScenBand": band_pct,
        "ilsaScenEnd": future[-1].strftime("%B %Y"),
        "ilsaScenReserveRows": "\n".join(rows),
        "ilsaProjCashEnd": money(base[-1]),
        "ilsaProjCashEndOpt": money(opt[-1]),
        "ilsaProjCashEndPess": money(pess[-1]),
    }


def budget_commands(invoice_m):
    brows, btotal = _budget_rows(invoice_m)
    return {
        "ilsaBudgetFyLabel": BUDGET_FY_LABEL,
        "ilsaBudgetRows": brows,
        "ilsaBudgetTotal": btotal,
        "ilsaOpexRows": _opex_rows(),
    }


def program_reconciliation_commands(invoice_m, monthly_full, period):
    """Program cost on both bases: invoiced (accrual) vs. paid (cash, ledger).

    The Dollywood bill is the cost incurred (accrual); bank payments clear about a
    month later, so cumulative invoiced minus paid is the outstanding payable. This
    keeps the cash-based reserves intact while reporting the true program cost.
    """
    start_p, end_p = period["start"], period["end"]
    inv_p = invoice_m.loc[(invoice_m.index >= start_p) & (invoice_m.index <= end_p)]
    paid_col = monthly_full["program_expense"]

    accrual_period = float(inv_p["accrual_cost"].sum(skipna=True))
    paid_period = float(paid_col.loc[(paid_col.index >= start_p) & (paid_col.index <= end_p)].sum())
    inv_to_date = float(invoice_m.loc[invoice_m.index <= end_p, "accrual_cost"].sum(skipna=True))
    paid_to_date = float(paid_col.loc[paid_col.index <= end_p].sum())
    payable = inv_to_date - paid_to_date

    billed = inv_p[inv_p["accrual_cost"].notna()]
    kids_billed = float(billed["kids"].sum())
    per_child = accrual_period / kids_billed if kids_billed else 0.0

    # Scope the per-year reconciliation to the reporting period so its totals
    # agree with the period figures above (the reporting period can end before
    # the latest invoice, e.g. an invoice issued after the last bank activity).
    inv_scoped = invoice_m.loc[invoice_m.index <= end_p]
    paid_scoped = paid_col.loc[paid_col.index <= end_p]
    years = sorted({p.year for p in inv_scoped.index} | {p.year for p in paid_scoped.index})
    rows = []
    cum_inv = cum_paid = 0.0
    for y in years:
        iy = float(inv_scoped.loc[inv_scoped.index.year == y, "accrual_cost"].sum(skipna=True))
        py = float(paid_scoped.loc[paid_scoped.index.year == y].sum())
        if iy == 0 and py == 0:
            continue
        cum_inv += iy
        cum_paid += py
        rows.append(f"{y} & {money(iy)} & {money(py)} & {money(cum_inv - cum_paid)} \\\\")
    recon_total = (f"\\textbf{{Total}} & \\textbf{{{money(cum_inv)}}} & "
                   f"\\textbf{{{money(cum_paid)}}} & \\textbf{{{money(cum_inv - cum_paid)}}} \\\\")

    return {
        "ilsaProgramAccrual": money(accrual_period),
        "ilsaProgramPaid": money(paid_period),
        "ilsaProgramPayable": money(payable),
        "ilsaCostPerChild": f"\\${per_child:.2f}",
        "ilsaProgramReconRows": "\n".join(rows),
        "ilsaProgramReconTotal": recon_total,
    }


def year_table_commands(monthly_full):
    """Build per-calendar-year rows for the Income, Expenses, and Cash Flow tables.

    The static report template expects exactly three year columns (currently
    2024-2026) plus a total/full-period column. Reserves columns use the
    inception-to-date cash position so opening/closing tie out across years.
    """
    years = sorted({p.year for p in monthly_full.index})

    def s(col, y):
        return float(monthly_full.loc[monthly_full.index.year == y, col].sum())

    def closing(y):
        sub = monthly_full.loc[monthly_full.index.year <= y, "cash_position"]
        return float(sub.iloc[-1]) if len(sub) else 0.0

    def opening(y):
        sub = monthly_full.loc[monthly_full.index.year < y, "cash_position"]
        return float(sub.iloc[-1]) if len(sub) else 0.0

    def row(label, vals, total, bold=False, paren=False):
        fmt = (lambda v: f"({money(v)})") if paren else money
        cells = [label] + [fmt(v) for v in vals] + [fmt(total)]
        if bold:
            cells = [f"\\textbf{{{c}}}" for c in cells]
        return " & ".join(cells) + " \\\\"

    rec = [s("recurring_income", y) for y in years]
    grt = [s("grant_income", y) for y in years]
    inc = [s("total_income", y) for y in years]
    prog = [s("program_expense", y) for y in years]
    oth = [s("other_expense", y) for y in years]
    exp = [s("total_expense", y) for y in years]
    op = [opening(y) for y in years]
    net = [inc[i] - exp[i] for i in range(len(years))]
    cl = [closing(y) for y in years]

    income_rows = "\n".join([
        row("Recurring giving (PayPal + Bonterra)", rec, sum(rec)),
        row("Grants \\& major gifts (bank deposits)", grt, sum(grt)),
    ])
    expense_rows = "\n".join([
        row("Program -- Imagination Library", prog, sum(prog)),
        row("Other (fees, chargebacks)", oth, sum(oth)),
    ])
    cashflow_rows = "\n".join([
        row("Opening reserves", op, opening(years[0])),
        row("Total income", inc, sum(inc)),
        row("Total expenses", exp, sum(exp), paren=True),
        row("Net change", net, sum(net), bold=True),
        row("Closing reserves", cl, closing(years[-1]), bold=True),
    ])

    cmd = {
        "ilsaIncomeYearRows": income_rows,
        "ilsaIncomeYearTotal": row("Total income", inc, sum(inc), bold=True),
        "ilsaExpenseYearRows": expense_rows,
        "ilsaExpenseYearTotal": row("Total expenses", exp, sum(exp), bold=True),
        "ilsaCashflowYearRows": cashflow_rows,
    }
    for i, y in enumerate(years[:3]):
        cmd[f"ilsaYear{'ABC'[i]}"] = str(y)
    return cmd


# --------------------------------------------------------------------------- #
# Write the commands file
# --------------------------------------------------------------------------- #
def write_commands(commands, out_path):
    """Write a \\newcommand definition for every key/value in ``commands``."""
    lines = [
        "% ILSA-commands.tex - GENERATED by treasurer.py. Do not edit by hand.",
        "% Re-run: python src/treasurer.py --year YYYY   (or --start/--end)",
        "% The report body (FiscalReport.tex) inserts these commands.",
        "",
    ]
    for name in sorted(commands):
        lines.append(f"\\newcommand{{\\{name}}}{{{commands[name]}}}")
    out_path.write_text("\n".join(lines) + "\n", encoding="utf-8")


# --------------------------------------------------------------------------- #
# Console summary
# --------------------------------------------------------------------------- #
def print_summary(ledger, period, cmd):
    print("\n" + "=" * 60)
    print(f"ILSA CONSOLIDATED FINANCIAL SUMMARY  ({period['label'].replace('--', ' to ')})")
    print("=" * 60)
    plain = {k: str(v).replace("\\$", "$").replace("\\%", "%") for k, v in cmd.items()}
    print(f"Months: {plain['ilsaNMonths']}")
    print(f"  Recurring giving: {plain['ilsaRecurringTotal']} ({plain['ilsaRecurringPct']})")
    print(f"  Grants & major gifts: {plain['ilsaGrantTotal']} ({plain['ilsaGrantPct']}, "
          f"{plain['ilsaGrantCount']} deposits, largest {plain['ilsaLargestGift']})")
    print(f"  Total income: {plain['ilsaTotalIncome']}")
    print(f"  Program expense: {plain['ilsaProgramTotal']} ({plain['ilsaProgramCount']} payments)")
    print(f"  Net change: {plain['ilsaNetChange']}")
    print(f"  Reserves: {plain['ilsaReservesStart']} -> {plain['ilsaReservesEnd']}")
    internal = ledger[
        (ledger["category"] == CAT_INTERNAL)
        & (ledger["month"] >= period["start"])
        & (ledger["month"] <= period["end"])
    ]
    print(f"Internal PayPal<->TCB transfers netted out (in period): {len(internal)} rows, "
          f"${internal['amount'].abs().sum():,.2f} gross movement")
    print("=" * 60)


# --------------------------------------------------------------------------- #
# Main
# --------------------------------------------------------------------------- #
def parse_args():
    p = argparse.ArgumentParser(description="ILSA fiscal-report figure and command generator.")
    p.add_argument("--year", type=int, help="Calendar year to report, e.g. 2025.")
    p.add_argument("--start", help="Period start as YYYY-MM (overridden by --year).")
    p.add_argument("--end", help="Period end as YYYY-MM (overridden by --year).")
    p.add_argument("--title", default="Fiscal Report",
                   help="Report title shown on the cover (default: 'Fiscal Report').")
    p.add_argument("--no-report", action="store_true",
                   help="Regenerate figures only; skip the LaTeX commands file.")
    p.add_argument("--no-invoices", action="store_true",
                   help="Skip refreshing invoices/summary.csv.")
    return p.parse_args()


def main():
    args = parse_args()
    print("Starting ILSA cash-flow analysis...")
    if not L.DATA_FILE.exists():
        print(f"ERROR: data file not found: {L.DATA_FILE}")
        return

    FIG_DIR.mkdir(parents=True, exist_ok=True)
    REPORT_DIR.mkdir(parents=True, exist_ok=True)

    # Keep the invoice summary current so the report always reflects the PDFs.
    if not args.no_invoices and parse_invoices is not None:
        try:
            n = parse_invoices.build_summary()
            print(f"Refreshed invoice summary: {n} invoices -> {L.INVOICES_DIR / 'summary.csv'}")
        except Exception as e:
            print(f"NOTE: invoice summary not refreshed ({e}).")

    ledger = load_ledger()
    monthly_full = build_monthly(ledger)
    invoice_m = invoice_monthly()
    # Invoiced (accrual) program cost, aligned to the ledger months. This is the
    # continuous cost-incurred series the figures and projection use; the gappy
    # cash payments stay in cash_position so reserves still tie to money on hand.
    monthly_full["program_accrual"] = (
        invoice_m["accrual_cost"].reindex(monthly_full.index).fillna(0.0)
    )
    period = resolve_period(monthly_full, year=args.year, start=args.start, end=args.end)
    monthly = period["monthly"]
    print(f"Reporting period: {period['label'].replace('--', ' to ')} ({len(monthly)} months)")

    proj = project_period(monthly, horizon=horizon_to_end(monthly.index[-1]),
                          expense_col="program_accrual")
    if proj is None:
        print("NOTE: too few months in period to project; skipping projection figures.")

    print("Generating figures...")
    plot_income_expense_actual(monthly, period["label"], FIG_DIR)
    plot_cash_position_actual(monthly, period["label"], period["opening_reserves"], FIG_DIR)
    if proj is not None:
        plot_income_expense_projection(monthly, proj, period["label"], FIG_DIR)
        plot_cash_position_projection(monthly, proj, FIG_DIR)
    print(f"  Figures written to {FIG_DIR}/")

    cmd = metric_commands(ledger, period, proj, args.title)
    print_summary(ledger, period, cmd)

    if not args.no_report:
        cmd.update(budget_commands(invoice_m))
        cmd.update(year_table_commands(monthly_full))
        cmd.update(program_reconciliation_commands(invoice_m, monthly_full, period))
        if cohort_explore is not None:
            try:
                cmd.update(cohort_explore.build_for_report(FIG_DIR / "cohort"))
                print(f"  Cohort figures + commands: {FIG_DIR / 'cohort'}/")
            except Exception as e:
                print(f"NOTE: cohort assets not generated ({e}).")
        if proj is not None:
            cmd.update(scenario_reserve_commands(monthly, proj))
        write_commands(cmd, REPORT_DIR / "ILSA-commands.tex")
        print(f"  Commands: {REPORT_DIR / 'ILSA-commands.tex'}")

    monthly.round(2).to_csv(FIG_DIR / "monthly_summary.csv")
    ledger.assign(month=ledger["month"].astype(str)).to_csv(
        FIG_DIR / "transactions_normalized.csv", index=False
    )
    print(f"  Data: {FIG_DIR / 'monthly_summary.csv'}, {FIG_DIR / 'transactions_normalized.csv'}")
    print("Done.")


if __name__ == "__main__":
    main()
