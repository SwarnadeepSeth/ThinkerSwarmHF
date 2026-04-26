import argparse
import json
import os
from dotenv import load_dotenv

# Load environment variables (NVIDIA_API_KEY)
load_dotenv()

# Import the compiled LangGraph application
from core.graph import trading_app


def print_header(title: str, verbose: bool = False):
    print(f"\n{'=' * 50}\n{title}\n{'=' * 50}")
    if verbose:
        print("[VERBOSE MODE ENABLED]")


def main():
    parser = argparse.ArgumentParser(
        description="Autonomous AI Trading Agent Framework"
    )
    parser.add_argument(
        "--ticker", type=str, required=True, help="Stock ticker to analyze (e.g., AAPL)"
    )
    # Defaulting the database argument to your specific file
    parser.add_argument(
        "--db", type=str, default="data/US_DB.db", help="Path to your SQLite database"
    )
    parser.add_argument(
        "-v", "--verbose", action="store_true", help="Enable verbose debug output"
    )

    args = parser.parse_args()

    # 1. Validate the database exists before burning LLM tokens
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
    # This seeds the LangGraph memory with your requested ticker and database
    initial_state = {
        "ticker": args.ticker.upper(),
        "db_path": args.db,
        "verbose": args.verbose,
        "iteration_count": 0,
        "coder_loop_count": 0,
        # Initialize empty defaults for dictionary safety down the pipeline
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
    }

    # 3. Execute the Graph
    try:
        # .invoke() runs the state through the nodes until it hits END
        final_state = trading_app.invoke(initial_state)

        print_header("🏁 FINAL TRADE SETUP APPROVED", args.verbose)

        # 4. Extract and print the final structured JSON from the Reviewer
        decision = final_state.get("final_decision", {})
        if decision:
            print(json.dumps(decision, indent=4))
        else:
            print("❌ Framework completed, but no final decision was generated.")
            print("Reviewer Feedback:", final_state.get("reviewer_feedback"))

    except Exception as e:
        print_header("⚠️ EXECUTION FAILED", args.verbose)
        print(f"An error occurred during agent routing: {str(e)}")


if __name__ == "__main__":
    main()
