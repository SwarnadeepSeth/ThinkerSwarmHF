"""
Research tools for the Researcher node.
Provides sector/peer comparative context and optional free web search context.
"""

import json
import urllib.parse
import urllib.request
import xml.etree.ElementTree as ET
from langchain_core.tools import tool
from tools.financial_db import get_financial_record, get_peer_records, format_financial_snapshot


def _fmt(v, decimals=2):
    try:
        return f"{round(float(v), decimals):,}"
    except Exception:
        return "N/A"


def _pct(v):
    try:
        return f"{round(float(v) * 100, 2)}%"
    except Exception:
        return "N/A"


def _http_get_json(url: str, timeout: int = 10):
    req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        return json.loads(resp.read().decode("utf-8", errors="ignore"))


def _http_get_text(url: str, timeout: int = 10):
    req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        return resp.read()


def _google_news_rss_search(query: str, max_results: int = 5) -> list[str]:
    rss_url = "https://news.google.com/rss/search?" + urllib.parse.urlencode(
        {"q": query, "hl": "en-US", "gl": "US", "ceid": "US:en"}
    )
    data = _http_get_text(rss_url, timeout=12)
    root = ET.fromstring(data)
    items = root.findall(".//item")[:max_results]
    results = []
    for item in items:
        title = (item.findtext("title") or "").strip()
        source = (item.findtext("{http://news.google.com/news}source") or "").strip()
        link = (item.findtext("link") or "").strip()
        pub = (item.findtext("pubDate") or "").strip()
        if not title:
            continue
        bits = [title]
        if source:
            bits.append(f"({source})")
        if pub:
            bits.append(f"[{pub}]")
        if link:
            bits.append(f"[{link}]")
        results.append(" ".join(bits))
    return results


@tool
def get_sector_peer_snapshot(ticker: str, max_peers: int = 6) -> str:
    """
    Build a sector/industry peer snapshot for comparative analysis.
    Pulls sector + industry for the ticker, then discovers same-sector equities
    and returns a concise comparable table.
    """
    try:
        import yfinance as yf

        base_ticker = ticker.upper().strip()
        max_peers = max(3, min(int(max_peers), 12))

        base_info = yf.Ticker(base_ticker).info or {}
        sector = base_info.get("sector") or "N/A"
        industry = base_info.get("industry") or "N/A"

        discovery_queries = []
        if sector != "N/A" and industry != "N/A":
            discovery_queries.append(f"{sector} {industry} stocks")
        if sector != "N/A":
            discovery_queries.append(f"{sector} stocks")
        discovery_queries.append(base_ticker)

        candidate_symbols = {base_ticker}
        for query in discovery_queries:
            try:
                search = yf.Search(
                    query=query,
                    max_results=40,
                    news_count=0,
                    lists_count=0,
                    include_nav_links=False,
                    include_research=False,
                    raise_errors=False,
                )
                for q in (search.quotes or []):
                    sym = str(q.get("symbol") or "").upper().strip()
                    quote_type = str(q.get("quoteType") or "").upper().strip()
                    if not sym:
                        continue
                    if quote_type and quote_type != "EQUITY":
                        continue
                    candidate_symbols.add(sym)
            except Exception:
                continue

        rows = []
        for sym in list(candidate_symbols)[:30]:
            try:
                info = yf.Ticker(sym).info or {}
                sec = info.get("sector")
                if sec and sector != "N/A" and sec != sector and sym != base_ticker:
                    continue

                db_row = get_financial_record(sym)
                db_price = None
                if db_row:
                    try:
                        shares = float(db_row.get("shares_outstanding") or 0.0)
                        mkt = float(db_row.get("market_cap") or 0.0)
                        db_price = mkt / shares if shares else None
                    except Exception:
                        db_price = None

                rows.append(
                    {
                        "symbol": sym,
                        "name": str(info.get("shortName") or info.get("longName") or sym)[:28],
                        "sector": sec or "N/A",
                        "industry": info.get("industry") or "N/A",
                        "market_cap_raw": float((db_row.get("market_cap") if db_row else info.get("marketCap")) or 0.0),
                        "market_cap": f"${_fmt(((db_row.get('market_cap') if db_row else info.get('marketCap')) or 0) / 1e9)}B",
                        "trailing_pe": _fmt(db_row.get("pe_ratio") if db_row else info.get("trailingPE")),
                        "forward_pe": _fmt(info.get("forwardPE")) if not db_row else _fmt(db_row.get("pe_ratio")),
                        "rev_growth": _pct((db_row.get("fcf_5y_growth") if db_row else info.get("revenueGrowth"))),
                        "gross_margin": _pct((db_row.get("operating_margin") if db_row else info.get("grossMargins"))),
                        "db_price": _fmt(db_price),
                    }
                )
            except Exception:
                continue

        if not rows:
            return f"Sector/Peer Snapshot ({base_ticker}): unavailable."

        base_row = next((r for r in rows if r["symbol"] == base_ticker), None)
        if not base_row:
            base_row = {
                "symbol": base_ticker,
                "name": base_ticker,
                "sector": sector,
                "industry": industry,
                "market_cap_raw": 0.0,
                "market_cap": "N/A",
                "trailing_pe": "N/A",
                "forward_pe": "N/A",
                "rev_growth": "N/A",
                "gross_margin": "N/A",
            }

        peer_rows = [r for r in rows if r["symbol"] != base_ticker]
        peer_rows.sort(key=lambda x: x["market_cap_raw"], reverse=True)
        selected = peer_rows[:max_peers]
        peer_syms = [r["symbol"] for r in selected]

        lines = [
            (
                f"Sector/Peer Snapshot ({base_ticker}): sector={base_row['sector']}, "
                f"industry={base_row['industry']}"
            ),
            (
                f"{'Ticker':8} {'Name':28} {'MktCap':>12} {'PE':>8} "
                f"{'FwdPE':>8} {'RevG':>8} {'GrossM':>8} {'DBPx':>8}"
            ),
            "-" * 92,
        ]

        ordered = [base_row] + selected
        for r in ordered:
            lines.append(
                f"{r['symbol'][:8]:8} {r['name'][:28]:28} {r['market_cap'][:12]:>12} "
                f"{r['trailing_pe'][:8]:>8} {r['forward_pe'][:8]:>8} "
                f"{r['rev_growth'][:8]:>8} {r['gross_margin'][:8]:>8} {r.get('db_price','N/A')[:8]:>8}"
            )
        lines.append(f"Peer tickers for comps: {', '.join(peer_syms) if peer_syms else 'N/A'}")
        lines.append("")
        lines.append("Local financials snapshot:")
        lines.append(format_financial_snapshot(base_ticker))
        return "\n".join(lines)
    except ImportError:
        return f"[{ticker}] yfinance not installed — sector/peer snapshot unavailable."
    except Exception as e:
        return f"[{ticker}] sector/peer snapshot error: {e}"


@tool
def free_web_search_context(query: str, max_results: int = 5) -> str:
    """
    Free internet search context using public endpoints.
    Uses DuckDuckGo Instant Answer API + Yahoo Finance search news fallback.
    """
    max_results = max(1, min(int(max_results), 10))
    q = query.strip()
    if not q:
        return "Web Search Context: empty query."

    lines = [f"Web Search Context: {q}"]
    seen = set()

    # Google News RSS first, because it is the most reliable public source here.
    try:
        for entry in _google_news_rss_search(q, max_results=max_results):
            key = entry.lower()
            if key not in seen:
                lines.append(f"- {entry}")
                seen.add(key)
                if len(seen) >= max_results:
                    break
    except Exception as rss_err:
        lines.append(f"- Google News RSS lookup unavailable: {rss_err}")

    # DuckDuckGo Instant Answer API
    try:
        ddg_url = (
            "https://api.duckduckgo.com/?"
            + urllib.parse.urlencode(
                {
                    "q": q,
                    "format": "json",
                    "no_html": "1",
                    "skip_disambig": "1",
                    "no_redirect": "1",
                }
            )
        )
        data = _http_get_json(ddg_url, timeout=10)

        abstract = (data.get("AbstractText") or "").strip()
        if abstract:
            key = abstract.lower()
            if key not in seen:
                lines.append(f"- {abstract}")
                seen.add(key)

        def _consume_related(items):
            for item in items:
                if "Text" in item:
                    text = (item.get("Text") or "").strip()
                    if text and text.lower() not in seen:
                        lines.append(f"- {text}")
                        seen.add(text.lower())
                        if len(seen) >= max_results:
                            return True
                if "Topics" in item:
                    if _consume_related(item.get("Topics") or []):
                        return True
            return False

        _consume_related(data.get("RelatedTopics") or [])
    except Exception as ddg_err:
        lines.append(f"- DuckDuckGo lookup unavailable: {ddg_err}")

    # Yahoo Finance news fallback/context
    try:
        import yfinance as yf

        search = yf.Search(
            query=q,
            max_results=8,
            news_count=max_results,
            lists_count=0,
            include_nav_links=False,
            include_research=False,
            raise_errors=False,
        )
        for item in (search.news or [])[:max_results]:
            title = (item.get("title") or "").strip()
            publisher = (item.get("publisher") or "").strip()
            link = (item.get("link") or item.get("url") or "").strip()
            text = f"{title} ({publisher})" if publisher else title
            if text and text.lower() not in seen:
                suffix = f" [{link}]" if link else ""
                lines.append(f"- {text}{suffix}")
                seen.add(text.lower())
                if len(seen) >= max_results:
                    break
    except Exception as yf_err:
        lines.append(f"- Yahoo finance news lookup unavailable: {yf_err}")

    if len(lines) == 1:
        lines.append("- No web results found.")
    return "\n".join(lines[: max_results + 6])
