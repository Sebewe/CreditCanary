-- Lender-quarter panel for the Call Report secondary outcome (and the
-- pre-registered fallback). Bank figures are summed across the lender's certs.
--   bank_nco_rate  = quarterly net charge-offs * 4 / average gross loans, percent
--   noncurrent_rate = noncurrent loans / gross loans, percent
--   asof_date = last day of the month containing quarter_end + 60 days
--   features  = complaint_features (role cr_main) at the as-of month
--   targets   = bank_nco_rate[q+h] - bank_nco_rate[q], h = 1..4 quarters
-- exports: panel_quarterly
CREATE OR REPLACE TABLE panel_quarterly AS
WITH certs AS (
    SELECT lender_id, CAST(cert AS INTEGER) AS cert
    FROM read_csv('{{seeds}}/lender_certs.csv', header = true, all_varchar = true)
),
lq AS (
    SELECT c.lender_id, r.quarter_end,
           SUM(r.nco_q)            AS nco_q,
           SUM(r.loans_gross)      AS loans_gross,
           SUM(r.noncurrent_loans) AS noncurrent_loans,
           COUNT(*)                AS n_certs
    FROM stg_call_report r JOIN certs c USING (cert)
    GROUP BY ALL
),
rates AS (
    SELECT *,
        100 * 4 * nco_q / NULLIF((loans_gross + LAG(loans_gross) OVER w) / 2, 0) AS bank_nco_rate,
        100 * noncurrent_loans / NULLIF(loans_gross, 0)                         AS noncurrent_rate
    FROM lq
    WINDOW w AS (PARTITION BY lender_id ORDER BY quarter_end)
),
d AS (
    SELECT *,
        (DATE_TRUNC('month', quarter_end + INTERVAL 60 DAY) + INTERVAL 1 MONTH - INTERVAL 1 DAY)::DATE AS asof_date,
        DATE_TRUNC('month', quarter_end + INTERVAL 60 DAY)::DATE AS asof_month,
        bank_nco_rate - LAG(bank_nco_rate, 1) OVER w AS d_nco_0,
        LAG(bank_nco_rate, 1) OVER w - LAG(bank_nco_rate, 2) OVER w AS d_nco_1,
        LAG(bank_nco_rate, 2) OVER w - LAG(bank_nco_rate, 3) OVER w AS d_nco_2,
        LEAD(bank_nco_rate, 1) OVER w - bank_nco_rate AS bank_nco_chg_1,
        LEAD(bank_nco_rate, 2) OVER w - bank_nco_rate AS bank_nco_chg_2,
        LEAD(bank_nco_rate, 3) OVER w - bank_nco_rate AS bank_nco_chg_3,
        LEAD(bank_nco_rate, 4) OVER w - bank_nco_rate AS bank_nco_chg_4
    FROM rates
    WINDOW w AS (PARTITION BY lender_id ORDER BY quarter_end)
),
xmean AS (
    SELECT quarter_end, AVG(d_nco_0) AS xmean_d_nco FROM d WHERE d_nco_0 IS NOT NULL GROUP BY 1
),
unrate AS (
    SELECT v.asof_date, MAX(v.obs_month) AS obs_month, MAX_BY(v.unrate, v.obs_month) AS unrate_latest
    FROM stg_unrate_vintages v GROUP BY 1
),
unrate_d AS (
    SELECT u.asof_date, u.unrate_latest - v3.unrate AS d_unrate
    FROM unrate u JOIN stg_unrate_vintages v3
      ON v3.asof_date = u.asof_date AND v3.obs_month = u.obs_month - INTERVAL 3 MONTH
)
SELECT
    d.lender_id, d.quarter_end, d.asof_month, d.asof_date, d.n_certs,
    d.bank_nco_rate, d.noncurrent_rate, d.d_nco_0, d.d_nco_1, d.d_nco_2,
    x.xmean_d_nco, ud.d_unrate,
    f.main_bucket, f.cmp_share, f.cmp_growth_yoy, f.hardship_share, f.timely_rate,
    f.n_main_3m, f.max_available_date AS feature_max_available_date,
    d.bank_nco_chg_1, d.bank_nco_chg_2, d.bank_nco_chg_3, d.bank_nco_chg_4
FROM d
LEFT JOIN xmean x ON x.quarter_end = d.quarter_end
LEFT JOIN unrate_d ud ON ud.asof_date = d.asof_date
LEFT JOIN complaint_features f ON f.lender_id = d.lender_id AND f.role = 'cr_main'
                              AND f.feature_month = d.asof_month
WHERE d.asof_month <= (SELECT MAX(feature_month) FROM complaint_features);
