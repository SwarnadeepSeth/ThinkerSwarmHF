from core.state import TradingState
from agents.llm_factory import get_llm
from agents.utils import load_prompt


def debug_print(msg: str, verbose: bool):
    if verbose:
        print(msg)


def technical_head_node(state: TradingState):
    """Synthesizes the Quant, Bull, and Bear into a final technical outlook."""
    verbose = state.get("verbose", False)

    print("\n" + "=" * 50)
    print("📋 TECHNICAL HEAD NODE STARTING")
    print(f"   Ticker: {state['ticker']}")
    print(f"   Iteration: {state.get('iteration_count', 0)}")
    print("=" * 50)
    if verbose:
        print(f"📋 Quant Strategy: {state.get('quant_strategy', 'None')[:200]}...")
        print(
            f"📋 Bull Case: {state.get('technical_analysis', {}).get('bull_case', 'None')[:200]}..."
        )
        print(
            f"📋 Bear Case: {state.get('technical_analysis', {}).get('bear_case', 'None')[:200]}..."
        )

    llm = get_llm()
    system_prompt = load_prompt("heads/technical_head")

    tech_data = state.get("technical_analysis", {})
    bull_case = tech_data.get("bull_case", "No bull case provided.")
    bear_case = tech_data.get("bear_case", "No bear case provided.")
    quant_strat = state.get("quant_strategy", "No quant strategy provided.")

    instruction = (
        f"{system_prompt}\n\n"
        f"Quant Strategy: {quant_strat}\n"
        f"Bull Argument: {bull_case}\n"
        f"Bear Argument: {bear_case}\n\n"
        "Synthesize this into a definitive Technical Report."
    )

    debug_print(f"📝 Calling LLM for technical synthesis...", verbose)
    response = llm.invoke(instruction)
    debug_print(f"📨 Technical synthesis: {response.content[:200]}...", verbose)

    print("✅ TECHNICAL HEAD NODE COMPLETE")

    return {"technical_analysis": {"head_synthesis": response.content}}


def fundamental_head_node(state: TradingState):
    """Synthesizes the fundamental data into a final intrinsic valuation outlook."""
    verbose = state.get("verbose", False)

    print("\n" + "=" * 50)
    print("📋 FUNDAMENTAL HEAD NODE STARTING")
    print(f"   Ticker: {state['ticker']}")
    print(f"   Iteration: {state.get('iteration_count', 0)}")
    print("=" * 50)
    if verbose:
        print(
            f"📋 Researcher Context: {state.get('fundamental_analysis', {}).get('researcher_context', 'None')[:200]}..."
        )

    llm = get_llm()
    system_prompt = load_prompt("heads/fundamental_head")

    fund_data = state.get("fundamental_analysis", {})
    research = fund_data.get("researcher_context", "No research provided.")

    instruction = (
        f"{system_prompt}\n\n"
        f"Raw Researcher Data: {research}\n\n"
        "Synthesize this into a definitive Fundamental Report."
    )

    debug_print(f"📝 Calling LLM for fundamental synthesis...", verbose)
    response = llm.invoke(instruction)
    debug_print(f"📨 Fundamental synthesis: {response.content[:200]}...", verbose)

    print("✅ FUNDAMENTAL HEAD NODE COMPLETE")

    return {"fundamental_analysis": {"head_synthesis": response.content}}
