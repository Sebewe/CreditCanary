-- Typed CFPB complaints, one row per complaint, from the latest bulk snapshot.
-- available_date is the conservative point-in-time publication date
-- (DECISIONS.md: date_sent_to_company + 15 days, fallback date_received + 15).
CREATE OR REPLACE TABLE stg_complaints AS
SELECT
    CAST("Complaint ID" AS BIGINT)                AS complaint_id,
    CAST("Date received" AS DATE)                 AS date_received,
    TRY_CAST("Date sent to company" AS DATE)      AS date_sent_to_company,
    COALESCE(TRY_CAST("Date sent to company" AS DATE),
             CAST("Date received" AS DATE)) + INTERVAL 15 DAY AS available_ts,
    "Product"                                     AS product,
    "Sub-product"                                 AS sub_product,
    "Issue"                                       AS issue,
    "Sub-issue"                                   AS sub_issue,
    "Company"                                     AS company,
    "State"                                       AS state,
    "Tags"                                        AS tags,
    "Submitted via"                               AS submitted_via,
    "Company response to consumer"                AS company_response,
    "Timely response?"                            AS timely_response
FROM read_csv('{{cfpb_csv}}', header = true, all_varchar = true);

ALTER TABLE stg_complaints ADD COLUMN available_date DATE;
UPDATE stg_complaints SET available_date = CAST(available_ts AS DATE);
ALTER TABLE stg_complaints DROP COLUMN available_ts;
