import os

def load_prompt(role: str) -> str:
    """Loads the system prompt for a specific agent from the /skills directory first."""
    for base in ("./skills", "./prompts"):
        path = f"{base}/{role}.txt"
        if os.path.exists(path):
            with open(path, "r") as f:
                return f.read()
    return f"You are the {role}. Perform your analysis based on the state data."
