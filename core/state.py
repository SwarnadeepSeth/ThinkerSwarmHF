import operator
from typing import TypedDict, Dict, Any, Annotated


def _merge_dicts(a: dict, b: dict) -> dict:
    """Merge two dicts; used as a LangGraph reducer for parallel branches."""
    return {**(a or {}), **(b or {})}


class TradingState(TypedDict):
    # ── Base Request Context ───────────────────────────────────────────────────
    ticker: str
    db_path: str
    financial_db_path: str
    verbose: bool
    allow_research_web: bool
    market_context: str
    manager_brief: str

    # ── Shared Researcher Context ──────────────────────────────────────────────
    researcher_context: str

    # ── Quantitative Wing ──────────────────────────────────────────────────────
    quant_bull_findings: str
    quant_bear_findings: str
    quant_wing_report: str          # final Technical Report from quant_head_synthesis

    # ── Fundamental Wing ──────────────────────────────────────────────────────
    fund_bull_findings: str
    fund_bear_findings: str
    fund_wing_report: str           # final Fundamental Report from fund_head_synthesis

    # ── Coder Sub-Graph State (kept for optional coder_loop fallback) ──────────
    indicator_requested: str
    draft_code: str
    test_results: str
    code_review_feedback: str
    code_approved: bool
    coder_loop_count: int

    # ── Tool Results ───────────────────────────────────────────────────────────
    quant_used_tools: bool
    quant_strategy: str
    coder_output: Dict[str, Any]    # populated by quant workers / coder fallback

    # ── Legacy analysis dicts (used by reviewer) ──────────────────────────────
    # Annotated with _merge_dicts so parallel wing updates don't overwrite each other
    technical_analysis:   Annotated[Dict[str, Any], _merge_dicts]
    fundamental_analysis: Annotated[Dict[str, Any], _merge_dicts]

    # ── Review & Routing ──────────────────────────────────────────────────────
    reviewer_feedback: str
    iteration_count: Annotated[int, operator.add]

    # ── Final Output ──────────────────────────────────────────────────────────
    final_decision: Dict[str, Any]

    # ── Execution Tracking ────────────────────────────────────────────────────
    execution_start_time: float
    # Merge reducers so parallel nodes don't clobber each other's entries
    node_timestamps: Annotated[Dict[str, float], _merge_dicts]
    node_outputs:    Annotated[Dict[str, Any],   _merge_dicts]
