# DECISIONS.md — Credit Canary pre-registration

Every methodology choice is logged here with its date. Entries are append-only:
a later entry may add information (for example a data-feasibility finding), but
the decision rule below cannot be changed after any model result has been seen.

---

## 2026-10-31 — Pre-registration (committed before any outcome data is downloaded)

At the time of this commit no 10-D, FDIC/Call Report or FRED/ALFRED data has
been downloaded to this repository or machine for this project.

### Question

Do public CFPB consumer complaints predict credit losses at public U.S. lenders
1 to 6 months ahead, beyond what the lender's own loss history and the
cross-issuer loss trend already tell you?

### Primary outcome

- `nco_rate`: monthly annualized net charge-off rate of the issuer's credit
  card master trust, taken from the trust's SEC Form 10-D (Exhibit 99 monthly
  servicer/noteholder report).
- Primary target: `nco_chg_h = nco_rate[p+h] - nco_rate[p]`, where `p` is the
  latest collection period known at the forecast date (see timing below).
- Primary horizon: **h = 3 months**. Also reported: h = 1, 2, 4, 5, 6.
- Where an issuer has more than one card trust, the issuer series is the
  receivables-weighted average across its trusts when weights are available,
  otherwise the largest trust.

### Secondary outcomes (reported only; cannot trigger a GO)

- `dq30_chg_h`: change in the 30+ day delinquency rate from the same trusts,
  same horizons.
- `bank_nco_q`: quarterly Call Report net charge-off rate (NCO over average
  loans) of the lender's bank subsidiaries, summed across FDIC certs, at
  h = 1 quarter.

### Timing (forecast origin)

- A 10-D for collection period `p` is filed during month `p+1`. The forecast
  origin for row `(lender, p)` is the **as-of date = last calendar day of month
  p+1**. A row is used only if the 10-D for `p` was filed on or before that
  date; otherwise `nco_rate[p]` is treated as unknown at the origin and the row
  is dropped.
- All complaint features for row `(lender, p)` use only complaint records with
  `available_date <= as-of date`.
- Walk-forward training rows must have their target realised by the origin:
  when predicting at origin `p`, a training row `p'` at horizon `h` is allowed
  only if `p' + h <= p - 1` (its target's 10-D was filed by the end of month
  `p' + h + 1 <= p`, i.e. strictly before the current as-of month).

### Point-in-time rules for complaint data

- `available_date = date_sent_to_company + 15 days` (conservative upper bound
  on CFPB publication). If `date_sent_to_company` is missing, use
  `date_received + 15 days`.
- A complaint's **feature month** is the calendar month of its
  `available_date`. All counts are bucketed by feature month, so a feature for
  as-of month `m` never sees a record whose `available_date` is after the
  end of `m`.
- Only consumer-supplied fields are used (product, sub-product, issue,
  sub-issue, state, tags). The single exception is `timely_rate`, which uses
  the company's "Timely response?" field and is lagged 2 additional months.
- Features are within-product shares or growth relative to the market, never
  raw counts.
- Product/issue categories are mapped to 8–12 stable buckets through the
  `taxonomy_map` table, which is committed before any outcome data loads.
- Narratives are not used in phases 1–3.

### Features (test model)

Let `m` be the as-of month (= p+1). The lender's **main product bucket** is
`credit_card` for every lender scored on the primary (card trust) outcome. For
the Call Report secondary outcome it is the lender's highest-volume credit
bucket over 2012–2016 (fixed, not re-chosen later).

- `cmp_share`: lender's complaints in its main product bucket over feature
  months m-2..m, divided by all CFPB complaints in that bucket over the same
  months.
- `cmp_growth_yoy`: `ln((1+L[m-2..m]) / (1+L[m-14..m-12])) -
  ln(M[m-2..m] / M[m-14..m-12])`, where `L` is the lender's main-bucket count
  and `M` is the market's main-bucket count.
- `hardship_share`: share of the lender's main-bucket complaints over feature
  months m-2..m whose issue maps to the `payment_trouble` or `collections`
  buckets.
- `timely_rate`: share of the lender's complaints (all buckets) over feature
  months m-4..m-2 with `timely_response = 'Yes'` (i.e. lagged 2 months).

Features are used as levels, not standardized, so coefficient signs are
directly interpretable. No other features and no feature search before the
go/no-go decision.

### Models

- **Baseline** (OLS): `nco_chg_h ~ issuer fixed effects + nco_rate[p] +
  Δnco[p] + Δnco[p-1] + Δnco[p-2] + xmean_Δnco[p] + Δunrate`
  - `Δnco[k] = nco_rate[k] - nco_rate[k-1]` (the outcome's own lags).
  - `xmean_Δnco[p]`: cross-issuer mean of `Δnco[p]` (change t-1 to t, known
    at the origin), over issuers whose 10-D for `p` was filed by the as-of date.
  - `Δunrate`: 3-month change in UNRATE as published in the ALFRED vintage in
    effect on the as-of date (latest observation in that vintage minus the
    observation 3 months earlier in the same vintage).
- **Test model** = baseline + `cmp_share` + `cmp_growth_yoy` +
  `hardship_share` + `timely_rate`.
- Linear models come first and decide GO/NO-GO. A gradient-boosted tree model
  (scikit-learn HistGradientBoostingRegressor, default settings, seed
  20261031) is a reported robustness check only.

### Walk-forward evaluation

- Expanding window, refit at every origin month. The panel starts at the
  first as-of month in which every feature is defined for at least one lender.
  The first 36 panel months are training only; every later month is in the
  test window.
- The test window is split into 3 consecutive, equal-length thirds (by
  calendar month; if the month count is not divisible by 3 the remainder goes
  to the last third).
- `OOS R² lift = (SSE_baseline - SSE_test) / SST`, where SST is the sum of
  squared deviations of the realised target from its mean over the evaluated
  rows. A positive lift means the test model has lower out-of-sample squared
  error than the baseline.
- Also reported: directional hit rate on charge-off increases
  (sign agreement between forecast and realised `nco_chg_h`).

### Decision rule — GO requires ALL of the following; anything else is NO-GO

1. The point estimate of the OOS R² lift over the baseline at h = 3 is
   above 0 in at least 2 of the 3 test-window splits.
2. Over the full test window, the OOS R² lift point estimate is above 0 for
   at least 2 of h = 2, 3, 4.
3. In the full-sample OLS fit of the test model, the coefficients on
   `cmp_share` and `cmp_growth_yoy` are both above 0 at every h = 1..6.
4. At h = 3, the 90% bootstrap CI for both of those coefficients is entirely
   above 0.
5. At h = 3, neither coefficient flips sign in any split: the test model is
   fitted separately on the rows of each of the 3 test-window splits, and both
   coefficients must be above 0 in every split.

Results that look good but miss any condition count as NO-GO. This rule cannot
be changed after results are seen.

### Confidence intervals

- 90% percentile block bootstrap, 2,000 draws, seed **20261031**.
- Each draw resamples lenders with replacement and, independently, 12-month
  calendar time blocks with replacement (blocks aligned to calendar years of
  the as-of month); the draw's sample is every row of every drawn lender in
  every drawn block. Duplicated lenders get distinct fixed-effect ids.
- Coefficient CIs come from refitting the full-sample OLS on each draw. OOS R²
  lift CIs resample the stored walk-forward forecast errors with the same
  scheme (no refit). R² lift CIs are reported but do not gate the decision.

### Fallback

- An issuer has **usable monthly 10-D NCO** if its parsed series has at
  least 60 monthly observations with collection periods from 2013-01 onward
  and no gap longer than 3 consecutive months.
- If fewer than 3 issuers have usable monthly 10-D NCO, the primary outcome
  becomes the quarterly Call Report NCO rate change (`bank_nco_chg`) on a
  lender-quarter panel, under the same rule with horizons read in quarters:
  conditions 1, 4 and 5 use h = 1 quarter; condition 2 uses h = 1, 2, 3
  quarters (at least 2 of 3 above 0); condition 3 uses h = 1..4 quarters. The
  first 12 quarters are training only; bootstrap blocks are 4 quarters. The
  as-of date for quarter q is 60 days after quarter end (Call Report filing
  deadline is 30–35 days after quarter end; FDIC publication follows).
  Features are built at the quarter's as-of month the same way.
- The switch and the issuer count are logged in this file before any model
  runs.

### Sample

- Complaint features start 2012-01 (feature months).
- Primary sample: all panel months.
- Robustness runs, reported but not scored:
  (a) as-of months from 2017-01 onward;
  (b) excluding every row whose as-of month or target collection month falls
      in 2020-03 through 2021-12.

### Data hygiene

- Raw downloads go to `data/raw/{source}/{YYYY-MM-DD}/` and are never modified.
- SEC EDGAR requests send `User-Agent: CreditCanary research 7thvex@gmail.com`
  and stay at or below 10 requests/second.
- FRED unemployment comes from ALFRED vintages as of each as-of date.

---

## 2026-10-31 — Lender universe and taxonomy (committed before any outcome data loads)

- CFPB bulk snapshot of 2026-10-31: 18,792,616 complaints, date_received
  2011-12-01 to 2026-10-30. The bulk CSV no longer carries the
  "Consumer complaint narrative" or "Consumer consent provided?" columns
  (relevant to phase 4 only).
- `taxonomy_map` (`sql/seeds/taxonomy_map.csv`, generated by
  `sql/seeds/build_taxonomy_map.py`): 11 product buckets covering every
  product/sub-product label, and 10 issue buckets covering every issue under the
  credit product buckets (credit_card, personal_loan, vehicle_loan,
  prepaid_card). Category rebuilds seen in the data: 2017-04 and 2023-08.
- Known limitation, not a methodology change: `hardship_share` has level
  shifts at the category rebuilds (credit-card "Collection practices" /
  "Collection debt dispute" issues end 2013-07 when Debt collection became its
  own product; payment-trouble issues are renamed in 2017-04). These shifts hit
  all lenders at once. `hardship_share` does not gate the decision.
- Lender universe (`sql/seeds/lender_universe.csv`): 15 public lenders, ranked
  by complaint volume in credit card + personal/vehicle loan buckets
  (`lender_ranking` mart): Capital One, Citi, JPMorgan Chase, Synchrony, Bank of
  America, American Express, Wells Fargo, Bread Financial, Discover, Barclays
  US, U.S. Bancorp, Ally, TD US, Goldman Sachs Bank USA, Citizens. Excluded:
  credit bureaus (not lenders), Navy Federal / USAA / PenFed (not public),
  Santander (CFPB name split across two entities), fintechs and auto finance
  companies without a bank Call Report or card trust (Affirm, OneMain, Credit
  Acceptance, Westlake). Wells Fargo's card trust only began in 2024, so it is
  Call-Report-only.
- Discover: acquired by Capital One 2025-05-18; Discover-named complaints end
  2026-03. Both lenders are kept as separate entities with their own series.

---

## 2026-10-31 — Step 4: 10-D feasibility (recorded before any model runs)

Pulled every 10-D filed 2011-01 onward for 11 card trusts (`sql/seeds/trusts.csv`,
1,948 filings, 1.3 GB raw). Every trust reports a monthly annualized net
charge-off / net loss rate and a delinquency-by-bucket table. Parser:
`ingest/parse_10d.py` (one label spec per trust).

| Issuer | Trust(s) used | NCO field | Months with NCO since 2013-01 | Max gap | Usable |
|---|---|---|---|---|---|
| American Express | AmEx Credit Account Master Trust | Annualized Default Rate, Net of Recoveries | 165 | 0 | yes |
| Bank of America | BA Credit Card Trust | Investor Default Amount net of Recoveries (% of weighted avg investor interest) | 165 | 0 | yes |
| Barclays US | Barclays Dryrock Issuance Trust | Total Net Losses % of Portfolio Principal (2013–15: gross loss rate × (1 − recoveries/defaults)) | 164 (from 2013-02) | 0 | yes |
| Capital One | COMET (Capital One Master Trust statement) | Annualized Net Default Rate (to 2016: gross default rate × (1 − recoveries/defaults)) | 165 | 0 | yes |
| Citi | Citibank Credit Card Issuance Trust | Credit Loss Component of Portfolio Yield | 165 | 0 | yes |
| Discover | Discover Card Master Trust I (DCENT fills gaps) | Net Charge-offs (annualized) | 147 (to 2025-11) | 2 | yes |
| JPMorgan Chase | Chase Issuance Trust | Net Losses % of Average Pool Balance (to 2015-10: Net Credit Losses line of the Asset Pool One excess-spread table) | 165 | 0 | yes |
| Synchrony | Synchrony Credit Card Master Note Trust (to 2023-04), Synchrony Card Issuance Trust (2018-09 on) | Net Charge-Off Rate | 123 + 97 | 1 | yes |
| Bread Financial | WFN Credit Card Master Note Trust | Net Principal Charge-Off Rate | 156 | **9** | **no** |

**Usable issuer count: 8** (≥ 3), so the primary outcome stays monthly 10-D NCO;
no fallback.

- Bread Financial fails the pre-registered usability rule: its 10-Ds for
  collection months 2022-09 through 2023-05 were filed without the servicer
  report exhibit (checked on EDGAR, including the depositor CIK 1139552). It is
  excluded from the primary outcome and kept for the Call Report secondary.
- Wells Fargo, U.S. Bancorp, TD, Goldman Sachs, Ally and Citizens have no card
  trust with 10-D history and are Call-Report-only, as planned in step 3.
- Validation of derived rates: where both exist, COF's reported net rate equals
  gross × (1 − recoveries/defaults) to ±0.01pp (2016-03..2017-10), and Chase's
  excess-spread "Net Credit Losses" equals the later pool "Net Losses" line
  exactly (2015-11..2016-05). Discover rows are kept only if
  gross − recoveries = net within 0.025pp.

Implementation details fixed before any model runs:
- Collection month of a 10-D = filing month − 1 (EDGAR reportDate is the
  distribution date for some trusts and is mislabeled once). Only original
  10-Ds are used; 10-D/A amendments are dropped; earliest original wins.
- Issuer series when an issuer has two trusts: the parser does not extract
  receivables, so the "largest trust" fallback applies. Synchrony = SCCMNT
  while it reports (to 2023-04), then SCIT. Discover = DCMT, DCENT where
  DCMT is missing (same receivables pool).
- Outcome changes (`nco_chg_h`, own lags `Δnco`) are only computed when both
  endpoints come from the same trust, so the Synchrony trust switch never
  creates an artificial jump.
- DQ30 coverage is incomplete in some early years (AXP before 2014, BofA
  before 2015, Bread before 2015). DQ30 is secondary and reported only.

---

## 2026-10-31 — Backtest implementation details (recorded before any model runs)

These fill in mechanics the pre-registration left open. None of them has been
informed by any model output: no model has been run yet.

- **Panel start**: first as-of month where all four features and all baseline
  regressors are defined for at least one issuer = **2013-02**. Training-only
  months: 2013-02 .. 2016-01 (36 months).
- **Estimation sample**: complete cases on baseline + test regressors and the
  target, so baseline and test model are always fitted and scored on the same
  rows.
- **Test window** (fixed for all horizons): as-of months after the 36 training
  months, through the last as-of month that has at least one realised h = 3
  target. Split into thirds by calendar month (remainder to the last third).
  Each horizon is scored on its rows inside this window.
- **Walk-forward**: at as-of month m (= p + 1), fit on rows with
  `p' + h <= p - 1` and predict the rows of month m. Lender fixed effects are
  dummies; an issuer with no training rows yet is not scored that month.
- **Directional hit rate**: share of scored rows with sign(forecast) =
  sign(realised change), excluding realised changes of exactly 0; also the share
  of realised increases that were forecast as increases.
- **OOS R² lift bootstrap**: resample (lender, calendar-year block) cells of the
  stored out-of-sample squared errors, using the same scheme as the coefficient
  bootstrap.
- **Tree robustness**: HistGradientBoostingRegressor (default settings,
  random_state 20261031) with the same regressors plus lender one-hot, same
  walk-forward; full-window R² lift vs the OLS baseline only.
- **Robustness samples**: (a) as-of months ≥ 2017-01, with that sample's own
  first 36 months as training; (b) rows whose as-of month or target month
  (p + h) falls in 2020-03 .. 2021-12 are dropped from both training and
  scoring. Neither is scored against the decision rule.
- **Secondary DQ30**: same design, with the outcome's own lags (dq30 level,
  Δdq30 at p, p-1, p-2) and the cross-issuer mean Δdq30 in place of the NCO
  terms. **Secondary Call Report**: lender-quarter panel, 12 training quarters,
  training rows need `q' + h <= q`, baseline = bank NCO level + three lagged
  changes + cross-lender mean change + Δunrate + lender FE, features from the
  lender's `cr_main` bucket. Both are reported only.
