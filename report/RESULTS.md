# Results: NO-GO

**Decision under the pre-registered rule (DECISIONS.md, 2026-10-31): NO-GO.** GO requires all five conditions; anything else is NO-GO.

Primary outcome: monthly card master-trust NCO rate change from SEC 10-D filings, 8 usable issuers. Panel starts 2013-02; training-only months to 2016-02 (exclusive); test window 2016-02..2026-07, split S1 2016-02..2019-07, S2 2019-08..2023-01, S3 2023-02..2026-07. Bootstrap: 2000 draws, seed 20261031, lenders × 12-month blocks.

## Decision conditions

| condition | rule | values | result |
|---|---|---|---|
| 1 | OOS R² lift > 0 at h=3 in >= 2 of 3 splits | S1=-0.0209; S2=-0.0763; S3=+0.0076 | FAIL |
| 2 | Full-window OOS R² lift > 0 for >= 2 of h=[2, 3, 4] | h2=-0.1008; h3=-0.0389; h4=+0.0066 | FAIL |
| 3 | Full-sample coefs on ['cmp_share', 'cmp_growth_yoy'] > 0 at every h=[1, 2, 3, 4, 5, 6] | h1 cmp_share=-0.05948; h1 cmp_growth_yoy=-0.05643; h2 cmp_share=-0.1788; h2 cmp_growth_yoy=-0.1208; h3 cmp_share=-0.2332; h3 cmp_growth_yoy=-0.1627; h4 cmp_share=-0.2309; h4 cmp_growth_yoy=-0.1944; h5 cmp_share=-0.4349; h5 cmp_growth_yoy=-0.2035; h6 cmp_share=-0.7137; h6 cmp_growth_yoy=-0.1981 | FAIL |
| 4 | 90% CI of both coefs entirely > 0 at h=3 | cmp_share [-1.772, +2.351]; cmp_growth_yoy [-0.3259, +0.00577] | FAIL |
| 5 | Neither coef flips sign (both > 0) in any split at h=3 | S1 cmp_share=+0.7428; S1 cmp_growth_yoy=-0.2875; S2 cmp_share=+1.151; S2 cmp_growth_yoy=-0.08337; S3 cmp_share=-10.37; S3 cmp_growth_yoy=+0.03165 | FAIL |

## Primary: out-of-sample R² lift over the baseline

| h | rows | R² baseline | R² test | R² lift | 90% CI (not gating) | hit rate base/test | tree R² lift (robustness) |
|---|---|---|---|---|---|---|---|
| 1 | 960 | -0.630 | -0.708 | -0.0781 | [-0.2057, +0.0002] | 0.63 / 0.62 | +0.6649 |
| 2 | 958 | -1.283 | -1.384 | -0.1008 | [-0.2314, +0.0011] | 0.59 / 0.58 | +1.1877 |
| 3 | 955 | -0.952 | -0.991 | -0.0389 | [-0.1706, +0.0471] | 0.55 / 0.54 | +0.7334 |
| 4 | 948 | -0.310 | -0.304 | +0.0066 | [-0.1069, +0.1155] | 0.60 / 0.59 | +0.1815 |
| 5 | 940 | -0.179 | -0.180 | -0.0008 | [-0.1277, +0.1044] | 0.58 / 0.59 | +0.0650 |
| 6 | 930 | -0.162 | -0.193 | -0.0316 | [-0.1103, +0.0332] | 0.59 / 0.60 | +0.0948 |

R² lift by test-window split:

| h | S1 | S2 | S3 |
|---|---|---|---|
| 1 | -0.0046 | -0.2177 | -0.0026 |
| 2 | -0.0138 | -0.2348 | +0.0067 |
| 3 | -0.0209 | -0.0763 | +0.0076 |
| 4 | -0.0123 | +0.0183 | +0.0056 |
| 5 | -0.0034 | -0.0074 | +0.0163 |
| 6 | -0.0081 | -0.0649 | +0.0153 |

## Primary: full-sample coefficients (test model, OLS with issuer FE)

| h | cmp_growth_yoy | cmp_share | hardship_share | timely_rate |
|---|---|---|---|---|
| 1 | -0.0564 [-0.1465, +0.0472] | -0.0595 [-0.7128, +1.1402] | +0.0778 [-0.5069, +0.9651] | +0.2465 [-1.2792, +2.7797] |
| 2 | -0.1208 [-0.2418, +0.0083] | -0.1788 [-1.2963, +1.5916] | -0.0357 [-0.8876, +1.5057] | +0.2534 [-0.7164, +6.0092] |
| 3 | -0.1627 [-0.3259, +0.0058] | -0.2332 [-1.7717, +2.3514] | -0.3388 [-1.4990, +1.4838] | +0.2419 [-1.1379, +7.0112] |
| 4 | -0.1944 [-0.4281, +0.0456] | -0.2309 [-2.5556, +3.4444] | -0.6387 [-2.0752, +1.6302] | +0.3026 [-3.2312, +8.4369] |
| 5 | -0.2035 [-0.4944, +0.0852] | -0.4349 [-3.3532, +4.1627] | -1.1431 [-2.9148, +1.2249] | +0.1466 [-10.2474, +6.3528] |
| 6 | -0.1981 [-0.5412, +0.1300] | -0.7137 [-4.2655, +4.9747] | -1.2898 [-3.5378, +1.3169] | +0.0830 [-14.5632, +6.8566] |

h = 3 coefficients fitted within each test split:

| sample | cmp_growth_yoy | cmp_share | hardship_share | timely_rate |
|---|---|---|---|---|
| S1 | -0.2875 | +0.7428 | -1.3607 | -5.5119 |
| S2 | -0.0834 | +1.1509 | -10.7508 | +0.1404 |
| S3 | +0.0317 | -10.3714 | -9.6691 | +0.9137 |

## Robustness (reported, not scored)

| sample | h | rows | R² lift | cmp_share | cmp_growth_yoy |
|---|---|---|---|---|---|
| as-of ≥ 2017-01 | 1 | 601 | -0.4704 | -0.0948 | -0.0852 |
| as-of ≥ 2017-01 | 2 | 600 | -1.6070 | -0.6187 | -0.1464 |
| as-of ≥ 2017-01 | 3 | 597 | -1.2190 | -0.8565 | -0.1876 |
| as-of ≥ 2017-01 | 4 | 589 | -0.1897 | -1.0712 | -0.2399 |
| as-of ≥ 2017-01 | 5 | 580 | -0.1693 | -1.0698 | -0.2807 |
| as-of ≥ 2017-01 | 6 | 570 | -0.3852 | -1.2208 | -0.3151 |
| ex 2020-03..2021-12 | 1 | 796 | -0.0141 | +0.4436 | -0.0867 |
| ex 2020-03..2021-12 | 2 | 785 | -0.0251 | +0.5583 | -0.1691 |
| ex 2020-03..2021-12 | 3 | 775 | -0.0522 | +0.7455 | -0.2219 |
| ex 2020-03..2021-12 | 4 | 759 | -0.0628 | +1.1417 | -0.2591 |
| ex 2020-03..2021-12 | 5 | 743 | -0.0989 | +1.3074 | -0.2729 |
| ex 2020-03..2021-12 | 6 | 726 | -0.0857 | +1.3414 | -0.2678 |

## Secondary outcomes (reported only; cannot trigger a GO)

**Trust 30+ day delinquency rate change** (test 2016-02..2026-07, 8 lenders)

| h (months) | rows | R² lift | cmp_share | cmp_growth_yoy |
|---|---|---|---|---|
| 1 | 904 | -0.0596 | -0.0545 | -0.0094 |
| 2 | 900 | -0.1669 | -0.1104 | -0.0241 |
| 3 | 896 | -0.2671 | -0.2494 | -0.0453 |
| 4 | 889 | -0.2647 | -0.4606 | -0.0721 |
| 5 | 881 | -0.3309 | -0.6494 | -0.1016 |
| 6 | 870 | -0.4209 | -0.7761 | -0.1296 |

**Call Report bank NCO rate change** (test 2015Q4..2026Q1, 15 lenders)

| h (quarters) | rows | R² lift | cmp_share | cmp_growth_yoy |
|---|---|---|---|---|
| 1 | 561 | +0.0577 | -0.6900 [-2.5424, +0.5089] | -0.0174 [-0.1351, +0.0794] |
| 2 | 547 | +0.6340 | -0.7465 [-3.7233, +0.8086] | -0.0067 [-0.1418, +0.1501] |
| 3 | 534 | +0.3263 | -0.4939 [-3.9899, +1.7370] | +0.0111 [-0.1336, +0.2037] |
| 4 | 521 | +0.0270 | -0.2809 [-5.0055, +1.9035] | -0.0116 [-0.1562, +0.1936] |

## Why the out-of-sample R² values are negative

Both models score below the test-window mean because of 2020: the pre-registered baseline includes the real-time 3-month UNRATE change, which jumped by about 11 points in April 2020 while trust charge-offs fell. The linear models extrapolate that into large forecast increases. Share of baseline out-of-sample SSE from as-of year 2020: h1 55%, h2 67%, h3 58%, h4 37%, h5 25%, h6 21%. Trees do not extrapolate, which is most of why the tree's R² lift over the OLS baseline is large; it is not evidence of a complaint signal. The ex-COVID robustness run above removes these rows.

## Notes

- R² lift = (SSE_baseline − SSE_test) / SST on the scored rows; positive means the complaint features lowered out-of-sample squared error.
- Coefficients are in outcome units (percentage points of annualized NCO) per unit of the feature (shares are 0–1; growth is a log difference).
- All methodology, timing and sample choices are in DECISIONS.md, dated before the first model run.
