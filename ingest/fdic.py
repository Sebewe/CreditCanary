"""FDIC BankFind quarterly financials (Call Report data) for the lender certs
in sql/seeds/lender_certs.csv, 2010Q1 onward.

Writes raw JSON per cert to data/raw/fdic/{pull date}/financials_{cert}.json.
Key fields (FDIC definitions, $ thousands):
  NTLNLS  net charge-offs, total loans and leases, year-to-date
  LNLSGR  total loans and leases, gross
  NCLNLS  noncurrent loans and leases
  NTLNLSR / NCLNLSR  FDIC's own ratios (annualized YTD), kept for checking
"""
from __future__ import annotations

import argparse
import csv
import json
import sys
from pathlib import Path

import requests

sys.path.insert(0, str(Path(__file__).resolve().parent))
from common import ROOT, raw_dir, today, write_once  # noqa: E402

URL = "https://api.fdic.gov/banks/financials"
FIELDS = "CERT,REPDTE,NAME,ASSET,NTLNLS,LNLSGR,NCLNLS,NTLNLSR,NCLNLSR,NTCRCD,LNCRCD"


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--date", default=today())
    a = ap.parse_args()
    d = raw_dir("fdic", a.date)
    s = requests.Session()
    s.headers["User-Agent"] = "CreditCanary research 7thvex@gmail.com"
    with open(ROOT / "sql" / "seeds" / "lender_certs.csv") as f:
        certs = sorted({int(r["cert"]) for r in csv.DictReader(f)})
    for c in certs:
        out = d / f"financials_{c}.json"
        if out.exists():
            continue
        r = s.get(URL, params={"filters": f"CERT:{c} AND REPDTE:[20100101 TO 20991231]",
                               "fields": FIELDS, "limit": 10000, "sort_by": "REPDTE",
                               "sort_order": "ASC", "format": "json"}, timeout=120)
        r.raise_for_status()
        rows = [x["data"] for x in r.json()["data"]]
        write_once(out, json.dumps(rows).encode())
        print(f"cert {c}: {len(rows)} quarters")
    print(f"fdic ok: {d}")


if __name__ == "__main__":
    main()
