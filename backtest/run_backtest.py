"""Walk-forward backtest exactly per DECISIONS.md.

Reads data/marts/panel_monthly.parquet and panel_quarterly.parquet, writes
results tables to report/results/*.csv and forecasts to data/results/.
report/write_results.py turns the tables into report/RESULTS.md.

Usage: python backtest/run_backtest.py [--draws 2000]
"""
from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path

# Small data: single-threaded OpenMP is ~10x faster for the tree robustness fits.
os.environ.setdefault("OMP_NUM_THREADS", "1")

import numpy as np
import pandas as pd
from sklearn.ensemble import HistGradientBoostingRegressor

sys.path.insert(0, str(Path(__file__).resolve().parent))
from models import (SEED, Spec, block_bootstrap_coefs, block_bootstrap_lift,  # noqa: E402
                    fit_coefs, oos_metrics, walk_forward)

ROOT = Path(__file__).resolve().parents[1]
MARTS = ROOT / "data" / "marts"
OUT = ROOT / "report" / "results"
PRED = ROOT / "data" / "results"

FEATS = ["cmp_share", "cmp_growth_yoy", "hardship_share", "timely_rate"]
GATED = ["cmp_share", "cmp_growth_yoy"]
NCO_BASE = ["nco_rate", "d_nco_0", "d_nco_1", "d_nco_2", "xmean_d_nco", "d_unrate"]
DQ_BASE = ["dq30_rate", "d_dq_0", "d_dq_1", "d_dq_2", "xmean_d_dq", "d_unrate"]
CR_BASE = ["bank_nco_rate", "d_nco_0", "d_nco_1", "d_nco_2", "xmean_d_nco", "d_unrate"]
HORIZONS = range(1, 7)
TRAIN_MONTHS = 36
COVID = (pd.Timestamp("2020-03-01"), pd.Timestamp("2021-12-01"))


# ---------------------------------------------------------------- setup
def month_index(s: pd.Series) -> pd.Series:
    d = pd.to_datetime(s)
    return d.dt.year * 12 + d.dt.month - 1


def load_monthly() -> pd.DataFrame:
    df = pd.read_parquet(MARTS / "panel_monthly.parquet")
    df["asof_month"] = pd.to_datetime(df.asof_month)
    df["t"] = month_index(df.asof_month)
    df["fe_id"] = df.lender_id
    df["block"] = df.asof_month.dt.year
    return df


def complete(df: pd.DataFrame, cols: list[str]) -> pd.DataFrame:
    return df.dropna(subset=cols).copy()


def windows(df: pd.DataFrame, base: list[str], primary_y: str, train_n: int,
            start: pd.Timestamp | None = None):
    """Panel start, training months and the three test splits (DECISIONS.md)."""
    full = complete(df, base + FEATS)
    if start is not None:
        full = full[full.asof_month >= start]
    months = sorted(full.t.unique())
    panel_start = months[0]
    all_t = list(range(panel_start, max(months) + 1))
    test_start = panel_start + train_n
    last = complete(full, [primary_y]).t.max()
    test_t = [t for t in all_t if test_start <= t <= last]
    k = len(test_t) // 3
    splits = {"S1": test_t[:k], "S2": test_t[k:2 * k], "S3": test_t[2 * k:]}
    return panel_start, test_t, splits


def t_to_month(t: int) -> str:
    return f"{t // 12}-{t % 12 + 1:02d}"


# ---------------------------------------------------------------- tree
def tree_model(spec: Spec):
    def fn(train: pd.DataFrame, score: pd.DataFrame) -> np.ndarray:
        cols = spec.test
        levels = sorted(train.fe_id.unique())
        def X(d):
            oh = np.column_stack([(d.fe_id == l).to_numpy(float) for l in levels])
            return np.column_stack([d[cols].to_numpy(float), oh])
        m = HistGradientBoostingRegressor(random_state=SEED)
        m.fit(X(train), train[spec.y].to_numpy(float))
        return m.predict(X(score))
    return fn


# ---------------------------------------------------------------- one study
def run_study(name: str, df: pd.DataFrame, base: list[str], ycol: str, horizons, gap: int,
              train_n: int, primary_h: int, draws: int, start=None, drop_rows=None,
              with_tree: bool = False, bootstrap: bool = True) -> dict[str, pd.DataFrame]:
    """Walk-forward + full-sample coefficients for one outcome/sample.

    gap: publication lag in periods; a training row t' is allowed at origin t
    when t' + h <= t - gap  (monthly: gap 1 -> p'+h <= p-1; quarterly: gap 0).
    drop_rows(df, h) -> boolean mask of rows to exclude for horizon h.
    """
    panel_start, test_t, splits = windows(df, base, f"{ycol}_{primary_h}", train_n, start)
    oos_rows, coef_rows, preds = [], [], []
    for h in horizons:
        y = f"{ycol}_{h}"
        spec = Spec(y=y, base=base, feats=FEATS)
        d = complete(df, spec.test + [y])
        d = d[d.t >= panel_start]
        if drop_rows is not None:
            d = d[~drop_rows(d, h)]
        extra = {"pred_tree": tree_model(spec)} if with_tree else None
        p = walk_forward(d, spec, test_t, train_max_offset=h + gap, extra_models=extra)
        p["h"] = h
        preds.append(p)
        for split, ts in [("full", test_t), *splits.items()]:
            ps = p[p.t.isin(ts)]
            if len(ps) < 5:
                continue
            m = oos_metrics(ps)
            if split == "full" and bootstrap:
                m["lift_ci_lo"], m["lift_ci_hi"] = block_bootstrap_lift(ps, n_draws=draws)
            if split == "full" and with_tree:
                m["r2_lift_tree"] = oos_metrics(ps, "pred_tree")["r2_lift"]
            oos_rows.append({"study": name, "h": h, "split": split,
                             "first_month": t_to_month(min(ts)), "last_month": t_to_month(max(ts)), **m})
        # full-sample fit (all panel rows) and per-split fits
        c = fit_coefs(d, y, spec.test)
        ci = (block_bootstrap_coefs(d, y, spec.test, FEATS, n_draws=draws).set_index("feature")
              if bootstrap else None)
        for f in FEATS:
            coef_rows.append({"study": name, "h": h, "sample": "full", "feature": f, "coef": c[f],
                              "ci_lo": ci.loc[f, "ci_lo"] if ci is not None else np.nan,
                              "ci_hi": ci.loc[f, "ci_hi"] if ci is not None else np.nan,
                              "n_rows": len(d)})
        for split, ts in splits.items():
            ds = d[d.t.isin(ts)]
            if len(ds) < len(spec.test) + 10:
                continue
            cs = fit_coefs(ds, y, spec.test)
            for f in FEATS:
                coef_rows.append({"study": name, "h": h, "sample": split, "feature": f,
                                  "coef": cs[f], "ci_lo": np.nan, "ci_hi": np.nan, "n_rows": len(ds)})
    meta = pd.DataFrame([{"study": name, "panel_start": t_to_month(panel_start),
                          "test_start": t_to_month(test_t[0]), "test_end": t_to_month(test_t[-1]),
                          **{f"{k}_range": f"{t_to_month(v[0])}..{t_to_month(v[-1])}"
                             for k, v in splits.items()},
                          "n_lenders": df.lender_id.nunique()}])
    return {"oos": pd.DataFrame(oos_rows), "coefs": pd.DataFrame(coef_rows),
            "preds": pd.concat(preds, ignore_index=True), "meta": meta}


# ---------------------------------------------------------------- decision rule
def decide(oos: pd.DataFrame, coefs: pd.DataFrame, primary_h: int, cond2_h: list[int],
           cond3_h: list[int]) -> pd.DataFrame:
    o = oos.set_index(["h", "split"])
    c = coefs.set_index(["h", "sample", "feature"])
    rows = []
    lifts = {s: o.loc[(primary_h, s), "r2_lift"] for s in ("S1", "S2", "S3")}
    n_pos = sum(v > 0 for v in lifts.values())
    rows.append((1, f"OOS R² lift > 0 at h={primary_h} in >= 2 of 3 splits",
                 "; ".join(f"{s}={v:+.4f}" for s, v in lifts.items()), n_pos >= 2))
    l2 = {h: o.loc[(h, "full"), "r2_lift"] for h in cond2_h}
    n2 = sum(v > 0 for v in l2.values())
    rows.append((2, f"Full-window OOS R² lift > 0 for >= 2 of h={cond2_h}",
                 "; ".join(f"h{h}={v:+.4f}" for h, v in l2.items()), n2 >= 2))
    c3 = {(h, f): c.loc[(h, "full", f), "coef"] for h in cond3_h for f in GATED}
    rows.append((3, f"Full-sample coefs on {GATED} > 0 at every h={cond3_h}",
                 "; ".join(f"h{h} {f}={v:+.4g}" for (h, f), v in c3.items()),
                 all(v > 0 for v in c3.values())))
    c4 = {f: (c.loc[(primary_h, "full", f), "ci_lo"], c.loc[(primary_h, "full", f), "ci_hi"])
          for f in GATED}
    rows.append((4, f"90% CI of both coefs entirely > 0 at h={primary_h}",
                 "; ".join(f"{f} [{lo:+.4g}, {hi:+.4g}]" for f, (lo, hi) in c4.items()),
                 all(lo > 0 for lo, _ in c4.values())))
    c5 = {(s, f): c.loc[(primary_h, s, f), "coef"] for s in ("S1", "S2", "S3") for f in GATED
          if (primary_h, s, f) in c.index}
    rows.append((5, f"Neither coef flips sign (both > 0) in any split at h={primary_h}",
                 "; ".join(f"{s} {f}={v:+.4g}" for (s, f), v in c5.items()),
                 len(c5) == 6 and all(v > 0 for v in c5.values())))
    out = pd.DataFrame(rows, columns=["condition", "rule", "values", "pass"])
    verdict = "GO" if out["pass"].all() else "NO-GO"
    return out, verdict


# ---------------------------------------------------------------- main
def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--draws", type=int, default=2000)
    a = ap.parse_args()
    OUT.mkdir(parents=True, exist_ok=True)
    PRED.mkdir(parents=True, exist_ok=True)

    m = load_monthly()
    usable = pd.read_parquet(MARTS / "issuer_usability.parquet")
    n_usable = int(usable.usable.sum())
    if n_usable < 3:
        raise SystemExit("fewer than 3 usable issuers: fallback applies (see DECISIONS.md)")

    results = {}
    print("[backtest] primary NCO", flush=True)
    results["primary"] = run_study("primary", m, NCO_BASE, "nco_chg", HORIZONS, gap=1,
                                   train_n=TRAIN_MONTHS, primary_h=3, draws=a.draws, with_tree=True)
    decision, verdict = decide(results["primary"]["oos"], results["primary"]["coefs"],
                               primary_h=3, cond2_h=[2, 3, 4], cond3_h=list(HORIZONS))

    print("[backtest] robustness", flush=True)
    results["rob_2017"] = run_study("rob_2017on", m, NCO_BASE, "nco_chg", HORIZONS, gap=1,
                                    train_n=TRAIN_MONTHS, primary_h=3, draws=a.draws,
                                    start=pd.Timestamp("2017-01-01"), bootstrap=False)

    def covid_mask(d, h):
        tgt = d.asof_month - pd.DateOffset(months=1) + pd.DateOffset(months=h)
        inwin = lambda s: (s >= COVID[0]) & (s <= COVID[1])  # noqa: E731
        return inwin(d.asof_month) | inwin(tgt)
    results["rob_covid"] = run_study("rob_ex_covid", m, NCO_BASE, "nco_chg", HORIZONS, gap=1,
                                     train_n=TRAIN_MONTHS, primary_h=3, draws=a.draws,
                                     drop_rows=covid_mask, bootstrap=False)

    print("[backtest] secondary DQ30", flush=True)
    results["dq30"] = run_study("secondary_dq30", m, DQ_BASE, "dq30_chg", HORIZONS, gap=1,
                                train_n=TRAIN_MONTHS, primary_h=3, draws=a.draws, bootstrap=False)

    print("[backtest] secondary Call Report", flush=True)
    q = pd.read_parquet(MARTS / "panel_quarterly.parquet")
    q["asof_month"] = pd.to_datetime(q.asof_month)
    q["t"] = (pd.to_datetime(q.quarter_end).dt.year * 4 + pd.to_datetime(q.quarter_end).dt.quarter - 1)
    q["fe_id"] = q.lender_id
    q["block"] = q.asof_month.dt.year
    results["callreport"] = run_study("secondary_callreport", q, CR_BASE, "bank_nco_chg",
                                      range(1, 5), gap=0, train_n=12, primary_h=1,
                                      draws=a.draws, bootstrap=True)

    for key in ("oos", "coefs", "meta"):
        pd.concat([r[key] for r in results.values()], ignore_index=True) \
          .to_csv(OUT / f"{key}.csv", index=False)
    pd.concat([r["preds"].assign(study=k) for k, r in results.items()], ignore_index=True) \
      .to_parquet(PRED / "oos_predictions.parquet", index=False)
    decision.to_csv(OUT / "decision.csv", index=False)
    pd.DataFrame([{"verdict": verdict, "n_usable_issuers": n_usable, "draws": a.draws,
                   "seed": SEED}]).to_csv(OUT / "verdict.csv", index=False)
    print(decision.to_string())
    print(f"VERDICT: {verdict}")


if __name__ == "__main__":
    main()
