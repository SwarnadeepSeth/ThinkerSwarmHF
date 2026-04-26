import subprocess
import os
from langchain_core.tools import tool

# Ensure absolute paths for safety validation
ALLOWED_DIRS = [
    "/home/swdseth/MegaSync/ThinkerSwarmHF/indicators",
    "/home/swdseth/MegaSync/ThinkerSwarmHF/data",
    "/home/swdseth/MegaSync/ThinkerSwarmHF/library",
]


def is_safe(path: str) -> bool:
    target = os.path.abspath(path)
    return any(target.startswith(safe_dir) for safe_dir in ALLOWED_DIRS)


@tool
def tool_grep(search_term: str, file_path: str) -> str:
    """Equivalent to bash 'grep -n'. Searches file for a specific keyword."""
    if not is_safe(file_path):
        return "Permission denied. Restricted path."
    try:
        result = subprocess.run(
            ["grep", "-n", search_term, file_path],
            capture_output=True,
            text=True,
            timeout=5,
        )
        return result.stdout if result.stdout else "No matches found."
    except Exception as e:
        return f"Grep error: {str(e)}"


@tool
def tool_ls(directory: str) -> str:
    """Equivalent to bash 'ls'. Lists files in a directory to see what scripts exist."""
    if not is_safe(directory):
        return "Permission denied. Restricted path."
    try:
        result = subprocess.run(
            ["ls", "-la", directory], capture_output=True, text=True, timeout=5
        )
        return result.stdout if result.stdout else "Empty directory."
    except Exception as e:
        return f"LS error: {str(e)}"


@tool
def tool_cat(file_path: str) -> str:
    """Equivalent to bash 'cat'. Reads entire file contents."""
    if not is_safe(file_path):
        return "Permission denied. Restricted path."
    try:
        with open(file_path, "r") as f:
            return f.read()
    except Exception as e:
        return f"Cat error: {str(e)}"


@tool
def tool_sed_replace(old_text: str, new_text: str, file_path: str) -> str:
    """Surgical text replacement in a file. Emulates sed to fix bugs without rewriting whole files."""
    if not is_safe(file_path):
        return "Permission denied. Restricted path."
    try:
        with open(file_path, "r") as file:
            data = file.read()
        data = data.replace(old_text, new_text)
        with open(file_path, "w") as file:
            file.write(data)
        return f"Successfully replaced text in {file_path}"
    except Exception as e:
        return f"Sed error: {str(e)}"
