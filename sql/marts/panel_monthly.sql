-- Lender-month panel for the primary (card-trust) outcome. DECISIONS.md timing:
--   period_month p   = collection month of the latest known 10-D
--   asof_month       = p + 1; asof_date = last day of asof_month
--   row kept only if the 10-D for p was filed by asof_date
--   features         = complaint_features at feature_month = asof_month (role card)
--   d_unrate         = 3-month UNRATE change in the ALFRED vintage of asof_date
--   targets          = nco_rate[p+h] - nco_rate[p], same trust only, h = 1..6
-- Only issuers that pass issuer_usability enter the panel.
-- exports: panel_monthly
CREATE OR REPLACE TABLE panel_monthly AS
WITH o AS (
    SELECT o.* FROM issuer_outcomes_monthly o
    JOIN issuer_usability u ON u.lender_id = o.lender_id AND u.usable
),
base AS (
    SELECT
        o.lender_id, o.period_month, o.trust_id, o.filing_date, o.nco_rate, o.dq30_rate,
        (o.period_month + INTERVAL 1 MONTH)::DATE                        AS asof_month,
        (o.period_month + INTERVAL 2 MONTH - INTERVAL 1 DAY)::DATE       AS asof_date
    FROM o
),
lags AS (   -- own lags by calendar month, same trust only
    SELECT b.*,
        b.nco_rate - l1.nco_rate                                                AS d_nco_0,
        CASE WHEN l2.trust_id = l1.trust_id THEN l1.nco_rate - l2.nco_rate END  AS d_nco_1,
        CASE WHEN l3.trust_id = l2.trust_id THEN l2.nco_rate - l3.nco_rate END  AS d_nco_2,
        b.dq30_rate - l1.dq30_rate                                              AS d_dq_0,
        CASE WHEN l2.trust_id = l1.trust_id THEN l1.dq30_rate - l2.dq30_rate END AS d_dq_1,
        CASE WHEN l3.trust_id = l2.trust_id THEN l2.dq30_rate - l3.dq30_rate END AS d_dq_2,
        l1.filing_date AS lag1_filing_date
    FROM base b
    LEFT JOIN o l1 ON l1.lender_id = b.lender_id AND l1.period_month = b.period_month - INTERVAL 1 MONTH
                  AND l1.trust_id = b.trust_id
    LEFT JOIN o l2 ON l2.lender_id = b.lender_id AND l2.period_month = b.period_month - INTERVAL 2 MONTH
    LEFT JOIN o l3 ON l3.lender_id = b.lender_id AND l3.period_month = b.period_month - INTERVAL 3 MONTH
),
xmean AS (  -- cross-issuer mean change t-1 -> t, among issuers known by the as-of date
    SELECT period_month, AVG(d_nco_0) AS xmean_d_nco, COUNT(d_nco_0) AS xmean_n,
           AVG(d_dq_0) AS xmean_d_dq
    FROM lags
    WHERE filing_date <= asof_date
    GROUP BY period_month
),
unrate AS (
    SELECT v.asof_date,
           MAX_BY(v.unrate, v.obs_month) AS unrate_latest,
           MAX(v.obs_month)              AS unrate_obs_month
    FROM stg_unrate_vintages v
    GROUP BY v.asof_date
),
unrate_chg AS (
    SELECT u.asof_date, u.unrate_obs_month,
           u.unrate_latest - v3.unrate AS d_unrate
    FROM unrate u
    JOIN stg_unrate_vintages v3 ON v3.asof_date = u.asof_date
                               AND v3.obs_month = u.unrate_obs_month - INTERVAL 3 MONTH
),
targets AS (
    SELECT b.lender_id, b.period_month,
        MAX(CASE WHEN t.period_month = b.period_month + INTERVAL 1 MONTH THEN t.nco_rate - b.nco_rate END) AS nco_chg_1,
        MAX(CASE WHEN t.period_month = b.period_month + INTERVAL 2 MONTH THEN t.nco_rate - b.nco_rate END) AS nco_chg_2,
        MAX(CASE WHEN t.period_month = b.period_month + INTERVAL 3 MONTH THEN t.nco_rate - b.nco_rate END) AS nco_chg_3,
        MAX(CASE WHEN t.period_month = b.period_month + INTERVAL 4 MONTH THEN t.nco_rate - b.nco_rate END) AS nco_chg_4,
        MAX(CASE WHEN t.period_month = b.period_month + INTERVAL 5 MONTH THEN t.nco_rate - b.nco_rate END) AS nco_chg_5,
        MAX(CASE WHEN t.period_month = b.period_month + INTERVAL 6 MONTH THEN t.nco_rate - b.nco_rate END) AS nco_chg_6,
        MAX(CASE WHEN t.period_month = b.period_month + INTERVAL 1 MONTH THEN t.dq30_rate - b.dq30_rate END) AS dq30_chg_1,
        MAX(CASE WHEN t.period_month = b.period_month + INTERVAL 2 MONTH THEN t.dq30_rate - b.dq30_rate END) AS dq30_chg_2,
        MAX(CASE WHEN t.period_month = b.period_month + INTERVAL 3 MONTH THEN t.dq30_rate - b.dq30_rate END) AS dq30_chg_3,
        MAX(CASE WHEN t.period_month = b.period_month + INTERVAL 4 MONTH THEN t.dq30_rate - b.dq30_rate END) AS dq30_chg_4,
        MAX(CASE WHEN t.period_month = b.period_month + INTERVAL 5 MONTH THEN t.dq30_rate - b.dq30_rate END) AS dq30_chg_5,
        MAX(CASE WHEN t.period_month = b.period_month + INTERVAL 6 MONTH THEN t.dq30_rate - b.dq30_rate END) AS dq30_chg_6
    FROM base b
    JOIN o t ON t.lender_id = b.lender_id AND t.trust_id = b.trust_id
            AND t.period_month BETWEEN b.period_month + INTERVAL 1 MONTH AND b.period_month + INTERVAL 6 MONTH
    GROUP BY ALL
)
SELECT
    l.lender_id, l.period_month, l.asof_month, l.asof_date, l.trust_id, l.filing_date,
    l.nco_rate, l.d_nco_0, l.d_nco_1, l.d_nco_2,
    x.xmean_d_nco, x.xmean_n, x.xmean_d_dq,
    u.d_unrate, u.unrate_obs_month,
    f.cmp_share, f.cmp_growth_yoy, f.hardship_share, f.timely_rate,
    f.n_main_3m, f.max_available_date AS feature_max_available_date,
    l.dq30_rate, l.d_dq_0, l.d_dq_1, l.d_dq_2,
    t.* EXCLUDE (lender_id, period_month)
FROM lags l
LEFT JOIN xmean x       ON x.period_month = l.period_month
LEFT JOIN unrate_chg u  ON u.asof_date = l.asof_date
LEFT JOIN complaint_features f ON f.lender_id = l.lender_id AND f.role = 'card'
                              AND f.feature_month = l.asof_month
LEFT JOIN targets t     ON t.lender_id = l.lender_id AND t.period_month = l.period_month
WHERE l.filing_date <= l.asof_date
  AND l.asof_month <= (SELECT MAX(feature_month) FROM complaint_features);
