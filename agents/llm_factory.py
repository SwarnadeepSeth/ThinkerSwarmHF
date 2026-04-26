import os
from langchain_nvidia_ai_endpoints import ChatNVIDIA


def get_llm(model_name: str = None, temperature: float = 0.3):
    """Initializes the NVIDIA NIM endpoint."""
    # Use environment variable or hardcoded key
    api_key = (
        os.getenv("NVIDIA_API_KEY")
        or "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"
    )

    # Default tool-capable model for agents
    if model_name is None:
        model_name = "meta/llama-3.1-8b-instruct"

    return ChatNVIDIA(model=model_name, temperature=temperature, api_key=api_key)
