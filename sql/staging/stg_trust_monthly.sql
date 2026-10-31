-- Monthly card master trust metrics from parsed 10-D servicer reports.
-- One row per (trust_id, period_month).
--   period_month: the collection month = filing month - 1. Every trust files its
--     10-D in the month after the collection period; EDGAR's reportDate is not
--     reliable for this (some trusts use the distribution date, one filing is
--     mislabeled).
--   Only original 10-D filings are used (10-D/A amendments are dropped: the
--     original is what was public at the time). If two originals cover the same
--     month, the earliest filed wins.
CREATE OR REPLACE TABLE stg_trust_monthly AS
WITH parsed AS (
    SELECT
        p.trust_id,
        CAST(p.cik AS INTEGER)                                        AS cik,
        t.lender_id,
        p.accession,
        CAST(p.filing_date AS DATE)                                   AS filing_date,
        CAST(p.report_date AS DATE)                                   AS report_date,
        (DATE_TRUNC('month', CAST(p.filing_date AS DATE)) - INTERVAL 1 MONTH)::DATE AS period_month,
        CAST(p.nco_rate AS DOUBLE)                                    AS nco_rate,
        CAST(p.gco_rate AS DOUBLE)                                    AS gco_rate,
        CAST(p.dq30_rate AS DOUBLE)                                   AS dq30_rate,
        p.nco_method,
        p.exhibit
    FROM read_parquet('{{work}}/trust_10d_parsed.parquet') p
    JOIN read_csv('{{seeds}}/trusts.csv', header = true, all_varchar = true) t
      ON t.trust_id = p.trust_id
    WHERE p.form = '10-D'
)
SELECT *
FROM parsed
QUALIFY ROW_NUMBER() OVER (PARTITION BY trust_id, period_month
                           ORDER BY filing_date, accession) = 1;
