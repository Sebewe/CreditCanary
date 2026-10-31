"""Parse card master trust 10-D servicer reports into monthly trust metrics.

Reads every exhibit saved by ingest/sec_10d.py and writes
data/work/trust_10d_parsed.parquet with one row per (trust, filing):
  trust_id, cik, accession, form, filing_date, report_date,
  nco_rate   annualized net charge-off (net loss / net default) rate, percent
  gco_rate   annualized gross charge-off (default) rate, percent, if reported
  dq30_rate  30+ days delinquent receivables as percent of receivables
  nco_method how nco_rate was obtained ('reported' or 'gross_x_net_share')
  exhibit    exhibit file the values came from

Each trust has its own label spec (TRUST_SPECS). Exhibits are flattened to a
list of text lines; a value is the first percentage on the label's line (after
the label) or on the following few lines. sql/staging/stg_trust_monthly.sql
types and de-duplicates the output (original 10-D wins over 10-D/A).
"""
from __future__ import annotations

import csv
import json
import re
import sys
import warnings
from pathlib import Path

import pandas as pd
from bs4 import BeautifulSoup, XMLParsedAsHTMLWarning

sys.path.insert(0, str(Path(__file__).resolve().parent))
from common import DATA, ROOT, latest_raw_dir  # noqa: E402

warnings.filterwarnings("ignore", category=XMLParsedAsHTMLWarning)

PCT = re.compile(r"(\(?-?\d{1,3}(?:\.\d+)?\)?)\s*%")
MONEY = re.compile(r"^\$?\s*(\(?[\d,]*\d\.\d{2}\)?)$")


# ---------------------------------------------------------------- text helpers
def lines_of(path: Path) -> list[str]:
    raw = path.read_bytes()
    if path.suffix.lower() in (".htm", ".html"):
        text = BeautifulSoup(raw, "lxml").get_text("\n")
    else:
        text = raw.decode("latin-1")
    out: list[str] = []
    for ln in text.split("\n"):
        ln = re.sub(r"[ \t\xa0​]+", " ", ln).strip()
        if not ln:
            continue
        # glue a leading "%" (e.g. "%", "% (annualized)") onto the previous token
        if out and ln.startswith("%"):
            out[-1] += "%"
            ln = ln[1:].strip()
            if not ln:
                continue
        # re-join labels wrapped mid-phrase ("Net Charge-Off" / "Rate (...)")
        if out and re.search(r"Charge-Off$", out[-1], re.I) and ln.startswith("Rate"):
            out[-1] += " " + ln
            continue
        out.append(ln)
    return out


def _num(s: str) -> float:
    neg = s.startswith("(") and s.endswith(")")
    v = float(s.strip("()").replace(",", ""))
    return -v if neg else v


def pct_after(L: list[str], label: str, k: int = 8, nth: int = 1,
              stop: str | None = None, anchor: str | None = None) -> float | None:
    """nth percentage after the first line matching `label` (case-insensitive)."""
    lab = re.compile(label, re.I)
    stp = re.compile(stop, re.I) if stop else None
    start = 0
    if anchor:
        a = next((i for i, l in enumerate(L) if re.search(anchor, l, re.I)), None)
        if a is None:
            return None
        start = a
    for i in range(start, len(L)):
        m = lab.search(L[i])
        if not m:
            continue
        found = [x for x in PCT.findall(L[i][m.end():])]
        for j in range(i + 1, min(i + 1 + k, len(L))):
            if stp and stp.search(L[j]):
                break
            found += PCT.findall(L[j])
            if len(found) >= nth:
                break
        if len(found) >= nth:
            return _num(found[nth - 1])
    return None


def money_after(L: list[str], label: str, k: int = 6, anchor: str | None = None) -> float | None:
    """First dollar amount (n,nnn.nn) after the first line matching `label`."""
    lab = re.compile(label, re.I)
    start = 0
    if anchor:
        a = next((i for i, l in enumerate(L) if re.search(anchor, l, re.I)), None)
        if a is None:
            return None
        start = a
    for i in range(start, len(L)):
        m = lab.search(L[i])
        if not m:
            continue
        tail = [L[i][m.end():].strip()] + L[i + 1:i + 1 + k]
        for t in tail:
            for tok in re.split(r"\s+(?=\$|\d)", t):
                mm = MONEY.match(tok.strip())
                if mm:
                    return _num(mm.group(1))
    return None


def last_pct_in_rows(L: list[str], row_labels: list[str], anchor: str, k: int = 6,
                     row_end: str = r"^(total|current)\b", which: int = -1) -> float | None:
    """Sum, over delinquency bucket rows, of the last percentage on each row.
    A row runs from its label to the next bucket label / row_end line (max k
    lines). For each bucket the first occurrence after `anchor` that carries a
    percentage is used (tables often show dollars first, percentages second)."""
    a = next((i for i, l in enumerate(L) if re.search(anchor, l, re.I)), None)
    if a is None:
        return None
    labs = [re.compile(x, re.I) for x in row_labels]
    end_re = re.compile(row_end, re.I)
    total = 0.0
    for lr in labs:
        got = None
        for i in range(a, min(a + 600, len(L))):
            m = lr.search(L[i])
            if not m:
                continue
            vals = PCT.findall(L[i][m.end():])
            for j in range(i + 1, min(i + 1 + k, len(L))):
                if (end_re.search(L[j]) or any(o.search(L[j]) for o in labs)
                        or len(L[j]) > 60):
                    break
                vals += PCT.findall(L[j])
            if vals:
                got = _num(vals[which])
                break
        if got is None:
            return None
        total += got
    return round(total, 6)


# ---------------------------------------------------------------- trust specs
def net_from_gross(L, gross_label, default_label, recov_label, anchor=None):
    g = pct_after(L, gross_label, anchor=anchor)
    d = money_after(L, default_label, anchor=anchor)
    r = money_after(L, recov_label, anchor=anchor)
    if g is None or not d or r is None:
        return None, g
    return g * (d - r) / d, g


def spec_comet(L):
    nco = pct_after(L, r"Annualized Net Default Rate")
    method = "reported"
    gco = pct_after(L, r"Annualized Default Rate as a Percent")
    if nco is None:
        nco, gco = net_from_gross(L, r"Annualized Default Rate as a Percent",
                                  r"Defaulted Accounts during the Month",
                                  r"Recoveries of Charged.?Off Accounts")
        method = "gross_x_net_share"
    dq = pct_after(L, r"Delinquencies 30 ?\+ ?Days as a Percent")
    return dict(nco_rate=nco, gco_rate=gco, dq30_rate=dq, nco_method=method)


def spec_cccit(L):
    nco = pct_after(L, r"Credit Loss Component")
    dq = last_pct_in_rows(
        L, [r"^31-60\b", r"^61-90\b", r"^91-120\b", r"^121-150\b", r"^151-180\b"],
        anchor=r"Delinquen", which=0)
    if dq is None:  # pre-2016 dot-leader format, buckets offset by 5 days
        dq = last_pct_in_rows(
            L, [r"^35-64 days", r"^65-94 days", r"^95-124 days", r"^125-154 days",
                r"^155-184 days"], anchor=r"Delinquen", which=0)
    return dict(nco_rate=nco, gco_rate=None, dq30_rate=dq, nco_method="reported")


def spec_chait(L):
    nco = pct_after(L, r"Net Losses as a percentage of Average")
    method = "reported"
    if nco is None:  # pre-2015-11 format: excess-spread table, Asset Pool One
        nco = pct_after(L, r"Less: Net Credit Losses", k=3)
        method = "reported_excess_spread_table"
    gco = pct_after(L, r"Gross Losses as a Percentage of Average")
    dq = pct_after(L, r"^TOTAL$", k=4, nth=1,
                   anchor=r"Delinquencies as of the last day|Number of Days Delinquent")
    if dq is None:  # pre-2016 format: percentage table in the Ex 99.2 certificate
        dq = pct_after(L, r"^TOTAL$", k=3, anchor=r"percentage of outstanding balances.*delinquent")
    return dict(nco_rate=nco, gco_rate=gco, dq30_rate=dq, nco_method=method)


def spec_syf(L):
    nco = pct_after(L, r"^Net Charge-Off Rate( \(Default|$)")
    gco = pct_after(L, r"^Gross Charge-Off Rate( \(Default|$)")
    dq = last_pct_in_rows(
        L, [r"^30-59 Days Delinquent", r"^60-89 Days Delinquent", r"^90-119 Days Delinquent",
            r"^120-149 Days Delinquent", r"^150-179 Days Delinquent", r"^180 or Greater Days"],
        anchor=r"^Delinquency Data")
    return dict(nco_rate=nco, gco_rate=gco, dq30_rate=dq, nco_method="reported")


def spec_axp(L):
    nco = pct_after(L, r"Annualized Default Rate, Net of Recoveries")
    gco = pct_after(L, r"^Annualized Default Rate$|^Annualized Default Rate\b(?!,)")
    dq = pct_after(L, r"Total 30\+ Days Delinquent", k=6)
    return dict(nco_rate=nco, gco_rate=gco, dq30_rate=dq, nco_method="reported")


def spec_wfn(L):
    nco = pct_after(L, r"Net Principal Charge.?Off Rate|Net Principal Charge.?Offs \(%")
    gco = pct_after(L, r"Gross Principal Charge.?Off Rate|Gross Principal Charge.?Offs \(%")
    dq = last_pct_in_rows(
        L, [r"31-60 days delinquent", r"61-90 days delinquent", r"91-120 days delinquent",
            r"121-150 days delinquent", r"151\+ days delinquent"],
        anchor=r"DELINQUENCIES AND LOSSES", which=0, row_end=r"^\([a-z]\)|days delinquent")
    return dict(nco_rate=nco, gco_rate=gco, dq30_rate=dq, nco_method="reported")


def spec_bacct(L):
    nco = pct_after(L, r"Default Amount net of Recoveries", k=4)
    method = "reported"
    if nco is None:
        nco = pct_after(L, r"Net Charge-Offs as a percentage of Average Principal", k=4)
        method = "reported_pool_table"
    gco = pct_after(L, r"Investor Default Amount for the related Monthly Period as a percentage", k=4)
    dq = pct_after(L, r"^Total$", k=6, anchor=r"Receivables Delinquent")
    return dict(nco_rate=nco, gco_rate=gco, dq30_rate=dq, nco_method=method)


def spec_discover(L):
    """Discover Card Master Trust I certificate statement. From 2017 the HTML is a
    flattened PDF whose labels and values are detached, so parse the joined text:
    the first three percentages after '(a) Gross Charge-offs (rate shown' are
    gross, recoveries and net in every layout; keep them only if
    gross - recoveries == net (within rounding)."""
    t = " ".join(L)
    nco = gco = dq = None
    i = t.find("Gross Charge-offs (rate shown")
    if i >= 0:
        pcts = [_num(x) for x in PCT.findall(t[i:i + 2500])[:3]]
        if len(pcts) == 3 and abs(pcts[0] - pcts[1] - pcts[2]) <= 0.025:
            gco, nco = pcts[0], pcts[2]
    j = t.find("Delinquency Summary")
    if j >= 0:
        m = re.search(r"Total\s*\|?\s*[\d,]+\s*\|?\s*\$\s*\|?\s*[\d,]+\.\d{2}\s*\|?\s*(\d+\.\d+)\s*%",
                      t[j:j + 3000])
        if m:
            dq = float(m.group(1))
    return dict(nco_rate=nco, gco_rate=gco, dq30_rate=dq, nco_method="reported")


def spec_dryrock(L):
    nco = pct_after(L, r"Total Net Losses as a percentage of the Portfolio Principal", k=3)
    method = "reported"
    gco = pct_after(L, r"Total Gross Losses as a percentage|^Gross loss rate", k=3)
    if nco is None:
        nco, gco = net_from_gross(L, r"^Gross loss rate", r"^Default Amount",
                                  r"^Recoveries$|^Total Recoveries")
        method = "gross_x_net_share"
    dq = last_pct_in_rows(
        L, [r"^31-60 days delinquent", r"^61-90 days delinquent", r"^91-120 days delinquent",
            r"^121-150 days delinquent", r"^151-180 days delinquent",
            r"^181 and greater days delinquent"],
        anchor=r"^Delinquency Data", which=0)
    return dict(nco_rate=nco, gco_rate=gco, dq30_rate=dq, nco_method=method)


def spec_generic(L):
    return dict(nco_rate=None, gco_rate=None, dq30_rate=None, nco_method=None)


TRUST_SPECS = {
    "comet": spec_comet, "cccit": spec_cccit, "chait": spec_chait,
    "sccmnt": spec_syf, "scit": spec_syf, "axp": spec_axp, "wfn": spec_wfn, "bacct": spec_bacct,
    "dcmt": spec_discover, "dcent": spec_discover, "dryrock": spec_dryrock,
}


# ---------------------------------------------------------------- driver
def parse_filing(trust_id: str, fdir: Path, exhibits: list[list[str]]) -> dict:
    spec = TRUST_SPECS.get(trust_id, spec_generic)
    best: dict = {}
    for _, name in exhibits:
        p = fdir / name
        if not p.exists():
            continue
        try:
            res = spec(lines_of(p))
        except Exception as e:  # keep going; record nothing for this exhibit
            print(f"  parse error {p}: {e}", file=sys.stderr)
            continue
        # merge: first exhibit that yields a field wins for that field
        # (nco_method travels with nco_rate)
        if best.get("nco_rate") is None and res.get("nco_rate") is not None:
            best["nco_rate"], best["nco_method"] = res["nco_rate"], res.get("nco_method")
        for k in ("gco_rate", "dq30_rate"):
            if best.get(k) is None and res.get(k) is not None:
                best[k] = res[k]
        best.setdefault("exhibit", name)
        if best.get("nco_rate") is not None and best.get("dq30_rate") is not None:
            best["exhibit"] = name
            break
    return best


def main(only: list[str] | None = None) -> pd.DataFrame:
    raw = latest_raw_dir("sec_10d")
    trusts = list(csv.DictReader(open(ROOT / "sql" / "seeds" / "trusts.csv")))
    rows = []
    for t in trusts:
        if t["use"] != "1" or (only and t["trust_id"] not in only):
            continue
        man = raw / t["cik"] / "filings.csv"
        if not man.exists():
            continue
        for f in csv.DictReader(open(man)):
            res = parse_filing(t["trust_id"], raw / t["cik"] / f["accessionNumber"],
                               json.loads(f["exhibits"]))
            rows.append({"trust_id": t["trust_id"], "cik": int(t["cik"]),
                         "accession": f["accessionNumber"], "form": f["form"],
                         "filing_date": f["filingDate"], "report_date": f["reportDate"],
                         **{k: res.get(k) for k in ("nco_rate", "gco_rate", "dq30_rate",
                                                     "nco_method", "exhibit")}})
    df = pd.DataFrame(rows)
    if not only:
        out = DATA / "work" / "trust_10d_parsed.parquet"
        out.parent.mkdir(parents=True, exist_ok=True)
        df.to_parquet(out, index=False)
        print(f"wrote {len(df)} rows to {out}")
    return df


if __name__ == "__main__":
    main(sys.argv[1:] or None)
