"""Run SQL files against the project DuckDB and export the tables they create
to Parquet.

Each .sql file creates tables named like the file (stg_x.sql -> stg_x). After a
file runs, every table it lists in a `-- exports:` header (default: the file's
own name) is written to data/{staging|marts}/{table}.parquet.

Placeholders like {{cfpb_csv}} are filled from the PARAMS dict below.

Usage: python sql/run_sql.py sql/staging/stg_complaints.sql [more.sql ...]
"""
from __future__ import annotations

import re
import sys
from pathlib import Path

import duckdb

ROOT = Path(__file__).resolve().parents[1]
DATA = ROOT / "data"
DB = DATA / "warehouse.duckdb"
WORK = DATA / "work"

PARAMS = {
    "cfpb_csv": str(WORK / "cfpb" / "complaints.csv"),
    "seeds": str(ROOT / "sql" / "seeds"),
    "staging": str(DATA / "staging"),
    "marts": str(DATA / "marts"),
    "raw": str(DATA / "raw"),
    "work": str(WORK),
}


def render(sql: str) -> str:
    def sub(m):
        key = m.group(1)
        if key not in PARAMS:
            raise KeyError(f"unknown placeholder {{{{{key}}}}}")
        return PARAMS[key]
    return re.sub(r"\{\{(\w+)\}\}", sub, sql)


def exports_for(path: Path, sql: str) -> list[str]:
    m = re.search(r"^--\s*exports:\s*(.+)$", sql, re.M)
    if m:
        return [t.strip() for t in m.group(1).split(",") if t.strip()]
    return [path.stem]


def run(paths: list[str], con: duckdb.DuckDBPyConnection | None = None) -> None:
    own = con is None
    con = con or duckdb.connect(str(DB))
    for p in map(Path, paths):
        sql = p.read_text()
        print(f"[sql] {p.relative_to(ROOT) if p.is_absolute() else p}", flush=True)
        con.execute(render(sql))
        layer = "staging" if "staging" in p.parts else "marts"
        out = DATA / layer
        out.mkdir(parents=True, exist_ok=True)
        for t in exports_for(p, sql):
            con.execute(f"COPY {t} TO '{out / (t + '.parquet')}' (FORMAT parquet)")
    if own:
        con.close()


if __name__ == "__main__":
    run(sys.argv[1:])
