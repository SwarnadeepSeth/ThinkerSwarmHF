"""
Helpers for reading local fundamental data from financials.db.

The database currently ships with two tables:
- financials_us
- financials_india

The helpers below prefer a configured path, then fall back to the repo's
default locations.
"""

from __future__ import annotations

import os
import sqlite3
from typing import Any

_FINANCIAL_DB_PATH = "data/financials.db"


def set_financial_db_path(path: str | None):
    global _FINANCIAL_DB_PATH
    if path:
        _FINANCIAL_DB_PATH = path


def resolve_financial_db_path(path: str | None = None) -> str | None:
    candidates = [
        path,
        _FINANCIAL_DB_PATH,
        "data/financials.db",
        "data/financial.db",
    ]
    for candidate in candidates:
        if candidate and os.path.exists(candidate):
            return candidate
    return None


def _row_to_dict(cursor, row) -> dict[str, Any]:
    return {desc[0]: row[idx] for idx, desc in enumerate(cursor.description)}


def get_financial_record(ticker: str, path: str | None = None) -> dict[str, Any]:
    db_path = resolve_financial_db_path(path)
    if not db_path:
        return {}

    sym = ticker.upper().strip()
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    cur = conn.cursor()
    try:
        for table in ("financials_us", "financials_india"):
            try:
                row = cur.execute(
                    f"SELECT * FROM {table} WHERE symbol = ?",
                    (sym,),
                ).fetchone()
            except Exception:
                continue
            if row:
                result = dict(row)
                result["_table"] = table
                result["_db_path"] = db_path
                return result
    finally:
        conn.close()
    return {}


def get_peer_records(
    ticker: str,
    path: str | None = None,
    limit: int = 6,
) -> list[dict[str, Any]]:
    db_path = resolve_financial_db_path(path)
    if not db_path:
        return []

    base = get_financial_record(ticker, path=db_path)
    table = base.get("_table")
    if not table:
        return []

    exchange = base.get("exchange")
    sym = ticker.upper().strip()
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    cur = conn.cursor()
    try:
        if exchange:
            rows = cur.execute(
                f"""
                SELECT * FROM {table}
                WHERE symbol != ? AND exchange = ?
                ORDER BY market_cap DESC
                LIMIT ?
                """,
                (sym, exchange, int(limit)),
            ).fetchall()
        else:
            rows = cur.execute(
                f"""
                SELECT * FROM {table}
                WHERE symbol != ?
                ORDER BY market_cap DESC
                LIMIT ?
                """,
                (sym, int(limit)),
            ).fetchall()
        return [dict(row) | {"_table": table, "_db_path": db_path} for row in rows]
    finally:
        conn.close()


def format_financial_snapshot(ticker: str, path: str | None = None, limit_peers: int = 5) -> str:
    record = get_financial_record(ticker, path=path)
    if not record:
        return f"[{ticker}] financials.db record unavailable."

    peers = get_peer_records(ticker, path=path, limit=limit_peers)

    def fmt(v, decimals=2):
        try:
            return f"{round(float(v), decimals):,}"
        except Exception:
            return "N/A"

    def pct(v):
        try:
            return f"{round(float(v) * 100, 2)}%"
        except Exception:
            return "N/A"

    lines = [
        f"Financial DB Snapshot ({ticker})",
        f"source={os.path.basename(record.get('_db_path') or '')}, table={record.get('_table', 'N/A')}, exchange={record.get('exchange', 'N/A')}",
        (
            f"market_cap=${fmt((record.get('market_cap') or 0) / 1e9)}B, "
            f"pe_ratio={fmt(record.get('pe_ratio'))}, eps={fmt(record.get('eps'))}, "
            f"ebitda=${fmt((record.get('ebitda') or 0) / 1e9)}B"
        ),
        (
            f"cash=${fmt((record.get('cash') or 0) / 1e9)}B, "
            f"debt=${fmt((record.get('debt') or 0) / 1e9)}B, "
            f"shares_outstanding={fmt(record.get('shares_outstanding'))}"
        ),
        (
            f"fcf_current=${fmt((record.get('fcf_current') or 0) / 1e9)}B, "
            f"fcf_5y_growth={pct(record.get('fcf_5y_growth'))}, "
            f"revenue_current=${fmt((record.get('revenue_current') or 0) / 1e9)}B"
        ),
        (
            f"dcf_moderate=${fmt(record.get('dcf_moderate'))}, "
            f"dcf_conservative=${fmt(record.get('dcf_conservative'))}, "
            f"dcf_optimistic=${fmt(record.get('dcf_optimistic'))}"
        ),
    ]

    if peers:
        lines.append("Peers:")
        for peer in peers:
            lines.append(
                f"  {peer.get('symbol', 'N/A')}: "
                f"mkt_cap=${fmt((peer.get('market_cap') or 0) / 1e9)}B, "
                f"pe_ratio={fmt(peer.get('pe_ratio'))}, "
                f"fcf_current=${fmt((peer.get('fcf_current') or 0) / 1e9)}B"
            )
    return "\n".join(lines)
