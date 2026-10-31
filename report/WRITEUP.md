# Do CFPB complaints predict credit card losses? A pre-registered backtest says no

*October 2026. Code, data pipeline and every number below: this repository.
Decision rule: [DECISIONS.md](../DECISIONS.md). Full tables:
[RESULTS.md](RESULTS.md).*

## The question

The CFPB publishes every consumer complaint it forwards to a company, about
19 million of them since December 2011, updated daily and free to download.
When a card issuer starts approving riskier customers or its collections start
going badly, it seems plausible that complaints would rise before charge-offs
do. If so, the complaint database would be a cheap leading indicator of credit
losses, and the kind of thing an alternative-data buyer would pay for.

So the question was narrow: **do public CFPB complaints predict credit losses
at large U.S. lenders 1 to 6 months ahead, beyond what the lender's own loss
history and the industry-wide loss trend already tell you?**

The answer, under a rule written down before any outcome data was
downloaded, is no. This write-up explains how the test was built, what it
found, and where it could still be wrong.

## Why pre-register

With a handful of lenders and about ten years of monthly data, it is easy to
find a complaint feature, a horizon and a sample window that look predictive.
To avoid fooling myself, I committed the full design to `DECISIONS.md` before
downloading a single charge-off number: the outcome, the features, the
baseline, the timing rules, the bootstrap, and a five-part GO/NO-GO rule.
Later entries in that file only add facts discovered during data work (for
example, which trusts were parseable); none changes the rule, and each is
dated before the first model run.

The rule required **all five** of these for a GO:

1. Out-of-sample R² lift over the baseline above 0 at h = 3 months in at least
   2 of 3 time splits.
2. Full-window R² lift above 0 for at least 2 of h = 2, 3, 4.
3. Positive full-sample coefficients on the two headline features,
   `cmp_share` and `cmp_growth_yoy`, at every horizon from 1 to 6 months.
4. 90% bootstrap confidence intervals for both coefficients entirely above 0
   at h = 3.
5. Both coefficients positive within every time split at h = 3.

Anything else is NO-GO, including results that "look good but miss."

## Data

**Features: CFPB complaints.** The bulk snapshot of 2026-10-31 (18.8M
complaints). Four features per lender per month, all relative to the market
rather than raw counts, because total CFPB volume has grown enormously:

- `cmp_share`: the lender's share of all credit card complaints, trailing
  3 months.
- `cmp_growth_yoy`: year-over-year growth in the lender's card complaints,
  minus the market's growth.
- `hardship_share`: share of the lender's card complaints about payment
  trouble or collections.
- `timely_rate`: share of the lender's complaints answered on time.

Product and issue labels were mapped to 11 stable product buckets and 10
issue buckets in a committed `taxonomy_map`, since the CFPB rebuilt its
categories in 2017 and 2023.

**Outcome: card master trust charge-offs.** Large card issuers securitize
part of their receivables and file a monthly SEC Form 10-D for each trust,
with the trust's annualized net charge-off (NCO) and delinquency rates. This
gives a monthly loss series, three times more frequent than bank Call Reports.
I pulled 1,948 10-D filings for 11 trusts and wrote a parser per trust. Eight
issuers passed the pre-registered usability test (at least 60 months from
2013 onward, no gap longer than 3 months): American Express, Bank of America,
Barclays US, Capital One, Citi, Discover, JPMorgan Chase and Synchrony. Bread
Financial failed: nine of its 10-Ds in 2022–23 were filed without the
servicer report.

The primary target is the change in a trust's NCO rate over the next *h*
months. Two secondary outcomes were reported but could not trigger a GO: the
change in the trust 30+ day delinquency rate, and the quarterly Call Report
NCO rate for 15 lenders' bank subsidiaries.

**Macro control: unemployment.** The 3-month change in the unemployment rate,
taken from ALFRED vintages, so each forecast sees the number as it was
published at the time, not as later revised.

## Point-in-time handling

Every number a model sees at a forecast date has to have been public on that
date. That is the first thing an alternative-data buyer checks, and the
easiest thing to get wrong.

- **Complaints.** The CFPB publishes a complaint once the company responds or
  15 days pass, whichever is first. I treat every complaint as available 15
  days after it was sent to the company, a conservative upper bound, and bucket
  features by that availability month. Only consumer-supplied fields are used;
  the one company-response field, `timely_rate`, is lagged two extra months.
- **Outcomes.** A 10-D for collection month *p* is filed during month *p*+1.
  The forecast origin is the end of month *p*+1, and a row is used only if its
  10-D was actually filed by then.
- **Training rows.** In the walk-forward, a training row is allowed only if
  its own target had already been filed before the forecast date. This stops
  the model from learning from charge-offs that were not yet public.
- **Unemployment.** As published in the vintage in effect on the forecast
  date.

The evaluation is an expanding-window walk-forward: refit every month, predict
the next month's rows. The panel starts in February 2013. The first 36 months
are training only; the test window runs from February 2016 to July 2026, split
into three equal thirds. The baseline is OLS with issuer fixed effects, the
trust's current NCO level, three lagged monthly changes, the cross-issuer mean
change, and the unemployment change. The test model adds the four complaint
features. Confidence intervals come from a block bootstrap (2,000 draws) that
resamples lenders and 12-month blocks independently, because with 8 lenders a
lucky result is easy.

## Results

**The decision is NO-GO. All five conditions fail, not just one.**

At the primary horizon of 3 months, adding complaint features made
out-of-sample forecasts slightly *worse*: R² lift −0.039, 90% CI
[−0.171, +0.047], over 955 scored lender-months. By split, the lift was
−0.021 (2016–19), −0.076 (2019–23) and +0.008 (2023–26), so it was positive
in only one of three. Across horizons, only h = 4 showed a positive full-window
lift, at +0.007.

| h (months) | R² lift | 90% CI |
|---|---|---|
| 1 | −0.078 | [−0.206, +0.000] |
| 2 | −0.101 | [−0.231, +0.001] |
| 3 | −0.039 | [−0.171, +0.047] |
| 4 | +0.007 | [−0.107, +0.116] |
| 5 | −0.001 | [−0.128, +0.104] |
| 6 | −0.032 | [−0.110, +0.033] |

The coefficients point the wrong way. If rising complaints warned of rising
losses, both headline features should have positive coefficients. In the
full-sample fit, **both are negative at every horizon from 1 to 6 months**.
At h = 3, `cmp_share` is −0.23 (90% CI [−1.77, +2.35]) and `cmp_growth_yoy`
is −0.16 ([−0.33, +0.01]). Fitted within each split, the signs are not even
stable: `cmp_share` is positive in the first two splits and strongly negative
in the third, while `cmp_growth_yoy` does the reverse. That is what noise
looks like.

The directional hit rate on charge-off changes was about the same with and
without complaints (0.55 vs 0.54 at h = 3).

**Robustness runs** (reported, not scored) do not change the picture. Starting
the sample in 2017 makes the lift negative at every horizon, with both
coefficients negative. Dropping every row that touches March 2020 through
December 2021 also leaves the lift negative at every horizon (−0.052 at
h = 3). In that ex-COVID run `cmp_share` turns positive (+0.75 at h = 3) while
`cmp_growth_yoy` stays negative, so the two features still disagree.

**Secondary outcomes.** On trust delinquency, the lift is negative at every
horizon and both coefficients are negative. The quarterly Call Report outcome
is the one loose end: the test model's R² lift is positive at all four
quarterly horizons (+0.06 to +0.63), but the `cmp_share` coefficient is
negative at every horizon with intervals spanning zero. This outcome was
pre-registered as reported-only, it covers 15 lenders at quarterly frequency,
and it does not show complaints rising ahead of losses. I note it rather than
explain it away; it is the place I would look first if I revisited this.

## The caveat about negative R²

Both linear models have **negative** out-of-sample R², meaning they forecast
worse than the test-window average of the target would have. A reader should
know why, because it affects how much the comparison between them means.

The cause is 2020. The pre-registered baseline includes the real-time 3-month
change in unemployment, which jumped about 11 points in April 2020, while
card charge-offs *fell* as stimulus and forbearance arrived. A linear model
extrapolates that spike into large predicted loss increases that never
happened. As-of year 2020 alone accounts for 58% of the baseline's
out-of-sample squared error at h = 3, and 55–67% at h = 1 to 3.

Two consequences:

- **The comparison is dominated by one year.** The R² lift is a difference in
  squared errors, so a single bad year can move it. That is why the ex-COVID
  robustness run matters: with those rows removed, the lift is still negative
  at every horizon, so the NO-GO does not depend on 2020.
- **The tree model's big "lift" is not a signal.** A gradient-boosted tree,
  run as a robustness check, beats the OLS baseline by +0.73 R² at h = 3. Trees
  cannot extrapolate beyond the training range, so they simply avoid the 2020
  blow-up. That is a statement about the baseline's functional form, not about
  complaints.

A better baseline would cap or drop the unemployment term. I did not change it,
because the rule says the baseline is fixed, and a baseline tuned after seeing
results is exactly what pre-registration is meant to prevent.

## Limits

- **Eight issuers.** All are large, prime-leaning card lenders. A complaint
  signal might exist for subprime or fintech lenders, but most of those have no
  monthly loss series to test against.
- **Trusts are not the whole book.** Master trusts hold seasoned, selected
  receivables. New accounts, where early complaints might matter most, are
  under-represented.
- **Backfill was not measured.** The bulk CSV may include complaints that were
  not public at the time. Daily snapshots began on the day of the run, so
  there is not yet any history to measure this. Backfill would bias the test
  *toward* finding a signal, so it cannot rescue a negative result, but it
  would matter for any future positive one.
- **Complaints are not a sample.** They come from consumers who know the CFPB
  exists and choose to file. Volume reflects publicity, CFPB outreach and
  company response practices as much as customer distress.
- **Taxonomy shifts.** `hardship_share` has level shifts at the 2013 and 2017
  category changes. These hit all lenders at once, and that feature did not
  gate the decision.
- **Structural events.** Capital One acquired Discover in May 2025, and
  Discover-named complaints end in March 2026. Synchrony switched trusts in
  2023. Both are handled by rule (separate entities; no change computed across
  a trust switch), but each removes some clean data.

## What follows

Under the pre-registered rule, a NO-GO ends the project's commercial branch.
The planned phase 4, tagging complaint narratives with an LLM to find finer
hardship categories, is skipped: it was meant to strengthen an existing
signal, and there is none to strengthen at this level.

The result is useful on its own terms. Complaint counts and shares,
normalized to the market and handled point-in-time, do not add predictive
information about card losses beyond what issuers' own loss trends and the
industry trend already carry. If complaints lead losses at all, the lead is
too weak or too unstable to show up across eight large issuers and ten years
of monthly data.

The whole pipeline rebuilds from raw public data with `make all`, and every
methodology choice, including the ones made before results were seen, is in
`DECISIONS.md` with its date.
