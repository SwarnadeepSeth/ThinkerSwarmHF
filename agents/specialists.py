from core.state import TradingState
from agents.llm_factory import get_llm
from agents.utils import load_prompt
from tools.file_tools import tool_grep, tool_cat
import time
import json


def debug_print(msg: str, verbose: bool):
    if verbose:
        print(msg)


def researcher_node(state: TradingState):
    """Parses macro data, news, and earnings from the /library."""
    verbose = state.get("verbose", False)
    start_time = time.time()

    print("\n" + "=" * 50)
    print("📋 RESEARCHER NODE STARTING")
    print(f"   Ticker: {state['ticker']}")
    print(f"   Iteration: {state.get('iteration_count', 0)}")
    print("=" * 50)
    if verbose:
        print(f"📋 Market Context: {state.get('market_context', 'None')[:200]}...")

    # Try to get library data directly
    try:
        lib_data = tool_cat("/home/swdseth/MegaSync/ThinkerSwarmHF/library/MSFT.txt")
    except Exception as e:
        lib_data = f"Library data unavailable: {e}"

    llm = get_llm()
    system_prompt = load_prompt("specialists/researcher")

    instruction = (
        f"{system_prompt}\n\n"
        f"Ticker: {state['ticker']}\n"
        f"Library Data: {lib_data}\n"
        "Summarize relevant findings for trading analysis."
    )

    debug_print(f"📝 Calling LLM...", verbose)
    response = llm.invoke(instruction)
    debug_print(f"📨 Researcher output: {response.content[:200]}...", verbose)
    print("✅ RESEARCHER NODE COMPLETE")

    elapsed = time.time() - start_time
    node_outputs = state.get("node_outputs", {})
    node_outputs["researcher"] = {
        "llm_output": response.content,
        "model_used": llm.llm.model if hasattr(llm, "llm") else "unknown",
    }
    node_timestamps = state.get("node_timestamps", {})
    node_timestamps["researcher"] = elapsed

    return {
        "fundamental_analysis": {"researcher_context": response.content},
        "node_outputs": node_outputs,
        "node_timestamps": node_timestamps,
    }


def quant_node(state: TradingState):
    """Designs the mathematical strategy and dictates what the Coder must build."""
    verbose = state.get("verbose", False)
    start_time = time.time()

    print("\n" + "=" * 50)
    print("📋 QUANT NODE STARTING")
    print(f"   Ticker: {state['ticker']}")
    print(f"   Iteration: {state.get('iteration_count', 0)}")
    print("=" * 50)

    llm = get_llm()
    system_prompt = load_prompt("specialists/quant")

    instruction = (
        f"{system_prompt}\n\n"
        f"Ticker: {state['ticker']}. Formulate a technical strategy.\n"
        "Analyze AT LEAST 5 DIFFERENT independent indicators.\n"
        "Output as a comma-separated list (for code generation):\n"
        "INDICATOR_NAME(PARAM1,PARAM2,...), INDICATOR_NAME(PARAM1,PARAM2,...)\n"
        "Example: RSI(14), MACD(12,26,9), BollingerBands(20,2), ATR(14), SMA(50)\n"
        "Only output the list, no explanations."
    )

    debug_print(f"📝 Calling LLM...", verbose)
    response = llm.invoke(instruction)
    debug_print(f"📨 Quant strategy: {response.content[:200]}...", verbose)

    print("✅ QUANT NODE COMPLETE")

    elapsed = time.time() - start_time
    node_outputs = state.get("node_outputs", {})
    node_outputs["quant"] = {
        "llm_output": response.content,
        "model_used": llm.llm.model if hasattr(llm, "llm") else "unknown",
    }
    node_timestamps = state.get("node_timestamps", {})
    node_timestamps["quant"] = elapsed

    return {
        "quant_strategy": response.content,
        "indicator_requested": response.content,
        "node_outputs": node_outputs,
        "node_timestamps": node_timestamps,
    }


def bull_node(state: TradingState):
    """Argues the long case based strictly on Quant/Coder math and Researcher data."""
    verbose = state.get("verbose", False)
    start_time = time.time()

    print("\n" + "=" * 50)
    print("📋 BULL NODE STARTING")
    print(f"   Ticker: {state['ticker']}")
    print(f"   Iteration: {state.get('iteration_count', 0)}")
    print("=" * 50)
    if verbose:
        coder_output = state.get("coder_output", {})
        print(f"📋 Coder Output: {str(coder_output)[:200]}...")
        fund_data = state.get("fundamental_analysis", {})
        print(f"📋 Fundamental Data: {str(fund_data)[:200]}...")

    llm = get_llm()
    system_prompt = load_prompt("specialists/bull")

    instruction = (
        f"{system_prompt}\n\n"
        f"Ticker: {state['ticker']}.\n"
        f"Verified Math Data: {state.get('coder_output', 'None')}\n"
        f"Fundamental Data: {state.get('fundamental_analysis', {}).get('researcher_context', 'None')}\n"
        "Build the strongest possible case for going LONG."
    )

    debug_print(f"📝 Calling LLM for bull case...", verbose)
    response = llm.invoke(instruction)
    debug_print(f"📨 Bull case: {response.content[:200]}...", verbose)

    # Safely update the dictionary without overwriting previous data
    tech_data = state.get("technical_analysis", {})
    tech_data["bull_case"] = response.content
    print("✅ BULL NODE COMPLETE")

    elapsed = time.time() - start_time
    node_outputs = state.get("node_outputs", {})
    node_outputs["bull"] = {
        "llm_output": response.content,
        "model_used": llm.llm.model if hasattr(llm, "llm") else "unknown",
    }
    node_timestamps = state.get("node_timestamps", {})
    node_timestamps["bull"] = elapsed

    return {
        "technical_analysis": tech_data,
        "node_outputs": node_outputs,
        "node_timestamps": node_timestamps,
    }


def bear_node(state: TradingState):
    """Argues the short case based strictly on Quant/Coder math and Researcher data."""
    verbose = state.get("verbose", False)
    start_time = time.time()

    print("\n" + "=" * 50)
    print("📋 BEAR NODE STARTING")
    print(f"   Ticker: {state['ticker']}")
    print(f"   Iteration: {state.get('iteration_count', 0)}")
    print("=" * 50)
    if verbose:
        coder_output = state.get("coder_output", {})
        print(f"📋 Coder Output: {str(coder_output)[:200]}...")
        fund_data = state.get("fundamental_analysis", {})
        print(f"📋 Fundamental Data: {str(fund_data)[:200]}...")

    llm = get_llm()
    system_prompt = load_prompt("specialists/bear")

    instruction = (
        f"{system_prompt}\n\n"
        f"Ticker: {state['ticker']}.\n"
        f"Verified Math Data: {state.get('coder_output', 'None')}\n"
        f"Fundamental Data: {state.get('fundamental_analysis', {}).get('researcher_context', 'None')}\n"
        "Build the strongest possible case for going SHORT."
    )

    debug_print(f"📝 Calling LLM for bear case...", verbose)
    response = llm.invoke(instruction)
    debug_print(f"📨 Bear case: {response.content[:200]}...", verbose)

    # Safely update the dictionary without overwriting previous data
    tech_data = state.get("technical_analysis", {})
    tech_data["bear_case"] = response.content
    print("✅ BEAR NODE COMPLETE")

    elapsed = time.time() - start_time
    node_outputs = state.get("node_outputs", {})
    node_outputs["bear"] = {
        "llm_output": response.content,
        "model_used": llm.llm.model if hasattr(llm, "llm") else "unknown",
    }
    node_timestamps = state.get("node_timestamps", {})
    node_timestamps["bear"] = elapsed

    return {
        "technical_analysis": tech_data,
        "node_outputs": node_outputs,
        "node_timestamps": node_timestamps,
    }
