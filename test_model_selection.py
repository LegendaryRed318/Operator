#!/usr/bin/env python3
"""Test model selection logic."""
import sys
sys.path.insert(0, 'backend')

from ws_server import classify_intent, select_model_for_intent

print("=== Intent Classification Tests ===")
test_queries = [
    "Why is the sky blue",
    "Explain quantum computing",
    "Analyze this error",
    "Write python code",
    "What is 2+2",
    "Help me debug this",
]
for q in test_queries:
    intent = classify_intent(q)
    print(f"'{q}' -> '{intent}'")

print("\n=== Model Selection Tests ===")
for q in test_queries:
    model = select_model_for_intent(q)
    print(f"'{q}' -> {model!r}")
