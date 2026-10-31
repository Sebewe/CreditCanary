-- ALFRED real-time UNRATE: one row per (vintage as-of date, observation month)
-- exactly as published on that date. File name carries the as-of date.
CREATE OR REPLACE TABLE stg_unrate_vintages AS
SELECT
    CAST(regexp_extract(filename, 'UNRATE_(\d{4}-\d{2}-\d{2})\.csv', 1) AS DATE) AS asof_date,
    CAST(observation_date AS DATE)                                              AS obs_month,
    TRY_CAST(value AS DOUBLE)                                                   AS unrate
FROM read_csv('{{raw}}/alfred/*/UNRATE_*.csv', header = true,
              names = ['observation_date', 'value'], all_varchar = true, filename = true)
WHERE TRY_CAST(value AS DOUBLE) IS NOT NULL;
