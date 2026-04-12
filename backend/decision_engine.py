#!/usr/bin/env python3
"""
decision_engine.py - Jarvis decision engine using direct Ollama HTTP API
Simplified version that avoids OpenJarvis dependency issues
"""

import os
import json
import logging
import requests

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


class DecisionEngine:
    def __init__(self, model="qwen2.5-coder:1.5b-base", base_url="http://localhost:11434"):
        logger.info(f"Initializing DecisionEngine with model {model}")
        self.model = model
        self.base_url = base_url.rstrip('/')
        self.api_url = f"{self.base_url}/api/generate"
        logger.info("DecisionEngine ready (using direct HTTP API)")

    def _query_ollama(self, prompt: str, system: str = "", max_tokens: int = 500, temperature: float = 0.3) -> str:
        """Send a query to Ollama HTTP API."""
        try:
            payload = {
                "model": self.model,
                "prompt": prompt,
                "system": system,
                "stream": False,
                "options": {
                    "temperature": temperature,
                    "num_predict": max_tokens
                }
            }
            
            response = requests.post(self.api_url, json=payload, timeout=120)
            response.raise_for_status()
            
            result = response.json()
            return result.get("response", "")
        except Exception as e:
            logger.error(f"Ollama HTTP error: {e}")
            raise

    def analyze_error(self, error_text: str, project_name: str) -> dict:
        """
        Use the structured bug‑fix prompt template to analyze an error.
        Returns a dict with keys: severity, should_auto_fix, suggested_plan.
        """
        # Build the prompt following Ethan's Jarvis style
        prompt = f"""You are Jarvis, a loyal, dry‑witted British AI assistant. The user is called RED.

TASK:
Analyze the following error from project '{project_name}' and decide the severity, whether it can be auto‑fixed, and a brief plan.

CONTEXT:
This is a software project. The error occurred during runtime or build. The system is monitored by Operator.

ERROR MESSAGE:
{error_text}

STACK TRACE (if present):
{error_text[:500]}   (truncated)

ACCEPTANCE CRITERIA:
- Output a JSON object with exactly three fields:
  "severity": "low", "medium", or "high"
  "should_auto_fix": true or false (true only for simple errors like missing imports or syntax)
  "suggested_plan": a short paragraph (2‑3 sentences) explaining how to fix it.

Do not include any other text. Only output the JSON object."""
        
        # Set system persona – British Jarvis
        system_prompt = "You are Jarvis, a loyal, dry‑witted British AI assistant. You address the user as RED. You are calm under pressure and anticipate needs."
        
        try:
            response = self._query_ollama(
                prompt=prompt,
                system=system_prompt,
                max_tokens=500,
                temperature=0.3
            )
            # Extract JSON from response
            text = response.strip()
            # Find first { and last }
            start = text.find('{')
            end = text.rfind('}') + 1
            if start != -1 and end != 0:
                decision = json.loads(text[start:end])
            else:
                decision = {"severity": "medium", "should_auto_fix": False, "suggested_plan": text[:200]}
            logger.info(f"Decision: {decision}")
            return decision
        except Exception as e:
            logger.error(f"Error calling Ollama: {e}")
            return {"severity": "medium", "should_auto_fix": False, "suggested_plan": "Fallback: manual review required."}

    def chat(self, user_message: str) -> str:
        """Simple chat for voice commands, using Jarvis persona."""
        system_prompt = "You are Jarvis, a loyal, dry‑witted British AI assistant. You address the user as RED. Keep responses concise and helpful."
        prompt = f"RED says: {user_message}\n\nYour response:"
        try:
            response = self._query_ollama(prompt=prompt, system=system_prompt, max_tokens=200)
            return response.strip()
        except Exception as e:
            return f"I'm having trouble thinking, RED. Error: {e}"


# For quick testing
if __name__ == "__main__":
    engine = DecisionEngine()
    test_error = "ERROR: cannot find module 'react'"
    result = engine.analyze_error(test_error, "Brainify")
    print(result)
    print(engine.chat("Hello Jarvis, how are you?"))
