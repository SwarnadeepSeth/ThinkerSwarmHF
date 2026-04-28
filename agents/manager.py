import time
from agents.llm_factory import get_llm
from agents.utils import load_prompt
from agents.print_utils import (
    node_banner, dispatch_banner, section_divider, node_complete,
)
from core.state import TradingState


def manager_node(state: TradingState):
    """General Manager — sets macro context and dispatches both wings."""
    start_time = time.time()
    ticker    = state["ticker"]
    iteration = state.get("iteration_count", 0)

    node_banner("Manager", ticker=ticker, iteration=iteration, emoji="🏢")

    llm_obj  = get_llm()
    base_llm = llm_obj.llm if hasattr(llm_obj, "llm") else llm_obj
    system_prompt = load_prompt("manager")

    instruction = (
        f"{system_prompt}\n\n"
        f"Ticker: {ticker}\n"
        "Issue a brief Market Context directive (2-3 sentences) for both the Quantitative "
        "and Fundamental wings. Set the macro tone. Do not analyze the stock yourself."
    )

    response = llm_obj.invoke(instruction)
    elapsed  = time.time() - start_time

    print(f"\n  Market Context Brief:")
    for line in response.content.strip().splitlines()[:4]:
        print(f"    {line.strip()}")

    dispatch_banner(
        "Dispatching both wings in PARALLEL",
        [
            ("📊 QUANTITATIVE WING", "→ quant_head → bull_worker → bear_worker → synthesis"),
            ("💼 FUNDAMENTAL WING",  "→ fund_head  → bull_worker → bear_worker → synthesis"),
        ],
    )

    node_outputs = state.get("node_outputs", {})
    node_outputs["manager"] = {
        "llm_output": response.content,
        "model_used": getattr(base_llm, "model", "unknown"),
    }
    node_timestamps = state.get("node_timestamps", {})
    node_timestamps["manager"] = elapsed
    node_complete("Manager", elapsed, "wings dispatched")

    return {
        "market_context": response.content,
        "manager_brief":  response.content,
        "node_outputs":   node_outputs,
        "node_timestamps": node_timestamps,
    }


def manager_decision_node(state: TradingState):
    """Final Manager synthesis — reconciles both wing reports into the trade brief."""
    start_time = time.time()
    ticker = state["ticker"]

    node_banner("Manager — Final Decision", ticker=ticker, emoji="🏢")

    llm_obj  = get_llm()
    base_llm = llm_obj.llm if hasattr(llm_obj, "llm") else llm_obj

    quant_report = state.get("quant_wing_report", "No quantitative report.")
    fund_report  = state.get("fund_wing_report",  "No fundamental report.")

    section_divider("Wing Reports Received")
    print(f"    📊 Quant Report   : {len(quant_report):,} chars")
    print(f"    💼 Fundamental Report: {len(fund_report):,} chars")

    instruction = (
        f"You are the General Manager of an autonomous AI trading firm. "
        f"Review both wing reports for {ticker} and make the final call.\n\n"
        f"QUANTITATIVE / TECHNICAL WING REPORT:\n{quant_report}\n\n"
        f"FUNDAMENTAL WING REPORT:\n{fund_report}\n\n"
        "Synthesize these into a single, decisive trade brief for the Risk Reviewer. Include:\n"
        "- Overall direction: LONG, SHORT, or NEUTRAL\n"
        "- Conviction level (High / Medium / Low) and reasoning\n"
        "- Key agreement and disagreement between the wings\n"
        "- Final recommended entry zone, stop loss, and profit target (in price terms)\n"
        "- Time horizon\n"
        "- Top 3 risks to monitor\n"
        "Be decisive. The Reviewer will use this to generate the final structured trade setup."
    )

    response = llm_obj.invoke(instruction)
    elapsed  = time.time() - start_time

    print(f"\n  Manager Decision Preview:")
    for line in response.content.strip().splitlines()[:5]:
        print(f"    {line.strip()[:90]}")

    node_outputs = state.get("node_outputs", {})
    node_outputs["manager_decision"] = {
        "llm_output": response.content,
        "model_used": getattr(base_llm, "model", "unknown"),
    }
    node_timestamps = state.get("node_timestamps", {})
    node_timestamps["manager_decision"] = elapsed

    tech_analysis = state.get("technical_analysis", {})
    fund_analysis = state.get("fundamental_analysis", {})
    if "head_synthesis" not in tech_analysis:
        tech_analysis["head_synthesis"] = quant_report
    if "head_synthesis" not in fund_analysis:
        fund_analysis["head_synthesis"] = fund_report

    node_complete("Manager Decision", elapsed, "→ Reviewer")
    return {
        "market_context":      response.content,
        "technical_analysis":  tech_analysis,
        "fundamental_analysis": fund_analysis,
        "node_outputs":        node_outputs,
        "node_timestamps":     node_timestamps,
    }
