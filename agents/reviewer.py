from core.state import TradingState
from agents.llm_factory import get_llm
from agents.utils import load_prompt
from pydantic import BaseModel, Field
import time


def debug_print(msg: str, verbose: bool):
    if verbose:
        print(msg)


# Define the strict output schema
class TradeSetup(BaseModel):
    direction: str = Field(description="LONG, SHORT, or NEUTRAL")
    entry_price: float = Field(description="Suggested entry price based on data")
    stoploss: float = Field(description="Hard stop loss level")
    target: float = Field(description="Take profit target")
    risk_volatility: str = Field(
        description="Assessment of current risk and volatility (High/Med/Low)"
    )
    timeframe: str = Field(description="Expected time to reach target")
    reasoning: str = Field(description="Brief 2-sentence justification")


def reviewer_node(state: TradingState):
    """Critiques the setup and enforces the final JSON output schema."""
    verbose = state.get("verbose", False)
    start_time = time.time()

    print("\n" + "=" * 50)
    print("📋 REVIEWER NODE STARTING")
    print(f"   Ticker: {state['ticker']}")
    print(f"   Iteration: {state.get('iteration_count', 0)}")
    print("=" * 50)
    if verbose:
        print(
            f"📋 Technical Synthesis: {state.get('technical_analysis', {}).get('head_synthesis', 'None')[:200]}..."
        )
        print(
            f"📋 Fundamental Synthesis: {state.get('fundamental_analysis', {}).get('head_synthesis', 'None')[:200]}..."
        )

    # Bind the Pydantic schema to the LLM so it MUST output JSON
    llm = get_llm().with_structured_output(TradeSetup)
    system_prompt = load_prompt("reviewer")

    tech_synthesis = state.get("technical_analysis", {}).get("head_synthesis", "None")
    fund_synthesis = state.get("fundamental_analysis", {}).get("head_synthesis", "None")

    instruction = (
        f"{system_prompt}\n\n"
        f"Ticker: {state['ticker']}\n"
        f"Technical Report: {tech_synthesis}\n"
        f"Fundamental Report: {fund_synthesis}\n\n"
        "If the setup is logically sound, output the final trade setup in the requested format."
    )

    try:
        debug_print(f"📝 Calling LLM for final trade setup...", verbose)
        # The response is now a validated Pydantic object, not a string
        structured_response = llm.invoke(instruction)

        debug_print(f"📨 Trade setup: {structured_response.dict()}", verbose)
        print("✅ REVIEWER NODE COMPLETE")

        elapsed = time.time() - start_time
        node_outputs = state.get("node_outputs", {})
        node_outputs["reviewer"] = {
            "llm_output": structured_response.dict(),
            "model_used": llm.llm.model if hasattr(llm, "llm") else "unknown",
        }
        node_timestamps = state.get("node_timestamps", {})
        node_timestamps["reviewer"] = elapsed

        # Convert Pydantic object back to a standard dictionary for the state
        return {
            "final_decision": structured_response.dict(),
            "reviewer_feedback": "PASS",
            "iteration_count": 1,  # Increments the counter
            "node_outputs": node_outputs,
            "node_timestamps": node_timestamps,
        }
    except Exception as e:
        # If the LLM fails to match the schema or logic fails
        print(f"❌ REVIEWER NODE FAILED: {e}")

        elapsed = time.time() - start_time
        node_timestamps = state.get("node_timestamps", {})
        node_timestamps["reviewer"] = elapsed

        return {
            "reviewer_feedback": f"FAIL: {str(e)}",
            "iteration_count": 1,
            "node_timestamps": node_timestamps,
        }
