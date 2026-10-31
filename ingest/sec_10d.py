"""Download SEC Form 10-D filings (servicer report exhibits) for card master trusts.

For each trust CIK in sql/seeds/trusts.csv:
  - fetch the EDGAR submissions index (including older paged files),
  - for every 10-D / 10-D/A filed from 2011-01-01 on, fetch the filing index
    and save every EX-99* exhibit (htm/txt) under
    data/raw/sec_10d/{pull date}/{cik}/{accession}/.
A manifest (filings.csv) per CIK records form, filing date, period of report
and the exhibit files. Already-downloaded files are skipped, so reruns resume.

EDGAR rules: User-Agent "CreditCanary research 7thvex@gmail.com", <=10 req/s
(we use 8/s).
"""
from __future__ import annotations

import argparse
import csv
import json
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from common import ROOT, raw_dir, sec_session, write_once  # noqa: E402

SEEDS = ROOT / "sql" / "seeds"
MIN_DATE = "2011-01-01"


def submissions(s, cik: int) -> list[dict]:
    base = "https://data.sec.gov/submissions/"
    j = s.get(f"{base}CIK{cik:010d}.json").json()
    pages = [j["filings"]["recent"]] + [
        s.get(base + f["name"]).json() for f in j["filings"].get("files", [])
    ]
    out = []
    for p in pages:
        for i, form in enumerate(p["form"]):
            out.append({k: p[k][i] for k in ("accessionNumber", "form", "filingDate",
                                              "reportDate", "primaryDocument")})
    return out


def exhibits(s, cik: int, acc: str) -> list[tuple[str, str]]:
    """(type, filename) of EX-99 documents in a filing, from its index.json."""
    acc_nd = acc.replace("-", "")
    url = f"https://www.sec.gov/Archives/edgar/data/{cik}/{acc_nd}/index.json"
    r = s.get(url)
    r.raise_for_status()
    items = r.json()["directory"]["item"]
    names = [it["name"] for it in items]
    # index.json lacks doc types; fetch the -index.htm table for EX-99 types.
    r2 = s.get(f"https://www.sec.gov/Archives/edgar/data/{cik}/{acc_nd}/{acc}-index.htm")
    types = {}
    if r2.ok:
        for m in re.finditer(r'<a href="[^"]*/([^"/]+)">[^<]*</a></td>\s*<td[^>]*>(EX-99[^<]*)</td>',
                             r2.text, re.I):
            types[m.group(1)] = m.group(2).strip()
    out = [(t, n) for n, t in types.items()]
    if not out:  # fall back: any htm/txt named like an exhibit 99
        out = [("EX-99?", n) for n in names
               if re.search(r"(ex|exh|exhibit)[-_]?99", n, re.I) and n.lower().endswith((".htm", ".html", ".txt"))]
    return out


def pull(cik: int, date: str, s=None, limit: int | None = None) -> Path:
    s = s or sec_session()
    d = raw_dir("sec_10d", date) / str(cik)
    d.mkdir(parents=True, exist_ok=True)
    subs = [f for f in submissions(s, cik)
            if f["form"] in ("10-D", "10-D/A") and f["filingDate"] >= MIN_DATE]
    subs.sort(key=lambda f: f["filingDate"])
    if limit:
        subs = subs[-limit:]
    manifest = d / "filings.csv"
    done = set()
    if manifest.exists():
        with open(manifest) as f:
            done = {r["accessionNumber"] for r in csv.DictReader(f)}
    new = not manifest.exists()
    with open(manifest, "a", newline="") as f:
        w = csv.DictWriter(f, ["accessionNumber", "form", "filingDate", "reportDate",
                               "primaryDocument", "exhibits"])
        if new:
            w.writeheader()
        for fl in subs:
            acc = fl["accessionNumber"]
            if acc in done:
                continue
            fd = d / acc
            fd.mkdir(exist_ok=True)
            exs = exhibits(s, cik, acc)
            for _, name in exs:
                url = f"https://www.sec.gov/Archives/edgar/data/{cik}/{acc.replace('-', '')}/{name}"
                r = s.get(url)
                if r.ok:
                    write_once(fd / name, r.content)
            w.writerow({**fl, "exhibits": json.dumps(exs)})
            f.flush()
    return d


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--date", required=False)
    ap.add_argument("--cik", type=int, action="append")
    ap.add_argument("--limit", type=int)
    a = ap.parse_args()
    from common import today
    date = a.date or today()
    if a.cik:
        ciks = a.cik
    else:
        with open(SEEDS / "trusts.csv") as f:
            ciks = [int(r["cik"]) for r in csv.DictReader(f) if r["use"] == "1"]
    s = sec_session()  # one shared rate limiter across threads (<= 8 req/s total)

    def one(c):
        print(f"[10-D] cik {c} start", flush=True)
        pull(c, date, s, a.limit)
        print(f"[10-D] cik {c} done", flush=True)

    from concurrent.futures import ThreadPoolExecutor
    with ThreadPoolExecutor(max_workers=6) as ex:
        list(ex.map(one, ciks))


if __name__ == "__main__":
    main()
