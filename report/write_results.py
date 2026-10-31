"""Write report/RESULTS.md from the results tables in report/results/ only."""
from __future__ import annotations

from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
RES = ROOT / "report" / "results"


def fmt(x, nd=4, sign=True):
    if pd.isna(x):
        return "–"
    return f"{x:+.{nd}f}" if sign else f"{x:.{nd}f}"


def table(df: pd.DataFrame) -> str:
    cols = list(df.columns)
    out = ["| " + " | ".join(cols) + " |", "|" + "|".join("---" for _ in cols) + "|"]
    for _, r in df.iterrows():
        out.append("| " + " | ".join(str(r[c]) for c in cols) + " |")
    return "\n".join(out)


def main() -> None:
    oos = pd.read_csv(RES / "oos.csv")
    coefs = pd.read_csv(RES / "coefs.csv")
    meta = pd.read_csv(RES / "meta.csv").set_index("study")
    dec = pd.read_csv(RES / "decision.csv")
    v = pd.read_csv(RES / "verdict.csv").iloc[0]
    pm = meta.loc["primary"]

    L = []
    L.append(f"# Results: {v.verdict}\n")
    L.append(f"**Decision under the pre-registered rule (DECISIONS.md, 2026-10-31): "
             f"{v.verdict}.** GO requires all five conditions; anything else is NO-GO.\n")
    L.append(f"Primary outcome: monthly card master-trust NCO rate change from SEC 10-D filings, "
             f"{int(v.n_usable_issuers)} usable issuers. Panel starts {pm.panel_start}; "
             f"training-only months to {pm.test_start} (exclusive); test window "
             f"{pm.test_start}..{pm.test_end}, split S1 {pm.S1_range}, S2 {pm.S2_range}, "
             f"S3 {pm.S3_range}. Bootstrap: {int(v.draws)} draws, seed {int(v.seed)}, "
             f"lenders × 12-month blocks.\n")

    L.append("## Decision conditions\n")
    d = dec.assign(result=dec["pass"].map({True: "PASS", False: "FAIL"}))[
        ["condition", "rule", "values", "result"]]
    L.append(table(d) + "\n")

    L.append("## Primary: out-of-sample R² lift over the baseline\n")
    p = oos[oos.study == "primary"].copy()
    full = p[p.split == "full"]
    t1 = pd.DataFrame({
        "h": full.h,
        "rows": full.n_rows,
        "R² baseline": full.r2_baseline.map(lambda x: fmt(x, 3)),
        "R² test": full.r2_test.map(lambda x: fmt(x, 3)),
        "R² lift": full.r2_lift.map(fmt),
        "90% CI (not gating)": [f"[{fmt(a)}, {fmt(b)}]" for a, b in zip(full.lift_ci_lo, full.lift_ci_hi)],
        "hit rate base/test": [f"{a:.2f} / {b:.2f}" for a, b in zip(full.hit_rate_base, full.hit_rate_test)],
        "tree R² lift (robustness)": full.r2_lift_tree.map(fmt),
    })
    L.append(table(t1) + "\n")
    sp = p[p.split != "full"].pivot(index="h", columns="split", values="r2_lift")
    sp = sp.map(fmt).reset_index()
    L.append("R² lift by test-window split:\n")
    L.append(table(sp) + "\n")

    L.append("## Primary: full-sample coefficients (test model, OLS with issuer FE)\n")
    c = coefs[(coefs.study == "primary") & (coefs["sample"] == "full")].copy()
    c["coef (90% CI)"] = [f"{fmt(a)} [{fmt(lo)}, {fmt(hi)}]" for a, lo, hi in zip(c.coef, c.ci_lo, c.ci_hi)]
    L.append(table(c.pivot(index="h", columns="feature", values="coef (90% CI)").reset_index()) + "\n")
    cs = coefs[(coefs.study == "primary") & (coefs["sample"] != "full") & (coefs.h == 3)]
    L.append("h = 3 coefficients fitted within each test split:\n")
    L.append(table(cs.pivot(index="sample", columns="feature", values="coef").map(fmt).reset_index()) + "\n")

    L.append("## Robustness (reported, not scored)\n")
    rows = []
    for s, label in [("rob_2017on", "as-of ≥ 2017-01"), ("rob_ex_covid", "ex 2020-03..2021-12")]:
        o = oos[(oos.study == s) & (oos.split == "full")].set_index("h")
        cc = coefs[(coefs.study == s) & (coefs["sample"] == "full")]
        for h in sorted(o.index):
            k = cc[cc.h == h].set_index("feature").coef
            rows.append({"sample": label, "h": h, "rows": int(o.loc[h, "n_rows"]),
                         "R² lift": fmt(o.loc[h, "r2_lift"]),
                         "cmp_share": fmt(k.get("cmp_share")), "cmp_growth_yoy": fmt(k.get("cmp_growth_yoy"))})
    L.append(table(pd.DataFrame(rows)) + "\n")

    L.append("## Secondary outcomes (reported only; cannot trigger a GO)\n")
    for s, label, unit in [("secondary_dq30", "Trust 30+ day delinquency rate change", "months"),
                           ("secondary_callreport", "Call Report bank NCO rate change", "quarters")]:
        o = oos[(oos.study == s) & (oos.split == "full")]
        cc = coefs[(coefs.study == s) & (coefs["sample"] == "full")]
        rows = []
        for _, r in o.iterrows():
            k = cc[cc.h == r.h].set_index("feature")
            def cell(f):
                if f not in k.index:
                    return "–"
                lo, hi = k.loc[f, "ci_lo"], k.loc[f, "ci_hi"]
                return fmt(k.loc[f, "coef"]) + ("" if pd.isna(lo) else f" [{fmt(lo)}, {fmt(hi)}]")
            rows.append({f"h ({unit})": int(r.h), "rows": int(r.n_rows), "R² lift": fmt(r.r2_lift),
                         "cmp_share": cell("cmp_share"), "cmp_growth_yoy": cell("cmp_growth_yoy")})
        L.append(f"**{label}** (test {meta.loc[s, 'test_start']}..{meta.loc[s, 'test_end']}, "
                 f"{int(meta.loc[s, 'n_lenders'])} lenders)\n")
        L.append(table(pd.DataFrame(rows)) + "\n")

    L.append("## Notes\n")
    L.append("- R² lift = (SSE_baseline − SSE_test) / SST on the scored rows; positive means the "
             "complaint features lowered out-of-sample squared error.\n"
             "- Coefficients are in outcome units (percentage points of annualized NCO) per unit "
             "of the feature (shares are 0–1; growth is a log difference).\n"
             "- All methodology, timing and sample choices are in DECISIONS.md, dated before "
             "the first model run.\n")
    (ROOT / "report" / "RESULTS.md").write_text("\n".join(L))
    print("wrote report/RESULTS.md")


if __name__ == "__main__":
    main()
