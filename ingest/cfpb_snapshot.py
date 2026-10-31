"""Daily CFPB complaint snapshot.

Downloads the bulk complaints.csv.zip into data/raw/cfpb/{YYYY-MM-DD}/, writes a
small Parquet of counts by company, product and date_received next to it, and
prunes zips older than 14 days (count files are kept forever).

Usage: python ingest/cfpb_snapshot.py [--keep-days 14]
"""
from __future__ import annotations

import argparse
import datetime as dt
import shutil
import sys
from pathlib import Path

import duckdb

sys.path.insert(0, str(Path(__file__).resolve().parent))
from common import RAW, download, raw_dir, today  # noqa: E402

URL = "https://files.consumerfinance.gov/ccdb/complaints.csv.zip"


def snapshot(date: str) -> Path:
    d = raw_dir("cfpb", date)
    zpath = download(URL, d / "complaints.csv.zip")
    counts = d / "counts_company_product_day.parquet"
    if not counts.exists():
        # DuckDB cannot read inside a zip, so extract to a temp CSV, then delete it.
        tmp = d / "_extract"
        tmp.mkdir(exist_ok=True)
        shutil.unpack_archive(zpath, tmp)
        csv = next(tmp.glob("*.csv"))
        con = duckdb.connect()
        con.execute(f"""
            COPY (
              SELECT "Company" AS company, "Product" AS product,
                     CAST("Date received" AS DATE) AS date_received,
                     COUNT(*) AS n_complaints
              FROM read_csv('{csv}', header=true, all_varchar=true)
              GROUP BY ALL
            ) TO '{counts}' (FORMAT parquet)
        """)
        con.close()
        shutil.rmtree(tmp)
    return d


def prune(keep_days: int) -> None:
    cutoff = dt.date.today() - dt.timedelta(days=keep_days)
    for z in (RAW / "cfpb").glob("????-??-??/complaints.csv.zip"):
        if dt.date.fromisoformat(z.parent.name) < cutoff:
            z.unlink()


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--keep-days", type=int, default=14)
    ap.add_argument("--date", default=today())
    a = ap.parse_args()
    d = snapshot(a.date)
    prune(a.keep_days)
    print(f"snapshot ok: {d}")


if __name__ == "__main__":
    main()
