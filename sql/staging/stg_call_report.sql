-- FDIC BankFind quarterly Call Report data per cert ($ thousands).
-- NTLNLS is year-to-date; quarterly net charge-offs = YTD minus prior quarter's
-- YTD within the same calendar year (Q1 = YTD).
CREATE OR REPLACE TABLE stg_call_report AS
WITH raw AS (
    SELECT DISTINCT
        CAST(CERT AS INTEGER)                          AS cert,
        strptime(CAST(REPDTE AS VARCHAR), '%Y%m%d')::DATE AS quarter_end,
        CAST(NTLNLS AS DOUBLE)                         AS nco_ytd,
        CAST(LNLSGR AS DOUBLE)                         AS loans_gross,
        CAST(NCLNLS AS DOUBLE)                         AS noncurrent_loans,
        CAST(NTLNLSR AS DOUBLE)                        AS fdic_nco_rate_ytd,
        CAST(ASSET AS DOUBLE)                          AS assets,
        NAME                                           AS bank_name
    FROM read_json_auto('{{raw}}/fdic/*/financials_*.json')
)
SELECT
    *,
    nco_ytd - COALESCE(LAG(nco_ytd) OVER (PARTITION BY cert, YEAR(quarter_end)
                                          ORDER BY quarter_end), 0) AS nco_q
FROM raw;
