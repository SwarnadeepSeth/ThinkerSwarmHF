import sys
import io
import pandas as pd
import numpy as np
import sqlite3
from langchain_core.tools import tool


def run_sandbox_code(code: str, ticker: str = None, db_path: str = None) -> str:
    """Execute python code in a restricted sandbox."""
    # Check for forbidden imports before execution
    forbidden = ["arch", "ta(", "pandas_ta", "TA-Lib", "technical", "ta_lib"]
    code_lower = code.lower()
    for f in forbidden:
        if f in code_lower:
            raise ImportError(f"Code contains forbidden import: {f}")

    safe_locals = {
        "pd": pd,
        "np": np,
        "sqlite3": sqlite3,
        "datetime": __import__("datetime"),
        "json": __import__("json"),
    }

    if ticker:
        safe_locals["ticker"] = ticker
    if db_path:
        safe_locals["db_path"] = db_path

    safe_globals = {
        "__builtins__": {
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
            "AssertionError": AssertionError,
            "ValueError": ValueError,
            "TypeError": TypeError,
            "KeyError": KeyError,
            "IndexError": IndexError,
        },
        "__import__": __import__,
    }

    old_stdout = sys.stdout
    redirected_output = sys.stdout = io.StringIO()

    try:
        exec(code, safe_globals, safe_locals)
    except Exception:
        sys.stdout = old_stdout
        raise

    output = redirected_output.getvalue()
    sys.stdout = old_stdout

    if not output:
        raise RuntimeError("Code executed but produced no output")

    return output


@tool
def execute_python_code(code: str, ticker: str = None, db_path: str = None) -> str:
    """
    Executes python code in a restricted sandbox.
    Use this to run and test generated indicators against SQLite data.
    """
    return run_sandbox_code(code, ticker, db_path)
