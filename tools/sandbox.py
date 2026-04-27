import sys
import io
import pandas as pd
import numpy as np
import sqlite3
import json
import ast

# Try import optional libraries
optional_libs = {}
for lib_name in ["ta", "arch", "talib", "mplfinance"]:
    try:
        optional_libs[lib_name] = __import__(lib_name)
    except ImportError:
        pass

from langchain_core.tools import tool


def run_sandbox_code(code: str, ticker: str = None, db_path: str = None) -> str:
    """Execute python code in a restricted sandbox."""
    code_lower = code.lower()

    # Check for only truly forbidden imports
    forbidden = ["ta-lib", "TA-Lib"]
    for f in forbidden:
        if f in code_lower:
            raise ImportError(f"Code contains forbidden import: {f}")

    # Must use allowed base libs
    if (
        "sqlite3" not in code_lower
        and not any(lib in code_lower for lib in optional_libs.keys())
        and ("pandas" not in code_lower and "pd" not in code_lower)
    ):
        raise ImportError(
            "Code must use sqlite3, pandas, or other allowed libs (ta, arch, talib, mplfinance)"
        )

    # Pre-validate Python syntax
    try:
        ast.parse(code)
    except SyntaxError as e:
        raise ValueError(f"Code has syntax error at line {e.lineno}: {e.msg}")

    safe_locals = {
        "pd": pd,
        "np": np,
        "sqlite3": sqlite3,
        "json": json,
    }
    safe_locals.update(optional_libs)

    if ticker:
        safe_locals["ticker"] = ticker
    if db_path:
        safe_locals["db_path"] = db_path

    safe_builtins = {
        "print": print,
        "range": range,
        "len": len,
        "sum": sum,
        "abs": abs,
        "min": min,
        "max": max,
        "round": round,
        "pow": pow,
        "float": float,
        "int": int,
        "bool": bool,
        "list": list,
        "dict": dict,
        "str": str,
        "zip": zip,
        "slice": slice,
        "type": type,
        "isinstance": isinstance,
        "Exception": Exception,
        "ValueError": ValueError,
        "TypeError": TypeError,
        "KeyError": KeyError,
        "IndexError": IndexError,
    }

    safe_globals = {
        "__builtins__": safe_builtins,
        "__name__": "__main__",
    }

    safe_locals.update(safe_locals)

    old_stdout = sys.stdout
    redirected_output = sys.stdout = io.StringIO()

    try:
        exec(code, safe_globals, safe_locals)
    except Exception as e:
        sys.stdout = old_stdout
        raise RuntimeError(f"Code execution failed: {e}")

    output = redirected_output.getvalue()
    sys.stdout = old_stdout

    if not output:
        raise RuntimeError("Code executed but produced no output")

    return output


@tool
def execute_python_code(code: str, ticker: str = None, db_path: str = None) -> str:
    """Executes python code in a restricted sandbox."""
    return run_sandbox_code(code, ticker, db_path)
