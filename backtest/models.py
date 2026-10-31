"""Model mechanics for the walk-forward backtest (DECISIONS.md).

Everything is plain OLS with lender fixed effects, solved with numpy so each
step is easy to follow:
  - design():        intercept + lender dummies + regressors
  - ols():           least-squares coefficients
  - walk_forward():  expanding-window refit at every origin, out-of-sample
                     forecasts for the baseline and the test model
  - oos_metrics():   R² of each model, R² lift, directional hit rates
  - block_bootstrap_*: 90% CIs by resampling lenders and calendar-year blocks
"""
from __future__ import annotations

from dataclasses import dataclass

import numpy as np
import pandas as pd

SEED = 20261031
N_DRAWS = 2000


# ---------------------------------------------------------------- OLS helpers
def design(df: pd.DataFrame, xcols: list[str], fe_levels: list) -> np.ndarray:
    """[1, lender dummies (first level dropped), regressors]."""
    n = len(df)
    fe = np.zeros((n, max(len(fe_levels) - 1, 0)))
    codes = pd.Categorical(df["fe_id"], categories=fe_levels).codes
    for j in range(1, len(fe_levels)):
        fe[:, j - 1] = codes == j
    return np.column_stack([np.ones(n), fe, df[xcols].to_numpy(float)])


def ols(X: np.ndarray, y: np.ndarray) -> np.ndarray:
    beta, *_ = np.linalg.lstsq(X, y, rcond=None)
    return beta


def fit_coefs(df: pd.DataFrame, y: str, xcols: list[str]) -> dict[str, float]:
    """Full-sample OLS with lender FE; returns the regressor coefficients."""
    levels = sorted(df["fe_id"].unique())
    beta = ols(design(df, xcols, levels), df[y].to_numpy(float))
    return dict(zip(xcols, beta[len(levels):]))


# ---------------------------------------------------------------- walk-forward
@dataclass
class Spec:
    y: str
    base: list[str]
    feats: list[str]

    @property
    def test(self) -> list[str]:
        return self.base + self.feats


def walk_forward(df: pd.DataFrame, spec: Spec, test_t: list[int], train_max_offset: int,
                 extra_models: dict | None = None) -> pd.DataFrame:
    """Expanding-window forecasts.

    df has columns t (integer as-of period index), fe_id, the target and regressors
    (complete cases). At origin t a training row t' is allowed only if
    t' <= t - train_max_offset (caller encodes the horizon/publication lag).
    Returns one row per scored observation with baseline and test forecasts.
    """
    out = []
    for t in test_t:
        score = df[df.t == t]
        if score.empty:
            continue
        train = df[df.t <= t - train_max_offset]
        score = score[score.fe_id.isin(train.fe_id.unique())]
        if score.empty or len(train) < len(spec.test) + 10:
            continue
        levels = sorted(train.fe_id.unique())
        yt = train[spec.y].to_numpy(float)
        bb = ols(design(train, spec.base, levels), yt)
        bt = ols(design(train, spec.test, levels), yt)
        rec = pd.DataFrame({
            "t": t, "lender_id": score.lender_id.values, "asof_month": score.asof_month.values,
            "y": score[spec.y].values,
            "pred_base": design(score, spec.base, levels) @ bb,
            "pred_test": design(score, spec.test, levels) @ bt,
        })
        for name, fn in (extra_models or {}).items():
            rec[name] = fn(train, score)
        out.append(rec)
    return pd.concat(out, ignore_index=True) if out else pd.DataFrame()


def oos_metrics(p: pd.DataFrame, pred_test: str = "pred_test") -> dict[str, float]:
    y = p.y.to_numpy(float)
    eb = y - p.pred_base.to_numpy(float)
    et = y - p[pred_test].to_numpy(float)
    sst = float(((y - y.mean()) ** 2).sum())
    nz = y != 0
    inc = y > 0
    return {
        "n_rows": len(p),
        "n_months": p.t.nunique(),
        "r2_baseline": 1 - (eb ** 2).sum() / sst,
        "r2_test": 1 - (et ** 2).sum() / sst,
        "r2_lift": ((eb ** 2).sum() - (et ** 2).sum()) / sst,
        "hit_rate_base": float((np.sign(p.pred_base[nz]) == np.sign(y[nz])).mean()),
        "hit_rate_test": float((np.sign(p[pred_test][nz]) == np.sign(y[nz])).mean()),
        "increase_hit_base": float((p.pred_base[inc] > 0).mean()) if inc.any() else np.nan,
        "increase_hit_test": float((p[pred_test][inc] > 0).mean()) if inc.any() else np.nan,
    }


# ---------------------------------------------------------------- bootstrap
def _cells(df: pd.DataFrame) -> tuple[list, list, dict]:
    lenders = sorted(df.lender_id.unique())
    years = sorted(df.block.unique())
    idx = {k: np.asarray(v) for k, v in df.groupby(["lender_id", "block"]).indices.items()}
    return lenders, years, idx


def _draw(rng, lenders, years, idx):
    """One resample: lenders and year blocks drawn independently with replacement.
    Returns (row positions, fe ids) - each drawn lender copy is its own FE."""
    ls = rng.choice(len(lenders), size=len(lenders), replace=True)
    ys = rng.choice(len(years), size=len(years), replace=True)
    rows, fes = [], []
    for i, li in enumerate(ls):
        for yi in ys:
            r = idx.get((lenders[li], years[yi]))
            if r is not None and len(r):
                rows.append(r)
                fes.append(np.full(len(r), i))
    if not rows:
        return np.array([], int), np.array([], int)
    return np.concatenate(rows), np.concatenate(fes)


def block_bootstrap_coefs(df: pd.DataFrame, y: str, xcols: list[str], which: list[str],
                          n_draws: int = N_DRAWS, seed: int = SEED) -> pd.DataFrame:
    """Percentile 90% CI for coefficients `which` (full-sample OLS with lender FE)."""
    rng = np.random.default_rng(seed)
    df = df.reset_index(drop=True)
    lenders, years, idx = _cells(df)
    X_all = df[xcols].to_numpy(float)
    y_all = df[y].to_numpy(float)
    pos = [xcols.index(w) for w in which]
    draws = []
    for _ in range(n_draws):
        r, fe = _draw(rng, lenders, years, idx)
        if len(r) < len(xcols) + len(lenders) + 5:
            continue
        k = fe.max() + 1
        D = np.zeros((len(r), k))
        D[np.arange(len(r)), fe] = 1.0
        X = np.column_stack([D, X_all[r]])
        beta = ols(X, y_all[r])
        draws.append(beta[k:][pos])
    draws = np.array(draws)
    return pd.DataFrame({"feature": which,
                         "ci_lo": np.percentile(draws, 5, axis=0),
                         "ci_hi": np.percentile(draws, 95, axis=0),
                         "n_draws": len(draws)})


def block_bootstrap_lift(p: pd.DataFrame, n_draws: int = N_DRAWS, seed: int = SEED,
                         pred_test: str = "pred_test") -> tuple[float, float]:
    """Percentile 90% CI of the OOS R² lift by resampling stored forecast errors."""
    rng = np.random.default_rng(seed)
    p = p.reset_index(drop=True).assign(block=pd.to_datetime(p.asof_month).dt.year.values)
    lenders, years, idx = _cells(p)
    y = p.y.to_numpy(float)
    eb2 = (y - p.pred_base.to_numpy(float)) ** 2
    et2 = (y - p[pred_test].to_numpy(float)) ** 2
    lifts = []
    for _ in range(n_draws):
        r, _ = _draw(rng, lenders, years, idx)
        if len(r) < 10:
            continue
        yy = y[r]
        sst = ((yy - yy.mean()) ** 2).sum()
        if sst > 0:
            lifts.append((eb2[r].sum() - et2[r].sum()) / sst)
    return float(np.percentile(lifts, 5)), float(np.percentile(lifts, 95))
