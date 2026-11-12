"""
01_generate_data.py
Creates a SYNTHETIC dental-network appointment & billing dataset.
No real clinic, patient or staff data is used - every value is random.

Run:  python scripts/01_generate_data.py
Output: data/raw/dental_appointments_raw.csv  (deliberately messy)
"""
import numpy as np
import pandas as pd
from pathlib import Path

rng = np.random.default_rng(2026)          # fixed seed = same data every run
N = 3200                                   # clean rows before mess is added
START, END = pd.Timestamp("2024-07-01"), pd.Timestamp("2026-06-30")  # FY25 + FY26 (Australian financial years)

# ---- reference tables --------------------------------------------------------
clinics = {   # name: (share of appointments, no-show rate, late-cancel rate)
    "Northside":        (0.22, 0.07, 0.04),
    "Eastgate":         (0.20, 0.15, 0.06),
    "Riverbend":        (0.18, 0.08, 0.04),
    "Harbour Street":   (0.17, 0.09, 0.05),
    "Westfield":        (0.13, 0.10, 0.05),
    "Mobile Outreach":  (0.10, 0.22, 0.08),
}
# category: (share, avg list fee, fee sd, chair minutes, consumable+lab cost % of fee, practitioner)
services = {
    "Check-up & Clean":    (0.34, 190,  35, 45, 0.12, "Hygienist"),
    "Restorative":         (0.22, 380,  90, 40, 0.28, "Dentist"),
    "Emergency":           (0.10, 260,  60, 30, 0.22, "Dentist"),
    "Oral Surgery":        (0.07, 420, 110, 45, 0.28, "Dentist"),
    "Endodontic":          (0.06, 1150, 250, 90, 0.35, "Dentist"),
    "Crown & Bridge":      (0.07, 1700, 350, 90, 0.42, "Dentist"),
    "Orthodontic":         (0.08, 640, 140, 40, 0.20, "Orthodontist"),
    "Cosmetic":            (0.06, 950, 260, 60, 0.30, "Dentist"),
}
prac_rate = {"Dentist": 160, "Hygienist": 80, "Orthodontist": 210, "Dental Therapist": 95}  # $/hour, assumption
# funding: (share, fee factor, mean days to pay, sd, write-off chance, unpaid-at-extract chance)
funding = {
    "Private":            (0.38, 1.00, 4,  3,  0.035, 0.03),
    "Health Fund":        (0.34, 0.92, 18, 7,  0.010, 0.05),
    "Government Scheme":  (0.18, 0.68, 52, 18, 0.015, 0.12),
    "Concession":         (0.10, 0.75, 40, 15, 0.060, 0.10),
}

def pick(d, n, idx=0):
    keys = list(d.keys())
    p = np.array([v[idx] for v in d.values()], dtype=float)
    return rng.choice(keys, size=n, p=p / p.sum())

# ---- dates (no Sundays, quieter Dec/Jan) -------------------------------------
all_days = pd.date_range(START, END)
w = np.array([0 if d.dayofweek == 6 else (0.35 if d.dayofweek == 5 else 1.0) for d in all_days])
w = w * np.array([0.6 if d.month in (12, 1) else 1.0 for d in all_days])
dates = rng.choice(all_days, size=N, p=w / w.sum())

df = pd.DataFrame({"service_date": pd.to_datetime(dates)})
df["clinic"] = pick(clinics, N)
df["service_category"] = pick(services, N)
df["funding_source"] = pick(funding, N)
df["patient_id"] = ["P" + str(x).zfill(5) for x in rng.integers(1, 1900, N)]

# practitioner
def prac(cat):
    base = services[cat][5]
    if base == "Hygienist" and rng.random() < 0.30:
        return "Dental Therapist"
    return base
df["practitioner_type"] = df["service_category"].map(prac)

# ---- fees, time, cost ---------------------------------------------------------
df["chair_minutes"] = df["service_category"].map(lambda c: services[c][3])
list_fee = np.array([max(60, rng.normal(services[c][1], services[c][2])) for c in df["service_category"]])
df["list_fee"] = np.round(list_fee, 0)
df["billed_fee"] = np.round(df["list_fee"] * df["funding_source"].map(lambda f: funding[f][1]), 2)
df["materials_lab_cost"] = np.round(df["list_fee"] * df["service_category"].map(lambda c: services[c][4]) * rng.normal(1, 0.08, N), 2)
df["practitioner_cost"] = np.round(df["chair_minutes"] / 60 * df["practitioner_type"].map(prac_rate), 2)

# ---- attendance ---------------------------------------------------------------
dna_p = df["clinic"].map(lambda c: clinics[c][1]).values.copy()
lc_p = df["clinic"].map(lambda c: clinics[c][2]).values.copy()
dow = df["service_date"].dt.dayofweek.values
dna_p = dna_p * np.where(np.isin(dow, [0, 4]), 1.3, 1.0)           # Mondays/Fridays worse
dna_p = dna_p * np.where(df["funding_source"].isin(["Government Scheme", "Concession"]), 1.35, 1.0)
r = rng.random(N)
status = np.where(r < dna_p, "No-show", np.where(r < dna_p + lc_p, "Late cancellation", "Attended"))
df["appointment_status"] = status
att = df["appointment_status"] == "Attended"

# lost appointments earn nothing; materials not used; practitioner cost still paid (empty chair)
df.loc[~att, "billed_fee"] = 0.0
df.loc[~att, "materials_lab_cost"] = 0.0

# ---- payment ------------------------------------------------------------------
days = np.zeros(N); paid = np.zeros(N); pstatus = np.array(["n/a"] * N, dtype=object)
for i in np.where(att)[0]:
    f = df.at[i, "funding_source"]
    _, _, mu, sd, wo, unpaid = funding[f]
    fee = df.at[i, "billed_fee"]
    # Westfield health-fund claims are rejected more often (planted finding)
    if df.at[i, "clinic"] == "Westfield" and f == "Health Fund":
        unpaid, wo = 0.16, 0.04
    u = rng.random()
    d = max(0, int(rng.normal(mu, sd)))
    age = (END - df.at[i, "service_date"]).days
    if u < wo:
        pstatus[i], paid[i], days[i] = "Written off", 0.0, np.nan
    elif u < wo + unpaid or d > age:
        pstatus[i], paid[i], days[i] = "Outstanding", 0.0, np.nan
    elif rng.random() < 0.06:
        pstatus[i], paid[i], days[i] = "Part paid", round(fee * rng.uniform(0.4, 0.9), 2), d
    else:
        pstatus[i], paid[i], days[i] = "Paid", fee, d
df["payment_status"] = pstatus
df["amount_paid"] = paid
df["days_to_payment"] = days

df["invoice_id"] = ["INV" + str(100000 + i) for i in range(N)]
df = df.sort_values("service_date").reset_index(drop=True)

cols = ["invoice_id", "service_date", "clinic", "patient_id", "service_category", "practitioner_type",
        "funding_source", "appointment_status", "chair_minutes", "list_fee", "billed_fee",
        "materials_lab_cost", "practitioner_cost", "payment_status", "amount_paid", "days_to_payment"]
df = df[cols]

# ============================ ADD REALISTIC MESS ================================
raw = df.copy()
raw["service_date"] = raw["service_date"].dt.strftime("%Y-%m-%d")
n = len(raw)

# 1. mixed date formats (~35% of rows)
idx = rng.choice(n, int(n * 0.35), replace=False)
half = len(idx) // 2
raw.loc[idx[:half], "service_date"] = pd.to_datetime(raw.loc[idx[:half], "service_date"]).dt.strftime("%d/%m/%Y")
raw.loc[idx[half:], "service_date"] = pd.to_datetime(raw.loc[idx[half:], "service_date"]).dt.strftime("%d-%b-%Y")

# 2. inconsistent clinic names (case, trailing spaces, abbreviations)
idx = rng.choice(n, int(n * 0.12), replace=False)
raw.loc[idx, "clinic"] = [rng.choice([c.upper(), c.lower(), c + " ", " " + c]) for c in raw.loc[idx, "clinic"]]
raw.loc[raw["clinic"].str.strip().str.lower() == "harbour street", "clinic"] = [
    rng.choice(["Harbour Street", "Harbour St", "Harbour St."]) for _ in range((raw["clinic"].str.strip().str.lower() == "harbour street").sum())]

# 3. category / funding label variants
idx = rng.choice(n, int(n * 0.05), replace=False)
raw.loc[idx, "service_category"] = raw.loc[idx, "service_category"].replace({"Check-up & Clean": "Checkup and Clean", "Crown & Bridge": "Crown/Bridge", "Oral Surgery": "oral surgery"})
idx = rng.choice(n, int(n * 0.04), replace=False)
raw.loc[idx, "funding_source"] = raw.loc[idx, "funding_source"].replace({"Government Scheme": "Govt Scheme", "Health Fund": "health fund"})

# 4. money stored as text with $ and commas
raw["billed_fee"] = raw["billed_fee"].astype(object)
idx = rng.choice(n, int(n * 0.08), replace=False)
raw.loc[idx, "billed_fee"] = raw.loc[idx, "billed_fee"].map(lambda x: "${:,.2f}".format(x))

# 5. blanks
for col, share in [("funding_source", 0.03), ("clinic", 0.006), ("practitioner_type", 0.02), ("chair_minutes", 0.015)]:
    raw.loc[rng.choice(n, int(n * share), replace=False), col] = np.nan

# 6. impossible values (negative days, missing paid amount for 'Paid')
idx = rng.choice(np.where(raw["payment_status"] == "Paid")[0], 8, replace=False)
raw.loc[idx, "days_to_payment"] = -raw.loc[idx, "days_to_payment"] - 1
idx = rng.choice(np.where(raw["payment_status"] == "Paid")[0], 15, replace=False)
raw.loc[idx, "amount_paid"] = np.nan

# 7. exact duplicate rows (system export glitch) + a few test rows
dups = raw.sample(60, random_state=1)
raw = pd.concat([raw, dups], ignore_index=True)
test = raw.sample(4, random_state=2).copy()
test["clinic"] = "TEST CLINIC"; test["invoice_id"] = ["INV-TEST" + str(i) for i in range(4)]
raw = pd.concat([raw, test], ignore_index=True)
raw = raw.sample(frac=1, random_state=3).reset_index(drop=True)

out = Path(__file__).resolve().parents[1] / "data" / "raw" / "dental_appointments_raw.csv"
raw.to_csv(out, index=False)
print(f"Saved {len(raw):,} rows to {out}")
