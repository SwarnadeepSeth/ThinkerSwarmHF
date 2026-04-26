import os

def load_prompt(role: str) -> str:
    """Loads the system prompt for a specific agent from the /prompts directory."""
    path = f"./prompts/{role}.txt"
    if not os.path.exists(path):
        return f"You are the {role}. Perform your analysis based on the state data."
    with open(path, "r") as f:
        return f.read() 
