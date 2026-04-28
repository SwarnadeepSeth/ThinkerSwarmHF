"""
Unified print helpers for all agent nodes.
No external dependencies — pure ASCII/Unicode box drawing.
"""

import re
import textwrap

W = 60   # default box width
TABLE_W = 88


# ── Low-level primitives ──────────────────────────────────────────────────────

def _pad(text: str, width: int) -> str:
    return text + " " * max(0, width - len(text))


def _clean(text) -> str:
    return re.sub(r"\s+", " ", str(text)).strip()


def _clip(text: str, width: int) -> str:
    text = _clean(text)
    if len(text) <= width:
        return text
    if width <= 1:
        return text[:width]
    return text[: max(0, width - 1)] + "…"


def _wrap(text: str, width: int) -> list[str]:
    text = _clean(text)
    if not text:
        return [""]
    wrapped = textwrap.wrap(
        text,
        width=width,
        break_long_words=False,
        break_on_hyphens=False,
    )
    return wrapped or [""]


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


def _table_top(width: int, title: str) -> str:
    title = f" {title} " if title else ""
    room = max(0, width - 2 - len(title))
    left = room // 2
    right = room - left
    return "╔" + "═" * left + title + "═" * right + "╗"


def _table_mid(width: int) -> str:
    return "╠" + "═" * (width - 2) + "╣"


def _table_bot(width: int) -> str:
    return "╚" + "═" * (width - 2) + "╝"


def render_table(title: str, headers: list[str], rows: list[list[str]], width: int = TABLE_W):
    """Render a bordered terminal table with wrapped cells."""
    if not headers:
        return

    cols = len(headers)
    if cols == 0:
        return

    clean_rows = [[_clean(cell) for cell in row] for row in rows]
    clean_headers = [_clean(header) for header in headers]
    inner_width = width - 4 - (3 * (cols - 1))
    if inner_width < cols * 8:
        width = max(width, cols * 10 + 4 + 3 * (cols - 1))
        inner_width = width - 4 - (3 * (cols - 1))

    natural = []
    for idx, header in enumerate(clean_headers):
        longest = len(header)
        for row in clean_rows:
            if idx < len(row):
                longest = max(longest, len(row[idx]))
        cap = 34 if cols <= 2 else 24
        natural.append(min(max(longest + 2, len(header) + 2), cap))

    total = sum(natural)
    if total > inner_width:
        shrink = inner_width / total
        widths = [max(8, int(w * shrink)) for w in natural]
        while sum(widths) > inner_width:
            for i in range(len(widths)):
                if sum(widths) <= inner_width:
                    break
                if widths[i] > 8:
                    widths[i] -= 1
    else:
        widths = natural[:]
        extra = inner_width - total
        i = 0
        while extra > 0 and widths:
            widths[i % len(widths)] += 1
            extra -= 1
            i += 1

    print()
    print(_table_top(width, title))

    def _print_row(values: list[str], is_header: bool = False):
        wrapped_cells = []
        max_lines = 1
        for idx, value in enumerate(values):
            cell_lines = _wrap(value, widths[idx])
            if is_header:
                cell_lines = [_clip(value, widths[idx])]
            wrapped_cells.append(cell_lines)
            max_lines = max(max_lines, len(cell_lines))

        for line_idx in range(max_lines):
            parts = []
            for idx, cell_lines in enumerate(wrapped_cells):
                line = cell_lines[line_idx] if line_idx < len(cell_lines) else ""
                parts.append(f"{line:<{widths[idx]}}")
            print("║ " + " │ ".join(parts) + " ║")

    _print_row(clean_headers, is_header=True)
    print(_table_mid(width))
    for idx, row in enumerate(clean_rows):
        padded = row + [""] * max(0, cols - len(row))
        _print_row(padded[:cols])
        if idx < len(clean_rows) - 1:
            print("╟" + "─" * (width - 2) + "╢")
    print(_table_bot(width))


def render_kv_table(title: str, items: list[tuple[str, str]], width: int = TABLE_W):
    """Convenience wrapper for two-column summary tables."""
    render_table(title, ["Field", "Value"], [[k, v] for k, v in items], width=width)


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

    render_kv_table(title, [(label, value) for label, value in extracted.items()])


def findings_preview(text: str, label: str, max_chars: int = 300, width: int = W):
    """Show a truncated preview of a worker's findings."""
    snippet = text.replace("\n", " ").strip()[:max_chars]
    wrapped = textwrap.fill(snippet + ("…" if len(text) > max_chars else ""),
                            width=width - 4, initial_indent="    ",
                            subsequent_indent="    ")
    print(f"\n  [{label}]")
    print(wrapped)
