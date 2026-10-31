-- Monthly card-trust outcome series per issuer (DECISIONS.md, step 4):
--   * one trust per issuer-month: Discover = DCMT then DCENT; Synchrony =
--     SCCMNT while it reports, then SCIT (largest-trust rule);
--   * usable = >= 60 NCO months from 2013-01 with no gap > 3 months, on the
--     issuer's chosen series.
-- exports: issuer_outcomes_monthly, issuer_usability
CREATE OR REPLACE TABLE issuer_outcomes_monthly AS
SELECT lender_id, period_month, trust_id, filing_date, nco_rate, gco_rate, dq30_rate, nco_method
FROM stg_trust_monthly
WHERE nco_rate IS NOT NULL
QUALIFY ROW_NUMBER() OVER (
    PARTITION BY lender_id, period_month
    ORDER BY CASE trust_id WHEN 'dcmt' THEN 1 WHEN 'dcent' THEN 2
                           WHEN 'sccmnt' THEN 1 WHEN 'scit' THEN 2 ELSE 1 END) = 1;

CREATE OR REPLACE TABLE issuer_usability AS
WITH s AS (
    SELECT lender_id, period_month,
           DATEDIFF('month', LAG(period_month) OVER (PARTITION BY lender_id ORDER BY period_month),
                    period_month) - 1 AS gap
    FROM issuer_outcomes_monthly
    WHERE period_month >= DATE '2013-01-01'
)
SELECT lender_id,
       COUNT(*)                     AS n_months_since_2013,
       COALESCE(MAX(gap), 0)        AS max_gap_months,
       COUNT(*) >= 60 AND COALESCE(MAX(gap), 0) <= 3 AS usable
FROM s
GROUP BY lender_id;
