"""
Head nodes for each analytical wing.
Each head briefs its workers and synthesises their findings into a structured report.
"""

import time
from agents.llm_factory import get_llm
from agents.utils import load_prompt
from agents.print_utils import (
    node_banner, dispatch_banner, section_divider,
    synthesis_summary, findings_preview, node_complete,
)
from core.state import TradingState


_REPORT_SCHEMA = """\
Structure your report with these exact Markdown headers (include all of them):
## Rationale
Include a compact markdown table named Evidence Snapshot with columns Signal | Reading | Interpretation.
## Bull Perspective
## Bear Perspective
## Risks
## Opportunities
## Priority
(One of: High / Medium / Low)
## Recommended Stop Loss
(Specific price level with justification)
## Profit Target
(Specific price level with justification)
## Time Horizon
(e.g. 2–4 weeks, 1–3 months)
## Overall Bias
(BULLISH / BEARISH / NEUTRAL)"""


def _bookkeep(state, node_name, content, base_llm, elapsed):
    node_outputs = state.get("node_outputs", {})
    node_outputs[node_name] = {
        "llm_output": content,
        "model_used": getattr(base_llm, "model", "unknown"),
    }
    node_timestamps = state.get("node_timestamps", {})
    node_timestamps[node_name] = elapsed
    return node_outputs, node_timestamps


# ── Quantitative Wing ─────────────────────────────────────────────────────────

def quant_head_node(state: TradingState):
    """Briefs quant bull & bear workers — sets the analytical framework."""
    start_time = time.time()
    ticker    = state["ticker"]
    iteration = state.get("iteration_count", 0)

    node_banner("Quant Head — Briefing Workers", ticker=ticker, iteration=iteration, emoji="📊")

    llm_obj  = get_llm()
    base_llm = llm_obj.llm if hasattr(llm_obj, "llm") else llm_obj

    instruction = (
        f"You are the Head of Quantitative Research overseeing analysis of {ticker}.\n"
        f"Market Context: {state.get('market_context', 'N/A')}\n"
        f"Manager Brief: {state.get('manager_brief', 'N/A')}\n\n"
        f"Sentiment Context: {state.get('sentiment_context', 'N/A')[:400]}\n\n"
        "In 3-4 sentences, set the technical analytical framework for your Bull and Bear analysts: "
        "which indicator families to prioritize (trend, momentum, volatility, volume), "
        "the appropriate time horizon, the most important support/resistance levels, "
        "and the exact invalidation threshold that would break the thesis."
    )

    response = llm_obj.invoke(instruction)
    elapsed  = time.time() - start_time

    print(f"\n  Quant Head Brief:")
    for line in response.content.strip().splitlines()[:4]:
        print(f"    {line.strip()[:90]}")

    dispatch_banner(
        "Dispatching Quant Workers",
        [
            ("📈 quant_bull_worker", "→ technical indicator tools (≤3 tool rounds)"),
            ("📉 quant_bear_worker", "→ technical indicator tools (≤3 tool rounds)"),
        ],
    )

    node_outputs, node_timestamps = _bookkeep(state, "quant_head", response.content, base_llm, elapsed)
    node_complete("Quant Head", elapsed)
    return {
        "quant_wing_report": "",
        "node_outputs":      node_outputs,
        "node_timestamps":   node_timestamps,
    }


def quant_head_synthesis_node(state: TradingState):
    """Synthesises quant bull+bear into the authoritative Technical Wing Report."""
    start_time = time.time()
    ticker    = state["ticker"]
    iteration = state.get("iteration_count", 0)

    node_banner("Quant Head — Synthesis", ticker=ticker, iteration=iteration, emoji="📊")

    llm_obj  = get_llm()
    base_llm = llm_obj.llm if hasattr(llm_obj, "llm") else llm_obj

    bull_case = state.get("quant_bull_findings", "No bull findings.")
    bear_case = state.get("quant_bear_findings", "No bear findings.")

    section_divider("Worker Findings Received")
    findings_preview(bull_case, "Bull Analyst", max_chars=250)
    findings_preview(bear_case, "Bear Analyst", max_chars=250)

    instruction = (
        f"You are the Head of Quantitative Research. Synthesise your analysts' findings on {ticker}.\n\n"
        f"BULL ANALYST FINDINGS:\n{bull_case}\n\n"
        f"BEAR ANALYST FINDINGS:\n{bear_case}\n\n"
        f"Sentiment Context: {state.get('sentiment_context','')[:300]}\n\n"
        f"Market Context: {state.get('market_context','')[:300]}\n\n"
        "Produce the definitive Technical / Quantitative Wing Report. Be objective. "
        "Derive specific price levels for Stop Loss (e.g. ATR-based, below key support) "
        "and Profit Target (e.g. resistance, Bollinger upper band). "
        "State a clear time horizon, conviction level, and the exact condition that would invalidate the setup.\n\n"
        f"{_REPORT_SCHEMA}"
    )

    response = llm_obj.invoke(instruction)
    elapsed  = time.time() - start_time

    synthesis_summary(response.content, "Technical Wing Report")

    tech_analysis = state.get("technical_analysis", {})
    tech_analysis["head_synthesis"] = response.content

    node_outputs, node_timestamps = _bookkeep(
        state, "quant_head_synthesis", response.content, base_llm, elapsed
    )
    node_complete("Quant Head Synthesis", elapsed, "→ manager_decision")
    return {
        "quant_wing_report":  response.content,
        "technical_analysis": tech_analysis,
        "node_outputs":       node_outputs,
        "node_timestamps":    node_timestamps,
    }


# ── Fundamental Wing ──────────────────────────────────────────────────────────

def fund_head_node(state: TradingState):
    """Briefs fundamental bull & bear workers — sets the valuation framework."""
    start_time = time.time()
    ticker    = state["ticker"]
    iteration = state.get("iteration_count", 0)

    node_banner("Fundamental Head — Briefing Workers", ticker=ticker, iteration=iteration, emoji="💼")

    llm_obj  = get_llm()
    base_llm = llm_obj.llm if hasattr(llm_obj, "llm") else llm_obj

    instruction = (
        f"You are the Head of Fundamental Research overseeing analysis of {ticker}.\n"
        f"Market Context: {state.get('market_context', 'N/A')}\n"
        f"Manager Brief: {state.get('manager_brief', 'N/A')}\n"
        f"Researcher Context: {state.get('researcher_context', 'N/A')[:400]}\n\n"
        f"Sentiment Context: {state.get('sentiment_context', 'N/A')[:400]}\n\n"
        "In 3-4 sentences, set the valuation analytical framework for your Bull and Bear analysts: "
        "which methods to prioritize (DCF, multiples, FCF yield, comps), "
        "what assumptions to stress-test, what fair-value anchor matters most, "
        "and which business-quality variables could invalidate the thesis."
    )

    response = llm_obj.invoke(instruction)
    elapsed  = time.time() - start_time

    print(f"\n  Fundamental Head Brief:")
    for line in response.content.strip().splitlines()[:4]:
        print(f"    {line.strip()[:90]}")

    dispatch_banner(
        "Dispatching Fundamental Workers",
        [
            ("💚 fund_bull_worker", "→ valuation tools: DCF, PE, EV/EBITDA, FCF, comps (≤3 rounds)"),
            ("🔴 fund_bear_worker", "→ valuation tools: scenario analysis, risk metrics   (≤3 rounds)"),
        ],
    )

    node_outputs, node_timestamps = _bookkeep(state, "fund_head", response.content, base_llm, elapsed)
    node_complete("Fundamental Head", elapsed)
    return {
        "fund_wing_report": "",
        "node_outputs":     node_outputs,
        "node_timestamps":  node_timestamps,
    }


def fund_head_synthesis_node(state: TradingState):
    """Synthesises fund bull+bear into the authoritative Fundamental Wing Report."""
    start_time = time.time()
    ticker    = state["ticker"]
    iteration = state.get("iteration_count", 0)

    node_banner("Fundamental Head — Synthesis", ticker=ticker, iteration=iteration, emoji="💼")

    llm_obj  = get_llm()
    base_llm = llm_obj.llm if hasattr(llm_obj, "llm") else llm_obj

    bull_case    = state.get("fund_bull_findings", "No bull findings.")
    bear_case    = state.get("fund_bear_findings", "No bear findings.")
    research_ctx = state.get("researcher_context", "")

    section_divider("Worker Findings Received")
    findings_preview(bull_case, "Bull Analyst", max_chars=250)
    findings_preview(bear_case, "Bear Analyst", max_chars=250)

    instruction = (
        f"You are the Head of Fundamental Research. Synthesise your analysts' findings on {ticker}.\n\n"
        f"BULL ANALYST FINDINGS:\n{bull_case}\n\n"
        f"BEAR ANALYST FINDINGS:\n{bear_case}\n\n"
        f"Researcher Context: {research_ctx[:400]}\n\n"
        f"Sentiment Context: {state.get('sentiment_context','')[:400]}\n\n"
        "Produce the definitive Fundamental Wing Report. Be objective. "
        "Anchor Stop Loss and Profit Target to specific valuation levels "
        "(e.g. DCF intrinsic value, peer comps median, a specific price where PE would be stretched). "
        "Provide a fair-value range, a clear invalidation point, and the most important assumption to watch.\n\n"
        f"{_REPORT_SCHEMA}"
    )

    response = llm_obj.invoke(instruction)
    elapsed  = time.time() - start_time

    synthesis_summary(response.content, "Fundamental Wing Report")

    fund_analysis = state.get("fundamental_analysis", {})
    fund_analysis["head_synthesis"] = response.content

    node_outputs, node_timestamps = _bookkeep(
        state, "fund_head_synthesis", response.content, base_llm, elapsed
    )
    node_complete("Fundamental Head Synthesis", elapsed, "→ manager_decision")
    return {
        "fund_wing_report":    response.content,
        "fundamental_analysis": fund_analysis,
        "node_outputs":        node_outputs,
        "node_timestamps":     node_timestamps,
    }
