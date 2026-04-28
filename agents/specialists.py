from core.state import TradingState
from agents.llm_factory import get_llm
from agents.utils import load_prompt
from agents.print_utils import node_banner, section_divider, node_complete, dispatch_banner
from tools.file_tools import tool_grep, tool_cat
import tools.indicator_tools as _itmod
from tools.indicator_tools import get_all_indicator_tools
from langchain_core.messages import HumanMessage, ToolMessage
import time
import json


def researcher_node(state: TradingState):
    """Parses macro data, news, and earnings from the /library."""
    start_time = time.time()
    ticker    = state["ticker"]
    iteration = state.get("iteration_count", 0)

    node_banner("Researcher", ticker=ticker, iteration=iteration, emoji="📰")
    print(f"  Loading library data for {ticker}…")

    try:
        lib_data = tool_cat.invoke(
            {"file_path": f"/home/swdseth/MegaSync/ThinkerSwarmHF/library/{ticker}.txt"}
        )
        print(f"  Library file loaded ({len(lib_data):,} chars)")
    except Exception as e:
        lib_data = f"Library data unavailable: {e}"
        print(f"  ⚠ Library unavailable: {e}")

    llm = get_llm()
    system_prompt = load_prompt("specialists/researcher")
    instruction = (
        f"{system_prompt}\n\n"
        f"Ticker: {ticker}\n"
        f"Library Data: {lib_data}\n"
        "Summarize relevant findings for trading analysis."
    )

    response = llm.invoke(instruction)
    elapsed  = time.time() - start_time

    preview = response.content.replace("\n", " ").strip()[:200]
    print(f"\n  Context Preview: {preview}…")

    dispatch_banner(
        "Context ready — dispatching wings",
        [
            ("📊 QUANTITATIVE WING", "→ quant_head"),
            ("💼 FUNDAMENTAL WING",  "→ fund_head"),
        ],
    )

    node_outputs = state.get("node_outputs", {})
    node_outputs["researcher"] = {
        "llm_output": response.content,
        "model_used": llm.llm.model if hasattr(llm, "llm") else "unknown",
    }
    node_timestamps = state.get("node_timestamps", {})
    node_timestamps["researcher"] = elapsed
    node_complete("Researcher", elapsed)

    return {
        "researcher_context":   response.content,
        "fundamental_analysis": {"researcher_context": response.content},
        "node_outputs":         node_outputs,
        "node_timestamps":      node_timestamps,
    }


def quant_node(state: TradingState):
    """
    Calls indicator tools directly via LangChain tool calling.
    Falls back to setting indicator_requested (for coder_loop) only when
    the LLM makes no tool calls.
    """
    verbose = state.get("verbose", False)
    start_time = time.time()

    ticker = state["ticker"]
    db_path = state.get("db_path", "data/US_DB.db")

    print("\n" + "=" * 50)
    print("📋 QUANT NODE STARTING")
    print(f"   Ticker: {ticker}")
    print(f"   Iteration: {state.get('iteration_count', 0)}")
    print("=" * 50)

    # Point indicator tools at the correct DB
    _itmod._DB_PATH = db_path

    indicator_tools = get_all_indicator_tools()
    tool_map = {t.name: t for t in indicator_tools}

    # Bind tools to the base LLM (bypass RetryLLM wrapper)
    llm_obj = get_llm()
    base_llm = llm_obj.llm if hasattr(llm_obj, "llm") else llm_obj
    llm_with_tools = base_llm.bind_tools(indicator_tools)

    system_prompt = load_prompt("specialists/quant")
    instruction = (
        f"{system_prompt}\n\n"
        f"Ticker: {ticker}. Use the available indicator tools to calculate AT LEAST 5 "
        "different technical indicators. Call each tool with the ticker and appropriate "
        "parameters. Do not explain — just call the tools."
    )

    debug_print("📝 Calling LLM with tools...", verbose)

    # Multi-turn tool loop: keep calling until we have 5+ indicators or LLM stops
    messages = [HumanMessage(content=instruction)]
    tool_results = {}
    TARGET = 5
    MAX_ROUNDS = 4

    for round_num in range(MAX_ROUNDS):
        response = llm_with_tools.invoke(messages)
        tcs = getattr(response, "tool_calls", None) or []

        if not tcs:
            break  # LLM finished or gave up

        print(f"🔧 Round {round_num+1}: LLM called {len(tcs)} tool(s) — executing...")
        messages.append(response)  # add AI turn with tool calls

        for tc in tcs:
            name = tc["name"]
            args = dict(tc.get("args", {}))
            if "ticker" not in args:
                args["ticker"] = ticker
            print(f"   → {name}({args})")
            try:
                result = tool_map[name].invoke(args)
                tool_results[name] = result
                debug_print(f"      {result}", verbose)
            except Exception as e:
                result = f"Error: {e}"
                tool_results[name] = result
                print(f"   ⚠️ {name} failed: {e}")
            messages.append(ToolMessage(content=str(result), tool_call_id=tc["id"]))

        if len(tool_results) >= TARGET:
            break  # enough indicators collected

        # Ask LLM to call more tools
        still_needed = TARGET - len(tool_results)
        called_so_far = ", ".join(tool_results.keys())
        messages.append(HumanMessage(
            content=f"Good. You've computed: {called_so_far}. "
                    f"Now call {still_needed} more DIFFERENT indicator tools you haven't used yet."
        ))

    used_tools = bool(tool_results)

    if used_tools:
        print(f"✅ QUANT NODE COMPLETE — {len(tool_results)} indicators computed via tools")
        coder_output = {"tool_results": tool_results}
        quant_strategy = "\n".join(f"{k}: {v}" for k, v in tool_results.items())
        indicator_requested = quant_strategy
    else:
        # LLM made zero tool calls across all rounds — fall back to coder_loop
        print("⚠️ QUANT NODE: no tool calls after all rounds — falling back to coder_loop")
        quant_strategy = getattr(response, "content", "")
        indicator_requested = quant_strategy
        coder_output = {}

    elapsed = time.time() - start_time
    node_outputs = state.get("node_outputs", {})
    node_outputs["quant"] = {
        "llm_output": quant_strategy,
        "tool_results": tool_results,
        "used_tools": used_tools,
        "model_used": getattr(base_llm, "model", "unknown"),
    }
    node_timestamps = state.get("node_timestamps", {})
    node_timestamps["quant"] = elapsed

    return {
        "quant_strategy": quant_strategy,
        "indicator_requested": indicator_requested,
        "quant_used_tools": used_tools,
        "coder_output": coder_output if used_tools else state.get("coder_output", {}),
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
