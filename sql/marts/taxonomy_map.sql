-- Stable product/issue buckets (seed: sql/seeds/taxonomy_map.csv), and every
-- complaint tagged with its buckets.
-- exports: taxonomy_map, complaints_bucketed
CREATE OR REPLACE TABLE taxonomy_map AS
SELECT kind, product, COALESCE(sub_label, '') AS sub_label, bucket
FROM read_csv('{{seeds}}/taxonomy_map.csv', header = true, all_varchar = true);

CREATE OR REPLACE TABLE complaints_bucketed AS
SELECT
    c.complaint_id,
    c.company,
    c.date_received,
    c.available_date,
    DATE_TRUNC('month', c.available_date)::DATE AS feature_month,
    pb.bucket AS product_bucket,
    ib.bucket AS issue_bucket,
    c.timely_response
FROM stg_complaints c
LEFT JOIN taxonomy_map pb
       ON pb.kind = 'product' AND pb.product = c.product
      AND pb.sub_label = COALESCE(c.sub_product, '')
LEFT JOIN taxonomy_map ib
       ON ib.kind = 'issue' AND ib.product = c.product
      AND ib.sub_label = COALESCE(c.issue, '');
