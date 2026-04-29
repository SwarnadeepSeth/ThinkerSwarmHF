"""
snapshot.py — Python wrapper for QuantJuice chart snapshots.
Fetches OHLCV from SQLite and calls snapshot.js via Node.
"""

import base64
import json
import os
import sqlite3
import subprocess
import tempfile
from datetime import datetime, timezone

_SCRIPT = os.path.join(os.path.dirname(__file__), "snapshot.js")
_NODE   = "node"
_PROJECT_ROOT = os.path.dirname(os.path.dirname(__file__))


def _fetch_ohlcv(ticker: str, db_path: str, limit: int = 300) -> list[dict]:
    conn = sqlite3.connect(db_path)
    cur  = conn.cursor()
    cur.execute(
        "SELECT date, open, high, low, close, volume FROM ohlcv "
        "WHERE symbol = ? ORDER BY date DESC LIMIT ?",
        (ticker, limit),
    )
    rows = cur.fetchall()
    conn.close()
    rows.reverse()  # oldest first
    result = []
    for date_str, o, h, l, c, v in rows:
        dt = datetime.strptime(date_str, "%Y-%m-%d").replace(tzinfo=timezone.utc)
        result.append({
            "time": int(dt.timestamp()),
            "open": float(o), "high": float(h),
            "low":  float(l), "close": float(c),
            "volume": float(v),
        })
    return result


def take_snapshot(
    ticker: str,
    db_path: str,
    output_path: str | None = None,
    width: int = 1600,
    height: int = 900,
    limit: int = 300,
) -> str:
    """Render a chart PNG for *ticker* and save to *output_path*. Returns the path."""
    data = _fetch_ohlcv(ticker, db_path, limit=limit)
    if not data:
        raise ValueError(f"No OHLCV data for {ticker!r} in {db_path!r}")

    if output_path is None:
        fd, output_path = tempfile.mkstemp(suffix=".png")
        os.close(fd)

    with tempfile.NamedTemporaryFile(mode="w", suffix=".json", delete=False) as f:
        json.dump(data, f)
        data_file = f.name

    try:
        result = subprocess.run(
            [
                _NODE, _SCRIPT,
                "--data",   data_file,
                "--output", output_path,
                "--ticker", ticker,
                "--width",  str(width),
                "--height", str(height),
            ],
            capture_output=True,
            text=True,
            timeout=60,
            cwd=_PROJECT_ROOT,
        )
        if result.returncode != 0:
            raise RuntimeError(
                f"snapshot.js exited {result.returncode}:\n{result.stderr.strip()}"
            )
    finally:
        try:
            os.unlink(data_file)
        except OSError:
            pass

    return output_path


def take_snapshot_b64(ticker: str, db_path: str, **kwargs) -> str:
    """Returns a base64-encoded PNG string (no file left on disk)."""
    fd, tmp = tempfile.mkstemp(suffix=".png")
    os.close(fd)
    try:
        take_snapshot(ticker, db_path, output_path=tmp, **kwargs)
        with open(tmp, "rb") as f:
            return base64.b64encode(f.read()).decode("ascii")
    finally:
        try:
            os.unlink(tmp)
        except OSError:
            pass
