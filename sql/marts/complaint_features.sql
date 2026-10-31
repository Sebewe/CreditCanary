-- Point-in-time complaint features per lender and feature month m
-- (DECISIONS.md "Features"). Every count is bucketed by the month of
-- available_date, so a feature for month m only sees records with
-- available_date <= last day of m. max_available_date records the latest
-- available_date that fed each row (checked by tests).
--
-- role = 'card'    : main bucket credit_card (primary, card-trust outcome)
-- role = 'cr_main' : lender's highest-volume credit bucket over feature
--                    months 2012-2016 (Call Report secondary outcome)
-- exports: lender_main_bucket, complaint_features
CREATE OR REPLACE TABLE lender_main_bucket AS
WITH lc AS (
    SELECT l.lender_id, b.product_bucket, COUNT(*) AS n
    FROM complaints_bucketed b
    JOIN lender_map l ON l.cfpb_company = b.company
    WHERE b.feature_month BETWEEN DATE '2012-01-01' AND DATE '2016-12-01'
      AND b.product_bucket IN ('credit_card', 'personal_loan', 'vehicle_loan', 'mortgage', 'student_loan')
    GROUP BY ALL
)
SELECT lender_id, 'card' AS role, 'credit_card' AS main_bucket FROM lender_map
UNION ALL
SELECT lender_id, 'cr_main' AS role, product_bucket AS main_bucket
FROM lc
QUALIFY ROW_NUMBER() OVER (PARTITION BY lender_id ORDER BY n DESC, product_bucket) = 1;

CREATE OR REPLACE TABLE complaint_features AS
WITH snapshot AS (
    SELECT MAX(date_received) + 1 AS snapshot_date FROM stg_complaints
),
c AS (   -- complaints public by the snapshot date (conservative availability)
    SELECT b.*
    FROM complaints_bucketed b, snapshot s
    WHERE b.available_date <= s.snapshot_date
),
months AS (
    SELECT UNNEST(generate_series(DATE '2011-12-01',
                                  (SELECT DATE_TRUNC('month', snapshot_date) FROM snapshot),
                                  INTERVAL 1 MONTH))::DATE AS feature_month
),
market AS (
    SELECT product_bucket, feature_month, COUNT(*) AS n_market
    FROM c GROUP BY ALL
),
lender AS (
    SELECT
        l.lender_id,
        mb.role,
        mb.main_bucket,
        c.feature_month,
        COUNT(*) FILTER (WHERE c.product_bucket = mb.main_bucket)                       AS n_main,
        COUNT(*) FILTER (WHERE c.product_bucket = mb.main_bucket
                           AND c.issue_bucket IN ('payment_trouble', 'collections'))     AS n_hardship,
        COUNT(*) FILTER (WHERE c.timely_response = 'Yes')                               AS n_timely_yes,
        COUNT(*) FILTER (WHERE c.timely_response IN ('Yes', 'No'))                       AS n_timely_known,
        MAX(c.available_date) FILTER (WHERE c.product_bucket = mb.main_bucket)          AS max_avail_main,
        MAX(c.available_date)                                                            AS max_avail_all
    FROM c
    JOIN lender_map l ON l.cfpb_company = c.company
    JOIN lender_main_bucket mb ON mb.lender_id = l.lender_id
    GROUP BY ALL
),
spine AS (   -- every lender x role x month, zero-filled
    SELECT mb.lender_id, mb.role, mb.main_bucket, m.feature_month,
           COALESCE(x.n_main, 0)         AS n_main,
           COALESCE(x.n_hardship, 0)     AS n_hardship,
           COALESCE(x.n_timely_yes, 0)   AS n_timely_yes,
           COALESCE(x.n_timely_known, 0) AS n_timely_known,
           x.max_avail_main, x.max_avail_all,
           COALESCE(mk.n_market, 0)      AS n_market
    FROM lender_main_bucket mb
    CROSS JOIN months m
    LEFT JOIN lender x ON x.lender_id = mb.lender_id AND x.role = mb.role
                      AND x.feature_month = m.feature_month
    LEFT JOIN market mk ON mk.product_bucket = mb.main_bucket AND mk.feature_month = m.feature_month
),
rolled AS (
    SELECT *,
        SUM(n_main)     OVER w3 AS l3,
        SUM(n_market)   OVER w3 AS m3,
        SUM(n_hardship) OVER w3 AS h3,
        -- timely: feature months m-4..m-2 (lagged 2 months)
        SUM(n_timely_yes)   OVER wt AS ty3,
        SUM(n_timely_known) OVER wt AS tk3,
        MAX(max_avail_all)  OVER w5 AS max_avail_5m,
        COUNT(*) OVER w3 AS k3,
        COUNT(*) OVER wt AS kt
    FROM spine
    WINDOW w3 AS (PARTITION BY lender_id, role ORDER BY feature_month ROWS BETWEEN 2 PRECEDING AND CURRENT ROW),
           wt AS (PARTITION BY lender_id, role ORDER BY feature_month ROWS BETWEEN 4 PRECEDING AND 2 PRECEDING),
           w5 AS (PARTITION BY lender_id, role ORDER BY feature_month ROWS BETWEEN 4 PRECEDING AND CURRENT ROW)
),
lagged AS (
    SELECT *,
        LAG(l3, 12) OVER (PARTITION BY lender_id, role ORDER BY feature_month) AS l3_ly,
        LAG(m3, 12) OVER (PARTITION BY lender_id, role ORDER BY feature_month) AS m3_ly,
        LAG(k3, 12) OVER (PARTITION BY lender_id, role ORDER BY feature_month) AS k3_ly
    FROM rolled
)
SELECT
    lender_id,
    role,
    main_bucket,
    feature_month,
    (feature_month + INTERVAL 1 MONTH - INTERVAL 1 DAY)::DATE                   AS feature_date,
    l3                                                                          AS n_main_3m,
    m3                                                                          AS n_market_3m,
    CASE WHEN k3 = 3 AND m3 > 0 THEN l3 / m3 END                                AS cmp_share,
    CASE WHEN k3 = 3 AND k3_ly = 3 AND m3 > 0 AND m3_ly > 0
         THEN LN((1 + l3) / (1 + l3_ly)) - LN(m3 / m3_ly) END                   AS cmp_growth_yoy,
    CASE WHEN k3 = 3 AND l3 > 0 THEN h3 / l3 END                                AS hardship_share,
    CASE WHEN kt = 3 AND tk3 > 0 THEN ty3 / tk3 END                             AS timely_rate,
    max_avail_5m                                                                AS max_available_date
FROM lagged;
