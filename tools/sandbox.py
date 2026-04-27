import sys
import io
import pandas as pd
import numpy as np
import sqlite3
import ast
import ta
import arch
from langchain_core.tools import tool


def run_sandbox_code(code: str, ticker: str = None, db_path: str = None) -> str:
    """Execute python code in a restricted sandbox."""
    code_lower = code.lower()

    # Check for only truly forbidden imports
    forbidden = ["pandas_ta", "ta-lib", "TA-Lib"]
    for f in forbidden:
        if f in code_lower:
            raise ImportError(f"Code contains forbidden import: {f}")

    # Must use allowed base libs
    if (
        "sqlite3" not in code_lower
        and ("ta" not in code_lower)
        and ("pandas" not in code_lower and "pd" not in code_lower)
    ):
        raise ImportError("Code must use sqlite3, pandas, or ta")

    # Pre-validate Python syntax
    try:
        ast.parse(code)
    except SyntaxError as e:
        raise ValueError(f"Code has syntax error at line {e.lineno}: {e.msg}")

    safe_locals = {
        "pd": pd,
        "np": np,
        "sqlite3": sqlite3,
        "ta": ta,
        "arch": arch,
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
            "ValueError": ValueError,
            "TypeError": TypeError,
            "KeyError": KeyError,
            "IndexError": IndexError,
            "__import__": __import__,
        }
    }

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
    """
    Executes python code in a restricted sandbox.
    Use this to run and test generated indicators against SQLite data.
    """
    return run_sandbox_code(code, ticker, db_path)
