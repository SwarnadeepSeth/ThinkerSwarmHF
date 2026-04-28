"""
Unified print helpers for all agent nodes.
No external dependencies — pure ASCII/Unicode box drawing.
"""

import re
import textwrap

W = 60   # default box width


# ── Low-level primitives ──────────────────────────────────────────────────────

def _pad(text: str, width: int) -> str:
    return text + " " * max(0, width - len(text))


def _box_top(width=W):    return "╔" + "═" * (width - 2) + "╗"
def _box_mid(width=W):    return "╠" + "═" * (width - 2) + "╣"
def _box_bot(width=W):    return "╚" + "═" * (width - 2) + "╝"
def _box_row(text, width=W):
    inner = width - 4          # 2 for '║ ' + ' ║'
    return "║ " + _pad(text[:inner], inner) + " ║"

def _inner_top(width=W):  return "  ┌" + "─" * (width - 4) + "┐"
def _inner_bot(width=W):  return "  └" + "─" * (width - 4) + "┘"
def _inner_row(text, width=W):
    inner = width - 6
    return "  │ " + _pad(text[:inner], inner) + " │"


# ── Public API ────────────────────────────────────────────────────────────────

def node_banner(title: str, ticker: str = "", iteration: int = -1,
                emoji: str = "📋", width: int = W):
    """Full box header when a node starts."""
    print()
    print(_box_top(width))
    tag = f"[iter:{iteration}]" if iteration >= 0 else ""
    header = f"{emoji}  {title.upper()}"
    print(_box_row(f"{header:<{width-4-len(tag)}}{tag}", width))
    if ticker:
        print(_box_row(f"Ticker: {ticker}", width))
    print(_box_bot(width))


def dispatch_banner(heading: str, workers: list[tuple[str, str]], width: int = W):
    """
    Show a dispatch tree.
    workers = [(emoji_and_name, description), ...]
    """
    print()
    print(f"  ┌─ {heading} {'─' * max(0, width - 6 - len(heading))}┐")
    for i, (name, desc) in enumerate(workers):
        connector = "└──" if i == len(workers) - 1 else "├──"
        print(f"  │  {connector} {name}  {desc}")
    print(f"  └{'─' * (width - 3)}┘")


def tool_round_banner(round_num: int, n_tools: int, max_rounds: int = 3, width: int = W):
    """Compact banner for each tool-calling round."""
    print(f"\n  {'─'*3} Tool Round {round_num}/{max_rounds} — calling {n_tools} tool(s) {'─'*3}")


def tool_result_line(name: str, result: str, max_result: int = 110):
    """Single tool call result line."""
    r = str(result).replace("\n", " ").strip()
    if len(r) > max_result:
        r = r[:max_result] + "…"
    print(f"     ✦ {name:<35} {r}")


def section_divider(label: str = "", width: int = W):
    if label:
        side = (width - len(label) - 2) // 2
        print(f"\n  {'─'*side} {label} {'─'*side}")
    else:
        print(f"  {'─'*width}")


def node_complete(name: str, elapsed: float, extra: str = ""):
    suffix = f" — {extra}" if extra else ""
    print(f"\n  ✅  {name.upper()} COMPLETE  ({elapsed:.1f}s){suffix}")
    print()


def synthesis_summary(report_text: str, title: str = "Report Summary", width: int = W):
    """
    Parse the structured report and display key fields in a tidy inner box.
    Looks for Markdown ## Section headers and grabs the first non-empty line after each.
    """
    FIELDS = [
        ("Overall Bias",           "## Overall Bias"),
        ("Stop Loss",              "## Recommended Stop Loss"),
        ("Profit Target",          "## Profit Target"),
        ("Time Horizon",           "## Time Horizon"),
        ("Priority",               "## Priority"),
        ("Opportunities",          "## Opportunities"),
        ("Risks",                  "## Risks"),
    ]

    extracted: dict[str, str] = {}
    for label, header in FIELDS:
        pattern = re.compile(
            re.escape(header) + r"[^\n]*\n(.*?)(?=\n##|\Z)",
            re.IGNORECASE | re.DOTALL,
        )
        m = pattern.search(report_text)
        if m:
            text = m.group(1).strip()
            # Grab first non-empty line / sentence
            first = next((l.strip() for l in text.splitlines() if l.strip()), text)
            first = re.sub(r"^[-*•]\s*", "", first)  # strip list markers
            extracted[label] = first[:70]

    if not extracted:
        # Fallback: show first 3 lines of text
        lines = [l.strip() for l in report_text.splitlines() if l.strip()][:3]
        print(f"\n  [{title}]  (structured fields not found — first lines shown)")
        for l in lines:
            print(f"    {l[:width-6]}")
        return

    print()
    print(f"  ┌─ {title} {'─' * max(0, width - 6 - len(title))}┐")
    for label, value in extracted.items():
        label_str = f"  │  {label+':':<20}"
        val_str   = value
        avail     = width - len(label_str) - 4
        print(f"{label_str} {val_str[:avail]:<{avail}}  │")
    print(f"  └{'─' * (width - 3)}┘")


def findings_preview(text: str, label: str, max_chars: int = 300, width: int = W):
    """Show a truncated preview of a worker's findings."""
    snippet = text.replace("\n", " ").strip()[:max_chars]
    wrapped = textwrap.fill(snippet + ("…" if len(text) > max_chars else ""),
                            width=width - 4, initial_indent="    ",
                            subsequent_indent="    ")
    print(f"\n  [{label}]")
    print(wrapped)
