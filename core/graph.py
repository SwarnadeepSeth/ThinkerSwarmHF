"""
ThinkerSwarm Graph — two-wing architecture
==========================================

START → manager → researcher
                      │
            ┌─────────┴──────────┐   (parallel fan-out)
            ▼                    ▼
        quant_head           fund_head
            │                    │
      quant_bull_worker    fund_bull_worker
            │                    │
      quant_bear_worker    fund_bear_worker
            │                    │
   quant_head_synthesis   fund_head_synthesis
            │                    │
            └─────────┬──────────┘   (parallel fan-in)
                      ▼
               manager_decision
                      │
                   reviewer
                      │
              END  /  manager (retry ≤3)
"""

from langgraph.graph import StateGraph, START, END
from core.state import TradingState

from agents.manager import manager_node, manager_decision_node
from agents.specialists import researcher_node
from agents.heads import (
    quant_head_node,
    quant_head_synthesis_node,
    fund_head_node,
    fund_head_synthesis_node,
)
from agents.wing_workers import (
    quant_bull_worker_node,
    quant_bear_worker_node,
    fund_bull_worker_node,
    fund_bear_worker_node,
)
from agents.reviewer import reviewer_node

builder = StateGraph(TradingState)

# ── Register nodes ────────────────────────────────────────────────────────────
builder.add_node("manager",               manager_node)
builder.add_node("researcher",            researcher_node)

# Quantitative wing
builder.add_node("quant_head",            quant_head_node)
builder.add_node("quant_bull_worker",     quant_bull_worker_node)
builder.add_node("quant_bear_worker",     quant_bear_worker_node)
builder.add_node("quant_head_synthesis",  quant_head_synthesis_node)

# Fundamental wing
builder.add_node("fund_head",             fund_head_node)
builder.add_node("fund_bull_worker",      fund_bull_worker_node)
builder.add_node("fund_bear_worker",      fund_bear_worker_node)
builder.add_node("fund_head_synthesis",   fund_head_synthesis_node)

# Final
builder.add_node("manager_decision",      manager_decision_node)
builder.add_node("reviewer",              reviewer_node)

# ── Wire the graph ────────────────────────────────────────────────────────────

# Shared setup
builder.add_edge(START,        "manager")
builder.add_edge("manager",    "researcher")

# Fan-out: researcher → both wings in parallel
builder.add_edge("researcher", "quant_head")
builder.add_edge("researcher", "fund_head")

# Quantitative wing (sequential within the wing)
builder.add_edge("quant_head",           "quant_bull_worker")
builder.add_edge("quant_bull_worker",    "quant_bear_worker")
builder.add_edge("quant_bear_worker",    "quant_head_synthesis")

# Fundamental wing (sequential within the wing)
builder.add_edge("fund_head",            "fund_bull_worker")
builder.add_edge("fund_bull_worker",     "fund_bear_worker")
builder.add_edge("fund_bear_worker",     "fund_head_synthesis")

# Fan-in: both wing syntheses → manager_decision
builder.add_edge("quant_head_synthesis", "manager_decision")
builder.add_edge("fund_head_synthesis",  "manager_decision")

builder.add_edge("manager_decision",     "reviewer")


# ── Reviewer retry router ─────────────────────────────────────────────────────
def reviewer_router(state: TradingState):
    if "FAIL" in state.get("reviewer_feedback", "FAIL") and state.get("iteration_count", 0) < 3:
        return "manager"
    return END


builder.add_conditional_edges("reviewer", reviewer_router)

# ── Compile ───────────────────────────────────────────────────────────────────
trading_app = builder.compile()
