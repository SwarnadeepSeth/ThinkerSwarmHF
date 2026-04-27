import operator
from typing import TypedDict, Dict, Any, Annotated


class TradingState(TypedDict):
    # Base Request Context
    ticker: str
    db_path: str
    verbose: bool
    market_context: str

    # --- Coder & Reviewer Sub-Graph State ---
    indicator_requested: str
    draft_code: str
    test_results: str
    code_review_feedback: str
    code_approved: bool
    coder_loop_count: int

    # --- Analysis State ---
    quant_strategy: str
    coder_output: Dict[str, Any]
    technical_analysis: Dict[str, Any]
    fundamental_analysis: Dict[str, Any]

    # --- Review & Routing ---
    reviewer_feedback: str
    # Annotated with operator.add allows nodes to increment the count safely
    iteration_count: Annotated[int, operator.add]

    # Final Output Schema
    final_decision: Dict[str, Any]

    # Execution tracking for out.json
    execution_start_time: float
    node_timestamps: Dict[str, float]
    node_outputs: Dict[str, Any]
