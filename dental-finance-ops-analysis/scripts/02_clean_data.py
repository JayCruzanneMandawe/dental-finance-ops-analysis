"""
02_clean_data.py
Cleans the raw synthetic dental appointments file and writes:
  data/clean/dental_appointments_clean.csv
  data/clean/cleaning_log.csv       (what was fixed, and how many rows)
  data/clean/dental_ops.db          (SQLite database so the SQL file can run)

Run:  python scripts/02_clean_data.py
"""
import sqlite3
from pathlib import Path
import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
raw = pd.read_csv(ROOT / "data" / "raw" / "dental_appointments_raw.csv", dtype={"billed_fee": str})
log = []
def note(step, n): log.append({"step": step, "rows_affected": int(n)})

df = raw.copy()
note("Rows in raw file", len(df))

# 1. Remove test rows -------------------------------------------------------------
test = df["clinic"].fillna("").str.upper().str.contains("TEST")
note("Removed TEST CLINIC rows", test.sum()); df = df[~test]

# 2. Remove exact duplicate rows, then duplicate invoice IDs ---------------------
before = len(df); df = df.drop_duplicates(); note("Removed exact duplicate rows", before - len(df))
before = len(df); df = df.drop_duplicates(subset="invoice_id"); note("Removed repeated invoice IDs", before - len(df))

# 3. Dates: three formats in one column -------------------------------------------
def parse_date(s):
    for fmt in ("%Y-%m-%d", "%d/%m/%Y", "%d-%b-%Y"):
        try: return pd.to_datetime(s, format=fmt)
        except (ValueError, TypeError): pass
    return pd.NaT
df["service_date"] = df["service_date"].map(parse_date)
note("Dates that were not in YYYY-MM-DD format (standardised)", (~raw.loc[df.index, "service_date"].str.match(r"^\d{4}-\d{2}-\d{2}$")).sum())
note("Dates that could not be read (should be 0)", df["service_date"].isna().sum())

# 4. Clinic names: case, spaces, abbreviations, blanks ---------------------------
clinic_map = {"northside": "Northside", "eastgate": "Eastgate", "riverbend": "Riverbend",
              "harbour street": "Harbour Street", "harbour st": "Harbour Street", "harbour st.": "Harbour Street",
              "westfield": "Westfield", "mobile outreach": "Mobile Outreach"}
orig = df["clinic"].copy()
df["clinic"] = df["clinic"].str.strip().str.lower().map(clinic_map)
note("Clinic names standardised (case/spaces/abbreviations)", ((orig != df["clinic"]) & orig.notna()).sum())
note("Blank clinic -> 'Unknown'", df["clinic"].isna().sum()); df["clinic"] = df["clinic"].fillna("Unknown")

# 5. Category and funding labels ---------------------------------------------------
cat_map = {"Checkup and Clean": "Check-up & Clean", "Crown/Bridge": "Crown & Bridge", "oral surgery": "Oral Surgery"}
note("Service category labels fixed", df["service_category"].isin(cat_map).sum())
df["service_category"] = df["service_category"].replace(cat_map)
fund_map = {"Govt Scheme": "Government Scheme", "health fund": "Health Fund"}
note("Funding source labels fixed", df["funding_source"].isin(fund_map).sum())
df["funding_source"] = df["funding_source"].replace(fund_map)
note("Blank funding source -> 'Unknown'", df["funding_source"].isna().sum())
df["funding_source"] = df["funding_source"].fillna("Unknown")

# 6. Money stored as text ("$1,234.50") ---------------------------------------------
txt = df["billed_fee"].str.contains(r"\$", na=False)
note("Billed fees stored as text with $ and commas", txt.sum())
df["billed_fee"] = pd.to_numeric(df["billed_fee"].str.replace(r"[$,]", "", regex=True), errors="coerce")

# 7. Blank practitioner / chair minutes: fill from the typical value for that service
mode_prac = df.dropna(subset=["practitioner_type"]).groupby("service_category")["practitioner_type"].agg(lambda s: s.mode().iloc[0])
note("Blank practitioner type filled (most common for that service)", df["practitioner_type"].isna().sum())
df["practitioner_type"] = df["practitioner_type"].fillna(df["service_category"].map(mode_prac))
med_min = df.groupby("service_category")["chair_minutes"].transform("median")
note("Blank chair minutes filled (median for that service)", df["chair_minutes"].isna().sum())
df["chair_minutes"] = df["chair_minutes"].fillna(med_min)

# 8. Impossible values -------------------------------------------------------------
neg = df["days_to_payment"] < 0
note("Negative days_to_payment set to blank", neg.sum()); df.loc[neg, "days_to_payment"] = np.nan
miss_paid = (df["payment_status"] == "Paid") & df["amount_paid"].isna()
note("'Paid' rows with blank amount_paid -> set equal to billed_fee", miss_paid.sum())
df.loc[miss_paid, "amount_paid"] = df.loc[miss_paid, "billed_fee"]

# 9. Derived columns used by the analysis ----------------------------------------------
df["month"] = df["service_date"].dt.to_period("M").astype(str)
df["financial_year"] = np.where(df["service_date"].dt.month >= 7, "FY" + (df["service_date"].dt.year + 1).astype(str).str[-2:], "FY" + df["service_date"].dt.year.astype(str).str[-2:])
df["weekday"] = df["service_date"].dt.day_name()
df["is_lost_appointment"] = (df["appointment_status"] != "Attended").astype(int)

# expected fee for a lost appointment = list fee x the average billed/list ratio for that funding source
att = df[df["appointment_status"] == "Attended"]
ratio = (att.groupby("funding_source")["billed_fee"].sum() / att.groupby("funding_source")["list_fee"].sum())
ratio["Unknown"] = att["billed_fee"].sum() / att["list_fee"].sum()
df["expected_fee"] = np.where(df["appointment_status"] == "Attended", df["billed_fee"], (df["list_fee"] * df["funding_source"].map(ratio)).round(2))
df["contribution"] = (df["billed_fee"] - df["materials_lab_cost"] - df["practitioner_cost"]).round(2)
df["balance_owing"] = np.where(df["payment_status"].isin(["Outstanding", "Part paid"]), df["billed_fee"] - df["amount_paid"], 0).round(2)

df = df.sort_values("service_date").reset_index(drop=True)
note("Rows in clean file", len(df))

out = ROOT / "data" / "clean"
df.to_csv(out / "dental_appointments_clean.csv", index=False, date_format="%Y-%m-%d")
pd.DataFrame(log).to_csv(out / "cleaning_log.csv", index=False)

db = out / "dental_ops.db"
if db.exists(): db.unlink()
with sqlite3.connect(db) as con:
    d2 = df.copy(); d2["service_date"] = d2["service_date"].dt.strftime("%Y-%m-%d")
    d2.to_sql("appointments", con, index=False)

print(pd.DataFrame(log).to_string(index=False))
print(f"\nClean file: {out / 'dental_appointments_clean.csv'}")
