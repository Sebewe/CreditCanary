# Credit Canary: rebuild everything from raw.
#   make all      ingest (skips files already pulled today) -> staging -> marts -> backtest -> report -> tests
#   make rebuild  everything except downloads (uses the latest raw pulls)
PY      := .venv/bin/python
SQL     := $(PY) sql/run_sql.py
CFPB_ZIP = $(shell ls -d data/raw/cfpb/*/complaints.csv.zip 2>/dev/null | tail -1)

.PHONY: all rebuild venv ingest staging marts backtest report test clean-work

all: ingest rebuild

rebuild: staging marts backtest report test

venv:
	python3 -m venv .venv && $(PY) -m pip install -q -r requirements.txt

ingest:
	$(PY) ingest/cfpb_snapshot.py
	$(PY) ingest/sec_10d.py
	$(PY) ingest/fdic.py
	$(PY) ingest/alfred_unrate.py

# The bulk CSV is extracted to data/work only while staging runs (5.7 GB).
staging:
	mkdir -p data/work/cfpb
	unzip -o -q $(CFPB_ZIP) -d data/work/cfpb
	$(SQL) sql/staging/stg_complaints.sql
	rm -f data/work/cfpb/complaints.csv
	$(PY) ingest/parse_10d.py
	$(SQL) sql/staging/stg_trust_monthly.sql sql/staging/stg_unrate_vintages.sql sql/staging/stg_call_report.sql

marts:
	$(SQL) sql/marts/taxonomy_map.sql sql/marts/lender_ranking.sql sql/marts/lender_map.sql \
	       sql/marts/issuer_outcomes_monthly.sql sql/marts/complaint_features.sql \
	       sql/marts/panel_monthly.sql sql/marts/panel_quarterly.sql

backtest:
	$(PY) backtest/run_backtest.py

report:
	$(PY) report/write_results.py

test:
	$(PY) -m pytest -q tests

clean-work:
	rm -rf data/work data/warehouse.duckdb data/staging data/marts data/results
