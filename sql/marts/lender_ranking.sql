-- Companies ranked by complaint volume in credit card and other consumer
-- credit buckets; used to choose the lender universe (sql/seeds/lender_universe.csv).
CREATE OR REPLACE TABLE lender_ranking AS
SELECT
    company,
    COUNT(*) FILTER (WHERE product_bucket = 'credit_card')                     AS n_credit_card,
    COUNT(*) FILTER (WHERE product_bucket IN ('personal_loan', 'vehicle_loan')) AS n_consumer_loan,
    COUNT(*)                                                                    AS n_credit_total,
    MIN(date_received)                                                          AS first_complaint,
    MAX(date_received)                                                          AS last_complaint,
    ROUND(COUNT(*) FILTER (WHERE YEAR(date_received) BETWEEN 2022 AND 2025) / 4.0) AS per_year_2022_2025,
    RANK() OVER (ORDER BY COUNT(*) DESC)                                        AS volume_rank
FROM complaints_bucketed
WHERE product_bucket IN ('credit_card', 'personal_loan', 'vehicle_loan')
GROUP BY company;
