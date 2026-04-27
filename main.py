import argparse
import json
import os
import time
from dotenv import load_dotenv
from docx import Document
from docx.shared import Inches, Pt
from docx.enum.text import WD_ALIGN_PARAGRAPH

# Load environment variables (NVIDIA_API_KEY)
load_dotenv()

# Import the compiled LangGraph application
from core.graph import trading_app


def print_header(title: str, verbose: bool = False):
    print(f"\n{'=' * 50}\n{title}\n{'=' * 50}")
    if verbose:
        print("[VERBOSE MODE ENABLED]")


def generate_docx_report(ticker: str, out_data: dict, decision: dict):
    """Generate a DOCX report from the analysis results."""
    doc = Document()

    # Title
    title = doc.add_heading(f"Trading Analysis Report: {ticker}", 0)
    title.alignment = WD_ALIGN_PARAGRAPH.CENTER

    # Date
    doc.add_paragraph(f"Generated: {time.strftime('%Y-%m-%d %H:%M:%S')}")
    doc.add_paragraph(f"Execution Time: {out_data.get('execution_time_ms', 0):.2f} ms")
    if out_data.get("error"):
        doc.add_paragraph(f"Error: {out_data.get('error')}")
    doc.add_paragraph()

    # Executive Summary / Final Decision
    doc.add_heading("Executive Summary", level=1)
    if decision:
        doc.add_paragraph(
            f"Direction: {decision.get('direction', 'N/A')}", style="Intense Quote"
        )
        doc.add_paragraph(f"Entry Price: ${decision.get('entry_price', 0)}")
        doc.add_paragraph(f"Stop Loss: ${decision.get('stoploss', 0)}")
        doc.add_paragraph(f"Target: ${decision.get('target', 0)}")
        doc.add_paragraph(f"Risk/Volatility: {decision.get('risk_volatility', 'N/A')}")
        doc.add_paragraph(f"Timeframe: {decision.get('timeframe', 'N/A')}")
        doc.add_paragraph(f"Reasoning: {decision.get('reasoning', '')}")
    else:
        doc.add_paragraph("No decision generated.")

    doc.add_paragraph()

    # Analysis Steps
    doc.add_heading("Analysis Steps", level=1)

    for step in out_data.get("steps", []):
        node_name = step.get("node", "unknown")
        timestamp = step.get("timestamp", 0)
        model = step.get("model_used", "unknown")
        output = step.get("llm_output", "")

        # Truncate long outputs
        if isinstance(output, str) and len(output) > 1500:
            output = output[:1500] + "..."

        doc.add_heading(f"{node_name.upper()} (timestamp: {timestamp:.2f}s)", level=2)
        doc.add_paragraph(f"Model: {model}")

        if isinstance(output, dict):
            for k, v in output.items():
                doc.add_paragraph(f"{k}: {v}")
        else:
            doc.add_paragraph(output)

        doc.add_paragraph()

    # Technical Details
    doc.add_heading("Nodes Executed", level=1)
    nodes = out_data.get("nodes_executed", [])
    for node in nodes:
        doc.add_paragraph(f"• {node}")

    doc.add_paragraph()

    # Save
    filename = f"{ticker}_analysis_report.docx"
    doc.save(filename)
    print(f"📄 DOCX report saved to {filename}")


def main():
    parser = argparse.ArgumentParser(
        description="Autonomous AI Trading Agent Framework"
    )
    parser.add_argument(
        "--ticker", type=str, required=True, help="Stock ticker to analyze (e.g., AAPL)"
    )
    parser.add_argument(
        "--db", type=str, default="data/US_DB.db", help="Path to your SQLite database"
    )
    parser.add_argument(
        "-v", "--verbose", action="store_true", help="Enable verbose debug output"
    )

    args = parser.parse_args()

    # 1. Validate the database exists
    if not os.path.exists(args.db):
        print(f"❌ Error: Database file not found at '{args.db}'")
        print("Please ensure your 'US_DB.db' is placed inside the 'data/' folder.")
        return

    print_header(f"🚀 Initializing Framework for {args.ticker.upper()}", args.verbose)
    print(f"🔌 Connected to database: {args.db}")
    if args.verbose:
        print(f"📋 Verbose mode: ENABLED")
    print(
        "🧠 Agents are starting their analysis... (This may take a few minutes if new indicators are being coded)"
    )

    # 2. Initialize the Shared State
    execution_start = time.time()
    initial_state = {
        "ticker": args.ticker.upper(),
        "db_path": args.db,
        "verbose": args.verbose,
        "iteration_count": 0,
        "coder_loop_count": 0,
        "market_context": "",
        "indicator_requested": "",
        "draft_code": "",
        "test_results": "",
        "code_review_feedback": "",
        "code_approved": False,
        "quant_strategy": "",
        "coder_output": {},
        "technical_analysis": {},
        "fundamental_analysis": {},
        "reviewer_feedback": "",
        "final_decision": {},
        "execution_start_time": execution_start,
        "node_timestamps": {},
        "node_outputs": {},
    }

    # 3. Execute the Graph
    error_msg = None
    try:
        final_state = trading_app.invoke(initial_state)

        print_header("🏁 FINAL TRADE SETUP APPROVED", args.verbose)

        decision = final_state.get("final_decision", {})
        if decision:
            print(json.dumps(decision, indent=4))
        else:
            print("❌ Framework completed, but no final decision was generated.")
            print("Reviewer Feedback:", final_state.get("reviewer_feedback"))

    except Exception as e:
        print_header("⚠️ EXECUTION FAILED", args.verbose)
        print(f"An error occurred during agent routing: {str(e)}")
        error_msg = str(e)
        final_state = {}

    # 4. Save output to out.json
    execution_total_time = time.time() - execution_start
    node_timestamps = final_state.get("node_timestamps", {}) if final_state else {}
    node_outputs = final_state.get("node_outputs", {}) if final_state else {}

    steps = []
    for node_name, output_data in node_outputs.items():
        step_entry = {
            "node": node_name,
            "timestamp": node_timestamps.get(node_name, 0),
            "llm_output": output_data.get("llm_output", ""),
            "execution_result": output_data.get("execution_result", ""),
            "model_used": output_data.get("model_used", "unknown"),
        }
        steps.append(step_entry)

    decision = final_state.get("final_decision", {}) if final_state else {}

    out_data = {
        "ticker": args.ticker.upper(),
        "execution_time_ms": round(execution_total_time * 1000, 2),
        "nodes_executed": list(node_outputs.keys()),
        "steps": steps,
        "final_decision": decision,
        "error": error_msg if error_msg else None,
    }

    with open("out.json", "w") as f:
        json.dump(out_data, f, indent=2)

    print(f"\n💾 Output saved to out.json")

    # 5. Generate DOCX report
    generate_docx_report(args.ticker.upper(), out_data, decision)


if __name__ == "__main__":
    main()
