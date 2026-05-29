"""EXPLORATORY cohort / age-structure analysis of the DPIL invoice population.

NOT part of the report pipeline yet. This is a sandbox for ideating figures and
tables that turn ``invoices/summary.csv`` into a forward view of program
commitments, by reading each Group 1-6 as an age cohort that ages up one group
per year until it graduates out after Group 6.

Core idea (the "runoff"): the children enrolled today are a locked-in future
obligation. With NO new enrollment, today's Group-6 kids graduate next year,
Group-5 the year after, ... and today's Group-1 kids stay the full remaining
span. Counting the current age pyramid therefore tells us the floor on future
book-months we are committed to, year by year.

The forward projection is driven by the OBSERVED enrollment flows the invoices
now expose: LETC (welcome books = new enrollments, the inflow) and GRAD
(graduation books = exits, the outflow). New enrollment is the linear trend of
LETC; graduation is endogenous (children age out at 72 months). Dollars use the
report's $/child (invoiced program cost / children served).

Run:
    python src/cohort_explore.py

Outputs (under figures/cohort/):
    enrollment_by_group.png      stacked enrollment history
    age_structure_snapshot.png   current population pyramid
    observed_flows.png           LETC inflow vs GRAD outflow, with LETC trend
    runoff_children.png          children remaining, by originating cohort
    runoff_dollars.png           annual committed $ + cumulative remaining
    group_trajectories.png       per-group enrollment over time
    enrollment_projection.png    population to 2029 (observed-LETC recruitment)
    cost_projection.png          monthly program $ to 2029
    horizon_pyramids.png         age structure at the horizon, by intake mix
    age_structure.csv            table A
    runoff_schedule.csv          table B
    cohort_matrix.csv            table C
    enrollment_projection.csv    table D
"""

import matplotlib

matplotlib.use("Agg")  # batch-safe: never opens a blocking window

import matplotlib.pyplot as plt
import numpy as np
import pandas as pd

from ilsa_ledger import INVOICES_DIR, FIG_DIR, invoice_monthly

# --------------------------------------------------------------------------- #
# Assumptions (edit here; every modeling choice is a named constant).
# --------------------------------------------------------------------------- #
NUM_GROUPS = 6                 # DPIL groups 1..6 (birth through the grad year)
LANGS = ("EN", "ES")

# Group g -> child's year of life. Group 1 = first year (birth->age 1), ...,
# Group 6 = sixth/graduation year (age 5->6). Used only for axis labels.
AGE_BAND = {
    1: "age 0-1", 2: "age 1-2", 3: "age 2-3",
    4: "age 3-4", 5: "age 4-5", 6: "age 5 (grad)",
}

# Remaining program-years for a child currently in group g, INCLUDING the
# current year: groups g, g+1, ..., 6  ->  (NUM_GROUPS - g + 1). Set False to
# count only FUTURE years (exclude the group the child is in right now).
COUNT_CURRENT_GROUP = True

# The runoff assumes no new enrollment and no attrition. It is the lower-bound
# "locked-in" obligation from children already enrolled.

# Green (youngest) -> red (graduating) so the gradient reads as "time left".
GROUP_COLORS = ["#2a9d8f", "#8ab17d", "#e9c46a", "#f4a261", "#e76f51", "#9d0208"]

OUT_DIR = FIG_DIR / "cohort"

# --------------------------------------------------------------------------- #
# Forward enrollment scenario (linear-regression recruitment + cohort aging).
# --------------------------------------------------------------------------- #
PROJECTION_END = "2029-12"     # horizon (matches the report's SCENARIO_PROJECTION_END)
ENROLL_BAND = 0.15             # +/- annual variation on recruitment (matches report band)
AGE_CLASSES = NUM_GROUPS * 12  # 72 monthly age-classes (exact aging, no 1/12 fudge)
# Dollars = projected children x the report's $/child (invoiced program cost /
# children served). Fallback only if the invoice model is unavailable.
FALLBACK_COST_PER_CHILD = 2.38


# --------------------------------------------------------------------------- #
# Helpers
# --------------------------------------------------------------------------- #
def usd(x):
    return f"-${abs(x):,.0f}" if x < 0 else f"${x:,.0f}"


def remaining_years(g):
    """Program-years still owed to a child currently in group g."""
    return (NUM_GROUPS - g + 1) if COUNT_CURRENT_GROUP else (NUM_GROUPS - g)


# --------------------------------------------------------------------------- #
# Load: monthly age structure (one row per month; groups summed over language)
# --------------------------------------------------------------------------- #
def load_enrollment():
    """Return (monthly_qty, monthly_amt): DataFrames indexed by Period[M] with
    columns g1..g6 (book quantity and $ amount, summed over EN+ES per month)."""
    df = pd.read_csv(INVOICES_DIR / "summary.csv")
    df = df[df["month"].notna() & (df["month"].astype(str).str.strip() != "")]

    q_cols = {g: [f"G{g}{lng}_Q" for lng in LANGS] for g in range(1, NUM_GROUPS + 1)}
    a_cols = {g: [f"G{g}{lng}_A" for lng in LANGS] for g in range(1, NUM_GROUPS + 1)}

    qty = pd.DataFrame(index=df.index)
    amt = pd.DataFrame(index=df.index)
    for g in range(1, NUM_GROUPS + 1):
        qty[f"g{g}"] = df[q_cols[g]].apply(pd.to_numeric, errors="coerce").fillna(0).sum(axis=1)
        amt[f"g{g}"] = df[a_cols[g]].apply(pd.to_numeric, errors="coerce").fillna(0).sum(axis=1)
    qty["month"] = pd.PeriodIndex(df["month"].astype(str), freq="M")
    amt["month"] = qty["month"]

    # Sum across any duplicate invoices in the same month (e.g. credit notes).
    qty = qty.groupby("month").sum().sort_index()
    amt = amt.groupby("month").sum().sort_index()
    return qty, amt


# --------------------------------------------------------------------------- #
# Tables
# --------------------------------------------------------------------------- #
def age_structure_table(qty, amt, cost_per_child):
    """Table A: latest-month pyramid with committed totals on the report basis.

    ``committed_dollars`` uses the report's $/child (full Dollywood bill);
    ``cost_per_book`` is kept only as an informational invoice-derived figure.
    """
    g_qty = qty.iloc[-1]
    g_amt = amt.iloc[-1]
    total_q = g_qty.sum()
    total_a = g_amt.sum()
    blended = total_a / total_q if total_q else 0.0

    rows = []
    for g in range(1, NUM_GROUPS + 1):
        n = float(g_qty[f"g{g}"])
        a = float(g_amt[f"g{g}"])
        book_cost = (a / n) if n else blended
        ry = remaining_years(g)
        book_months = n * 12 * ry
        rows.append({
            "group": g,
            "age_band": AGE_BAND[g],
            "children": int(n),
            "pct_of_pop": (n / total_q * 100) if total_q else 0.0,
            "cost_per_book": round(book_cost, 2),
            "remaining_years": ry,
            "remaining_book_months": int(book_months),
            "committed_dollars": book_months * cost_per_child,
        })
    out = pd.DataFrame(rows)
    out.loc["total"] = {
        "group": "TOTAL", "age_band": "", "children": int(total_q),
        "pct_of_pop": 100.0, "cost_per_book": round(blended, 2),
        "remaining_years": "", "remaining_book_months": int(out["remaining_book_months"].sum()),
        "committed_dollars": out["committed_dollars"].sum(),
    }
    return out, blended


def runoff_by_year(qty, cost_per_child):
    """Active children per future year k (no new enrollment), split by the
    originating group, plus the annual committed $ staircase.

    Returns (matrix, schedule):
      matrix[k, g] = children from today's group g still active at year k.
      schedule     = per-year active children, annual $, cumulative remaining $.
    """
    n = qty.iloc[-1][[f"g{g}" for g in range(1, NUM_GROUPS + 1)]].to_numpy(dtype=float)
    horizon = NUM_GROUPS  # year NUM_GROUPS: everyone has graduated

    # matrix: rows = future year k (0..horizon), cols = originating group 1..6
    matrix = np.zeros((horizon + 1, NUM_GROUPS))
    for k in range(horizon + 1):
        for gi, g in enumerate(range(1, NUM_GROUPS + 1)):
            if g + k <= NUM_GROUPS:        # child in group g is in group g+k at year k
                matrix[k, gi] = n[gi]

    active = matrix.sum(axis=1)
    annual_cost = active * 12 * cost_per_child
    # Remaining commitment from year k onward.
    cumulative_remaining = np.cumsum(annual_cost[::-1])[::-1]

    sched = pd.DataFrame({
        "year_offset": np.arange(horizon + 1),
        "active_children": active.astype(int),
        "annual_committed_dollars": annual_cost.round(0),
        "remaining_commitment_dollars": cumulative_remaining.round(0),
    })
    return matrix, sched


# --------------------------------------------------------------------------- #
# Figures
# --------------------------------------------------------------------------- #
def _month_labels(periods):
    return [p.strftime("%Y-%m") for p in periods]


def _thin_xticks(ax, labels, max_ticks=16):
    step = max(1, len(labels) // max_ticks)
    positions = list(range(0, len(labels), step))
    ax.set_xticks(positions)
    ax.set_xticklabels([labels[i] for i in positions], rotation=45, ha="right")


def plot_enrollment_by_group(qty, out_dir):
    labels = _month_labels(qty.index)
    x = np.arange(len(labels))
    fig, ax = plt.subplots(figsize=(12, 6))
    bottom = np.zeros(len(labels))
    for gi, g in enumerate(range(1, NUM_GROUPS + 1)):
        vals = qty[f"g{g}"].to_numpy()
        ax.bar(x, vals, bottom=bottom, color=GROUP_COLORS[gi],
               label=f"Group {g} ({AGE_BAND[g]})")
        bottom += vals
    for xi, tot in zip(x, bottom):
        ax.annotate(f"{int(tot):,}", xy=(xi, tot), xytext=(0, 3),
                    textcoords="offset points", ha="center", fontsize=7)
    ax.set_title("ILSA Enrollment by Age Group (books mailed per month)",
                 fontsize=14, fontweight="bold")
    ax.set_xlabel("Invoice month")
    ax.set_ylabel("Children (books mailed)")
    ax.set_xticks(x)
    ax.set_xticklabels(labels, rotation=45, ha="right")
    ax.legend(ncol=3, fontsize=8)
    ax.grid(True, axis="y", alpha=0.3)
    fig.tight_layout()
    fig.savefig(out_dir / "enrollment_by_group.png", dpi=300, bbox_inches="tight")
    plt.close(fig)


def plot_age_structure(qty, out_dir):
    g_qty = qty.iloc[-1]
    latest = qty.index[-1].strftime("%B %Y")
    groups = list(range(1, NUM_GROUPS + 1))
    y = np.arange(len(groups))
    vals = [g_qty[f"g{g}"] for g in groups]

    fig, ax = plt.subplots(figsize=(9, 6))
    ax.barh(y, vals, color=GROUP_COLORS)
    for yi, v in zip(y, vals):
        ax.annotate(f"{int(v):,}", xy=(v, yi), xytext=(4, 0),
                    textcoords="offset points", va="center", fontsize=9)
    ax.set_yticks(y)
    ax.set_yticklabels([f"Group {g}\n{AGE_BAND[g]}" for g in groups])
    ax.invert_yaxis()  # Group 1 (youngest) on top
    ax.set_title(f"Current Age Structure ({latest})\nbasis for the commitment runoff",
                 fontsize=13, fontweight="bold")
    ax.set_xlabel("Children enrolled")
    ax.grid(True, axis="x", alpha=0.3)
    fig.tight_layout()
    fig.savefig(out_dir / "age_structure_snapshot.png", dpi=300, bbox_inches="tight")
    plt.close(fig)


def _year_labels(latest_period, horizon):
    out = []
    for k in range(horizon + 1):
        p = latest_period + 12 * k
        tag = "Now" if k == 0 else f"+{k}y"
        out.append(f"{tag}\n{p.strftime('%b %Y')}")
    return out


def plot_runoff_children(qty, matrix, out_dir):
    horizon = matrix.shape[0] - 1
    x = np.arange(horizon + 1)
    labels = _year_labels(qty.index[-1], horizon)

    fig, ax = plt.subplots(figsize=(11, 6))
    bottom = np.zeros(horizon + 1)
    for gi, g in enumerate(range(1, NUM_GROUPS + 1)):
        ax.bar(x, matrix[:, gi], bottom=bottom, color=GROUP_COLORS[gi],
               label=f"From today's Group {g}")
        bottom += matrix[:, gi]
    for xi, tot in zip(x, bottom):
        ax.annotate(f"{int(tot):,}", xy=(xi, tot), xytext=(0, 3),
                    textcoords="offset points", ha="center", fontsize=8, fontweight="bold")
    ax.set_title("Commitment Runoff -- Children Still Enrolled\n"
                 "(today's population aged forward, no new enrollment)",
                 fontsize=13, fontweight="bold")
    ax.set_xlabel("Years from now")
    ax.set_ylabel("Children still receiving books")
    ax.set_xticks(x)
    ax.set_xticklabels(labels)
    ax.legend(ncol=2, fontsize=8)
    ax.grid(True, axis="y", alpha=0.3)
    fig.tight_layout()
    fig.savefig(out_dir / "runoff_children.png", dpi=300, bbox_inches="tight")
    plt.close(fig)


def plot_runoff_dollars(qty, sched, out_dir):
    horizon = len(sched) - 1
    x = np.arange(horizon + 1)
    labels = _year_labels(qty.index[-1], horizon)

    fig, ax = plt.subplots(figsize=(11, 6))
    ax.bar(x, sched["annual_committed_dollars"], color="#e76f51",
           label="Annual committed program $ (this cohort)")
    for xi, v in zip(x, sched["annual_committed_dollars"]):
        ax.annotate(usd(v), xy=(xi, v), xytext=(0, 3), textcoords="offset points",
                    ha="center", fontsize=8)
    ax.set_xlabel("Years from now")
    ax.set_ylabel("Annual committed program cost ($)")
    ax.set_xticks(x)
    ax.set_xticklabels(labels)
    ax.grid(True, axis="y", alpha=0.3)

    ax2 = ax.twinx()
    ax2.plot(x, sched["remaining_commitment_dollars"], marker="o", color="#1d3557",
             linewidth=2.5, label="Cumulative remaining commitment")
    ax2.set_ylabel("Cumulative remaining commitment ($)")

    lines1, lab1 = ax.get_legend_handles_labels()
    lines2, lab2 = ax2.get_legend_handles_labels()
    ax.legend(lines1 + lines2, lab1 + lab2, loc="upper right", fontsize=9)
    ax.set_title("Commitment Runoff -- Dollars\n"
                 "(no new enrollment; at report $/child)",
                 fontsize=13, fontweight="bold")
    fig.tight_layout()
    fig.savefig(out_dir / "runoff_dollars.png", dpi=300, bbox_inches="tight")
    plt.close(fig)


def plot_group_trajectories(qty, out_dir):
    labels = _month_labels(qty.index)
    x = np.arange(len(labels))
    fig, ax = plt.subplots(figsize=(12, 6))
    for gi, g in enumerate(range(1, NUM_GROUPS + 1)):
        ax.plot(x, qty[f"g{g}"], marker="o", markersize=3, color=GROUP_COLORS[gi],
                linewidth=2, label=f"Group {g} ({AGE_BAND[g]})")
    ax.set_title("Per-Group Enrollment Trajectories", fontsize=14, fontweight="bold")
    ax.set_xlabel("Invoice month")
    ax.set_ylabel("Children (books mailed)")
    ax.set_xticks(x)
    ax.set_xticklabels(labels, rotation=45, ha="right")
    ax.legend(ncol=3, fontsize=8)
    ax.grid(True, alpha=0.3)
    fig.tight_layout()
    fig.savefig(out_dir / "group_trajectories.png", dpi=300, bbox_inches="tight")
    plt.close(fig)


def plot_observed_flows(qty, inv, proj, out_dir):
    """Observed monthly inflow (LETC welcome books = new enrollments) vs. outflow
    (GRAD graduations), with the linear LETC trend used to drive the projection."""
    labels = _month_labels(qty.index)
    x = np.arange(len(labels))
    letc = inv["letc"].reindex(qty.index).fillna(0).to_numpy()
    grad = inv["grad"].reindex(qty.index).fillna(0).to_numpy()

    fig, ax = plt.subplots(figsize=(12, 6))
    ax.bar(x - 0.2, letc, 0.4, color="#2a9d8f", label="LETC: new enrollments (welcome books)")
    ax.bar(x + 0.2, grad, 0.4, color="#9d0208", label="GRAD: graduations")
    trend = proj["letc_slope"] * np.arange(len(x)) + proj["letc_intercept"]
    ax.plot(x, trend, color="#1d3557", linewidth=2, linestyle="--",
            label=f"LETC trend ({proj['letc_slope']:+.1f}/mo) -> projection driver")
    ax.set_title("Observed Monthly Flows: Enrollment Inflow (LETC) vs. Graduation (GRAD)",
                 fontsize=13, fontweight="bold")
    ax.set_xlabel("Invoice month")
    ax.set_ylabel("Children")
    ax.set_xticks(x)
    ax.set_xticklabels(labels, rotation=45, ha="right")
    ax.legend(fontsize=9)
    ax.grid(True, axis="y", alpha=0.3)
    fig.tight_layout()
    fig.savefig(out_dir / "observed_flows.png", dpi=300, bbox_inches="tight")
    plt.close(fig)


# --------------------------------------------------------------------------- #
# Forward scenario: monthly age-class cohort with observed-LETC recruitment
# --------------------------------------------------------------------------- #
def load_flows():
    """Observed monthly flows from the shared invoice model (ilsa_ledger):
    group_kids, letc (new enrollments), grad (graduations), kids, accrual_cost."""
    try:
        return invoice_monthly()
    except Exception as e:
        print(f"NOTE: invoice model unavailable ({e}); flows/cost will fall back.")
        return pd.DataFrame()


def cost_per_child(inv):
    """Report-basis $/child: invoiced (accrual) program cost / children served,
    over billed months. Matches the report's \\ilsaCostPerChild."""
    if inv is None or inv.empty:
        return FALLBACK_COST_PER_CHILD
    billed = inv["accrual_cost"].notna() & (inv["kids"] > 0)
    kids = float(inv.loc[billed, "kids"].sum())
    if not kids:
        return FALLBACK_COST_PER_CHILD
    return float(inv.loc[billed, "accrual_cost"].sum() / kids)


def _init_pop(qty):
    """Seed 72 monthly age-classes from the current pyramid (uniform within group)."""
    pop = np.zeros(AGE_CLASSES)
    last = qty.iloc[-1]
    for g in range(1, NUM_GROUPS + 1):
        pop[(g - 1) * 12:g * 12] = float(last[f"g{g}"]) / 12.0
    return pop


def _intake_weights(qty, mode):
    """Where new recruits land across the 72 age-classes (sums to 1)."""
    w = np.zeros(AGE_CLASSES)
    if mode == "birthfed":
        w[0] = 1.0                               # all enter at birth (age 0)
    else:                                        # "today": current pyramid proportions
        last = qty.iloc[-1]
        tot = sum(float(last[f"g{g}"]) for g in range(1, NUM_GROUPS + 1))
        for g in range(1, NUM_GROUPS + 1):
            prop = float(last[f"g{g}"]) / tot if tot else 0.0
            w[(g - 1) * 12:g * 12] = prop / 12.0
    return w


def _step(pop, recruits, w):
    """Age one month: shift up, graduate age 72, inject recruits by mix w."""
    survivors = np.empty_like(pop)
    survivors[1:] = pop[:-1]
    survivors[0] = 0.0                           # pop[-1] graduates out
    return survivors + recruits * w


def _regress(series):
    """Least-squares (slope, intercept) over sequential month indices."""
    y = np.asarray(series, dtype=float)
    slope, intercept = np.polyfit(np.arange(len(y)), y, 1)
    return float(slope), float(intercept)


def _run(qty, recruits, mode):
    """Run the cohort forward under a recruit schedule + intake mix.
    Returns (monthly totals, list of monthly 72-vectors, monthly graduations)."""
    w = _intake_weights(qty, mode)
    pop = _init_pop(qty)
    totals, pops, grads = [], [], []
    for r in recruits:
        grads.append(float(pop[-1]))   # age-72 children graduate out this month
        pop = _step(pop, r, w)
        totals.append(pop.sum())
        pops.append(pop.copy())
    return np.array(totals), pops, np.array(grads)


def _commitment_dollars(pop, cost):
    """Locked-in future obligation of a population: remaining book-months x cost.
    A child at age-class a owes (72 - a) more monthly books before graduating."""
    months_left = AGE_CLASSES - np.arange(AGE_CLASSES)
    return float((pop * months_left).sum()) * cost


def build_projection(qty, inv, cost):
    """Forward projection driven by OBSERVED enrollment inflow.

    Recruitment each month is the linear trend of LETC (welcome books = new
    enrollments); graduation is endogenous (children age out at 72 months). The
    band is +/-ENROLL_BAND/yr on recruitment. Two intake mixes bracket the
    unobserved entry age: today's pyramid skew (older, short tail) vs birth-fed
    (matured program, long tail) -- both fed the SAME recruitment schedule.
    """
    last_p = qty.index[-1]
    horizon = (pd.Period(PROJECTION_END, "M") - last_p).n
    future = [last_p + i for i in range(1, horizon + 1)]
    years = np.arange(1, horizon + 1) / 12.0

    letc = inv["letc"].reindex(qty.index).fillna(0.0).to_numpy(dtype=float)
    grad_obs = inv["grad"].reindex(qty.index).fillna(0.0).to_numpy(dtype=float)
    n = len(letc)
    slope, intercept = _regress(letc)
    fidx = np.arange(1, horizon + 1)
    recruit = np.maximum(slope * (n - 1 + fidx) + intercept, 0.0)

    tot_today, pops_today, grad_today = _run(qty, recruit, "today")
    tot_birth, pops_birth, _ = _run(qty, recruit, "birthfed")
    tot_hi, _, _ = _run(qty, recruit * (1 + ENROLL_BAND) ** years, "today")
    tot_lo, _, _ = _run(qty, recruit * (1 - ENROLL_BAND) ** years, "today")

    return {
        "future": future, "horizon": horizon,
        "letc_slope": slope, "letc_intercept": intercept,
        "recruit": recruit, "letc_hist": letc, "grad_hist": grad_obs,
        "cost": cost,
        "today": tot_today, "birth": tot_birth, "hi": tot_hi, "lo": tot_lo,
        "pops_today": pops_today, "pops_birth": pops_birth, "grad_today": grad_today,
    }


def projection_table(qty, proj):
    """Year-end snapshot: children, monthly program $, and locked-in commitment
    (future obligation beyond that date) for each intake mix."""
    cost = proj["cost"]
    rows = []
    by_year = {}
    for j, p in enumerate(proj["future"]):
        by_year[p.year] = j                      # last month index seen for each year
    for year in sorted(by_year):
        j = by_year[year]
        p = proj["future"][j]
        rows.append({
            "month": str(p),
            "children_today": int(round(proj["today"][j])),
            "children_birthfed": int(round(proj["birth"][j])),
            "monthly_cost_today": round(proj["today"][j] * cost, 0),
            "monthly_cost_birthfed": round(proj["birth"][j] * cost, 0),
            "commitment_today": round(_commitment_dollars(proj["pops_today"][j], cost), 0),
            "commitment_birthfed": round(_commitment_dollars(proj["pops_birth"][j], cost), 0),
        })
    return pd.DataFrame(rows)


def plot_enrollment_projection(qty, proj, out_dir):
    hist = qty[[f"g{g}" for g in range(1, NUM_GROUPS + 1)]].sum(axis=1).to_numpy()
    hist_labels = _month_labels(qty.index)
    fut_labels = _month_labels(proj["future"])
    all_labels = hist_labels + fut_labels
    xh = np.arange(len(hist))
    xf = np.arange(len(hist), len(all_labels))

    fig, ax = plt.subplots(figsize=(13, 6.5))
    ax.plot(xh, hist, marker="o", markersize=3, color="#1d3557", linewidth=2,
            label="Historical enrollment")
    ax.fill_between(xf, proj["lo"], proj["hi"], color="#9bb4c9", alpha=0.35,
                    label=f"+/-{ENROLL_BAND*100:.0f}%/yr recruitment band")
    ax.plot(xf, proj["today"], linestyle="--", linewidth=2.2, color="#2a9d8f",
            label="Today's-mix intake (observed older skew)")
    ax.plot(xf, proj["birth"], linestyle="--", linewidth=2.2, color="#9d0208",
            label="Birth-fed intake (matured program)")
    ax.set_title("Projected Enrollment to "
                 f"{proj['future'][-1].strftime('%Y')}: observed-LETC recruitment, "
                 "two intake mixes", fontsize=13, fontweight="bold")
    ax.set_xlabel("Month")
    ax.set_ylabel("Children enrolled")
    _thin_xticks(ax, all_labels)
    ax.legend(fontsize=9)
    ax.grid(True, alpha=0.3)
    ax.axvline(len(hist) - 0.5, color="black", linewidth=0.8, alpha=0.5)
    fig.tight_layout()
    fig.savefig(out_dir / "enrollment_projection.png", dpi=300, bbox_inches="tight")
    plt.close(fig)


def plot_cost_projection(qty, proj, out_dir):
    cost = proj["cost"]
    hist = qty[[f"g{g}" for g in range(1, NUM_GROUPS + 1)]].sum(axis=1).to_numpy() * cost
    hist_labels = _month_labels(qty.index)
    all_labels = hist_labels + _month_labels(proj["future"])
    xh = np.arange(len(hist))
    xf = np.arange(len(hist), len(all_labels))

    fig, ax = plt.subplots(figsize=(13, 6.5))
    ax.plot(xh, hist, marker="o", markersize=3, color="#1d3557", linewidth=2,
            label="Historical program cost (children x report $/child)")
    ax.fill_between(xf, proj["lo"] * cost, proj["hi"] * cost, color="#f0c0b0", alpha=0.40,
                    label=f"+/-{ENROLL_BAND*100:.0f}%/yr band")
    ax.plot(xf, proj["today"] * cost, linestyle="--", linewidth=2.2, color="#e76f51",
            label="Today's-mix monthly program cost")
    ax.plot(xf, proj["birth"] * cost, linestyle="--", linewidth=2.2, color="#9d0208",
            label="Birth-fed monthly program cost")
    ax.set_title(f"Projected Monthly Program Cost to {proj['future'][-1].strftime('%Y')} "
                 f"(at ${cost:.2f}/child)", fontsize=13, fontweight="bold")
    ax.set_xlabel("Month")
    ax.set_ylabel("Monthly program cost ($)")
    _thin_xticks(ax, all_labels)
    ax.legend(fontsize=9)
    ax.grid(True, alpha=0.3)
    ax.axvline(len(hist) - 0.5, color="black", linewidth=0.8, alpha=0.5)
    fig.tight_layout()
    fig.savefig(out_dir / "cost_projection.png", dpi=300, bbox_inches="tight")
    plt.close(fig)


def plot_horizon_pyramids(proj, out_dir):
    """Age composition at the horizon: today's-mix vs birth-fed diverge in shape."""
    def to_groups(pop):
        return [pop[(g - 1) * 12:g * 12].sum() for g in range(1, NUM_GROUPS + 1)]

    today = to_groups(proj["pops_today"][-1])
    birth = to_groups(proj["pops_birth"][-1])
    y = np.arange(NUM_GROUPS)
    h = 0.4
    horizon_lbl = proj["future"][-1].strftime("%b %Y")

    fig, ax = plt.subplots(figsize=(9, 6))
    ax.barh(y - h / 2, today, h, color="#2a9d8f", label="Today's-mix intake")
    ax.barh(y + h / 2, birth, h, color="#9d0208", label="Birth-fed intake")
    ax.set_yticks(y)
    ax.set_yticklabels([f"Group {g}\n{AGE_BAND[g]}" for g in range(1, NUM_GROUPS + 1)])
    ax.invert_yaxis()
    ax.set_title(f"Age Structure at Horizon ({horizon_lbl})\n"
                 "birth-fed loads the young groups -> long commitment tail",
                 fontsize=12, fontweight="bold")
    ax.set_xlabel("Children enrolled")
    ax.legend(fontsize=9)
    ax.grid(True, axis="x", alpha=0.3)
    fig.tight_layout()
    fig.savefig(out_dir / "horizon_pyramids.png", dpi=300, bbox_inches="tight")
    plt.close(fig)


# --------------------------------------------------------------------------- #
# Report integration: generate the cohort figures + LaTeX command values that
# the narrative in report/2Report.tex consumes. Called by treasurer.py.
# --------------------------------------------------------------------------- #
def build_for_report(out_dir=OUT_DIR):
    """Generate the report-bound cohort figures into ``out_dir`` and return a dict
    of LaTeX ``\\ilsaCohort...`` command values for report/2Report.tex."""
    from ilsa_ledger import money

    out_dir.mkdir(parents=True, exist_ok=True)
    qty, amt = load_enrollment()
    inv = load_flows()
    cost = cost_per_child(inv)
    table_a, _ = age_structure_table(qty, amt, cost)
    matrix, sched = runoff_by_year(qty, cost)
    proj = build_projection(qty, inv, cost)
    proj_table = projection_table(qty, proj)

    plot_age_structure(qty, out_dir)
    plot_observed_flows(qty, inv, proj, out_dir)
    plot_runoff_dollars(qty, sched, out_dir)
    plot_enrollment_projection(qty, proj, out_dir)
    plot_cost_projection(qty, proj, out_dir)
    plot_horizon_pyramids(proj, out_dir)

    letc_avg = float(inv["letc"].mean()) if not inv.empty else 0.0
    rows = []
    for _, r in proj_table.iterrows():
        lbl = pd.Period(r["month"], "M").strftime("%b %Y")
        rows.append(f"{lbl} & {int(r['children_today']):,} & {int(r['children_birthfed']):,} & "
                    f"{money(float(r['monthly_cost_today']))} & "
                    f"{money(float(r['monthly_cost_birthfed']))} \\\\")
    last = proj_table.iloc[-1]

    return {
        "ilsaCohortSnapshot": qty.index[-1].strftime("%B %Y"),
        "ilsaCohortKids": f"{int(qty.iloc[-1].sum()):,}",
        "ilsaCohortCostPerChild": f"\\${cost:.2f}",
        "ilsaCohortRunoffTotal": money(float(table_a.loc["total", "committed_dollars"])),
        "ilsaCohortBookMonths": f"{int(table_a.loc['total', 'remaining_book_months']):,}",
        "ilsaCohortLetcSlope": f"{proj['letc_slope']:+.1f}",
        "ilsaCohortLetcAvg": f"{letc_avg:.0f}",
        "ilsaCohortProjYear": str(proj["future"][-1].year),
        "ilsaCohortProjTodayKids": f"{int(last['children_today']):,}",
        "ilsaCohortProjBirthKids": f"{int(last['children_birthfed']):,}",
        "ilsaCohortProjTodayCost": money(float(last["monthly_cost_today"])),
        "ilsaCohortProjBirthCost": money(float(last["monthly_cost_birthfed"])),
        "ilsaCohortProjTodayCommit": money(float(last["commitment_today"])),
        "ilsaCohortProjBirthCommit": money(float(last["commitment_birthfed"])),
        "ilsaCohortProjRows": "\n".join(rows),
    }


# --------------------------------------------------------------------------- #
# Main
# --------------------------------------------------------------------------- #
def main():
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    qty, amt = load_enrollment()
    inv = load_flows()
    cost = cost_per_child(inv)

    table_a, book_cost = age_structure_table(qty, amt, cost)
    matrix, sched = runoff_by_year(qty, cost)

    # Cohort matrix (table C): rows = future year, cols = originating group.
    matrix_df = pd.DataFrame(
        matrix.astype(int),
        index=[f"year+{k}" for k in range(matrix.shape[0])],
        columns=[f"from_g{g}" for g in range(1, NUM_GROUPS + 1)],
    )
    matrix_df["active_total"] = matrix_df.sum(axis=1)

    proj = build_projection(qty, inv, cost)
    proj_table = projection_table(qty, proj)

    plot_enrollment_by_group(qty, OUT_DIR)
    plot_age_structure(qty, OUT_DIR)
    plot_observed_flows(qty, inv, proj, OUT_DIR)
    plot_runoff_children(qty, matrix, OUT_DIR)
    plot_runoff_dollars(qty, sched, OUT_DIR)
    plot_group_trajectories(qty, OUT_DIR)
    plot_enrollment_projection(qty, proj, OUT_DIR)
    plot_cost_projection(qty, proj, OUT_DIR)
    plot_horizon_pyramids(proj, OUT_DIR)

    table_a.to_csv(OUT_DIR / "age_structure.csv", index=False)
    sched.to_csv(OUT_DIR / "runoff_schedule.csv", index=False)
    matrix_df.to_csv(OUT_DIR / "cohort_matrix.csv")
    proj_table.to_csv(OUT_DIR / "enrollment_projection.csv", index=False)

    latest = qty.index[-1].strftime("%B %Y")
    total_kids = int(qty.iloc[-1].sum())
    committed = float(table_a.loc["total", "committed_dollars"])
    print("=" * 68)
    print(f"ILSA COHORT EXPLORATION  (snapshot: {latest})")
    print("=" * 68)
    print(f"Enrolled children (latest month): {total_kids:,}")
    print(f"Report cost basis: ${cost:.2f}/child   (invoice book cost: ${book_cost:.2f})")
    print(f"Locked-in remaining commitment (no new enrollment): {usd(committed)}")
    print(f"  = {int(table_a.loc['total', 'remaining_book_months']):,} remaining book-months\n")
    print("Table A -- Current age structure:")
    show_a = table_a.copy()
    show_a["committed_dollars"] = show_a["committed_dollars"].map(lambda v: f"${v:,.0f}")
    show_a["pct_of_pop"] = show_a["pct_of_pop"].map(lambda v: f"{v:.1f}%")
    print(show_a.to_string(index=False))
    print("\nTable B -- Runoff schedule (no new enrollment):")
    show_b = sched.copy()
    show_b["annual_committed_dollars"] = show_b["annual_committed_dollars"].map(lambda v: f"${v:,.0f}")
    show_b["remaining_commitment_dollars"] = show_b["remaining_commitment_dollars"].map(lambda v: f"${v:,.0f}")
    print(show_b.to_string(index=False))
    print("\nNOTE: runoff excludes new enrollment and attrition -- it is the floor")
    print("on obligations from children ALREADY enrolled. Spanish is currently 0.")

    print("\n" + "-" * 68)
    print(f"FORWARD SCENARIO (observed-LETC recruitment -> {PROJECTION_END}; "
          f"${cost:.2f}/child)")
    print(f"LETC recruitment trend: {proj['letc_slope']:+.1f} new enrollments/month "
          f"(intercept {proj['letc_intercept']:.0f}).")
    print(f"Band on the cost line: +/-{ENROLL_BAND*100:.0f}%/yr recruitment.")
    print("Graduation is endogenous (children age out at 72 months). Two intake")
    print("mixes bracket the unobserved entry age: today's older skew (short tail)")
    print("vs birth-fed (long tail), both fed the same LETC recruitment.\n")
    print("Table D -- Year-end projection (children | monthly $ | locked-in commitment):")
    show_d = proj_table.copy()
    for c in ("monthly_cost_today", "monthly_cost_birthfed",
              "commitment_today", "commitment_birthfed"):
        show_d[c] = show_d[c].map(lambda v: f"${v:,.0f}")
    print(show_d.to_string(index=False))
    print(f"\nFigures + CSVs -> {OUT_DIR}")


if __name__ == "__main__":
    main()
