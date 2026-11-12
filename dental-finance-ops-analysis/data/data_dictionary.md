# Data dictionary

All data is synthetic. Raw file: `raw/dental_appointments_raw.csv`. Clean file: `clean/dental_appointments_clean.csv`.

## Columns in the raw file

| Column | Meaning | Known issues in raw file |
|---|---|---|
| invoice_id | Unique appointment/invoice number | Duplicated rows; `INV-TEST` test rows |
| service_date | Date of the appointment | Three date formats mixed |
| clinic | Clinic name (6 clinics) | Mixed case, extra spaces, "Harbour St" variants, blanks |
| patient_id | Anonymous patient code | None |
| service_category | Type of treatment (8 categories) | Label variants (e.g. "Crown/Bridge") |
| practitioner_type | Dentist, Hygienist, Dental Therapist, Orthodontist | Blanks |
| funding_source | Private, Health Fund, Government Scheme, Concession | Label variants, blanks |
| appointment_status | Attended, No-show, Late cancellation | None |
| chair_minutes | Booked chair time in minutes | Blanks |
| list_fee | Standard fee for the treatment ($) | None |
| billed_fee | Amount invoiced after funding adjustment; 0 if not attended ($) | Some stored as text like "$1,250.00" |
| materials_lab_cost | Consumables and lab cost ($) | None |
| practitioner_cost | Practitioner hourly rate x booked hours ($, assumption) | None |
| payment_status | Paid, Part paid, Outstanding, Written off, n/a | None |
| amount_paid | Amount received ($) | Blank on some "Paid" rows |
| days_to_payment | Days from service to payment | Negative values |

## Columns added during cleaning

| Column | Meaning |
|---|---|
| month, financial_year, weekday | Date parts (financial year runs 1 July to 30 June) |
| is_lost_appointment | 1 if No-show or Late cancellation |
| expected_fee | Billed fee if attended; estimated fee if lost |
| contribution | billed_fee − materials_lab_cost − practitioner_cost |
| balance_owing | Unpaid amount on Outstanding or Part paid invoices |
