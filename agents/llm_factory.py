import os
from langchain_nvidia_ai_endpoints import ChatNVIDIA


def get_llm(model_name: str = "meta/llama-3.1-8b-instruct", temperature: float = 0.3):
    """Initializes the NVIDIA NIM endpoint with tool-capable model."""
    api_key = os.getenv("NVIDIA_API_KEY")
    if not api_key:
        raise ValueError("NVIDIA_API_KEY environment variable is not set.")

    return ChatNVIDIA(model=model_name, temperature=temperature, api_key=api_key)
