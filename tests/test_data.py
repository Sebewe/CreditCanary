"""Data checks: row counts, uniqueness, date ranges, and point-in-time rules
(no feature may use a record whose available_date is after the feature date)."""
from __future__ import annotations

import sys
from pathlib import Path

import duckdb
import numpy as np
import pandas as pd
import pytest

ROOT = Path(__file__).resolve().parents[1]
STG = ROOT / "data" / "staging"
MARTS = ROOT / "data" / "marts"
sys.path.insert(0, str(ROOT / "backtest"))


@pytest.fixture(scope="session")
def con():
    if not (MARTS / "panel_monthly.parquet").exists():
        pytest.skip("marts not built; run `make rebuild`")
    c = duckdb.connect()
    for d in (STG, MARTS):
        for p in d.glob("*.parquet"):
            c.execute(f"CREATE VIEW {p.stem} AS SELECT * FROM read_parquet('{p}')")
    return c


def one(con, sql):
    return con.execute(sql).fetchone()


# ---------------------------------------------------------------- row counts
@pytest.mark.parametrize("table,minimum", [
    ("stg_complaints", 15_000_000),
    ("stg_trust_monthly", 1_500),
    ("stg_call_report", 1_000),
    ("stg_unrate_vintages", 100_000),
    ("complaint_features", 4_000),
    ("panel_monthly", 1_200),
    ("panel_quarterly", 800),
])
def test_row_counts(con, table, minimum):
    assert one(con, f"SELECT COUNT(*) FROM {table}")[0] >= minimum


def test_lender_counts(con):
    assert one(con, "SELECT COUNT(*) FROM lender_map")[0] == 15
    assert 10 <= one(con, "SELECT COUNT(*) FROM lender_map")[0] <= 20
    usable = one(con, "SELECT COUNT(*) FROM issuer_usability WHERE usable")[0]
    assert usable >= 3, "fewer than 3 usable issuers: fallback must apply"
    assert one(con, "SELECT COUNT(DISTINCT lender_id) FROM panel_monthly")[0] == usable


# ---------------------------------------------------------------- uniqueness
@pytest.mark.parametrize("table,key", [
    ("stg_complaints", "complaint_id"),
    ("stg_trust_monthly", "trust_id, period_month"),
    ("issuer_outcomes_monthly", "lender_id, period_month"),
    ("complaint_features", "lender_id, role, feature_month"),
    ("panel_monthly", "lender_id, period_month"),
    ("panel_monthly", "lender_id, asof_month"),
    ("panel_quarterly", "lender_id, quarter_end"),
    ("lender_map", "lender_id"),
    ("lender_map", "cfpb_company"),
])
def test_unique(con, table, key):
    n, d = one(con, f"SELECT COUNT(*), COUNT(DISTINCT ({key})) FROM {table}")
    assert n == d, f"{table} not unique on ({key})"


# ---------------------------------------------------------------- date ranges
def test_complaint_dates(con):
    lo, hi, bad = one(con, """SELECT MIN(date_received), MAX(date_received),
                                     SUM((available_date < date_received)::INT)
                              FROM stg_complaints""")
    assert str(lo) >= "2011-12-01" and str(hi) <= pd.Timestamp.today().strftime("%Y-%m-%d")
    assert bad == 0


def test_available_date_rule(con):
    """available_date = date_sent_to_company + 15 days."""
    bad = one(con, """SELECT COUNT(*) FROM stg_complaints
                      WHERE available_date <> COALESCE(date_sent_to_company, date_received) + 15""")[0]
    assert bad == 0


def test_trust_and_panel_dates(con):
    lo, hi = one(con, "SELECT MIN(period_month), MAX(period_month) FROM stg_trust_monthly")
    assert str(lo) >= "2010-01-01" and str(hi) <= pd.Timestamp.today().strftime("%Y-%m-%d")
    lo, hi = one(con, "SELECT MIN(asof_month), MAX(asof_month) FROM panel_monthly")
    assert str(lo) >= "2011-01-01"
    assert str(hi) <= one(con, "SELECT MAX(feature_month) FROM complaint_features")[0].isoformat()
    lo, hi = one(con, "SELECT MIN(quarter_end), MAX(quarter_end) FROM panel_quarterly")
    assert str(lo) >= "2010-01-01"
    # rates live in sane ranges (percent)
    assert one(con, "SELECT COUNT(*) FROM stg_trust_monthly WHERE nco_rate < 0 OR nco_rate > 25")[0] == 0
    assert one(con, "SELECT COUNT(*) FROM stg_trust_monthly WHERE dq30_rate < 0 OR dq30_rate > 20")[0] == 0


# ---------------------------------------------------------------- point in time
def test_features_never_use_future_records(con):
    """No feature row uses a complaint whose available_date is after its feature date."""
    assert one(con, """SELECT COUNT(*) FROM complaint_features
                       WHERE max_available_date > feature_date""")[0] == 0
    assert one(con, """SELECT COUNT(*) FROM panel_monthly
                       WHERE feature_max_available_date > asof_date""")[0] == 0
    assert one(con, """SELECT COUNT(*) FROM panel_quarterly
                       WHERE feature_max_available_date > asof_date""")[0] == 0


def test_features_recomputed_independently(con):
    """Recompute cmp_share / hardship_share / timely_rate straight from staged
    complaints with an explicit available_date <= feature date filter and compare."""
    df = con.execute("""
        WITH f AS (
            SELECT * FROM complaint_features
            WHERE role = 'card' AND lender_id IN ('citi', 'synchrony', 'capital_one')
              AND feature_month IN (DATE '2014-06-01', DATE '2019-11-01', DATE '2025-03-01')
        ), c AS (
            SELECT b.*, l.lender_id FROM complaints_bucketed b
            LEFT JOIN lender_map l ON l.cfpb_company = b.company
        )
        SELECT f.lender_id, f.feature_month, f.cmp_share, f.hardship_share, f.timely_rate,
          (SELECT COUNT(*) FROM c WHERE c.lender_id = f.lender_id AND c.product_bucket = 'credit_card'
              AND c.available_date <= f.feature_date
              AND c.available_date >= f.feature_month - INTERVAL 2 MONTH)::DOUBLE /
          (SELECT COUNT(*) FROM c WHERE c.product_bucket = 'credit_card'
              AND c.available_date <= f.feature_date
              AND c.available_date >= f.feature_month - INTERVAL 2 MONTH)      AS share_chk,
          (SELECT AVG((issue_bucket IN ('payment_trouble', 'collections'))::INT) FROM c
              WHERE c.lender_id = f.lender_id AND c.product_bucket = 'credit_card'
              AND c.available_date <= f.feature_date
              AND c.available_date >= f.feature_month - INTERVAL 2 MONTH)      AS hard_chk,
          (SELECT AVG((timely_response = 'Yes')::INT) FROM c
              WHERE c.lender_id = f.lender_id AND timely_response IN ('Yes', 'No')
              AND c.available_date <  f.feature_month - INTERVAL 1 MONTH
              AND c.available_date >= f.feature_month - INTERVAL 4 MONTH)     AS timely_chk
        FROM f
    """).df()
    assert len(df) == 9
    np.testing.assert_allclose(df.cmp_share, df.share_chk, rtol=1e-9)
    np.testing.assert_allclose(df.hardship_share, df.hard_chk, rtol=1e-9)
    np.testing.assert_allclose(df.timely_rate, df.timely_chk, rtol=1e-9)


def test_outcomes_known_at_asof(con):
    """The 10-D for period p was filed by the as-of date; UNRATE vintage ends before it."""
    assert one(con, "SELECT COUNT(*) FROM panel_monthly WHERE filing_date > asof_date")[0] == 0
    assert one(con, """SELECT COUNT(*) FROM panel_monthly
                       WHERE unrate_obs_month >= asof_date""")[0] == 0
    assert one(con, """SELECT COUNT(*) FROM panel_monthly
                       WHERE asof_month <> period_month + INTERVAL 1 MONTH""")[0] == 0


def test_targets_match_outcome_series(con):
    bad = one(con, """
        SELECT COUNT(*) FROM panel_monthly p
        JOIN issuer_outcomes_monthly o
          ON o.lender_id = p.lender_id AND o.period_month = p.period_month + INTERVAL 3 MONTH
         AND o.trust_id = p.trust_id
        WHERE ABS(p.nco_chg_3 - (o.nco_rate - p.nco_rate)) > 1e-9""")[0]
    assert bad == 0
    # never across a trust switch
    assert one(con, """
        SELECT COUNT(*) FROM panel_monthly p
        JOIN issuer_outcomes_monthly o
          ON o.lender_id = p.lender_id AND o.period_month = p.period_month + INTERVAL 3 MONTH
        WHERE o.trust_id <> p.trust_id AND p.nco_chg_3 IS NOT NULL""")[0] == 0


# ---------------------------------------------------------------- taxonomy
def test_taxonomy_covers_everything(con):
    assert one(con, """SELECT COUNT(*) FROM complaints_bucketed
                       WHERE product_bucket IS NULL OR issue_bucket IS NULL""")[0] == 0
    n_prod = one(con, "SELECT COUNT(DISTINCT bucket) FROM taxonomy_map WHERE kind = 'product'")[0]
    n_iss = one(con, "SELECT COUNT(DISTINCT bucket) FROM taxonomy_map WHERE kind = 'issue'")[0]
    assert 8 <= n_prod <= 12 and 8 <= n_iss <= 12


# ---------------------------------------------------------------- walk-forward leakage
def test_walk_forward_never_trains_on_unrealised_targets():
    from models import Spec, walk_forward
    rng = np.random.default_rng(0)
    rows = []
    for lender in "abc":
        for t in range(100):
            rows.append({"lender_id": lender, "fe_id": lender, "t": t, "asof_month": t,
                         "x": rng.normal(), "f": rng.normal(), "y": rng.normal()})
    df = pd.DataFrame(rows)
    seen = []

    def probe(train, score):
        seen.append((score.t.iloc[0], train.t.max()))
        return np.zeros(len(score))

    h, gap = 3, 1
    walk_forward(df, Spec("y", ["x"], ["f"]), list(range(40, 100)), h + gap, {"probe": probe})
    assert seen and all(tmax <= t - h - gap for t, tmax in seen)
