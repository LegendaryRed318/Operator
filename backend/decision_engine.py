#!/usr/bin/env python3
"""
decision_engine.py - Jarvis decision engine using direct Ollama HTTP API
Simplified version that avoids OpenJarvis dependency issues
"""

import os
import json
import logging
import requests
import psutil

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
        """Send a query to Ollama HTTP API with dynamic RAM-aware model selection."""
        try:
            # Always check RAM before query for optimal model selection
            selected_model = select_model_by_ram()
            if selected_model is None:
                raise Exception("No suitable model available (insufficient RAM or no models installed)")
            
            payload = {
                "model": selected_model,
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
        Selects best model based on available RAM before querying.
        Returns a dict with keys: severity, should_auto_fix, suggested_plan.
        """
        # Log model selection for this query
        selected = select_model_by_ram()
        if selected:
            logger.info(f"[DecisionEngine] analyze_error using model: {selected}")
        
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
        """Simple chat for voice commands, using Jarvis persona with RAM-aware model selection."""
        # Log model selection for this query
        selected = select_model_by_ram()
        if selected:
            logger.info(f"[DecisionEngine] chat using model: {selected}")
        
        system_prompt = "You are Jarvis, a loyal, dry‑witted British AI assistant. You address the user as RED. Keep responses concise and helpful."
        prompt = f"RED says: {user_message}\n\nYour response:"
        try:
            response = self._query_ollama(prompt=prompt, system=system_prompt, max_tokens=200)
            return response.strip()
        except Exception as e:
            return f"I'm having trouble thinking, RED. Error: {e}"


def get_installed_models() -> set:
    """Fetch list of installed Ollama models."""
    try:
        import requests
        resp = requests.get("http://localhost:11434/api/tags", timeout=3)
        if resp.status_code == 200:
            data = resp.json()
            return {m["name"] for m in data.get("models", [])}
    except Exception as e:
        logger.warning(f"[AI] Failed to fetch installed models: {e}")
    return set()


def pull_model_in_background(model_name: str):
    """Start a background process to pull a model."""
    try:
        import subprocess
        # Extract base model name without tag for pull command
        base_name = model_name.split(":")[0]
        subprocess.Popen(
            ["ollama", "pull", base_name],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            creationflags=subprocess.CREATE_NO_WINDOW if hasattr(subprocess, 'CREATE_NO_WINDOW') else 0
        )
        logger.info(f"[AI] Started background pull for {base_name}")
    except Exception as e:
        logger.warning(f"[AI] Failed to start pull for {model_name}: {e}")


def select_model_by_ram() -> str | None:
    """
    Select the best Ollama model based on available RAM.
    Checks if model is installed, falls back to available models.
    Returns None to skip Ollama entirely and use Gemini fallback.
    """
    try:
        available_gb = psutil.virtual_memory().available / (1024 ** 3)
        installed = get_installed_models()
        
        # Priority order based on RAM
        if available_gb > 5:
            preferred = "deepseek-r1:7b"
            fallback = "qwen2.5-coder:7b"
        elif available_gb > 3:
            preferred = "qwen2.5-coder:7b"
            fallback = "qwen2.5-coder:1.5b-base"
        else:
            logger.info(f"[AI] RAM: {available_gb:.1f}GB available — skipping Ollama, using Gemini")
            return None
        
        # Check if preferred model is installed
        if preferred in installed:
            logger.info(f"[AI] RAM: {available_gb:.1f}GB available — using {preferred}")
            # Try to pull deepseek in background if not installed and RAM is sufficient
            if preferred == "deepseek-r1:7b" and "deepseek-r1:7b" not in installed:
                pull_model_in_background("deepseek-r1:7b")
            return preferred
        elif fallback in installed:
            logger.info(f"[AI] RAM: {available_gb:.1f}GB available — {preferred} not installed, using {fallback}")
            # Start background pull of preferred model
            pull_model_in_background(preferred)
            return fallback
        elif "qwen2.5-coder:1.5b-base" in installed:
            logger.info(f"[AI] RAM: {available_gb:.1f}GB available — using qwen2.5-coder:1.5b-base (fallback)")
            return "qwen2.5-coder:1.5b-base"
        else:
            logger.warning(f"[AI] No suitable models installed, using Gemini fallback")
            return None
            
    except Exception as e:
        logger.error(f"[AI] Error selecting model: {e}")
        return "qwen2.5-coder:1.5b-base"


# For quick testing
if __name__ == "__main__":
    engine = DecisionEngine()
    test_error = "ERROR: cannot find module 'react'"
    result = engine.analyze_error(test_error, "Brainify")
    print(result)
    print(engine.chat("Hello Jarvis, how are you?"))
