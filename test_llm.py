#!/usr/bin/env python3
import os

os.environ["NVIDIA_API_KEY"] = (
    "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"
)

print("Step 1: Importing...", flush=True)
from dotenv import load_dotenv

load_dotenv()

print("Step 2: Loading dotenv...", flush=True)
print("API:", os.getenv("NVIDIA_API_KEY", "MISSING")[:15], flush=True)

print("Step 3: Getting LLM...", flush=True)
from agents.llm_factory import get_llm

print("Step 4: Creating LLM instance...", flush=True)
llm = get_llm()

print("Step 5: Invoking...", flush=True)
response = llm.invoke("Say TEST")
print("Response:", response.content, flush=True)
