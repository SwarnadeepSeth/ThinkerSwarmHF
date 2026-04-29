"""
Bull and Bear worker nodes for both wings.
Each worker runs a multi-turn tool-calling loop (≤3 rounds), then synthesises
findings into a structured argument (bull or bear, technical or fundamental).
"""

import time
from langchain_core.messages import HumanMessage, ToolMessage

import tools.indicator_tools  as _itmod
from tools.indicator_tools    import get_all_indicator_tools
import tools.fundamental_tools as _fundmod
from tools.fundamental_tools  import get_all_fundamental_tools
from agents.llm_factory       import get_llm
from agents.print_utils       import (
    node_banner, tool_round_banner, tool_result_line,
    section_divider, findings_preview, node_complete,
)
from core.state import TradingState
from tools.indicator_tools    import get_indicator_tool_playbook


# ── Tool loop ─────────────────────────────────────────────────────────────────

def _tool_loop(llm_with_tools, tool_map, messages, ticker,
               target: int = 5, max_rounds: int = 3):
    """Multi-turn tool-calling loop. Returns {tool_name: result_str}."""
    results      = {}
    last_response = None

    for round_num in range(1, max_rounds + 1):
        response      = llm_with_tools.invoke(messages)
        last_response = response
        tcs           = getattr(response, "tool_calls", None) or []

        if not tcs:
            break

        tool_round_banner(round_num, len(tcs), max_rounds)
        messages.append(response)

        for tc in tcs:
            name = tc["name"]
            args = dict(tc.get("args", {}))
            if "ticker" not in args:
                args["ticker"] = ticker
            try:
                result = tool_map[name].invoke(args)
            except Exception as e:
                result = f"Error: {e}"
            results[name] = str(result)
            messages.append(ToolMessage(content=str(result), tool_call_id=tc["id"]))
            tool_result_line(name, result)

        if len(results) >= target:
            break

        still_needed = target - len(results)
        called       = ", ".join(results.keys())
        messages.append(HumanMessage(
            content=f"Good. Computed so far: {called}. "
                    f"Call {still_needed} more DIFFERENT tools you haven't used yet."
        ))

    return results, last_response


def _choose_structure_tool(tool_results: dict) -> str:
    text = " ".join(str(v).upper() for v in tool_results.values())
    if "WEAK_TREND" in text or "INSIDE_BANDS" in text or "NEUTRAL" in text:
        return "calculate_wt_oscillator"
    if "BREAKOUT" in text or "BULLISH" in text or "BEARISH" in text:
        return "calculate_renko"
    return "calculate_heikin_ashi_rsi"


def _ensure_structure_tool(tool_results, tool_map, ticker, messages, preferred=None):
    structure_tools = [
        "calculate_wt_oscillator",
        "calculate_heikin_ashi_rsi",
        "calculate_renko",
    ]
    if preferred and preferred in structure_tools:
        structure_tools.remove(preferred)
        structure_tools.insert(0, preferred)
    if any(name in tool_results for name in structure_tools):
        return tool_results
    selected = _choose_structure_tool(tool_results)
    if selected not in tool_map:
        return tool_results
    try:
        result = tool_map[selected].invoke({"ticker": ticker})
    except Exception as e:
        result = f"Error: {e}"
    tool_results[selected] = str(result)
    messages.append(HumanMessage(
        content=(
            f"Forced structure tool fallback: {selected} was not used in the LLM loop, "
            "so it was called directly to ensure a noise-reduced regime view."
        )
    ))
    return tool_results


def _base_context(state: TradingState) -> str:
    return (
        f"Ticker: {state['ticker']}\n"
        f"Market Context: {state.get('market_context', 'N/A')}\n"
        f"Manager Brief: {state.get('manager_brief', 'N/A')}\n"
        f"Researcher Context: {state.get('researcher_context', 'N/A')[:600]}\n"
    )


def _bookkeep(state, node_name, content, tool_results, base_llm, elapsed):
    node_outputs = state.get("node_outputs", {})
    node_outputs[node_name] = {
        "llm_output":   content,
        "tool_results": tool_results,
        "model_used":   getattr(base_llm, "model", "unknown"),
    }
    node_timestamps = state.get("node_timestamps", {})
    node_timestamps[node_name] = elapsed
    return node_outputs, node_timestamps


# ── Quantitative Bull ─────────────────────────────────────────────────────────

def quant_bull_worker_node(state: TradingState):
    start_time = time.time()
    ticker  = state["ticker"]
    db_path = state.get("db_path", "data/US_DB.db")

    node_banner("Quant Bull Worker", ticker=ticker, emoji="📈")
    print("  Gathering bullish technical evidence via indicator tools…")

    _itmod._DB_PATH = db_path
    tools    = get_all_indicator_tools()
    tool_map = {t.name: t for t in tools}

    llm_obj  = get_llm()
    base_llm = llm_obj.llm if hasattr(llm_obj, "llm") else llm_obj
    llm_wt   = base_llm.bind_tools(tools)

    context     = _base_context(state)
    instruction = (
        f"You are the Quantitative Bull Analyst for {ticker}. "
        "Call technical indicator tools to gather evidence for a LONG/BULL position. "
        "Call at least 5 different indicators. Focus on: regime, trend persistence, volatility clustering, "
        "acceptance above value, breakout quality, and invalidation structure.\n\n"
        f"{get_indicator_tool_playbook()}\n\n" + context
    )
    messages = [HumanMessage(content=instruction)]
    tool_results, _ = _tool_loop(llm_wt, tool_map, messages, ticker)
    tool_results = _ensure_structure_tool(tool_results, tool_map, ticker, messages, preferred="calculate_wt_oscillator")

    section_divider("Synthesising Bull Case")
    tool_summary    = "\n".join(f"  {k}: {v}" for k, v in tool_results.items())
    synthesis_prompt = (
        f"You are the Quantitative Bull Analyst. Computed indicators for {ticker}:\n"
        f"{tool_summary}\n\n{context}\n"
        "Write a rigorous BULL case. Include:\n"
        "- Which indicators are bullish and why (with numbers)\n"
        "- Regime assessment: trending, ranging, compressing, or breaking out\n"
        "- Key support levels, acceptance levels, and momentum signals\n"
        "- Upside catalysts and entry triggers\n"
        "- Risks that could invalidate the bull thesis\n"
        "- One compact markdown table with columns Signal | Reading | Interpretation"
    )
    findings = llm_obj.invoke(synthesis_prompt).content
    findings_preview(findings, "Bull Findings")

    elapsed = time.time() - start_time
    node_outputs, node_timestamps = _bookkeep(
        state, "quant_bull_worker", findings, tool_results, base_llm, elapsed
    )
    node_complete("Quant Bull Worker", elapsed,
                  f"{len(tool_results)} indicators → bear worker up next")
    return {
        "quant_bull_findings": findings,
        "node_outputs":        node_outputs,
        "node_timestamps":     node_timestamps,
    }


# ── Quantitative Bear ─────────────────────────────────────────────────────────

def quant_bear_worker_node(state: TradingState):
    start_time = time.time()
    ticker  = state["ticker"]
    db_path = state.get("db_path", "data/US_DB.db")

    node_banner("Quant Bear Worker", ticker=ticker, emoji="📉")
    print("  Gathering bearish technical evidence via indicator tools…")

    _itmod._DB_PATH = db_path
    tools    = get_all_indicator_tools()
    tool_map = {t.name: t for t in tools}

    llm_obj  = get_llm()
    base_llm = llm_obj.llm if hasattr(llm_obj, "llm") else llm_obj
    llm_wt   = base_llm.bind_tools(tools)

    context    = _base_context(state)
    bull_ctx   = state.get("quant_bull_findings", "")[:400]
    instruction = (
        f"You are the Quantitative Bear Analyst for {ticker}. "
        "Call technical indicator tools to find evidence for a SHORT/BEAR position. "
        f"The Bull analyst argued: {bull_ctx[:200]}. Counter with data.\n"
        "Call at least 5 different indicators. Focus on: regime failure, trend exhaustion, "
        "volatility expansion, rejection at value, and breakdown structure.\n\n"
        f"{get_indicator_tool_playbook()}\n\n" + context
    )
    messages = [HumanMessage(content=instruction)]
    tool_results, _ = _tool_loop(llm_wt, tool_map, messages, ticker)
    tool_results = _ensure_structure_tool(tool_results, tool_map, ticker, messages, preferred="calculate_renko")

    section_divider("Synthesising Bear Case")
    tool_summary    = "\n".join(f"  {k}: {v}" for k, v in tool_results.items())
    synthesis_prompt = (
        f"You are the Quantitative Bear Analyst. Computed indicators for {ticker}:\n"
        f"{tool_summary}\n\nBull thesis to counter: {bull_ctx}\n\n{context}\n"
        "Write a rigorous BEAR case. Include:\n"
        "- Which indicators are bearish and why (with numbers)\n"
        "- Regime assessment: trending, ranging, compressing, or breaking down\n"
        "- Key resistance levels, rejection zones, and bearish divergences\n"
        "- Downside catalysts and breakdown triggers\n"
        "- Risks that could invalidate the bear thesis\n"
        "- One compact markdown table with columns Signal | Reading | Interpretation"
    )
    findings = llm_obj.invoke(synthesis_prompt).content
    findings_preview(findings, "Bear Findings")

    elapsed = time.time() - start_time
    node_outputs, node_timestamps = _bookkeep(
        state, "quant_bear_worker", findings, tool_results, base_llm, elapsed
    )
    node_complete("Quant Bear Worker", elapsed,
                  f"{len(tool_results)} indicators → quant_head_synthesis")
    return {
        "quant_bear_findings": findings,
        "node_outputs":        node_outputs,
        "node_timestamps":     node_timestamps,
    }


# ── Fundamental Bull ──────────────────────────────────────────────────────────

def fund_bull_worker_node(state: TradingState):
    start_time = time.time()
    ticker = state["ticker"]

    node_banner("Fundamental Bull Worker", ticker=ticker, emoji="💚")
    print("  Gathering bullish valuation evidence via fundamental tools…")

    _fundmod.set_financial_db_path(state.get("financial_db_path", "data/financials.db"))
    tools    = get_all_fundamental_tools()
    tool_map = {t.name: t for t in tools}

    llm_obj  = get_llm()
    base_llm = llm_obj.llm if hasattr(llm_obj, "llm") else llm_obj
    llm_wt   = base_llm.bind_tools(tools)

    context     = _base_context(state)
    instruction = (
        f"You are the Fundamental Bull Analyst for {ticker}. "
        "Call valuation tools to find evidence the stock is UNDERVALUED or fundamentally strong. "
        "Call at least 4 different tools (e.g. DCF, PE ratios, FCF analysis, EV multiples, "
        "financial health). Look for margin of safety and quality metrics.\n\n" + context
    )
    messages = [HumanMessage(content=instruction)]
    tool_results, _ = _tool_loop(llm_wt, tool_map, messages, ticker, target=4)

    section_divider("Synthesising Fundamental Bull Case")
    tool_summary    = "\n".join(f"  {k}: {v}" for k, v in tool_results.items())
    synthesis_prompt = (
        f"You are the Fundamental Bull Analyst. Data for {ticker}:\n"
        f"{tool_summary}\n\n{context}\n"
        "Write a comprehensive BULL fundamental case. Include:\n"
        "- Valuation: is the stock cheap vs. intrinsic value and peers? (use numbers)\n"
        "- Business quality: FCF, margins, balance sheet\n"
        "- Growth catalysts and competitive advantages\n"
        "- Risks to the bull thesis\n"
        "- One compact markdown table with columns Metric | Reading | Interpretation"
    )
    findings = llm_obj.invoke(synthesis_prompt).content
    findings_preview(findings, "Fundamental Bull Findings")

    elapsed = time.time() - start_time
    node_outputs, node_timestamps = _bookkeep(
        state, "fund_bull_worker", findings, tool_results, base_llm, elapsed
    )
    node_complete("Fundamental Bull Worker", elapsed,
                  f"{len(tool_results)} tools → bear worker up next")
    return {
        "fund_bull_findings": findings,
        "node_outputs":       node_outputs,
        "node_timestamps":    node_timestamps,
    }


# ── Fundamental Bear ──────────────────────────────────────────────────────────

def fund_bear_worker_node(state: TradingState):
    start_time = time.time()
    ticker = state["ticker"]

    node_banner("Fundamental Bear Worker", ticker=ticker, emoji="🔴")
    print("  Gathering bearish valuation evidence via fundamental tools…")

    _fundmod.set_financial_db_path(state.get("financial_db_path", "data/financials.db"))
    tools    = get_all_fundamental_tools()
    tool_map = {t.name: t for t in tools}

    llm_obj  = get_llm()
    base_llm = llm_obj.llm if hasattr(llm_obj, "llm") else llm_obj
    llm_wt   = base_llm.bind_tools(tools)

    context    = _base_context(state)
    bull_ctx   = state.get("fund_bull_findings", "")[:400]
    instruction = (
        f"You are the Fundamental Bear Analyst for {ticker}. "
        "Call valuation tools to find evidence of OVERVALUATION or fundamental weakness. "
        f"Bull analyst argued: {bull_ctx[:200]}. Challenge this rigorously.\n"
        "Call at least 4 different tools. Look for stretched multiples, weak FCF, "
        "high debt, slowing growth, scenario downside.\n\n" + context
    )
    messages = [HumanMessage(content=instruction)]
    tool_results, _ = _tool_loop(llm_wt, tool_map, messages, ticker, target=4)

    section_divider("Synthesising Fundamental Bear Case")
    tool_summary    = "\n".join(f"  {k}: {v}" for k, v in tool_results.items())
    synthesis_prompt = (
        f"You are the Fundamental Bear Analyst. Data for {ticker}:\n"
        f"{tool_summary}\n\nBull thesis to counter: {bull_ctx}\n\n{context}\n"
        "Write a comprehensive BEAR fundamental case. Include:\n"
        "- Valuation: is the stock expensive? (use specific multiples and numbers)\n"
        "- Business risks: growth slowdown, margin compression, balance sheet\n"
        "- Competitive threats and scenario downside\n"
        "- Key downside price targets with justification\n"
        "- One compact markdown table with columns Metric | Reading | Interpretation"
    )
    findings = llm_obj.invoke(synthesis_prompt).content
    findings_preview(findings, "Fundamental Bear Findings")

    elapsed = time.time() - start_time
    node_outputs, node_timestamps = _bookkeep(
        state, "fund_bear_worker", findings, tool_results, base_llm, elapsed
    )
    node_complete("Fundamental Bear Worker", elapsed,
                  f"{len(tool_results)} tools → fund_head_synthesis")
    return {
        "fund_bear_findings": findings,
        "node_outputs":       node_outputs,
        "node_timestamps":    node_timestamps,
    }
