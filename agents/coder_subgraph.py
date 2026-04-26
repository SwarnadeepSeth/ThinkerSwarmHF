from langgraph.graph import StateGraph, START, END
from core.state import TradingState
from agents.llm_factory import get_llm
from tools.sandbox import execute_python_code
from tools.file_tools import tool_cat, tool_grep, tool_ls, tool_sed_replace
from agents.utils import load_prompt

# --- NEW MODERN IMPORTS ---
from langgraph.prebuilt import create_react_agent
from langchain_core.messages import SystemMessage, HumanMessage


def debug_print(msg: str, verbose: bool):
    if verbose:
        print(msg)


def coder_node(state: TradingState):
    """Writes code and ACTUALLY executes tools using LangGraph's native agent engine."""
    verbose = state.get("verbose", False)
    loop_count = state.get("coder_loop_count", 0)

    print("\n" + "=" * 50)
    print("📋 CODER NODE STARTING")
    print(f"   Ticker: {state.get('ticker', 'None')}")
    print(f"   Iteration: {state.get('iteration_count', 0)}")
    print(f"   Coder Loop: {loop_count + 1}")
    print("=" * 50)
    if verbose:
        print(f"📋 Indicator Requested: {state.get('indicator_requested', 'None')}")
        print(f"📋 Previous Feedback: {state.get('code_review_feedback', 'None')}")
        print(f"📋 DB Path: {state.get('db_path', 'None')}")

    llm = get_llm()
    tools = [tool_cat, tool_grep, tool_ls, tool_sed_replace, execute_python_code]

    # 1. Create the modern execution engine
    agent_executor = create_react_agent(llm, tools)

    # 2. Setup the messages
    system_prompt = load_prompt("specialists/coder")
    db_path = state.get("db_path", "data/US_DB.db")
    human_prompt = (
        f"Ticker: {state.get('ticker')}\n"
        f"Quant request: {state.get('indicator_requested')}\n"
        f"Feedback: {state.get('code_review_feedback')}\n"
        f"IMPORTANT: The SQLite database is at '{db_path}'. Use this exact path in your code to connect."
    )

    messages = [
        SystemMessage(content=system_prompt),
        HumanMessage(content=human_prompt),
    ]

    debug_print(f"📝 Invoking coder agent with {len(tools)} tools...", verbose)
    # 3. Run the tools!
    result = agent_executor.invoke({"messages": messages})

    # 4. Extract the final response string from the agent's last message
    final_output = result["messages"][-1].content

    debug_print(f"📨 Coder output: {final_output[:200]}...", verbose)
    print("✅ CODER NODE COMPLETE")

    return {
        "draft_code": final_output,
        "coder_output": {"sandbox_results": final_output},
        "coder_loop_count": loop_count + 1,
    }


def code_reviewer_node(state: TradingState):
    """Critiques the draft code and sandbox test outputs."""
    verbose = state.get("verbose", False)
    loop_count = state.get("coder_loop_count", 0)

    print("\n" + "=" * 50)
    print("📋 CODE REVIEWER NODE STARTING")
    print(f"   Coder Loop: {loop_count}")
    print("=" * 50)
    if verbose:
        print(f"📋 Draft Code: {state.get('draft_code', 'None')[:200]}...")

    llm = get_llm()
    instruction = (
        f"You are the Code Reviewer. Review this draft code and output: {state.get('draft_code')}. "
        "Does it pass unit tests? Is it efficient? Reply with exactly 'PASS' if approved, or provide strict feedback."
    )

    debug_print(f"📝 Calling LLM for code review...", verbose)
    response = llm.invoke(instruction)
    debug_print(f"📨 Review feedback: {response.content[:200]}...", verbose)

    approved = "PASS" in response.content.upper()
    print(f"✅ CODE REVIEWER NODE COMPLETE (Approved: {approved})")

    return {"code_approved": approved, "code_review_feedback": response.content}


def coder_router(state: TradingState):
    """Routes back to the Coder if the Reviewer fails the code."""
    if state.get("code_approved"):
        return END
    return "coder"


# Wire the Subgraph
coder_builder = StateGraph(TradingState)
coder_builder.add_node("coder", coder_node)
coder_builder.add_node("reviewer", code_reviewer_node)

coder_builder.add_edge(START, "coder")
coder_builder.add_edge("coder", "reviewer")
coder_builder.add_conditional_edges("reviewer", coder_router)

coder_subgraph = coder_builder.compile()
