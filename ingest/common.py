"""Shared helpers for ingest scripts: paths, polite HTTP, raw-file writing."""
from __future__ import annotations

import datetime as dt
import os
import threading
import time
from pathlib import Path

import requests

ROOT = Path(__file__).resolve().parents[1]
DATA = ROOT / "data"
RAW = DATA / "raw"

SEC_USER_AGENT = "CreditCanary research 7thvex@gmail.com"


def today() -> str:
    return dt.date.today().isoformat()


def raw_dir(source: str, date: str | None = None) -> Path:
    d = RAW / source / (date or today())
    d.mkdir(parents=True, exist_ok=True)
    return d


def latest_raw_dir(source: str) -> Path:
    dirs = sorted(p for p in (RAW / source).glob("????-??-??") if p.is_dir())
    if not dirs:
        raise FileNotFoundError(f"no raw pulls for {source}; run ingest first")
    return dirs[-1]


def write_once(path: Path, content: bytes) -> Path:
    """Raw files are immutable: never overwrite an existing file."""
    if path.exists():
        return path
    tmp = path.with_suffix(path.suffix + ".part")
    tmp.write_bytes(content)
    os.replace(tmp, path)
    return path


def download(url: str, dest: Path, session: requests.Session | None = None,
             chunk: int = 1 << 20) -> Path:
    """Stream a large file to dest (skips if dest already exists)."""
    if dest.exists():
        return dest
    s = session or requests.Session()
    tmp = dest.with_suffix(dest.suffix + ".part")
    with s.get(url, stream=True, timeout=120) as r:
        r.raise_for_status()
        with open(tmp, "wb") as f:
            for block in r.iter_content(chunk):
                f.write(block)
    os.replace(tmp, dest)
    return dest


class RateLimitedSession(requests.Session):
    """requests.Session that never exceeds `max_per_sec` requests per second."""

    def __init__(self, max_per_sec: float, user_agent: str):
        super().__init__()
        self.headers.update({"User-Agent": user_agent,
                             "Accept-Encoding": "gzip, deflate"})
        self._min_gap = 1.0 / max_per_sec
        self._last = 0.0
        self._lock = threading.Lock()

    def request(self, *args, **kwargs):
        kwargs.setdefault("timeout", 60)
        with self._lock:
            wait = self._last + self._min_gap - time.monotonic()
            if wait > 0:
                time.sleep(wait)
            self._last = time.monotonic()
        for attempt in range(5):
            r = super().request(*args, **kwargs)
            if r.status_code not in (429, 503):
                return r
            time.sleep(2 ** attempt * 2)
        return r


def sec_session() -> RateLimitedSession:
    # 8/s leaves headroom under SEC's 10 requests/second limit.
    return RateLimitedSession(8, SEC_USER_AGENT)
