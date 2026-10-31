-- One row per lender: CFPB company name, FDIC certs, card trust CIKs, ticker,
-- and how each match was confirmed.
CREATE OR REPLACE TABLE lender_map AS
WITH u AS (
    SELECT * FROM read_csv('{{seeds}}/lender_universe.csv', header = true, all_varchar = true)
), certs AS (
    SELECT lender_id,
           LIST(CAST(cert AS INTEGER) ORDER BY CAST(cert AS INTEGER)) AS fdic_certs,
           STRING_AGG(cert || ' ' || bank_name || ': ' || how_confirmed, '; ' ORDER BY cert) AS fdic_match_note
    FROM read_csv('{{seeds}}/lender_certs.csv', header = true, all_varchar = true)
    GROUP BY lender_id
), trusts AS (
    SELECT t.lender_id,
           LIST(CAST(t.cik AS INTEGER) ORDER BY t.trust_id)                 AS trust_ciks,
           STRING_AGG(t.trust_name || ' (CIK ' || t.cik || ')', '; ' ORDER BY t.trust_id) AS trust_names
    FROM read_csv('{{seeds}}/trusts.csv', header = true, all_varchar = true) t
    WHERE t.use = '1'
    GROUP BY t.lender_id
), cfpb AS (
    SELECT company, volume_rank, n_credit_total FROM lender_ranking
)
SELECT
    u.lender_id,
    u.cfpb_company,
    u.ticker,
    u.parent_public,
    c.fdic_certs,
    t.trust_ciks,
    'CFPB: exact company string in the 2026-10-31 bulk file; credit-product volume rank '
        || f.volume_rank || ' (' || f.n_credit_total || ' complaints). '
        || 'FDIC: ' || COALESCE(c.fdic_match_note, 'none') || '. '
        || 'Trusts: ' || COALESCE(t.trust_names || ' - found by EDGAR company search; 10-D servicer reports name the lender''s bank as sponsor/servicer', 'none')
        AS how_confirmed
FROM u
LEFT JOIN certs c USING (lender_id)
LEFT JOIN trusts t USING (lender_id)
LEFT JOIN cfpb f ON f.company = u.cfpb_company;
