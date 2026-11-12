"""
03_analysis_and_charts.py
Answers the 3 business questions with pandas (same logic as sql/analysis_queries.sql),
saves summary tables for Power BI / Tableau, and draws the dashboard images.

Run:  python scripts/03_analysis_and_charts.py
Outputs: dashboard/*.png and dashboard/powerbi_tables/*.csv
"""
from pathlib import Path
import pandas as pd
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.patches import FancyBboxPatch

ROOT = Path(__file__).resolve().parents[1]
DASH = ROOT / "dashboard"; TABLES = DASH / "powerbi_tables"; TABLES.mkdir(parents=True, exist_ok=True)
df = pd.read_csv(ROOT / "data" / "clean" / "dental_appointments_clean.csv", parse_dates=["service_date"])
AS_AT = pd.Timestamp("2026-06-30")

# ------------------------------------------------------------------ Q1 profitability
def per_hour(g):
    return pd.Series({
        "appointments_booked": len(g), "chair_hours_booked": g["chair_minutes"].sum() / 60,
        "revenue": g["billed_fee"].sum(), "contribution": g["contribution"].sum(),
        "contribution_margin_pct": 100 * g["contribution"].sum() / g["billed_fee"].sum(),
        "contribution_per_chair_hour": g["contribution"].sum() / (g["chair_minutes"].sum() / 60)})
q1_clinic = df[df.clinic != "Unknown"].groupby("clinic").apply(per_hour, include_groups=False).sort_values("contribution_per_chair_hour", ascending=False)
q1_service = df.groupby("service_category").apply(per_hour, include_groups=False).sort_values("contribution_per_chair_hour", ascending=False)

# ------------------------------------------------------------------ Q2 lost appointments
lost = df[df.is_lost_appointment == 1]
q2 = df[df.clinic != "Unknown"].groupby("clinic").agg(appointments_booked=("invoice_id", "count"), lost_appointments=("is_lost_appointment", "sum"))
q2["lost_rate_pct"] = 100 * q2.lost_appointments / q2.appointments_booked
q2["revenue_lost"] = lost[lost.clinic != "Unknown"].groupby("clinic")["expected_fee"].sum()
q2["paid_for_empty_chair"] = lost[lost.clinic != "Unknown"].groupby("clinic")["practitioner_cost"].sum()
q2 = q2.sort_values("revenue_lost", ascending=False)
q2_day = df.groupby("weekday").agg(appointments_booked=("invoice_id", "count"), lost_rate_pct=("is_lost_appointment", lambda s: 100 * s.mean())).sort_values("lost_rate_pct", ascending=False)

# ------------------------------------------------------------------ Q3 collections
att = df[df.appointment_status == "Attended"]
q3 = att.groupby("funding_source").agg(invoices=("invoice_id", "count"), billed=("billed_fee", "sum"), avg_days_to_pay=("days_to_payment", "mean"))
q3["outstanding_value"] = att[att.payment_status == "Outstanding"].groupby("funding_source")["billed_fee"].sum()
q3["written_off_value"] = att[att.payment_status == "Written off"].groupby("funding_source")["billed_fee"].sum()
q3 = q3.fillna(0); q3["outstanding_pct"] = 100 * q3.outstanding_value / q3.billed
q3 = q3.sort_values("avg_days_to_pay", ascending=False)

owing = df[df.balance_owing > 0].copy()
owing["age_days"] = (AS_AT - owing.service_date).dt.days
owing["age_bucket"] = pd.cut(owing.age_days, [-1, 30, 60, 90, 10_000], labels=["0-30 days", "31-60 days", "61-90 days", "90+ days"])
q3_age = owing.groupby("age_bucket", observed=False).agg(invoices=("invoice_id", "count"), balance_owing=("balance_owing", "sum"))

hf = att[(att.funding_source == "Health Fund") & (att.clinic != "Unknown")]
q3_hf = hf.groupby("clinic").agg(invoices=("invoice_id", "count"), outstanding_pct=("payment_status", lambda s: 100 * (s == "Outstanding").mean())).sort_values("outstanding_pct", ascending=False)

# monthly trend (for Power BI / Tableau)
monthly = df.groupby("month").agg(revenue=("billed_fee", "sum"), contribution=("contribution", "sum"),
                                  revenue_lost=("expected_fee", lambda s: s[df.loc[s.index, "is_lost_appointment"] == 1].sum())).reset_index()

for name, t in {"q1_by_clinic": q1_clinic, "q1_by_service": q1_service, "q2_lost_by_clinic": q2, "q2_lost_by_weekday": q2_day,
                "q3_collections_by_funding": q3, "q3_ageing": q3_age, "q3_health_fund_by_clinic": q3_hf}.items():
    t.round(2).to_csv(TABLES / f"{name}.csv")
monthly.round(2).to_csv(TABLES / "monthly_trend.csv", index=False)
df.to_csv(TABLES / "appointments_clean_for_bi.csv", index=False)

# ------------------------------------------------------------------ headline numbers
K = {
    "revenue": df.billed_fee.sum(), "contribution": df.contribution.sum(),
    "margin": 100 * df.contribution.sum() / df.billed_fee.sum(),
    "lost_rev": lost.expected_fee.sum(), "lost_rate": 100 * df.is_lost_appointment.mean(),
    "empty_chair_cost": lost.practitioner_cost.sum(),
    "owing": owing.balance_owing.sum(), "owing_90": q3_age.loc["90+ days", "balance_owing"],
}
K["owing_90_pct"] = 100 * K["owing_90"] / K["owing"]
print("HEADLINES:", {k: round(v, 1) for k, v in K.items()})
for n, t in [("Q1 clinic", q1_clinic), ("Q1 service", q1_service), ("Q2", q2), ("Q2 weekday", q2_day), ("Q3", q3), ("Q3 ageing", q3_age), ("Q3 HF by clinic", q3_hf)]:
    print(f"\n{n}\n{t.round(1).to_string()}")

# ------------------------------------------------------------------ charts
BG, INK, INK2, GRID = "#fcfcfb", "#0b0b0b", "#52514e", "#e6e5e1"
BLUE, ORANGE = "#2a78d6", "#eb6834"
plt.rcParams.update({"font.family": "DejaVu Sans", "axes.facecolor": BG, "figure.facecolor": BG,
                     "text.color": INK, "axes.edgecolor": GRID, "axes.labelcolor": INK2,
                     "xtick.color": INK2, "ytick.color": INK})

def hbar(ax, labels, values, highlight, fmt, title, subtitle, xlabel=None, extra=None):
    y = range(len(labels))[::-1]
    cols = [ORANGE if l in highlight else BLUE for l in labels]
    ax.barh(list(y), values, color=cols, height=0.55)
    ax.set_yticks(list(y)); ax.set_yticklabels(labels, fontsize=10)
    mx = max(values)
    for yi, v, l in zip(y, values, labels):
        ax.text(v + mx * 0.015, yi, fmt(v) + (extra[l] if extra else ""), va="center", fontsize=9.5, color=INK)
    ax.set_xlim(0, mx * 1.65)
    for s in ("top", "right", "bottom"): ax.spines[s].set_visible(False)
    ax.tick_params(axis="x", bottom=False, labelbottom=False); ax.tick_params(axis="y", length=0)
    ax.set_title(title, loc="left", fontsize=12.5, fontweight="bold", pad=24)
    ax.text(0, 1.03, subtitle, transform=ax.transAxes, fontsize=9, color=INK2, va="bottom")

def chart1(ax):
    t = q1_clinic
    hbar(ax, list(t.index), list(t.contribution_per_chair_hour), {"Mobile Outreach", "Eastgate"}, lambda v: f"${v:,.0f}",
         "Q1  Profit per chair hour", "Contribution per booked hour \u00b7 orange = two lowest clinics")
def chart2(ax):
    t = q2
    hbar(ax, list(t.index), list(t.revenue_lost / 1000), {"Mobile Outreach", "Eastgate"}, lambda v: f"${v:,.0f}k",
         "Q2  Revenue lost to no-shows & late cancels", "Orange = clinics losing >25% of booked appointments",
         extra={c: f"  ({t.loc[c, 'lost_rate_pct']:.0f}% of bookings)" for c in t.index})
def chart3(ax):
    t = q3.drop(index="Unknown", errors="ignore")
    hbar(ax, list(t.index), list(t.avg_days_to_pay), {"Government Scheme", "Concession"}, lambda v: f"{v:.0f} days",
         "Q3  Days to get paid", "Avg days to payment \u00b7 orange = slowest two",
         extra={c: f"  · {t.loc[c, 'outstanding_pct']:.0f}% unpaid" for c in t.index})

for i, fn in enumerate([chart1, chart2, chart3], 1):
    fig, ax = plt.subplots(figsize=(8, 4.2)); fn(ax); fig.tight_layout(); fig.savefig(DASH / f"chart{i}.png", dpi=160); plt.close(fig)

# ---- one-page dashboard
fig = plt.figure(figsize=(17, 9.6))
gs = fig.add_gridspec(2, 3, height_ratios=[0.8, 3.2], hspace=0.28, wspace=0.95, left=0.095, right=0.97, top=0.86, bottom=0.07)
fig.text(0.095, 0.945, "Dental Network: Finance & Operations Dashboard", fontsize=21, fontweight="bold", va="center")
fig.text(0.095, 0.903, "Synthetic data · 6 clinics · 3,200 booked appointments · FY25–FY26 (1 Jul 2024 – 30 Jun 2026)", fontsize=11, color=INK2, va="center")

tiles = [("Revenue billed", f"${K['revenue']/1e6:.2f}M", f"{K['margin']:.0f}% contribution margin"),
         ("Appointments lost", f"{K['lost_rate']:.0f}%", "no-shows + late cancellations"),
         ("Revenue lost", f"${K['lost_rev']/1000:,.0f}k", f"+ ${K['empty_chair_cost']/1000:,.0f}k paid for empty chairs"),
         ("Unpaid balances", f"${K['owing']/1000:,.0f}k", f"{K['owing_90_pct']:.0f}% older than 90 days")]
tg = gs[0, :].subgridspec(1, 4, wspace=0.08)
for i, (a, b, c) in enumerate(tiles):
    ax = fig.add_subplot(tg[0, i]); ax.axis("off")
    ax.add_patch(FancyBboxPatch((0, 0), 1, 1, boxstyle="round,pad=0,rounding_size=0.06", transform=ax.transAxes, fc="#f1f0ec", ec="none"))
    ax.text(0.05, 0.76, a, fontsize=11, color=INK2, transform=ax.transAxes)
    ax.text(0.05, 0.34, b, fontsize=26, fontweight="bold", transform=ax.transAxes, color=INK)
    ax.text(0.05, 0.10, c, fontsize=9.5, color=INK2, transform=ax.transAxes)
for i, fn in enumerate([chart1, chart2, chart3]):
    fn(fig.add_subplot(gs[1, i]))
fig.text(0.095, 0.02, "Contribution = billed fee − materials/lab − practitioner time. Lost revenue estimated from list fee × typical billing ratio for the funding source. All data is synthetic.", fontsize=9, color=INK2)
fig.savefig(DASH / "dashboard.png", dpi=130); plt.close(fig)
print("\nSaved charts to", DASH)
