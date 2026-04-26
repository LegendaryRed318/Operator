#!/usr/bin/env python3
"""
skill_chaining.py - Chain multiple skills together in sequences.
Allows skills to trigger other skills automatically.
"""

import json
import logging
import time
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional, Callable

from paths import LOGS_PATH

logger = logging.getLogger(__name__)

CHAINS_FILE = LOGS_PATH / "skill_chains.json"


class SkillChain:
    """A chain of skills that execute in sequence."""

    def __init__(self, chain_id: str, name: str, description: str = ""):
        self.chain_id = chain_id
        self.name = name
        self.description = description
        self.steps: List[Dict[str, Any]] = []
        self.enabled = True
        self.created_at = datetime.now().isoformat()

    def add_step(
        self,
        skill_name: str,
        params: Optional[Dict[str, Any]] = None,
        condition: Optional[str] = None,
        timeout_seconds: float = 30.0,
    ) -> "SkillChain":
        """Add a step to the chain."""
        self.steps.append({
            "skill_name": skill_name,
            "params": params or {},
            "condition": condition,  # "on_success", "on_failure", "always"
            "timeout_seconds": timeout_seconds,
        })
        return self

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for serialization."""
        return {
            "chain_id": self.chain_id,
            "name": self.name,
            "description": self.description,
            "steps": self.steps,
            "enabled": self.enabled,
            "created_at": self.created_at,
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "SkillChain":
        """Create from dictionary."""
        chain = cls(
            data["chain_id"],
            data["name"],
            data.get("description", ""),
        )
        chain.steps = data.get("steps", [])
        chain.enabled = data.get("enabled", True)
        chain.created_at = data.get("created_at", "")
        return chain


class SkillChainExecutor:
    """Execute skill chains with context passing between steps."""

    def __init__(self, skill_executor_callback: Optional[Callable] = None):
        self._skill_executor = skill_executor_callback
        self.chains: Dict[str, SkillChain] = {}
        self._load_chains()

    def _load_chains(self):
        """Load chains from disk."""
        if CHAINS_FILE.exists():
            try:
                with open(CHAINS_FILE, "r", encoding="utf-8") as f:
                    data = json.load(f)
                    for chain_id, chain_data in data.get("chains", {}).items():
                        self.chains[chain_id] = SkillChain.from_dict(chain_data)
            except Exception as e:
                logger.error(f"[ChainExecutor] Load error: {e}")

    def _save_chains(self):
        """Save chains to disk."""
        try:
            LOGS_PATH.mkdir(parents=True, exist_ok=True)
            with open(CHAINS_FILE, "w", encoding="utf-8") as f:
                json.dump({
                    "chains": {
                        cid: c.to_dict() for cid, c in self.chains.items()
                    }
                }, f, indent=2)
        except Exception as e:
            logger.error(f"[ChainExecutor] Save error: {e}")

    def create_chain(
        self,
        chain_id: str,
        name: str,
        description: str = "",
        steps: Optional[List[Dict[str, Any]]] = None,
    ) -> SkillChain:
        """Create a new skill chain."""
        chain = SkillChain(chain_id, name, description)
        if steps:
            chain.steps = steps
        self.chains[chain_id] = chain
        self._save_chains()
        return chain

    def remove_chain(self, chain_id: str) -> bool:
        """Remove a chain."""
        if chain_id in self.chains:
            del self.chains[chain_id]
            self._save_chains()
            return True
        return False

    def get_chain(self, chain_id: str) -> Optional[SkillChain]:
        """Get a chain by ID."""
        return self.chains.get(chain_id)

    def list_chains(self) -> List[Dict[str, Any]]:
        """List all chains."""
        return [
            {
                "chain_id": c.chain_id,
                "name": c.name,
                "description": c.description,
                "step_count": len(c.steps),
                "enabled": c.enabled,
            }
            for c in self.chains.values()
        ]

    def execute_chain(
        self,
        chain_id: str,
        initial_context: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        """Execute a skill chain."""
        chain = self.get_chain(chain_id)
        if not chain:
            return {
                "success": False,
                "error": f"Chain '{chain_id}' not found",
            }

        if not chain.enabled:
            return {
                "success": False,
                "error": f"Chain '{chain_id}' is disabled",
            }

        logger.info(f"[ChainExecutor] Executing chain: {chain.name}")

        context = dict(initial_context or {})
        step_results = []
        start_time = time.time()

        for i, step in enumerate(chain.steps):
            skill_name = step.get("skill_name")
            params = step.get("params", {})
            condition = step.get("condition", "on_success")
            timeout = step.get("timeout_seconds", 30.0)

            # Check condition
            if condition == "on_success" and step_results and not step_results[-1].get("success"):
                logger.info(f"[ChainExecutor] Skipping step {i+1} (condition: on_success)")
                continue

            if condition == "on_failure" and step_results and step_results[-1].get("success"):
                logger.info(f"[ChainExecutor] Skipping step {i+1} (condition: on_failure)")
                continue

            # Merge context into params
            merged_params = {**params}
            for key, value in context.items():
                if f"{{{key}}}" in str(merged_params):
                    merged_params = json.loads(
                        json.dumps(merged_params).replace(f'"{key}"', json.dumps(value))
                    )

            # Execute skill
            result = self._execute_skill(skill_name, merged_params, context, timeout)
            result["step_index"] = i
            step_results.append(result)

            # Store output in context
            if result.get("success"):
                context[f"step_{i}_result"] = result.get("response", "")
                context["last_result"] = result.get("response", "")

            # Stop on failure unless condition says otherwise
            if not result.get("success") and condition != "always":
                break

        total_time = time.time() - start_time
        all_success = all(s.get("success", False) for s in step_results)

        return {
            "success": all_success,
            "chain_id": chain_id,
            "chain_name": chain.name,
            "step_results": step_results,
            "total_time_ms": int(total_time * 1000),
            "final_context": context,
        }

    def _execute_skill(
        self,
        skill_name: str,
        params: Dict[str, Any],
        context: Dict[str, Any],
        timeout: float,
    ) -> Dict[str, Any]:
        """Execute a single skill."""
        try:
            if self._skill_executor:
                return self._skill_executor(skill_name, params)
            else:
                from skills import dispatch_skill_command
                return dispatch_skill_command(
                    skill_name=skill_name,
                    command_text=params.get("text", ""),
                    params={**params, "timeout_seconds": timeout},
                    source="chain"
                )
        except Exception as e:
            return {
                "success": False,
                "error": str(e),
                "skill_name": skill_name,
            }


# Predefined chain templates
PREDEFINED_CHAINS = {
    "morning_routine_chain": {
        "name": "Morning Routine",
        "description": "Full morning briefing: weather, calendar, system status, news",
        "steps": [
            {"skill_name": "weather", "params": {}, "condition": "always"},
            {"skill_name": "calendar", "params": {}, "condition": "always"},
            {"skill_name": "system_status", "params": {}, "condition": "always"},
        ],
    },
    "shutdown_routine": {
        "name": "Shutdown Routine",
        "description": "Evening shutdown: save work, backup, system check",
        "steps": [
            {"skill_name": "backup_now", "params": {}, "condition": "on_success"},
            {"skill_name": "file_organizer", "params": {}, "condition": "on_success"},
            {"skill_name": "system_health", "params": {}, "condition": "always"},
        ],
    },
    "focus_mode_chain": {
        "name": "Deep Focus",
        "description": "Enable focus mode: silence notifications, close distractions, start timer",
        "steps": [
            {"skill_name": "focus_mode", "params": {}, "condition": "always"},
            {"skill_name": "timer", "params": {"duration": 25}, "condition": "always"},
        ],
    },
    "research_workflow": {
        "name": "Research Workflow",
        "description": "Research a topic: search, summarize, save notes",
        "steps": [
            {"skill_name": "quick_research", "params": {}, "condition": "on_success"},
            {"skill_name": "quick_note", "params": {}, "condition": "on_success"},
        ],
    },
}


def setup_predefined_chains(executor: Optional[SkillChainExecutor] = None) -> None:
    """Set up predefined chain templates."""
    if executor is None:
        executor = get_chain_executor()

    for chain_id, config in PREDEFINED_CHAINS.items():
        if not executor.get_chain(chain_id):
            executor.create_chain(
                chain_id,
                config["name"],
                config["description"],
                config["steps"],
            )

    logger.info(f"[ChainExecutor] {len(PREDEFINED_CHAINS)} predefined chains configured")


# Global executor instance
_executor: Optional[SkillChainExecutor] = None


def get_chain_executor(skill_executor_callback: Optional[Callable] = None) -> SkillChainExecutor:
    """Get or create the global chain executor."""
    global _executor
    if _executor is None:
        _executor = SkillChainExecutor(skill_executor_callback)
    return _executor


def execute_skill_chain(chain_id: str, context: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    """Convenience function to execute a skill chain."""
    executor = get_chain_executor()
    return executor.execute_chain(chain_id, context)


if __name__ == "__main__":
    # Test skill chaining
    logging.basicConfig(level=logging.INFO)

    print("Testing skill chaining...")

    executor = get_chain_executor()

    # Create a test chain
    executor.create_chain(
        "test_chain",
        "Test Chain",
        "A simple test chain",
        [
            {"skill_name": "system_status", "params": {}, "condition": "always"},
            {"skill_name": "time", "params": {}, "condition": "always"},
        ],
    )

    print(f"Chains: {executor.list_chains()}")

    # Execute the chain
    result = executor.execute_chain("test_chain")
    print(f"Result: {result}")
