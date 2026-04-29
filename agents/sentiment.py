import time

from agents.llm_factory import get_llm
from agents.utils import load_prompt
from agents.print_utils import node_banner, dispatch_banner, node_complete
from core.state import TradingState
from tools.sentiment_tools import build_sentiment_context


def sentiment_node(state: TradingState):
    """Build a sentiment brief from local sentiment.db and live headlines."""
    start_time = time.time()
    ticker = state["ticker"]
    iteration = state.get("iteration_count", 0)

    node_banner("Sentiment Wing", ticker=ticker, iteration=iteration, emoji="🧠")
    print("  Building sentiment context from local db + live news…")

    sentiment_context = build_sentiment_context(ticker)

    llm = get_llm()
    system_prompt = load_prompt("specialists/sentiment")
    instruction = (
        f"{system_prompt}\n\n"
        f"Ticker: {ticker}\n"
        f"Sentiment Context:\n{sentiment_context}\n\n"
        "Summarize the market tone, the dominant narratives, and the key bullish and bearish"
        " sentiment drivers. Separate database-backed evidence from live-news inference."
    )

    response = llm.invoke(instruction)
    elapsed = time.time() - start_time

    print(f"\n  Sentiment Preview:")
    for line in response.content.strip().splitlines()[:4]:
        print(f"    {line.strip()[:90]}")

    dispatch_banner(
        "Sentiment ready — handing off to analytical wings",
        [
            ("📊 QUANTITATIVE WING", "→ quant_head"),
            ("💼 FUNDAMENTAL WING", "→ fund_head"),
        ],
    )

    node_outputs = state.get("node_outputs", {})
    node_outputs["sentiment"] = {
        "llm_output": response.content,
        "model_used": llm.llm.model if hasattr(llm, "llm") else "unknown",
    }
    node_timestamps = state.get("node_timestamps", {})
    node_timestamps["sentiment"] = elapsed
    node_complete("Sentiment Wing", elapsed)

    return {
        "sentiment_context": response.content,
        "sentiment_analysis": {
            "sentiment_context": response.content,
            "raw_sentiment_context": sentiment_context,
        },
        "node_outputs": node_outputs,
        "node_timestamps": node_timestamps,
    }
