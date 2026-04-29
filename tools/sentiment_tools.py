"""
Sentiment utilities for the sentiment analysis wing.

Reads local sentiment history from data/sentiments.db and supplements it with
live news headlines from Google News RSS when available.
"""

from __future__ import annotations

import os
import re
import sqlite3
import urllib.parse
import urllib.request
import xml.etree.ElementTree as ET
from statistics import mean

from langchain_core.tools import tool

_SENTIMENT_DB_PATH = "data/sentiments.db"

_POSITIVE = {
    "beat", "beats", "beat", "strong", "growth", "surge", "surges", "upgrade",
    "upgraded", "bullish", "approval", "approved", "record", "buy", "outperform",
    "rally", "gain", "gains", "expansion", "expands", "resilient", "improve",
    "improves", "improved", "beat", "tops", "outlook",
}
_NEGATIVE = {
    "miss", "misses", "weak", "decline", "declines", "drop", "drops", "downgrade",
    "downgraded", "bearish", "delay", "delays", "lawsuit", "cuts", "cut", "warning",
    "warns", "slowing", "slowdown", "slump", "risk", "risks", "concern", "concerns",
    "investigation", "probe", "pressure",
}


def set_sentiment_db_path(path: str | None):
    global _SENTIMENT_DB_PATH
    if path:
        _SENTIMENT_DB_PATH = path


def resolve_sentiment_db_path(path: str | None = None) -> str | None:
    candidates = [
        path,
        _SENTIMENT_DB_PATH,
        "data/sentiments.db",
    ]
    for candidate in candidates:
        if candidate and os.path.exists(candidate):
            return candidate
    return None


def _table_for_ticker(ticker: str) -> str:
    sym = ticker.upper().strip().replace("-", "_").replace(".", "_")
    return f"US_{sym}"


def _http_get_text(url: str, timeout: int = 12):
    req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        return resp.read()


def _google_news_rss_headlines(query: str, max_results: int = 5) -> list[dict]:
    rss_url = "https://news.google.com/rss/search?" + urllib.parse.urlencode(
        {"q": query, "hl": "en-US", "gl": "US", "ceid": "US:en"}
    )
    data = _http_get_text(rss_url, timeout=12)
    root = ET.fromstring(data)
    items = root.findall(".//item")[:max_results]
    results = []
    for item in items:
        title = (item.findtext("title") or "").strip()
        link = (item.findtext("link") or "").strip()
        source = (item.findtext("{http://news.google.com/news}source") or "").strip()
        pub = (item.findtext("pubDate") or "").strip()
        if title:
            results.append({"title": title, "link": link, "source": source, "date": pub})
    return results


def _lexicon_score(text: str) -> float:
    tokens = re.findall(r"[A-Za-z']+", text.lower())
    if not tokens:
        return 0.0
    score = 0.0
    for token in tokens:
        if token in _POSITIVE:
            score += 1.0
        elif token in _NEGATIVE:
            score -= 1.0
    return score / max(len(tokens), 1)


def _load_sentiment_rows(ticker: str, limit: int = 20) -> list[dict]:
    db_path = resolve_sentiment_db_path()
    if not db_path:
        return []

    table = _table_for_ticker(ticker)
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    cur = conn.cursor()
    try:
        rows = cur.execute(
            f"SELECT date, title, link, sentiment FROM {table} ORDER BY date DESC LIMIT ?",
            (int(limit),),
        ).fetchall()
        return [dict(r) for r in rows]
    except Exception:
        return []
    finally:
        conn.close()


@tool
def get_sentiment_snapshot(ticker: str, limit: int = 12) -> str:
    """
    Build a compact sentiment snapshot from the local sentiment database.
    """
    rows = _load_sentiment_rows(ticker, limit=limit)
    if not rows:
        return f"Sentiment Snapshot ({ticker}): unavailable."

    scores = [float(r.get("sentiment") or 0.0) for r in rows]
    avg_score = mean(scores) if scores else 0.0
    positive = sum(1 for s in scores if s > 0.05)
    negative = sum(1 for s in scores if s < -0.05)
    neutral = len(scores) - positive - negative

    lines = [
        f"Sentiment Snapshot ({ticker}) [sentiments.db]: avg_score={avg_score:.3f}, "
        f"positive={positive}, neutral={neutral}, negative={negative}",
        f"{'Date':20} {'Score':>7} {'Title':70} {'Source'}",
        "-" * 120,
    ]
    for row in rows[:limit]:
        title = re.sub(r"\s+", " ", str(row.get("title") or "")).strip()[:70]
        source = "Yahoo/News" if "finance.yahoo.com" in str(row.get("link") or "") else "News"
        lines.append(
            f"{str(row.get('date') or '')[:20]:20} {float(row.get('sentiment') or 0.0):7.2f} "
            f"{title:70} {source}"
        )
    return "\n".join(lines)


@tool
def get_live_news_sentiment(query: str, max_results: int = 5) -> str:
    """
    Pull live headlines from Google News RSS and apply a simple sentiment score.
    """
    q = query.strip()
    if not q:
        return "Live News Sentiment: empty query."

    try:
        items = _google_news_rss_headlines(q, max_results=max_results)
    except Exception as e:
        return f"Live News Sentiment ({q}) unavailable: {e}"

    if not items:
        return f"Live News Sentiment ({q}): no headlines found."

    scores = []
    lines = [f"Live News Sentiment ({q}):"]
    for item in items:
        title = item["title"]
        score = _lexicon_score(title)
        scores.append(score)
        source = item.get("source") or "News"
        link = item.get("link") or ""
        lines.append(f"- [{score:+.3f}] {title} ({source}) {link}")

    avg_score = mean(scores) if scores else 0.0
    tone = "POSITIVE" if avg_score > 0.01 else "NEGATIVE" if avg_score < -0.01 else "MIXED"
    lines.insert(1, f"Overall tone={tone}, avg_score={avg_score:.3f}")
    return "\n".join(lines)


def build_sentiment_context(ticker: str, limit: int = 12) -> str:
    local = get_sentiment_snapshot.invoke({"ticker": ticker, "limit": limit})
    live = get_live_news_sentiment.invoke({"query": f"{ticker} stock news", "max_results": 5})
    return f"{local}\n\n{live}"
