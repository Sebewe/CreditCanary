# Credit Canary

Do public CFPB consumer complaints predict credit losses at public U.S. lenders
1 to 6 months ahead? This repo answers that with a point-in-time, walk-forward
backtest whose decision rule was fixed before any outcome data was downloaded
(see [DECISIONS.md](DECISIONS.md)). The result is in
[report/RESULTS.md](report/RESULTS.md).

## Data

| Source | Role | Ingest |
|---|---|---|
| CFPB Consumer Complaint Database (bulk CSV) | features | `ingest/cfpb_snapshot.py` |
| SEC Form 10-D, card master trusts | primary outcome: monthly NCO, DQ30 | `ingest/sec_10d.py`, `ingest/parse_10d.py` |
| FDIC BankFind (Call Report) | secondary outcome: quarterly bank NCO | `ingest/fdic.py` |
| ALFRED UNRATE vintages | macro control, as published at each date | `ingest/alfred_unrate.py` |

Raw pulls land in `data/raw/{source}/{YYYY-MM-DD}/` and are never modified.
`data/` is gitignored. A full build uses about 3 GB on disk after staging
(the 5.7 GB extracted CSV is deleted once it is staged).

## Layout

```
ingest/        downloads (raw, immutable) and the 10-D parser
sql/staging/   raw -> typed tables (DuckDB)
sql/marts/     taxonomy_map, lender_map, features, monthly + quarterly panels
sql/seeds/     hand-maintained tables: taxonomy, lender universe, certs, trusts
backtest/      walk-forward OLS backtest (numpy), bootstrap CIs
report/        RESULTS.md and the results tables it is built from
tests/         pytest data checks (row counts, keys, dates, point-in-time)
launchd/       daily CFPB snapshot agent
```

## Run

```bash
python3 -m venv .venv && .venv/bin/pip install -r requirements.txt
```

```bash
make all
```

`make all` pulls anything not yet downloaded today, then rebuilds staging,
marts, the backtest, `report/RESULTS.md` and runs the tests. `make rebuild`
does the same from the existing raw pulls without downloading.

SEC requests send `User-Agent: CreditCanary research 7thvex@gmail.com` and stay
under 10 requests/second.

## Daily CFPB snapshot (launchd)

The bulk CSV is restated over time (backfill), so a daily snapshot is kept from
day one: the zip is kept for 14 days and a small Parquet of counts by company,
product and date_received is kept forever.

Install (runs `ingest/cfpb_snapshot.py` every day at 06:00):

```bash
./launchd/install.sh
```

Remove it:

```bash
./launchd/uninstall.sh
```

`uninstall.sh` runs `launchctl bootout gui/$(id -u)` on
`~/Library/LaunchAgents/com.creditcanary.snapshot.plist` and deletes that file.
Logs go to `data/logs/snapshot.log`.
