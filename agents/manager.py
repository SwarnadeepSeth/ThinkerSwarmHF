from core.state import TradingState
from agents.llm_factory import get_llm
from agents.utils import load_prompt
import time


def debug_print(msg: str, verbose: bool):
    if verbose:
        print(msg)


def manager_node(state: TradingState):
    """The General Manager that starts the analysis."""
    verbose = state.get("verbose", False)
    start_time = time.time()

    print("\n" + "=" * 50)
    print("📋 MANAGER NODE STARTING")
    print(f"   Ticker: {state['ticker']}")
    print(f"   Iteration: {state.get('iteration_count', 0)}")
    print("=" * 50)
    if verbose:
        print(f"📋 DB Path: {state.get('db_path', 'None')}")

    llm = get_llm()
    system_prompt = load_prompt("manager")

    instruction = (
        f"{system_prompt}\n\n"
        f"Ticker: {state['ticker']}\n"
        "Analyze the broad market context for this ticker to guide the team."
    )

    debug_print(f"📝 Calling LLM with instruction: {instruction[:200]}...", verbose)
    response = llm.invoke(instruction)
    debug_print(f"📨 LLM Response received: {response.content[:200]}...", verbose)

    elapsed = time.time() - start_time
    node_outputs = state.get("node_outputs", {})
    node_outputs["manager"] = {
        "llm_output": response.content,
        "model_used": llm.llm.model if hasattr(llm, "llm") else "unknown",
    }
    node_timestamps = state.get("node_timestamps", {})
    node_timestamps["manager"] = elapsed

    result = {
        "market_context": response.content,
        "node_outputs": node_outputs,
        "node_timestamps": node_timestamps,
    }
    print("✅ MANAGER NODE COMPLETE")
    debug_print(f"   Output preview: {str(result)[:200]}...", verbose)

    return result
