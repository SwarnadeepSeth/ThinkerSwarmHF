from langgraph.graph import StateGraph, START, END
from core.state import TradingState

# Import all agent nodes
from agents.manager import manager_node
from agents.specialists import researcher_node, quant_node, bull_node, bear_node
from agents.coder_subgraph import coder_subgraph
from agents.heads import technical_head_node, fundamental_head_node
from agents.reviewer import reviewer_node

builder = StateGraph(TradingState)

# 1. Register all nodes
builder.add_node("manager", manager_node)
builder.add_node("researcher", researcher_node)
builder.add_node("quant", quant_node)
builder.add_node("coder_loop", coder_subgraph)
builder.add_node("bull", bull_node)
builder.add_node("bear", bear_node)
builder.add_node("technical_head", technical_head_node)
builder.add_node("fundamental_head", fundamental_head_node)
builder.add_node("reviewer", reviewer_node)

# 2. Wire the sequential assembly line (Fixes the Concurrent Error)
builder.add_edge(START, "manager")
builder.add_edge("manager", "researcher")              # Gets fundamental context
builder.add_edge("researcher", "quant")                # Plans the math
builder.add_edge("quant", "coder_loop")                # Writes and tests the math
builder.add_edge("coder_loop", "bull")                 # Bull argues using the math
builder.add_edge("bull", "bear")                       # Bear argues using the math
builder.add_edge("bear", "technical_head")             # Head synthesizes technicals
builder.add_edge("technical_head", "fundamental_head") # Head synthesizes fundamentals
builder.add_edge("fundamental_head", "reviewer")       # Final risk check

# 3. Conditional routing for Reviewer rework
def reviewer_router(state: TradingState):
    # If the setup fails risk checks, loop back to the manager (max 3 times)
    if "FAIL" in state.get("reviewer_feedback", "FAIL") and state.get("iteration_count", 0) < 3:
        return "manager" 
    return END

builder.add_conditional_edges("reviewer", reviewer_router)

# Compile the final executable framework
trading_app = builder.compile()