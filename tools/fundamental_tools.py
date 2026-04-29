"""
Fundamental / valuation tools for the Fundamental Wing workers.
Uses yfinance where available; returns structured fallback messages otherwise.
All tools return plain strings so they fit cleanly into LangChain tool-calling.
"""

import json
import os
import warnings
from langchain_core.tools import tool
from tools.financial_db import (
    get_financial_record,
    get_peer_records,
    format_financial_snapshot,
    set_financial_db_path,
    resolve_financial_db_path,
)

# yfinance uses pd.Timestamp.utcnow() internally which is deprecated in pandas 4.
# Suppress it here since it's not our code and we cannot fix it upstream.
warnings.filterwarnings(
    "ignore",
    message=".*utcnow.*",
    category=FutureWarning,
)

# Prefer the repo's local financial database by default.
set_financial_db_path(resolve_financial_db_path())


def _yf(ticker: str):
    import yfinance as yf
    return yf.Ticker(ticker)


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


def _db_record(ticker: str):
    return get_financial_record(ticker)


def _db_price(record: dict) -> float | None:
    try:
        market_cap = float(record.get("market_cap") or 0.0)
        shares = float(record.get("shares_outstanding") or 0.0)
        if market_cap > 0 and shares > 0:
            return market_cap / shares
    except Exception:
        pass
    return None


def _db_growth_pct(value):
    try:
        v = float(value)
        if abs(v) <= 1.5:
            return v * 100
        return v
    except Exception:
        return None


def _db_row_available(record: dict) -> bool:
    return bool(record and record.get("symbol"))


# ── Tools ─────────────────────────────────────────────────────────────────────

@tool
def get_price_ratios(ticker: str) -> str:
    """
    Retrieve key price-based valuation ratios: trailing PE, forward PE, PEG,
    Price/Book, Price/Sales, and dividend yield.
    Signals whether the stock is cheap or expensive vs. historical norms.
    """
    record = _db_record(ticker)
    if _db_row_available(record):
        price = _db_price(record)
        pe = record.get("pe_ratio")
        market_cap = float(record.get("market_cap") or 0.0)
        revenue = float(record.get("revenue_current") or 0.0)
        book_value = float(record.get("book_value_per_share") or 0.0)
        shares = float(record.get("shares_outstanding") or 0.0)
        equity = book_value * shares if book_value and shares else None
        pb = (market_cap / equity) if equity else None
        ps = (market_cap / revenue) if revenue else None
        growth = _db_growth_pct(record.get("fcf_5y_growth"))
        peg = (float(pe) / growth) if pe and growth and growth != 0 else None
        div_yield = "N/A"
        val_signal = "EXPENSIVE" if pe and float(pe) > 35 else "FAIR" if pe and float(pe) > 18 else "CHEAP"
        return (
            f"Price Ratios ({ticker}) [financials.db]: price={_fmt(price)}, "
            f"trailingPE={_fmt(pe)} ({val_signal}), "
            f"forwardPE={_fmt(pe)}, PEG={_fmt(peg)}, P/B={_fmt(pb)}, P/S={_fmt(ps)}, "
            f"dividendYield={div_yield}"
        )
    try:
        info = _yf(ticker).info
        trailing_pe  = _fmt(info.get("trailingPE"))
        forward_pe   = _fmt(info.get("forwardPE"))
        peg          = _fmt(info.get("pegRatio"))
        pb           = _fmt(info.get("priceToBook"))
        ps           = _fmt(info.get("priceToSalesTrailing12Months"))
        div_yield    = _pct(info.get("dividendYield"))
        price        = _fmt(info.get("currentPrice") or info.get("regularMarketPrice"))

        def val_signal(pe):
            try:
                x = float(pe)
                return "EXPENSIVE" if x > 35 else "FAIR" if x > 18 else "CHEAP"
            except Exception:
                return "N/A"

        return (
            f"Price Ratios ({ticker}): price={price}, "
            f"trailingPE={trailing_pe} ({val_signal(info.get('trailingPE',''))}), "
            f"forwardPE={forward_pe}, PEG={peg}, P/B={pb}, P/S={ps}, "
            f"dividendYield={div_yield}"
        )
    except ImportError:
        return f"[{ticker}] yfinance not installed — price ratios unavailable. Needed: trailingPE, forwardPE, PEG, P/B, P/S."
    except Exception as e:
        return f"[{ticker}] Price ratios error: {e}"


@tool
def get_ev_multiples(ticker: str) -> str:
    """
    Retrieve Enterprise Value multiples: EV/EBITDA, EV/Revenue, EV/FCF.
    These are the primary multiples used in Comparable Company Analysis (Comps).
    """
    record = _db_record(ticker)
    if _db_row_available(record):
        market_cap = float(record.get("market_cap") or 0.0)
        debt = float(record.get("debt") or 0.0)
        cash = float(record.get("cash") or 0.0)
        ebitda = float(record.get("ebitda") or 0.0)
        revenue = float(record.get("revenue_current") or 0.0)
        fcf = float(record.get("fcf_current") or 0.0)
        ev = market_cap + debt - cash
        ev_ebitda = ev / ebitda if ev and ebitda else None
        ev_revenue = ev / revenue if ev and revenue else None
        ev_fcf = ev / fcf if ev and fcf else None
        fcf_val = f"${_fmt(fcf / 1e9)}B (EV/FCF={_fmt(ev_fcf)})" if fcf else "N/A"
        def ev_signal(x):
            try:
                return "OVERVALUED" if float(x) > 20 else "FAIR" if float(x) > 10 else "UNDERVALUED"
            except Exception:
                return "N/A"
        return (
            f"EV Multiples ({ticker}) [financials.db]: EV=${_fmt(ev/1e9)}B, "
            f"EV/EBITDA={_fmt(ev_ebitda)} ({ev_signal(ev_ebitda)}), "
            f"EV/Revenue={_fmt(ev_revenue)}, TTM_FCF={fcf_val}"
        )
    try:
        info = _yf(ticker).info
        ev         = info.get("enterpriseValue")
        ebitda     = info.get("ebitda")
        revenue    = info.get("totalRevenue")
        ev_ebitda  = _fmt(ev / ebitda) if ev and ebitda else "N/A"
        ev_revenue = _fmt(ev / revenue) if ev and revenue else "N/A"

        # FCF from cashflow
        cf = _yf(ticker).cashflow
        fcf_val = "N/A"
        if cf is not None and not cf.empty:
            try:
                op_cf  = cf.loc["Operating Cash Flow"].iloc[0]
                capex  = cf.loc["Capital Expenditure"].iloc[0]
                fcf    = op_cf + capex  # capex is negative in yfinance
                ev_fcf = _fmt(ev / fcf) if ev and fcf != 0 else "N/A"
                fcf_val = f"${_fmt(fcf / 1e9)}B (EV/FCF={ev_fcf})"
            except Exception:
                pass

        def ev_signal(x):
            try:
                return "OVERVALUED" if float(x) > 20 else "FAIR" if float(x) > 10 else "UNDERVALUED"
            except Exception:
                return "N/A"

        return (
            f"EV Multiples ({ticker}): EV=${_fmt(ev/1e9 if ev else None)}B, "
            f"EV/EBITDA={ev_ebitda} ({ev_signal(ev_ebitda)}), "
            f"EV/Revenue={ev_revenue}, TTM_FCF={fcf_val}"
        )
    except ImportError:
        return f"[{ticker}] yfinance not installed — EV multiples unavailable."
    except Exception as e:
        return f"[{ticker}] EV multiples error: {e}"


@tool
def get_free_cash_flow(ticker: str) -> str:
    """
    Analyze Free Cash Flow (FCF): TTM FCF, FCF yield, FCF margin, and 3-year trend.
    FCF is the gold standard metric for business quality.
    """
    record = _db_record(ticker)
    if _db_row_available(record):
        rows = []
        current = float(record.get("fcf_current") or 0.0)
        revenue = float(record.get("revenue_current") or 0.0)
        market_cap = float(record.get("market_cap") or 0.0)
        yield_pct = (current / market_cap) if market_cap else 0.0
        margin = (current / revenue) if revenue else None
        for label in ["fcf_current", "fcf_1y", "fcf_2y", "fcf_3y", "fcf_4y"]:
            v = record.get(label)
            if v is None:
                continue
            rows.append(f"  {label}: FCF=${_fmt(float(v)/1e9)}B")
        prev = float(record.get("fcf_4y") or current)
        trend = "GROWING" if current >= prev else "DECLINING"
        return (
            f"FCF Analysis ({ticker}) [financials.db] — trend={trend}:\n"
            f"  FCF=${_fmt(current/1e9)}B, yield={_pct(yield_pct)}, margin={_pct(margin)}\n"
            + "\n".join(rows)
        )
    try:
        t     = _yf(ticker)
        info  = t.info
        cf    = t.cashflow

        results = []
        if cf is not None and not cf.empty:
            try:
                op_cf = cf.loc["Operating Cash Flow"]
                capex = cf.loc["Capital Expenditure"]
                fcf   = op_cf + capex  # capex is negative
                mkt   = info.get("marketCap", 1)
                rev   = info.get("totalRevenue", 1)

                for i, col in enumerate(cf.columns[:3]):
                    year_fcf    = fcf.iloc[i]
                    fcf_yield   = _pct(year_fcf / mkt) if mkt else "N/A"
                    fcf_margin  = _pct(year_fcf / rev) if rev else "N/A"
                    results.append(
                        f"  {str(col)[:10]}: FCF=${_fmt(year_fcf/1e9)}B, "
                        f"yield={fcf_yield}, margin={fcf_margin}"
                    )

                trend = "GROWING" if fcf.iloc[0] > fcf.iloc[min(2, len(fcf)-1)] else "DECLINING"
                return f"FCF Analysis ({ticker}) — trend={trend}:\n" + "\n".join(results)
            except KeyError as ke:
                return f"[{ticker}] FCF calculation error (missing key: {ke}). Available rows: {list(cf.index[:8])}"
        return f"[{ticker}] No cash flow data available from yfinance."
    except ImportError:
        return f"[{ticker}] yfinance not installed — FCF analysis unavailable."
    except Exception as e:
        return f"[{ticker}] FCF error: {e}"


@tool
def dcf_valuation(
    ticker: str,
    growth_rate_pct: float = 10.0,
    discount_rate_pct: float = 10.0,
    terminal_growth_pct: float = 3.0,
    years: int = 5,
) -> str:
    """
    Discounted Cash Flow (DCF) valuation. Projects FCF forward at growth_rate_pct,
    discounts at discount_rate_pct (WACC), adds terminal value, returns intrinsic value per share.
    Compare to current price for margin of safety.
    """
    record = _db_record(ticker)
    if _db_row_available(record):
        moderate = record.get("dcf_moderate")
        conservative = record.get("dcf_conservative")
        optimistic = record.get("dcf_optimistic")
        current = _db_price(record)
        if current is None:
            current = float(record.get("market_cap") or 0.0) / float(record.get("shares_outstanding") or 1.0)
        intrinsic = moderate if moderate is not None else conservative if conservative is not None else optimistic
        if intrinsic is None:
            intrinsic = 0.0
        upside = ((float(intrinsic) - float(current)) / float(current) * 100) if current else 0.0
        signal = "UNDERVALUED" if upside > 15 else "OVERVALUED" if upside < -15 else "FAIRLY_VALUED"
        return (
            f"DCF ({ticker}) [financials.db]: conservative=${_fmt(conservative)}, "
            f"moderate=${_fmt(moderate)}, optimistic=${_fmt(optimistic)}\n"
            f"  Intrinsic value=${_fmt(intrinsic)}, Current=${_fmt(current)}, "
            f"Upside={_fmt(upside)}% → {signal}"
        )
    try:
        t    = _yf(ticker)
        info = t.info
        cf   = t.cashflow

        # Get base FCF
        base_fcf = None
        if cf is not None and not cf.empty:
            try:
                op_cf    = float(cf.loc["Operating Cash Flow"].iloc[0])
                capex    = float(cf.loc["Capital Expenditure"].iloc[0])
                base_fcf = op_cf + capex
            except Exception:
                pass

        if base_fcf is None or base_fcf <= 0:
            return (
                f"[{ticker}] DCF requires positive TTM FCF. "
                f"Got base_fcf={base_fcf}. Cannot compute intrinsic value."
            )

        g    = growth_rate_pct / 100
        wacc = discount_rate_pct / 100
        tg   = terminal_growth_pct / 100
        shares = info.get("sharesOutstanding", 1)
        net_debt = (info.get("totalDebt", 0) or 0) - (info.get("totalCash", 0) or 0)
        current_price = info.get("currentPrice") or info.get("regularMarketPrice", 0)

        # Project and discount FCF
        pv_sum = 0.0
        fcf = base_fcf
        for yr in range(1, years + 1):
            fcf *= (1 + g)
            pv_sum += fcf / ((1 + wacc) ** yr)

        # Terminal value
        terminal_fcf = fcf * (1 + tg)
        terminal_val = terminal_fcf / (wacc - tg)
        pv_terminal  = terminal_val / ((1 + wacc) ** years)

        equity_val    = pv_sum + pv_terminal - net_debt
        intrinsic     = equity_val / shares if shares else 0
        upside        = ((intrinsic - current_price) / current_price * 100) if current_price else 0

        signal = "UNDERVALUED" if upside > 15 else "OVERVALUED" if upside < -15 else "FAIRLY_VALUED"
        return (
            f"DCF ({ticker}): base_FCF=${_fmt(base_fcf/1e9)}B, "
            f"growth={growth_rate_pct}%, WACC={discount_rate_pct}%, terminal_g={terminal_growth_pct}%\n"
            f"  PV(FCFs)=${_fmt(pv_sum/1e9)}B, PV(terminal)=${_fmt(pv_terminal/1e9)}B, "
            f"net_debt=${_fmt(net_debt/1e9)}B\n"
            f"  Intrinsic value=${_fmt(intrinsic)}, Current=${_fmt(current_price)}, "
            f"Upside={_fmt(upside)}% → {signal}"
        )
    except ImportError:
        return f"[{ticker}] yfinance not installed. DCF formula: IV = Σ[FCFt/(1+WACC)^t] + TV/(1+WACC)^n - NetDebt / Shares"
    except Exception as e:
        return f"[{ticker}] DCF error: {e}"


@tool
def comparable_analysis(ticker: str, peers: str = "") -> str:
    """
    Comparable Company Analysis (Comps / Multiples). Compares ticker against peers
    on key multiples: PE, EV/EBITDA, PEG, revenue growth, gross margin.
    peers is a comma-separated list of ticker symbols (e.g. 'AAPL,GOOGL,META').
    Leave blank to use yfinance-suggested sector peers if available.
    """
    try:
        import yfinance as yf

        peer_list = [p.strip().upper() for p in peers.split(",") if p.strip()]
        if not peer_list:
            peer_list = [p.get("symbol") for p in get_peer_records(ticker, limit=6) if p.get("symbol")]
        all_tickers = [ticker.upper()] + [p for p in peer_list if p]

        rows = []
        for sym in all_tickers:
            rec = _db_record(sym)
            if _db_row_available(rec):
                ev = float(rec.get("market_cap") or 0.0) + float(rec.get("debt") or 0.0) - float(rec.get("cash") or 0.0)
                ebitda = float(rec.get("ebitda") or 0.0)
                rows.append({
                    "ticker": sym,
                    "PE": _fmt(rec.get("pe_ratio")),
                    "forwardPE": _fmt(rec.get("pe_ratio")),
                    "EV/EBITDA": _fmt(ev / ebitda) if ev and ebitda else "N/A",
                    "PEG": _fmt((float(rec.get("pe_ratio") or 0.0) / max(_db_growth_pct(rec.get("fcf_5y_growth")) or 1.0, 1.0))),
                    "revenueGrowth": _pct(rec.get("fcf_5y_growth")),
                    "grossMargin": _pct(rec.get("operating_margin")),
                    "mktCap": f"${_fmt((rec.get('market_cap') or 0)/1e9)}B",
                })
                continue
            try:
                info = yf.Ticker(sym).info
                rows.append({
                    "ticker":        sym,
                    "PE":            _fmt(info.get("trailingPE")),
                    "forwardPE":     _fmt(info.get("forwardPE")),
                    "EV/EBITDA":     _fmt(info.get("enterpriseToEbitda")),
                    "PEG":           _fmt(info.get("pegRatio")),
                    "revenueGrowth": _pct(info.get("revenueGrowth")),
                    "grossMargin":   _pct(info.get("grossMargins")),
                    "mktCap":        f"${_fmt((info.get('marketCap') or 0)/1e9)}B",
                })
            except Exception as row_err:
                rows.append({"ticker": sym, "error": str(row_err)})

        lines = ["Comparable Analysis:"]
        header = f"  {'Ticker':8} {'PE':>7} {'FwdPE':>7} {'EV/EBITDA':>10} {'PEG':>6} {'RevGrowth':>10} {'GrossMargin':>12} {'MktCap':>10}"
        lines.append(header)
        lines.append("  " + "-" * (len(header) - 2))
        for r in rows:
            if "error" in r:
                lines.append(f"  {r['ticker']:8} ERROR: {r['error']}")
            else:
                lines.append(
                    f"  {r['ticker']:8} {r['PE']:>7} {r['forwardPE']:>7} {r['EV/EBITDA']:>10} "
                    f"{r['PEG']:>6} {r['revenueGrowth']:>10} {r['grossMargin']:>12} {r['mktCap']:>10}"
                )
        return "\n".join(lines)
    except ImportError:
        return f"[{ticker}] yfinance not installed — comparable analysis unavailable."
    except Exception as e:
        return f"[{ticker}] Comps error: {e}"


@tool
def peg_ratio_analysis(ticker: str, expected_growth_pct: float = 0.0) -> str:
    """
    PEG ratio analysis (PE / EPS Growth Rate). PEG < 1 = potentially undervalued,
    PEG > 2 = potentially overvalued. Uses yfinance PEG or computes from PE and growth.
    Optionally override the growth estimate with expected_growth_pct.
    """
    record = _db_record(ticker)
    if _db_row_available(record):
        pe = float(record.get("pe_ratio") or 0.0)
        growth = _db_growth_pct(record.get("fcf_5y_growth"))
        if expected_growth_pct > 0:
            computed_peg = (pe / expected_growth_pct) if pe else None
            override_note = f"(overridden growth={expected_growth_pct}%)"
        else:
            computed_peg = (pe / growth) if pe and growth and growth != 0 else None
            override_note = f"(financials.db growth≈{_fmt(growth)}%)"

        def peg_signal(x):
            try:
                v = float(x)
                return "UNDERVALUED" if v < 1 else "FAIRLY_VALUED" if v <= 2 else "OVERVALUED"
            except Exception:
                return "N/A"

        return (
            f"PEG Analysis ({ticker}) [financials.db] {override_note}: "
            f"PE={_fmt(pe)}, PEG={_fmt(computed_peg)} → {peg_signal(computed_peg)}"
        )
    try:
        info   = _yf(ticker).info
        pe     = info.get("trailingPE")
        peg    = info.get("pegRatio")
        growth = info.get("earningsGrowth") or info.get("revenueGrowth")

        if expected_growth_pct > 0:
            computed_peg = (pe / expected_growth_pct) if pe else None
            override_note = f"(overridden growth={expected_growth_pct}%)"
        else:
            computed_peg = peg
            override_note = f"(yfinance PEG, growth≈{_pct(growth)})"

        def peg_signal(x):
            try:
                v = float(x)
                return "UNDERVALUED" if v < 1 else "FAIRLY_VALUED" if v <= 2 else "OVERVALUED"
            except Exception:
                return "N/A"

        peg_str = _fmt(computed_peg)
        return (
            f"PEG Analysis ({ticker}) {override_note}: "
            f"PE={_fmt(pe)}, PEG={peg_str} → {peg_signal(computed_peg)}"
        )
    except ImportError:
        return f"[{ticker}] yfinance not installed — PEG analysis unavailable."
    except Exception as e:
        return f"[{ticker}] PEG error: {e}"


@tool
def scenario_sensitivity_analysis(
    ticker: str,
    bull_eps_growth_pct: float = 20.0,
    base_eps_growth_pct: float = 10.0,
    bear_eps_growth_pct: float = -5.0,
    target_pe: float = 0.0,
) -> str:
    """
    Scenario & Sensitivity Analysis. Projects price targets under Bull / Base / Bear
    EPS growth scenarios applied to a target PE multiple.
    target_pe=0 uses the current trailing PE.
    """
    record = _db_record(ticker)
    if _db_row_available(record):
        current = _db_price(record)
        eps = float(record.get("eps") or 0.0)
        current_pe = float(record.get("pe_ratio") or target_pe or 25)
        pe = target_pe if target_pe > 0 else current_pe

        def project(growth_pct):
            projected_eps = float(eps) * (1 + growth_pct / 100)
            price_target = projected_eps * float(pe)
            upside = (price_target - float(current)) / float(current) * 100 if current else 0
            return _fmt(price_target), _fmt(upside)

        bull_pt, bull_up = project(bull_eps_growth_pct)
        base_pt, base_up = project(base_eps_growth_pct)
        bear_pt, bear_up = project(bear_eps_growth_pct)
        return (
            f"Scenario Analysis ({ticker}) [financials.db]: current=${_fmt(current)}, EPS=${_fmt(eps)}, "
            f"target_PE={_fmt(pe)}\n"
            f"  BULL (+{bull_eps_growth_pct}% EPS growth): target=${bull_pt} ({bull_up}% upside)\n"
            f"  BASE (+{base_eps_growth_pct}% EPS growth): target=${base_pt} ({base_up}% upside)\n"
            f"  BEAR ({bear_eps_growth_pct}% EPS growth): target=${bear_pt} ({bear_up}% upside)"
        )
    try:
        info       = _yf(ticker).info
        current    = info.get("currentPrice") or info.get("regularMarketPrice", 0)
        eps        = info.get("trailingEps", 0)
        current_pe = info.get("trailingPE", target_pe or 25)
        pe         = target_pe if target_pe > 0 else current_pe

        def project(growth_pct):
            projected_eps = float(eps) * (1 + growth_pct / 100)
            price_target  = projected_eps * float(pe)
            upside        = (price_target - float(current)) / float(current) * 100 if current else 0
            return _fmt(price_target), _fmt(upside)

        bull_pt, bull_up = project(bull_eps_growth_pct)
        base_pt, base_up = project(base_eps_growth_pct)
        bear_pt, bear_up = project(bear_eps_growth_pct)

        return (
            f"Scenario Analysis ({ticker}): current=${_fmt(current)}, EPS=${_fmt(eps)}, "
            f"target_PE={_fmt(pe)}\n"
            f"  BULL (+{bull_eps_growth_pct}% EPS growth): target=${bull_pt} ({bull_up}% upside)\n"
            f"  BASE (+{base_eps_growth_pct}% EPS growth): target=${base_pt} ({base_up}% upside)\n"
            f"  BEAR ({bear_eps_growth_pct}% EPS growth): target=${bear_pt} ({bear_up}% upside)"
        )
    except ImportError:
        return f"[{ticker}] yfinance not installed — scenario analysis unavailable."
    except Exception as e:
        return f"[{ticker}] Scenario analysis error: {e}"


@tool
def get_financial_health(ticker: str) -> str:
    """
    Assess balance sheet health: debt-to-equity, current ratio, quick ratio,
    interest coverage, cash runway, and overall financial strength signal.
    """
    record = _db_record(ticker)
    if _db_row_available(record):
        debt = float(record.get("debt") or 0.0)
        cash = float(record.get("cash") or 0.0)
        de = float(record.get("debt_to_equity") or 0.0)
        op_margins = _pct(record.get("operating_margin"))
        profit_marg = _pct(record.get("pretax_margin"))
        cash_to_debt = _fmt(cash / debt) if debt else "∞ (debt-free)"
        signal = "STRONG" if cash > debt and de < 100 else "ADEQUATE" if cash_to_debt != "N/A" else "STRESSED"
        return (
            f"Financial Health ({ticker}) [financials.db]: signal={signal}\n"
            f"  D/E={_fmt(de)}, currentRatio=N/A, quickRatio=N/A\n"
            f"  cash=${_fmt(cash/1e9)}B, debt=${_fmt(debt/1e9)}B, cash/debt={cash_to_debt}\n"
            f"  EBITDA interest_coverage≈N/A, operatingMargin={op_margins}, netMargin={profit_marg}"
        )
    try:
        info = _yf(ticker).info
        de          = _fmt(info.get("debtToEquity"))
        current_r   = _fmt(info.get("currentRatio"))
        quick_r     = _fmt(info.get("quickRatio"))
        cash        = info.get("totalCash", 0) or 0
        debt        = info.get("totalDebt", 0) or 0
        ebitda      = info.get("ebitda", 0) or 0
        int_cov     = _fmt(ebitda / (debt * 0.05)) if debt and ebitda else "N/A"  # assume 5% cost of debt
        cash_to_debt = _fmt(cash / debt) if debt else "∞ (debt-free)"
        op_margins  = _pct(info.get("operatingMargins"))
        profit_marg = _pct(info.get("profitMargins"))

        def health_signal():
            try:
                cr = float(info.get("currentRatio", 0))
                dq = float(info.get("debtToEquity", 999))
                if cr > 1.5 and dq < 100:
                    return "STRONG"
                elif cr > 1.0 and dq < 200:
                    return "ADEQUATE"
                else:
                    return "STRESSED"
            except Exception:
                return "N/A"

        return (
            f"Financial Health ({ticker}): signal={health_signal()}\n"
            f"  D/E={de}, currentRatio={current_r}, quickRatio={quick_r}\n"
            f"  cash=${_fmt(cash/1e9)}B, debt=${_fmt(debt/1e9)}B, cash/debt={cash_to_debt}\n"
            f"  EBITDA interest_coverage≈{int_cov}x, "
            f"operatingMargin={op_margins}, netMargin={profit_marg}"
        )
    except ImportError:
        return f"[{ticker}] yfinance not installed — financial health unavailable."
    except Exception as e:
        return f"[{ticker}] Financial health error: {e}"


@tool
def get_revenue_and_margins(ticker: str) -> str:
    """
    Revenue growth trend and margin analysis: gross margin, operating margin,
    net margin, and year-over-year revenue growth over the last 3 years.
    """
    record = _db_record(ticker)
    if _db_row_available(record):
        lines = [f"Revenue & Margins ({ticker}) [financials.db]:"]
        revs = [
            ("TTM", record.get("revenue_current")),
            ("1Y", record.get("revenue_1y")),
            ("2Y", record.get("revenue_2y")),
            ("3Y", record.get("revenue_3y")),
            ("4Y", record.get("revenue_4y")),
        ]
        for label, val in revs:
            if val is None:
                continue
            lines.append(
                f"  {label}: Rev=${_fmt(float(val)/1e9)}B, "
                f"grossMargin={_pct(record.get('operating_margin'))}, "
                f"opMargin={_pct(record.get('operating_margin'))}, "
                f"netMargin={_pct(record.get('pretax_margin'))}"
            )
        return "\n".join(lines)
    try:
        t    = _yf(ticker)
        info = t.info
        fin  = t.financials

        lines = [f"Revenue & Margins ({ticker}):"]
        if fin is not None and not fin.empty:
            try:
                rev_row  = fin.loc["Total Revenue"]
                gp_row   = fin.loc["Gross Profit"]
                op_row   = fin.loc["Operating Income"]
                net_row  = fin.loc["Net Income"]
                for i, col in enumerate(fin.columns[:3]):
                    rev = float(rev_row.iloc[i])
                    gp  = float(gp_row.iloc[i])
                    op  = float(op_row.iloc[i])
                    net = float(net_row.iloc[i])
                    yoy = ""
                    if i < len(fin.columns) - 1:
                        prev = float(rev_row.iloc[i+1])
                        yoy  = f"YoY={_pct((rev - prev)/prev)}" if prev else ""
                    lines.append(
                        f"  {str(col)[:10]}: Rev=${_fmt(rev/1e9)}B {yoy}, "
                        f"grossMargin={_pct(gp/rev)}, opMargin={_pct(op/rev)}, netMargin={_pct(net/rev)}"
                    )
            except KeyError as ke:
                lines.append(f"  (missing row: {ke}). Available: {list(fin.index[:8])}")
        else:
            gross_m = _pct(info.get("grossMargins"))
            op_m    = _pct(info.get("operatingMargins"))
            net_m   = _pct(info.get("profitMargins"))
            rev_g   = _pct(info.get("revenueGrowth"))
            lines.append(f"  TTM: grossMargin={gross_m}, opMargin={op_m}, netMargin={net_m}, revenueGrowth={rev_g}")

        return "\n".join(lines)
    except ImportError:
        return f"[{ticker}] yfinance not installed — revenue analysis unavailable."
    except Exception as e:
        return f"[{ticker}] Revenue/margins error: {e}"


@tool
def sotp_analysis(ticker: str, segments_json: str = "{}") -> str:
    """
    Sum of the Parts (SOTP) valuation. Provide segments as a JSON string where
    keys are segment names and values are dicts with 'revenue', 'margin', 'multiple'.
    Example: '{"Cloud": {"revenue": 50, "margin": 0.30, "multiple": 12}}'
    Revenue in billions. Returns aggregate SOTP value vs current market cap.
    """
    record = _db_record(ticker)
    if _db_row_available(record):
        mkt_cap = float(record.get("market_cap") or 0.0) / 1e9
        current = _db_price(record)
        lines = [f"SOTP Valuation ({ticker}) [financials.db]:"]
        lines.append(
            f"  Core snapshot: market_cap=${_fmt(mkt_cap)}B, "
            f"dcf_moderate=${_fmt(record.get('dcf_moderate'))}, "
            f"dcf_conservative=${_fmt(record.get('dcf_conservative'))}, "
            f"dcf_optimistic=${_fmt(record.get('dcf_optimistic'))}"
        )
        if segments_json.strip() != "{}":
            try:
                import json
                segments = json.loads(segments_json)
                for seg_name, props in segments.items():
                    rev = float(props.get("revenue", 0))
                    margin = float(props.get("margin", 0))
                    mult = float(props.get("multiple", 10))
                    ebitda = rev * margin
                    val = ebitda * mult
                    lines.append(f"  {seg_name}: Rev=${_fmt(rev)}B × {margin*100:.0f}% margin × {mult}x = ${_fmt(val)}B")
            except Exception as e:
                lines.append(f"  Segment parse error: {e}")
        lines.append(f"  Implied price=${_fmt(current)} vs current=${_fmt(current)}")
        return "\n".join(lines)
    try:
        import json
        segments = json.loads(segments_json) if segments_json.strip() != "{}" else {}

        info    = _yf(ticker).info
        mkt_cap = (info.get("marketCap", 0) or 0) / 1e9
        current = info.get("currentPrice") or info.get("regularMarketPrice", 0)
        shares  = (info.get("sharesOutstanding", 1) or 1) / 1e9  # in billions

        if not segments:
            return (
                f"SOTP ({ticker}): No segments provided. "
                f"Current mkt_cap=${_fmt(mkt_cap)}B, price=${_fmt(current)}. "
                "Provide segments_json with revenue/margin/multiple per business unit to compute SOTP."
            )

        total_val = 0.0
        lines = [f"SOTP Valuation ({ticker}):"]
        for seg_name, props in segments.items():
            rev     = float(props.get("revenue", 0))
            margin  = float(props.get("margin", 0))
            mult    = float(props.get("multiple", 10))
            ebitda  = rev * margin
            val     = ebitda * mult
            total_val += val
            lines.append(f"  {seg_name}: Rev=${_fmt(rev)}B × {margin*100:.0f}% margin × {mult}x = ${_fmt(val)}B")

        intrinsic_price = (total_val / shares) if shares else 0
        premium         = (total_val - mkt_cap) / mkt_cap * 100 if mkt_cap else 0
        signal = "UNDERVALUED" if premium > 15 else "OVERVALUED" if premium < -15 else "FAIRLY_VALUED"
        lines.append(f"  Total SOTP=${_fmt(total_val)}B vs mkt_cap=${_fmt(mkt_cap)}B ({_fmt(premium)}% {'premium' if premium > 0 else 'discount'}) → {signal}")
        lines.append(f"  Implied price=${_fmt(intrinsic_price)} vs current=${_fmt(current)}")
        return "\n".join(lines)
    except ImportError:
        return f"[{ticker}] yfinance not installed — SOTP base data unavailable."
    except Exception as e:
        return f"[{ticker}] SOTP error: {e}"


# ─────────────────────────────────────────────────────────────────────────────
ALL_FUNDAMENTAL_TOOLS = [
    get_price_ratios,
    get_ev_multiples,
    get_free_cash_flow,
    dcf_valuation,
    comparable_analysis,
    peg_ratio_analysis,
    scenario_sensitivity_analysis,
    get_financial_health,
    get_revenue_and_margins,
    sotp_analysis,
]


def get_all_fundamental_tools():
    return ALL_FUNDAMENTAL_TOOLS
