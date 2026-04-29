import argparse
import json
import os
import re
import time
from dotenv import load_dotenv
from docx import Document
from docx.oxml import OxmlElement
from docx.oxml.ns import qn
from docx.shared import Inches, Pt, RGBColor
from docx.enum.text import WD_ALIGN_PARAGRAPH
from agents.print_utils import render_kv_table
from tools.financial_db import set_financial_db_path, resolve_financial_db_path

# Load environment variables (NVIDIA_API_KEY)
load_dotenv()

# Import the compiled LangGraph application
from core.graph import trading_app


def print_header(title: str, verbose: bool = False):
    width = max(60, len(title) + 8)
    print()
    print("╔" + "═" * (width - 2) + "╗")
    print(f"║ {title:<{width - 4}} ║")
    print("╚" + "═" * (width - 2) + "╝")
    if verbose:
        print("[VERBOSE MODE ENABLED]")


def _clean_text(value) -> str:
    return re.sub(r"\s+", " ", str(value)).strip()


def _extract_report_sections(report_text: str, section_names: list[str], max_chars: int = 140):
    sections = []
    for section_name in section_names:
        pattern = re.compile(
            rf"##\s+{re.escape(section_name)}[^\n]*\n(.*?)(?=\n##|\Z)",
            re.IGNORECASE | re.DOTALL,
        )
        match = pattern.search(report_text or "")
        if not match:
            continue
        text = _clean_text(match.group(1))
        sections.append((section_name, text[:max_chars]))
    return sections


def _extract_tool_rows(tool_results):
    rows = []
    if isinstance(tool_results, dict):
        for tool_name, result in tool_results.items():
            value = result if isinstance(result, str) else json.dumps(result, ensure_ascii=False)
            value = _clean_text(value)
            if len(value) > 220:
                value = value[:220] + "…"
            rows.append([tool_name, value])
    return rows


def _collect_tool_summary_rows(node_outputs: dict) -> list[list[str]]:
    rows = []
    if not isinstance(node_outputs, dict):
        return rows
    for node_name, payload in node_outputs.items():
        tool_results = payload.get("tool_results", {}) if isinstance(payload, dict) else {}
        if not isinstance(tool_results, dict) or not tool_results:
            continue
        tool_names = ", ".join(tool_results.keys())
        rows.append([node_name, tool_names, str(len(tool_results))])
    return rows


def _split_lines(text: str) -> list[str]:
    return [line.rstrip() for line in str(text or "").splitlines()]


def _add_verbatim_section(doc, title: str, text: str):
    doc.add_heading(title, level=1)
    content = str(text or "").strip()
    if not content:
        doc.add_paragraph("No data available.")
        return
    for line in _split_lines(content):
        paragraph = doc.add_paragraph()
        paragraph.paragraph_format.space_after = Pt(0)
        run = paragraph.add_run(line)
        run.font.size = Pt(8)
        run.font.name = "Courier New"


def _md_escape(value) -> str:
    text = _clean_text(value)
    return text.replace("|", "\\|").replace("\n", " ")


def _md_table(headers: list[str], rows: list[list[str]]) -> str:
    safe_headers = [_md_escape(h) for h in headers]
    lines = [
        "| " + " | ".join(safe_headers) + " |",
        "| " + " | ".join(["---"] * len(safe_headers)) + " |",
    ]
    for row in rows:
        safe_row = [_md_escape(cell) for cell in row]
        if len(safe_row) < len(safe_headers):
            safe_row.extend([""] * (len(safe_headers) - len(safe_row)))
        lines.append("| " + " | ".join(safe_row[: len(safe_headers)]) + " |")
    return "\n".join(lines)


def _truncate_for_md(value, max_chars: int = 220) -> str:
    text = _clean_text(value)
    if len(text) > max_chars:
        return text[:max_chars] + "…"
    return text


def _set_cell_shading(cell, fill: str):
    tc_pr = cell._tc.get_or_add_tcPr()
    shd = OxmlElement("w:shd")
    shd.set(qn("w:fill"), fill)
    tc_pr.append(shd)


def _set_cell_text(cell, text, bold: bool = False, size: int = 9):
    cell.text = ""
    paragraph = cell.paragraphs[0]
    paragraph.paragraph_format.space_after = Pt(0)
    run = paragraph.add_run(str(text))
    run.bold = bold
    run.font.size = Pt(size)


def _style_table(table, widths=None):
    table.style = "Table Grid"
    table.autofit = False
    if widths:
        for idx, width in enumerate(widths):
            table.columns[idx].width = Inches(width)


def add_table_section(doc, title: str, headers: list[str], rows: list[list[str]], widths=None):
    doc.add_heading(title, level=1)
    if not rows:
        doc.add_paragraph("No data available.")
        return

    table = doc.add_table(rows=1, cols=len(headers))
    _style_table(table, widths)
    header_row = table.rows[0].cells
    for idx, header in enumerate(headers):
        _set_cell_text(header_row[idx], header, bold=True, size=10)
        _set_cell_shading(header_row[idx], "1F4E79")
        for paragraph in header_row[idx].paragraphs:
            for run in paragraph.runs:
                run.font.color.rgb = RGBColor(255, 255, 255)

    for row in rows:
        cells = table.add_row().cells
        padded = list(row) + [""] * max(0, len(headers) - len(row))
        for idx, value in enumerate(padded[: len(headers)]):
            _set_cell_text(cells[idx], value)

    doc.add_paragraph()


def generate_docx_report(ticker: str, out_data: dict, decision: dict):
    """Generate a DOCX report from the analysis results."""
    doc = Document()

    for section in doc.sections:
        section.top_margin = Inches(0.55)
        section.bottom_margin = Inches(0.55)
        section.left_margin = Inches(0.7)
        section.right_margin = Inches(0.7)

    # Title
    title = doc.add_heading(f"Trading Analysis Report: {ticker}", 0)
    title.alignment = WD_ALIGN_PARAGRAPH.CENTER

    meta_rows = [
        ["Generated", time.strftime("%Y-%m-%d %H:%M:%S")],
        ["Execution Time", f"{out_data.get('execution_time_ms', 0):.2f} ms"],
        ["Ticker", ticker],
        ["Nodes Executed", ", ".join(out_data.get("nodes_executed", [])) or "None"],
        ["Status", "ERROR" if out_data.get("error") else "SUCCESS"],
    ]
    if out_data.get("error"):
        meta_rows.append(["Error", out_data.get("error")])
    add_table_section(doc, "Run Metadata", ["Field", "Value"], meta_rows, widths=[1.7, 4.9])

    # Executive Summary / Final Decision
    if decision:
        entry = float(decision.get("entry_price", 0) or 0)
        stop = float(decision.get("stoploss", 0) or 0)
        target = float(decision.get("target", 0) or 0)
        rr = ""
        if entry and stop and target:
            risk = abs(entry - stop)
            reward = abs(target - entry)
            if risk:
                rr = f"{reward / risk:.2f}x"

        decision_rows = [
            ["Direction", decision.get("direction", "N/A")],
            ["Entry", f"${entry:,.2f}" if entry else "N/A"],
            ["Stop", f"${stop:,.2f}" if stop else "N/A"],
            ["Target", f"${target:,.2f}" if target else "N/A"],
            ["Risk / Reward", rr or "N/A"],
            ["Volatility", decision.get("risk_volatility", "N/A")],
            ["Timeframe", decision.get("timeframe", "N/A")],
            ["Reasoning", decision.get("reasoning", "")],
        ]
        add_table_section(doc, "Final Trade Setup", ["Field", "Value"], decision_rows, widths=[1.7, 4.9])
    else:
        doc.add_paragraph("No decision generated.")

    tech_report = ""
    fund_report = ""
    for step in out_data.get("steps", []):
        if step.get("node") == "quant_head_synthesis":
            tech_report = step.get("llm_output", "") or ""
        elif step.get("node") == "fund_head_synthesis":
            fund_report = step.get("llm_output", "") or ""

    if tech_report:
        add_table_section(
            doc,
            "Technical Wing Highlights",
            ["Section", "Excerpt"],
            _extract_report_sections(
                tech_report,
                [
                    "Rationale",
                    "Bull Perspective",
                    "Bear Perspective",
                    "Risks",
                    "Opportunities",
                    "Priority",
                    "Recommended Stop Loss",
                    "Profit Target",
                    "Time Horizon",
                    "Overall Bias",
                ],
            ),
            widths=[2.2, 4.4],
        )

    if fund_report:
        add_table_section(
            doc,
            "Fundamental Wing Highlights",
            ["Section", "Excerpt"],
            _extract_report_sections(
                fund_report,
                [
                    "Rationale",
                    "Bull Perspective",
                    "Bear Perspective",
                    "Risks",
                    "Opportunities",
                    "Priority",
                    "Recommended Stop Loss",
                    "Profit Target",
                    "Time Horizon",
                    "Overall Bias",
                ],
            ),
            widths=[2.2, 4.4],
        )

    fundamental_analysis = out_data.get("fundamental_analysis", {}) or {}
    sector_peer_context = fundamental_analysis.get("sector_peer_context", "")
    internet_context = fundamental_analysis.get("internet_context", "")
    if sector_peer_context:
        _add_verbatim_section(doc, "Sector & Peer Comparative Context", sector_peer_context)
    if internet_context:
        _add_verbatim_section(doc, "Internet Search Context", internet_context)

    node_outputs = out_data.get("node_outputs", {}) or {}
    tool_sections = [
        ("Quantitative Bull Tool Stack", node_outputs.get("quant_bull_worker", {}).get("tool_results", {})),
        ("Quantitative Bear Tool Stack", node_outputs.get("quant_bear_worker", {}).get("tool_results", {})),
        ("Fundamental Bull Tool Stack", node_outputs.get("fund_bull_worker", {}).get("tool_results", {})),
        ("Fundamental Bear Tool Stack", node_outputs.get("fund_bear_worker", {}).get("tool_results", {})),
        ("Quant Core Tool Stack", node_outputs.get("quant", {}).get("tool_results", {})),
    ]

    for title, tool_results in tool_sections:
        rows = _extract_tool_rows(tool_results)
        if rows:
            add_table_section(doc, title, ["Tool", "Result"], rows, widths=[2.4, 4.2])

    # Analysis Steps
    doc.add_heading("Analysis Steps", level=1)
    step_rows = []
    for step in out_data.get("steps", []):
        output = step.get("llm_output", "")
        if isinstance(output, dict):
            output = json.dumps(output, ensure_ascii=False)
        output = _clean_text(output)
        if len(output) > 180:
            output = output[:180] + "…"
        step_rows.append(
            [
                step.get("node", "unknown"),
                step.get("model_used", "unknown"),
                f"{step.get('timestamp', 0):.2f}s",
                output,
            ]
        )
    add_table_section(
        doc,
        "Execution Steps",
        ["Node", "Model", "Duration", "Preview"],
        step_rows,
        widths=[1.25, 1.35, 0.75, 3.75],
    )

    # Append full wing reports verbatim for auditability
    doc.add_heading("Appendix - Full Technical Wing Report", level=1)
    if tech_report:
        doc.add_paragraph(tech_report)
    else:
        doc.add_paragraph("No technical wing report available.")

    doc.add_heading("Appendix - Full Fundamental Wing Report", level=1)
    if fund_report:
        doc.add_paragraph(fund_report)
    else:
        doc.add_paragraph("No fundamental wing report available.")

    tool_summary_rows = _collect_tool_summary_rows(node_outputs)
    if tool_summary_rows:
        add_table_section(
            doc,
            "Appendix - Tool Calls by Node",
            ["Node", "Tools Used", "Count"],
            tool_summary_rows,
            widths=[2.0, 4.0, 0.8],
        )

    # Save
    filename = f"{ticker}_analysis_report.docx"
    doc.save(filename)
    print(f"📄 DOCX report saved to {filename}")


def generate_markdown_report(ticker: str, out_data: dict, decision: dict):
    """Generate a Markdown report from the analysis results."""
    lines = [f"# Trading Analysis Report: {ticker}", ""]

    meta_rows = [
        ["Generated", time.strftime("%Y-%m-%d %H:%M:%S")],
        ["Execution Time", f"{out_data.get('execution_time_ms', 0):.2f} ms"],
        ["Ticker", ticker],
        ["Nodes Executed", ", ".join(out_data.get("nodes_executed", [])) or "None"],
        ["Status", "ERROR" if out_data.get("error") else "SUCCESS"],
    ]
    if out_data.get("error"):
        meta_rows.append(["Error", out_data.get("error")])
    lines.extend(["## Run Metadata", _md_table(["Field", "Value"], meta_rows), ""])

    if decision:
        entry = float(decision.get("entry_price", 0) or 0)
        stop = float(decision.get("stoploss", 0) or 0)
        target = float(decision.get("target", 0) or 0)
        rr = ""
        if entry and stop and target:
            risk = abs(entry - stop)
            reward = abs(target - entry)
            if risk:
                rr = f"{reward / risk:.2f}x"

        decision_rows = [
            ["Direction", decision.get("direction", "N/A")],
            ["Entry", f"${entry:,.2f}" if entry else "N/A"],
            ["Stop", f"${stop:,.2f}" if stop else "N/A"],
            ["Target", f"${target:,.2f}" if target else "N/A"],
            ["Risk / Reward", rr or "N/A"],
            ["Volatility", decision.get("risk_volatility", "N/A")],
            ["Timeframe", decision.get("timeframe", "N/A")],
            ["Reasoning", decision.get("reasoning", "")],
        ]
        lines.extend(["## Final Trade Setup", _md_table(["Field", "Value"], decision_rows), ""])
    else:
        lines.extend(["## Final Trade Setup", "No decision generated.", ""])

    tech_report = ""
    fund_report = ""
    for step in out_data.get("steps", []):
        if step.get("node") == "quant_head_synthesis":
            tech_report = step.get("llm_output", "") or ""
        elif step.get("node") == "fund_head_synthesis":
            fund_report = step.get("llm_output", "") or ""

    if tech_report:
        tech_rows = _extract_report_sections(
            tech_report,
            [
                "Rationale",
                "Bull Perspective",
                "Bear Perspective",
                "Risks",
                "Opportunities",
                "Priority",
                "Recommended Stop Loss",
                "Profit Target",
                "Time Horizon",
                "Overall Bias",
            ],
        )
        if tech_rows:
            tech_rows = [[sec, _truncate_for_md(text, 300)] for sec, text in tech_rows]
            lines.extend(["## Technical Wing Highlights", _md_table(["Section", "Excerpt"], tech_rows), ""])

    if fund_report:
        fund_rows = _extract_report_sections(
            fund_report,
            [
                "Rationale",
                "Bull Perspective",
                "Bear Perspective",
                "Risks",
                "Opportunities",
                "Priority",
                "Recommended Stop Loss",
                "Profit Target",
                "Time Horizon",
                "Overall Bias",
            ],
        )
        if fund_rows:
            fund_rows = [[sec, _truncate_for_md(text, 300)] for sec, text in fund_rows]
            lines.extend(["## Fundamental Wing Highlights", _md_table(["Section", "Excerpt"], fund_rows), ""])

    fundamental_analysis = out_data.get("fundamental_analysis", {}) or {}
    sector_peer_context = fundamental_analysis.get("sector_peer_context", "")
    internet_context = fundamental_analysis.get("internet_context", "")
    if sector_peer_context:
        lines.extend(["## Sector & Peer Comparative Context", "```"])
        lines.append(sector_peer_context)
        lines.extend(["```", ""])
    if internet_context:
        lines.extend(["## Internet Search Context", "```"])
        lines.append(internet_context)
        lines.extend(["```", ""])

    node_outputs = out_data.get("node_outputs", {}) or {}
    tool_sections = [
        ("Quantitative Bull Tool Stack", node_outputs.get("quant_bull_worker", {}).get("tool_results", {})),
        ("Quantitative Bear Tool Stack", node_outputs.get("quant_bear_worker", {}).get("tool_results", {})),
        ("Fundamental Bull Tool Stack", node_outputs.get("fund_bull_worker", {}).get("tool_results", {})),
        ("Fundamental Bear Tool Stack", node_outputs.get("fund_bear_worker", {}).get("tool_results", {})),
        ("Quant Core Tool Stack", node_outputs.get("quant", {}).get("tool_results", {})),
    ]
    for section_title, tool_results in tool_sections:
        rows = _extract_tool_rows(tool_results)
        if rows:
            lines.extend([f"## {section_title}", _md_table(["Tool", "Result"], rows), ""])

    step_rows = []
    for step in out_data.get("steps", []):
        output = step.get("llm_output", "")
        if isinstance(output, dict):
            output = json.dumps(output, ensure_ascii=False)
        step_rows.append(
            [
                step.get("node", "unknown"),
                step.get("model_used", "unknown"),
                f"{step.get('timestamp', 0):.2f}s",
                _truncate_for_md(output, 220),
            ]
        )
    lines.extend(["## Execution Steps", _md_table(["Node", "Model", "Duration", "Preview"], step_rows), ""])

    lines.extend(["## Appendix - Full Technical Wing Report", "```"])
    lines.append(tech_report or "No technical wing report available.")
    lines.extend(["```", ""])

    lines.extend(["## Appendix - Full Fundamental Wing Report", "```"])
    lines.append(fund_report or "No fundamental wing report available.")
    lines.extend(["```", ""])

    tool_summary_rows = _collect_tool_summary_rows(node_outputs)
    if tool_summary_rows:
        lines.extend([
            "## Appendix - Tool Calls by Node",
            _md_table(["Node", "Tools Used", "Count"], tool_summary_rows),
            "",
        ])

    filename = f"{ticker}_analysis_report.md"
    with open(filename, "w", encoding="utf-8") as f:
        f.write("\n".join(lines).rstrip() + "\n")
    print(f"📝 Markdown report saved to {filename}")


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
        "--financial-db",
        type=str,
        default="",
        help="Path to the fundamental SQLite database (default: data/financials.db)",
    )
    parser.add_argument(
        "-v", "--verbose", action="store_true", help="Enable verbose debug output"
    )
    parser.add_argument(
        "--research-web",
        action="store_true",
        help="Enable free internet search context in the Researcher node",
    )

    args = parser.parse_args()

    # 1. Validate the database exists
    if not os.path.exists(args.db):
        print(f"❌ Error: Database file not found at '{args.db}'")
        print("Please ensure your 'US_DB.db' is placed inside the 'data/' folder.")
        return

    financial_db_path = resolve_financial_db_path(args.financial_db or None)
    if not financial_db_path:
        print("⚠️ Warning: financial database not found. Fundamental tools will fall back to yfinance.")
        financial_db_path = args.financial_db or "data/financials.db"
    set_financial_db_path(financial_db_path)

    print_header(f"🚀 Initializing Framework for {args.ticker.upper()}", args.verbose)
    print(f"🔌 Connected to database: {args.db}")
    print(f"💼 Financial database: {financial_db_path}")
    print(f"🌐 Research web search: {'ENABLED' if args.research_web else 'DISABLED'}")
    if args.verbose:
        print(f"📋 Verbose mode: ENABLED")
    print(
        "🧠 Agents are starting their analysis... (This may take a few minutes if new indicators are being coded)"
    )

    # 2. Initialize the Shared State
    execution_start = time.time()
    initial_state = {
        # Base
        "ticker": args.ticker.upper(),
        "db_path": args.db,
        "financial_db_path": financial_db_path,
        "verbose": args.verbose,
        "allow_research_web": args.research_web,
        "iteration_count": 0,
        "market_context": "",
        "manager_brief": "",
        # Researcher
        "researcher_context": "",
        # Quantitative wing
        "quant_bull_findings": "",
        "quant_bear_findings": "",
        "quant_wing_report": "",
        # Fundamental wing
        "fund_bull_findings": "",
        "fund_bear_findings": "",
        "fund_wing_report": "",
        # Coder fallback
        "coder_loop_count": 0,
        "indicator_requested": "",
        "draft_code": "",
        "test_results": "",
        "code_review_feedback": "",
        "code_approved": False,
        "quant_used_tools": False,
        "quant_strategy": "",
        "coder_output": {},
        # Legacy analysis dicts (for reviewer compat)
        "technical_analysis": {},
        "fundamental_analysis": {},
        # Review
        "reviewer_feedback": "",
        "final_decision": {},
        # Tracking
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
            entry = float(decision.get("entry_price", 0) or 0)
            stop = float(decision.get("stoploss", 0) or 0)
            target = float(decision.get("target", 0) or 0)
            rr = "N/A"
            if entry and stop and target:
                risk = abs(entry - stop)
                reward = abs(target - entry)
                if risk:
                    rr = f"{reward / risk:.2f}x"

            render_kv_table(
                "Final Trade Setup",
                [
                    ("Direction", decision.get("direction", "N/A")),
                    ("Entry", f"${entry:,.2f}" if entry else "N/A"),
                    ("Stop", f"${stop:,.2f}" if stop else "N/A"),
                    ("Target", f"${target:,.2f}" if target else "N/A"),
                    ("Risk / Reward", rr),
                    ("Volatility", decision.get("risk_volatility", "N/A")),
                    ("Timeframe", decision.get("timeframe", "N/A")),
                    ("Reasoning", decision.get("reasoning", "")),
                ],
            )
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
        "node_outputs": node_outputs,
        "fundamental_analysis": final_state.get("fundamental_analysis", {}) if final_state else {},
        "final_decision": decision,
        "error": error_msg if error_msg else None,
    }

    with open("out.json", "w") as f:
        json.dump(out_data, f, indent=2)

    print(f"\n💾 Output saved to out.json")

    # 5. Generate DOCX report
    generate_docx_report(args.ticker.upper(), out_data, decision)
    generate_markdown_report(args.ticker.upper(), out_data, decision)


if __name__ == "__main__":
    main()
