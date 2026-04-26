from core.state import TradingState
from agents.llm_factory import get_llm
from agents.utils import load_prompt
from tools.file_tools import tool_grep, tool_cat

# --- NEW MODERN IMPORTS ---
from langgraph.prebuilt import create_react_agent
from langchain_core.messages import SystemMessage, HumanMessage


def debug_print(msg: str, verbose: bool):
    if verbose:
        print(msg)


def researcher_node(state: TradingState):
    """Parses macro data, news, and earnings from the /library using executable tools."""
    verbose = state.get("verbose", False)

    print("\n" + "=" * 50)
    print("📋 RESEARCHER NODE STARTING")
    print(f"   Ticker: {state['ticker']}")
    print(f"   Iteration: {state.get('iteration_count', 0)}")
    print("=" * 50)
    if verbose:
        print(f"📋 Market Context: {state.get('market_context', 'None')[:200]}...")

    llm = get_llm()
    tools = [tool_grep, tool_cat]

    # 1. Create the modern execution engine
    agent_executor = create_react_agent(llm, tools)

    # 2. Setup the messages
    system_prompt = load_prompt("specialists/researcher")
    human_prompt = (
        f"Ticker: {state['ticker']}. Market Context: {state.get('market_context', 'None')}\n"
        "Use your tools to search the library for relevant earnings and macro data and summarize the findings."
    )

    messages = [
        SystemMessage(content=system_prompt),
        HumanMessage(content=human_prompt),
    ]

    debug_print(f"📝 Invoking researcher agent with tools...", verbose)
    # 3. Run the tools!
    result = agent_executor.invoke({"messages": messages})
    final_output = result["messages"][-1].content

    debug_print(f"📨 Researcher output: {final_output[:200]}...", verbose)
    print("✅ RESEARCHER NODE COMPLETE")

    return {"fundamental_analysis": {"researcher_context": final_output}}


def quant_node(state: TradingState):
    """Designs the mathematical strategy and dictates what the Coder must build."""
    verbose = state.get("verbose", False)

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
        "Output exactly the name and parameters of the mathematical indicator you need the Coder to execute."
    )

    debug_print(f"📝 Calling LLM...", verbose)
    response = llm.invoke(instruction)
    debug_print(f"📨 Quant strategy: {response.content[:200]}...", verbose)

    print("✅ QUANT NODE COMPLETE")

    return {"quant_strategy": response.content, "indicator_requested": response.content}


def bull_node(state: TradingState):
    """Argues the long case based strictly on Quant/Coder math and Researcher data."""
    verbose = state.get("verbose", False)

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

    return {"technical_analysis": tech_data}


def bear_node(state: TradingState):
    """Argues the short case based strictly on Quant/Coder math and Researcher data."""
    verbose = state.get("verbose", False)

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

    return {"technical_analysis": tech_data}
