"""ALFRED real-time vintages of UNRATE.

For every month-end as-of date from 2011-12-31 to today, save the UNRATE
series exactly as it was published on that date (ALFRED vintage) to
data/raw/alfred/{pull date}/UNRATE_{as_of}.csv. Downstream code uses only the
vintage for each as-of date, so later revisions never leak backwards.

No API key needed: uses ALFRED's public CSV graph endpoint, ~1 request/s.
"""
from __future__ import annotations

import argparse
import datetime as dt
import sys
import time
from pathlib import Path

import pandas as pd
import requests

sys.path.insert(0, str(Path(__file__).resolve().parent))
from common import raw_dir, today, write_once  # noqa: E402

URL = "https://alfred.stlouisfed.org/graph/alfredgraph.csv"
UA = "CreditCanary research 7thvex@gmail.com"


def month_ends(start: str, end: dt.date) -> list[dt.date]:
    return [d.date() for d in pd.date_range(start, end, freq="ME")]


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--date", default=today())
    a = ap.parse_args()
    d = raw_dir("alfred", a.date)
    s = requests.Session()
    s.headers["User-Agent"] = UA
    for asof in month_ends("2011-12-31", dt.date.today()):
        out = d / f"UNRATE_{asof.isoformat()}.csv"
        if out.exists():
            continue
        for attempt in range(4):
            try:
                r = s.get(URL, params={"id": "UNRATE", "vintage_date": asof.isoformat()}, timeout=60)
                r.raise_for_status()
                break
            except requests.RequestException:
                time.sleep(2 ** attempt * 2)
        else:
            raise SystemExit(f"ALFRED failed for {asof}")
        write_once(out, r.content)
        time.sleep(1.0)
    print(f"alfred ok: {d}")


if __name__ == "__main__":
    main()
