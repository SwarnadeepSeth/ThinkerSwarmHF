import os
import time
from langchain_nvidia_ai_endpoints import ChatNVIDIA


def get_llm(model_name: str = None, temperature: float = 0.7, max_retries: int = 3):
    """Initializes the NVIDIA NIM endpoint with automatic retry for rate limits."""
    api_key = os.getenv("NVIDIA_API_KEY") or os.getenv("OPENAI_API_KEY")

    if model_name is None:
        model_name = "openai/gpt-oss-120b"

    base_llm = ChatNVIDIA(model=model_name, temperature=temperature, api_key=api_key)

    class RetryLLM:
        def __init__(self, llm, retries):
            self.llm = llm
            self.retries = retries

        def invoke(self, message, **kwargs):
            last_error = None
            for attempt in range(self.retries):
                try:
                    return self.llm.invoke(message, **kwargs)
                except Exception as e:
                    last_error = e
                    error_str = str(e)
                    if (
                        "429" in error_str
                        or "502" in error_str
                        or "Bad Gateway" in error_str
                    ) and attempt < self.retries - 1:
                        wait_time = (attempt + 1) * 3
                        print(
                            f"API error ({error_str[:50]}...), retrying in {wait_time}s..."
                        )
                        time.sleep(wait_time)
                    elif attempt >= self.retries - 1:
                        raise last_error
            raise last_error

        def __getattr__(self, name):
            return getattr(self.llm, name)

    return RetryLLM(base_llm, max_retries)
