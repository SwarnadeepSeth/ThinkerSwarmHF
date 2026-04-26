# Open-Source AI Agent Trading Framework

A highly modular, multi-agent trading analysis framework powered by LangGraph and NVIDIA NIM (Llama 3/Mixtral). This system utilizes a hierarchy of specialized AI agents to analyze stock data, generate and test quantitative indicators in a secure sandbox, and debate fundamental and technical setups to output strict, risk-managed JSON trade setups.

---

## 🏗️ Architecture & Code Graph

The framework operates as a directed cyclic graph (LangGraph). The Manager routes tasks, Specialists generate data, the Coder writes and tests Python indicators safely, and the Reviewer enforces strict risk management.

```text
ai_trading_framework/
├── data/
│   └── market_data.sqlite          # 5-year 1D SQLite database
├── prompts/                        # Decoupled system instructions
│   ├── manager.txt, reviewer.txt
│   ├── heads/                      # technical_head.txt, fundamental_head.txt
│   └── specialists/                # bull, bear, researcher, quant, coder, code_reviewer
├── agents/                         # Node logic
│   ├── manager.py, heads.py, specialists.py, reviewer.py
│   ├── coder_subgraph.py           # Self-improving code generation loop
│   └── llm_factory.py              # NVIDIA NIM connection
├── tools/                          
│   ├── sqlite_tools.py, file_tools.py
│   └── sandbox.py                  # Secure Python REPL (Restricted execution)
├── indicators/                     # Auto-expanding library of AI-generated math
├── library/                        # PDFs, JSONs, text files for the Researcher
├── core/                           # LangGraph orchestration (state.py, graph.py)
└── main.py                         # Entry point
The Execution Flow
[Start] Data loaded (SQLite) -> Ticker passed to Manager.

[Routing] Manager delegates to Technical Head & Fundamental Head simultaneously.

[The Engine Room] * Researcher parses /library for macro data using CLI tools.

Quant designs a mathematical strategy.

Coder Loop: Coder writes indicator code -> executes in Sandbox -> Code Reviewer audits. Loops until tests pass, then saves to /indicators.

[Debate] Bull and Bear agents argue the setup using hard data from the Coder and Researcher.

[Synthesis] Heads synthesize arguments into concise reports.

[Review] Reviewer checks risk/reward. If failed, routes back to Manager. If passed, outputs strict JSON.

⚙️ Detailed Workflow
1. Data Ingestion & Context
The framework does not feed raw database dumps into the LLM context window. Instead, it passes a SQLite connection and file system tools. Agents query exactly what they need, drastically reducing token costs and hallucination risks.

2. The Self-Improving Coder Sandbox
When the Quant requests an indicator (e.g., MACD), the Coder checks if it exists. If not, it writes pandas/numpy code and a unit test. This code runs in a highly restricted sandbox that strips __builtins__ to prevent malicious OS execution. The Code Reviewer verifies the test output before passing the math back to the Quant.

3. File System Emulation
Agents use custom LangChain tools that emulate CLI commands (grep, cat, ls, sed). This allows them to quickly search large codebases or PDF libraries without loading massive files into memory.

🚀 How to Install and Run
Prerequisites
Python 3.10+

An NVIDIA API Key (Free tier available at build.nvidia.com)

Your own SQLite database with stock data

1. Clone & Install
Clone the repository and install the required dependencies:

Bash
git clone [https://github.com/yourusername/ai_trading_framework.git](https://github.com/yourusername/ai_trading_framework.git)
cd ai_trading_framework
pip install -r requirements.txt
2. Environment Setup
Create a .env file in the root directory and add your NVIDIA API key:

Bash
echo "NVIDIA_API_KEY=nvapi-your-key-goes-here" > .env
3. Prepare Your Data
Place your SQLite database in the /data folder and name it market_data.sqlite (or update config/settings.py).

(Optional) Populate the /library/papers and /library/earnings folders with PDFs or text files for the Researcher agent to read.

4. Run the Framework
You can execute the framework by running main.py and passing a ticker.

Bash
python main.py --ticker TSLA
Note: The first run may take longer if the Coder needs to write and test foundational indicators. Subsequent runs will be faster as the /indicators directory populates.


---

### `requirements.txt`

```text
# LangChain Core and Graph Orchestration
langchain>=0.1.0
langchain-core>=0.1.52
langgraph>=0.0.30

# NVIDIA Integration
langchain-nvidia-ai-endpoints>=0.0.8

# Data Manipulation & Math (Used by the Coder Agent)
pandas>=2.0.0
numpy>=1.24.0

# Structured Output
pydantic>=2.0.0

# Environment Management
python-dotenv>=1.0.0

# Optional: Required if you are implementing the pdfgrep tool
# Note: You must also install 'pdfgrep' on your host OS (e.g., sudo apt-get install pdfgrep)
# pdfminer.six>=20221105 
