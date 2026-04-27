from langgraph.graph import StateGraph, START, END
from core.state import TradingState
from agents.llm_factory import get_llm
from tools.sandbox import run_sandbox_code
from tools.file_tools import tool_cat, tool_grep, tool_ls, tool_sed_replace
from agents.utils import load_prompt
import sqlite3
import time
import json
import os


def debug_print(msg: str, verbose: bool):
    if verbose:
        print(msg)


def calculate_indicator(ticker, indicator_name, db_path):
    """Directly calculate an indicator without agent complexity."""
    try:
        conn = sqlite3.connect(db_path)
        conn.row_factory = sqlite3.Row
        cursor = conn.cursor()

        # Get recent data
        cursor.execute(
            "SELECT date, open, high, low, close, volume FROM ohlcv WHERE symbol = ? ORDER BY date DESC LIMIT 200",
            (ticker,),
        )
        rows = cursor.fetchall()
        conn.close()

        if not rows:
            return {"error": f"No data for {ticker}"}

        import pandas as pd
        import numpy as np

        df = pd.DataFrame(
            rows, columns=["date", "open", "high", "low", "close", "volume"]
        )
        close = df["close"]
        high = df["high"]
        low = df["low"]
        volume = df["volume"]

        results = {
            "ticker": ticker,
            "date": str(df.iloc[0]["date"]),
            "close": round(df.iloc[0]["close"], 4),
        }

        indicator_name = indicator_name.upper().strip()

        # Parse multiple indicators (split by newlines or commas)
        indicators = [i.strip() for i in indicator_name.replace("\n", ",").split(",")]

        for ind in indicators:
            ind = ind.strip()
            if not ind:
                continue

            try:
                if "MACD" in ind:
                    exp1 = close.ewm(span=12, adjust=False).mean()
                    exp2 = close.ewm(span=26, adjust=False).mean()
                    macd = exp1 - exp2
                    signal = macd.ewm(span=9, adjust=False).mean()
                    histogram = macd - signal
                    results["macd"] = {
                        "line": round(macd.iloc[0], 4),
                        "signal_line": round(signal.iloc[0], 4),
                        "histogram": round(histogram.iloc[0], 4),
                        "direction": "BULLISH" if histogram.iloc[0] > 0 else "BEARISH",
                    }

                elif "EMA" in ind:
                    # Parse EMA periods: EMA(50) -> 50
                    period = 50
                    if "(" in ind and ")" in ind:
                        period = int(ind.split("(")[1].split(")")[0])
                    ema = close.ewm(span=period, adjust=False).mean()
                    results[f"ema_{period}"] = round(ema.iloc[0], 4)

                elif "ATR" in ind:
                    period = 14
                    if "(" in ind and ")" in ind:
                        period = int(ind.split("(")[1].split(")")[0])
                    high_low = high - low
                    high_close = abs(high - close.shift())
                    low_close = abs(low - close.shift())
                    tr = pd.concat([high_low, high_close, low_close], axis=1).max(
                        axis=1
                    )
                    atr = tr.ewm(span=period, adjust=False).mean()
                    results["atr"] = round(atr.iloc[0], 4)

                elif "RSI" in ind:
                    period = 14
                    if "(" in ind and ")" in ind:
                        period = int(ind.split("(")[1].split(")")[0])
                    delta = close.diff()
                    gain = (delta.where(delta > 0, 0)).rolling(window=period).mean()
                    loss = (-delta.where(delta < 0, 0)).rolling(window=period).mean()
                    rs = gain / loss
                    rsi = 100 - (100 / (1 + rs))
                    results["rsi"] = round(rsi.iloc[0], 2)

                elif "SMA" in ind or "MA" in ind:
                    period = 20
                    if "(" in ind and ")" in ind:
                        period = int(ind.split("(")[1].split(")")[0])
                    sma = close.rolling(window=period).mean()
                    results[f"sma_{period}"] = round(sma.iloc[0], 4)

                elif "BB" in ind or "BOLLINGER" in ind:
                    period = 20
                    std_mult = 2
                    if "(" in ind and ")" in ind:
                        parts = ind.split("(")[1].split(")")[0].split(",")
                        period = int(parts[0])
                        if len(parts) > 1:
                            std_mult = float(parts[1])
                    sma = close.rolling(window=period).mean()
                    std = close.rolling(window=period).std()
                    upper = sma + (std * std_mult)
                    lower = sma - (std * std_mult)
                    results["bollinger"] = {
                        "upper": round(upper.iloc[0], 4),
                        "middle": round(sma.iloc[0], 4),
                        "lower": round(lower.iloc[0], 4),
                        "position": "MIDDLE"
                        if sma.iloc[0] < close.iloc[0] < upper.iloc[0]
                        else "ABOVE_UPPER"
                        if close.iloc[0] > upper.iloc[0]
                        else "BELOW_LOWER"
                        if close.iloc[0] < lower.iloc[0]
                        else "MIDDLE",
                    }

                elif "VOLUME" in ind:
                    avg_vol = volume.rolling(window=20).mean()
                    results["volume"] = {
                        "current": int(volume.iloc[0]),
                        "avg_20d": int(avg_vol.iloc[0]),
                        "ratio": round(volume.iloc[0] / avg_vol.iloc[0], 2),
                    }

                else:
                    results[ind] = {"calculated": True}

            except Exception as e:
                results[ind] = {"error": str(e)}

        return results

    except Exception as e:
        return {"error": str(e)}


def coder_node(state: TradingState):
    """Generates Python code based on quant strategy, then executes it."""
    verbose = state.get("verbose", False)
    loop_count = state.get("coder_loop_count", 0)
    start_time = time.time()

    print("\n" + "=" * 50)
    print("📋 CODER NODE STARTING")
    print(f"   Ticker: {state.get('ticker', 'None')}")
    print(f"   Iteration: {state.get('iteration_count', 0)}")
    print(f"   Coder Loop: {loop_count + 1}")
    print("=" * 50)

    ticker = state.get("ticker")
    quant_strategy = state.get("indicator_requested", "")
    db_path = state.get("db_path", "data/US_DB.db")

    if not quant_strategy or quant_strategy.strip() == "":
        raise ValueError("No indicator request from Quant node - cannot proceed")

    # LLM writes code based on quant strategy
    llm = get_llm()
    code_instruction = (
        f"Write Python code to calculate these indicators for {ticker}:\n"
        f"{quant_strategy}\n\n"
        "Database: data/US_DB.db, table: ohlcv, columns: symbol,date,open,high,low,close,volume\n"
        "Query ohlcv table using column 'symbol' (not 'ticker').\n"
        "Calculate the requested indicators.\n"
        "Print JSON output with all indicator values.\n"
        "Include if __name__ == '__main__' block.\n"
    )

    debug_print(f"📝 Asking LLM to write code...", verbose)
    response = llm.invoke(code_instruction)
    generated_code = response.content if response.content else ""

    # Clean up code blocks
    if "```python" in generated_code:
        generated_code = generated_code.split("```python")[1].split("```")[0]
    elif "```" in generated_code:
        generated_code = generated_code.split("```")[1].split("```")[0]

    if not generated_code.strip():
        raise ValueError("LLM returned empty code - cannot generate indicators")

    debug_print(f"📨 Generated code preview: {generated_code[:300]}...", verbose)

    # Execute the code in sandbox - with retry on errors
    print(f"🔢 Executing generated code...")
    max_retries = 2
    last_error = None

    for attempt in range(max_retries):
        try:
            result = run_sandbox_code(generated_code, ticker, db_path)
            debug_print(f"📨 Execution result: {result[:500]}...", verbose)
            break
        except (ValueError, SyntaxError) as e:
            # Syntax error - try to fix
            last_error = str(e)
            if attempt < max_retries - 1:
                fix_prompt = (
                    f"Fix this Python code syntax error:\n{last_error}\n\n"
                    f"Current code:\n{generated_code}\n\n"
                    "Return only the fixed code, no explanations."
                )
                debug_print(
                    f"📝 Fixing syntax error (attempt {attempt + 1})...", verbose
                )
                fix_response = llm.invoke(fix_prompt)
                generated_code = (
                    fix_response.content if fix_response.content else generated_code
                )
                if "```python" in generated_code:
                    generated_code = generated_code.split("```python")[1].split("```")[
                        0
                    ]
                elif "```" in generated_code:
                    generated_code = generated_code.split("```")[1].split("```")[0]
            else:
                raise ValueError(
                    f"Code syntax errors after {max_retries} attempts: {last_error}"
                )
        except RuntimeError as e:
            # Runtime error - try to fix
            last_error = str(e)
            if attempt < max_retries - 1:
                fix_prompt = (
                    f"Fix this Python code runtime error:\n{last_error}\n\n"
                    f"Current code:\n{generated_code}\n\n"
                    f"Database: data/US_DB.db, table: ohlcv, columns: date,open,high,low,close,volume\n"
                    "Return only the fixed code with no comments."
                )
                debug_print(
                    f"📝 Fixing runtime error (attempt {attempt + 1})...", verbose
                )
                fix_response = llm.invoke(fix_prompt)
                generated_code = (
                    fix_response.content if fix_response.content else generated_code
                )
                if "```python" in generated_code:
                    generated_code = generated_code.split("```python")[1].split("```")[
                        0
                    ]
                elif "```" in generated_code:
                    generated_code = generated_code.split("```")[1].split("```")[0]
            else:
                # Fall back to built-in calculator instead of failing
                debug_print(f"⚠️ Code failed after retries, using fallback...", verbose)
                result = calculate_indicator(ticker, quant_strategy, db_path)
                result = json.dumps({"fallback": True, "data": result})
        except Exception as e:
            raise

    print("✅ CODER NODE COMPLETE")

    elapsed = time.time() - start_time
    node_outputs = state.get("node_outputs", {})
    node_outputs["coder"] = {
        "llm_output": generated_code,
        "execution_result": str(result),
        "model_used": llm.llm.model if hasattr(llm, "llm") else "unknown",
    }
    node_timestamps = state.get("node_timestamps", {})
    node_timestamps["coder"] = elapsed

    # Save generated code to indicators folder (relative path)
    try:
        indicators_dir = "indicators"
        os.makedirs(indicators_dir, exist_ok=True)

        # Extract indicator name from quant strategy
        indicator_name = "indicator"
        if quant_strategy:
            first_ind = (
                quant_strategy.split(",")[0].strip().split("(")[0].strip().lower()
            )
            if first_ind:
                indicator_name = first_ind.replace(" ", "_")

        indicator_file = os.path.join(indicators_dir, f"{indicator_name}.py")
        with open(indicator_file, "w") as f:
            f.write(generated_code)
        print(f"💾 Saved indicator to {indicator_file}")
    except Exception as save_err:
        print(f"⚠️ Could not save indicator: {save_err}")

    return {
        "draft_code": generated_code,
        "coder_output": {"sandbox_results": str(result)},
        "coder_loop_count": loop_count + 1,
        "node_outputs": node_outputs,
        "node_timestamps": node_timestamps,
    }


def code_reviewer_node(state: TradingState):
    """Critiques the draft code and sandbox test outputs."""
    verbose = state.get("verbose", False)
    loop_count = state.get("coder_loop_count", 0)
    start_time = time.time()

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

    elapsed = time.time() - start_time
    node_outputs = state.get("node_outputs", {})
    node_outputs["code_reviewer"] = {
        "llm_output": response.content,
        "model_used": llm.llm.model if hasattr(llm, "llm") else "unknown",
    }
    node_timestamps = state.get("node_timestamps", {})
    node_timestamps["code_reviewer"] = elapsed

    return {
        "code_approved": approved,
        "code_review_feedback": response.content,
        "node_outputs": node_outputs,
        "node_timestamps": node_timestamps,
    }


def coder_router(state: TradingState):
    """Routes back to the Coder if the Reviewer fails the code."""
    loop_count = state.get("coder_loop_count", 0)
    if state.get("code_approved"):
        return END
    if loop_count >= 3:
        print("⚠️ Coder loop limit reached (3), proceeding...")
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
