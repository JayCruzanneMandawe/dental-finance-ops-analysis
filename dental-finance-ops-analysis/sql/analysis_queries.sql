-- =====================================================================
-- Dental network: finance & operations analysis
-- Table: appointments  (built from data/clean/dental_appointments_clean.csv)
-- Works in SQLite (DB Browser for SQLite). Data period: 1 Jul 2024 - 30 Jun 2026.
-- Key definitions:
--   contribution = billed_fee - materials_lab_cost - practitioner_cost
--   (practitioner cost is still incurred when a patient does not turn up)
--   scheduled chair hours = chair_minutes / 60 for ALL booked appointments
-- =====================================================================


-- ---------------------------------------------------------------------
-- Q1. Which clinics and services earn the most per chair hour?
-- ---------------------------------------------------------------------

-- 1a. By clinic
SELECT
    clinic,
    COUNT(*)                                             AS appointments_booked,
    ROUND(SUM(chair_minutes) / 60.0, 0)                  AS chair_hours_booked,
    ROUND(SUM(billed_fee), 0)                            AS revenue,
    ROUND(SUM(contribution), 0)                          AS contribution,
    ROUND(100.0 * SUM(contribution) / SUM(billed_fee), 1) AS contribution_margin_pct,
    ROUND(SUM(contribution) / (SUM(chair_minutes) / 60.0), 2) AS contribution_per_chair_hour
FROM appointments
WHERE clinic <> 'Unknown'
GROUP BY clinic
ORDER BY contribution_per_chair_hour DESC;

-- 1b. By service category
SELECT
    service_category,
    COUNT(*)                                             AS appointments_booked,
    ROUND(SUM(billed_fee), 0)                            AS revenue,
    ROUND(SUM(contribution), 0)                          AS contribution,
    ROUND(100.0 * SUM(contribution) / SUM(billed_fee), 1) AS contribution_margin_pct,
    ROUND(SUM(contribution) / (SUM(chair_minutes) / 60.0), 2) AS contribution_per_chair_hour
FROM appointments
GROUP BY service_category
ORDER BY contribution_per_chair_hour DESC;


-- ---------------------------------------------------------------------
-- Q2. How much revenue do no-shows and late cancellations cost us, and where?
-- ---------------------------------------------------------------------
SELECT
    clinic,
    COUNT(*)                                                    AS appointments_booked,
    SUM(is_lost_appointment)                                    AS lost_appointments,
    ROUND(100.0 * SUM(is_lost_appointment) / COUNT(*), 1)       AS lost_rate_pct,
    ROUND(SUM(CASE WHEN is_lost_appointment = 1 THEN expected_fee ELSE 0 END), 0)      AS revenue_lost,
    ROUND(SUM(CASE WHEN is_lost_appointment = 1 THEN practitioner_cost ELSE 0 END), 0) AS paid_for_empty_chair
FROM appointments
WHERE clinic <> 'Unknown'
GROUP BY clinic
ORDER BY revenue_lost DESC;

-- 2b. Which days of the week are worst?
SELECT
    weekday,
    COUNT(*)                                              AS appointments_booked,
    ROUND(100.0 * SUM(is_lost_appointment) / COUNT(*), 1) AS lost_rate_pct
FROM appointments
GROUP BY weekday
ORDER BY lost_rate_pct DESC;


-- ---------------------------------------------------------------------
-- Q3. Who pays us slowest, and how much cash is stuck?
-- ---------------------------------------------------------------------

-- 3a. Collection performance by funding source (attended appointments only)
SELECT
    funding_source,
    COUNT(*)                                                         AS invoices,
    ROUND(SUM(billed_fee), 0)                                        AS billed,
    ROUND(AVG(days_to_payment), 1)                                   AS avg_days_to_pay,
    ROUND(SUM(CASE WHEN payment_status = 'Outstanding' THEN billed_fee ELSE 0 END), 0) AS outstanding_value,
    ROUND(100.0 * SUM(CASE WHEN payment_status = 'Outstanding' THEN billed_fee ELSE 0 END) / SUM(billed_fee), 1) AS outstanding_pct,
    ROUND(SUM(CASE WHEN payment_status = 'Written off' THEN billed_fee ELSE 0 END), 0) AS written_off_value
FROM appointments
WHERE appointment_status = 'Attended'
GROUP BY funding_source
ORDER BY avg_days_to_pay DESC;

-- 3b. Ageing of unpaid balances as at 30 June 2026
SELECT
    CASE
        WHEN julianday('2026-06-30') - julianday(service_date) <= 30 THEN '0-30 days'
        WHEN julianday('2026-06-30') - julianday(service_date) <= 60 THEN '31-60 days'
        WHEN julianday('2026-06-30') - julianday(service_date) <= 90 THEN '61-90 days'
        ELSE '90+ days'
    END                              AS age_bucket,
    COUNT(*)                         AS invoices,
    ROUND(SUM(balance_owing), 0)     AS balance_owing
FROM appointments
WHERE balance_owing > 0
GROUP BY age_bucket
ORDER BY MIN(julianday('2026-06-30') - julianday(service_date));

-- 3c. Health-fund claims: which clinic has the most unpaid?
SELECT
    clinic,
    COUNT(*)                                                                 AS invoices,
    ROUND(100.0 * SUM(CASE WHEN payment_status = 'Outstanding' THEN 1 ELSE 0 END) / COUNT(*), 1) AS outstanding_pct
FROM appointments
WHERE appointment_status = 'Attended' AND funding_source = 'Health Fund' AND clinic <> 'Unknown'
GROUP BY clinic
ORDER BY outstanding_pct DESC;
