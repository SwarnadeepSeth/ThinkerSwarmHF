import sys
import io
import pandas as pd
import numpy as np
import sqlite3
from langchain_core.tools import tool


@tool
def execute_python_code(code: str) -> str:
    """
    Executes python code in a restricted sandbox.
    Use this to run and test generated indicators against SQLite data.
    """
    # Define explicitly allowed libraries/locals
    safe_locals = {"pd": pd, "np": np, "sqlite3": sqlite3}

    # Restrict builtins to prevent malicious imports like __import__('os')
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
            "Exception": Exception,
            "AssertionError": AssertionError,
            "ValueError": ValueError,
            "TypeError": TypeError,
        }
    }

    # Intercept standard output to capture print() statements and test results
    old_stdout = sys.stdout
    redirected_output = sys.stdout = io.StringIO()

    try:
        exec(code, safe_globals, safe_locals)
        output = redirected_output.getvalue()
        return output if output else "Execution successful, but no output returned."
    except Exception as e:
        return f"Execution failed with error: {str(e)}"
    finally:
        sys.stdout = old_stdout
