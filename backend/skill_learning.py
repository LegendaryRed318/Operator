#!/usr/bin/env python3
"""
skill_learning.py - Learn new triggers from user corrections.
When users rephrase commands, learn the new phrasing as an alias.
"""

import json
import logging
import re
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from paths import LOGS_PATH, SKILLS_PATH

logger = logging.getLogger(__name__)

LEARNING_FILE = LOGS_PATH / "skill_learning.json"


class SkillLearner:
    """Learn new trigger phrases from user behavior."""

    def __init__(self):
        self.learned_triggers: Dict[str, List[Dict[str, Any]]] = {}
        self.trigger_history: List[Dict[str, Any]] = []
        self._load_learning()

    def _load_learning(self):
        """Load learned triggers from disk."""
        if LEARNING_FILE.exists():
            try:
                with open(LEARNING_FILE, "r", encoding="utf-8") as f:
                    data = json.load(f)
                    self.learned_triggers = data.get("learned_triggers", {})
                    self.trigger_history = data.get("history", [])
            except Exception as e:
                logger.error(f"[Learning] Load error: {e}")

    def _save_learning(self):
        """Save learned triggers to disk."""
        try:
            LOGS_PATH.mkdir(parents=True, exist_ok=True)
            with open(LEARNING_FILE, "w", encoding="utf-8") as f:
                json.dump({
                    "learned_triggers": self.learned_triggers,
                    "history": self.trigger_history[-1000:],  # Keep last 1000
                }, f, indent=2)
        except Exception as e:
            logger.error(f"[Learning] Save error: {e}")

    def record_attempt(
        self,
        user_input: str,
        matched_skill: Optional[str],
        matched_by: str,
        success: bool,
    ) -> None:
        """Record a skill matching attempt for later learning."""
        self.trigger_history.append({
            "user_input": user_input,
            "matched_skill": matched_skill,
            "matched_by": matched_by,
            "success": success,
            "timestamp": datetime.now().isoformat(),
        })

        # Trim history
        if len(self.trigger_history) > 1000:
            self.trigger_history = self.trigger_history[-1000:]

        self._save_learning()

    def learn_new_trigger(
        self,
        skill_name: str,
        new_trigger: str,
        confidence: float = 1.0,
        source: str = "user_correction",
    ) -> bool:
        """
        Learn a new trigger phrase for a skill.

        Args:
            skill_name: The skill to add the trigger to
            new_trigger: The new trigger phrase
            confidence: Confidence score (0.0-1.0)
            source: How this was learned (user_correction, pattern_match, explicit)
        """
        if skill_name not in self.learned_triggers:
            self.learned_triggers[skill_name] = []

        # Check if trigger already exists
        for existing in self.learned_triggers[skill_name]:
            if existing["trigger"].lower() == new_trigger.lower():
                # Update confidence
                existing["confidence"] = max(existing["confidence"], confidence)
                existing["usage_count"] = existing.get("usage_count", 0) + 1
                self._save_learning()
                return True

        # Add new trigger
        self.learned_triggers[skill_name].append({
            "trigger": new_trigger,
            "confidence": confidence,
            "source": source,
            "usage_count": 1,
            "learned_at": datetime.now().isoformat(),
            "last_used": None,
        })

        # Apply to skill file
        self._apply_learned_trigger_to_skill(skill_name, new_trigger)

        self._save_learning()
        logger.info(f"[Learning] Learned new trigger for '{skill_name}': '{new_trigger}'")
        return True

    def _apply_learned_trigger_to_skill(self, skill_name: str, new_trigger: str) -> None:
        """Add the learned trigger to the skill's TOML file."""
        skill_file = SKILLS_PATH / f"{skill_name}.toml"

        if not skill_file.exists():
            # Try to find the skill file with different naming
            for f in SKILLS_PATH.glob("*.toml"):
                try:
                    with open(f, "r", encoding="utf-8") as fh:
                        content = fh.read()
                        if f'name = "{skill_name}"' in content:
                            skill_file = f
                            break
                except Exception:
                    continue

        if not skill_file.exists():
            logger.warning(f"[Learning] Could not find skill file for '{skill_name}'")
            return

        try:
            with open(skill_file, "r", encoding="utf-8") as f:
                content = f.read()

            # Check if aliases line exists
            if "aliases = " in content:
                # Add to existing aliases
                def add_alias(match):
                    aliases_str = match.group(1)
                    aliases = json.loads(aliases_str.replace("'", '"'))
                    if new_trigger.lower() not in [a.lower() for a in aliases]:
                        aliases.append(new_trigger)
                        return f'aliases = {json.dumps(aliases)}'
                    return match.group(0)

                content = re.sub(r'aliases = (\[.*?\])', add_alias, content, flags=re.DOTALL)
            else:
                # Add new aliases line after trigger
                content = re.sub(
                    r'(trigger = "[^"]+")',
                    f'\\1\naliases = ["{new_trigger}"]',
                    content,
                )

            with open(skill_file, "w", encoding="utf-8") as f:
                f.write(content)

            logger.info(f"[Learning] Updated skill file: {skill_file}")

        except Exception as e:
            logger.error(f"[Learning] Failed to update skill file: {e}")

    def get_learned_triggers(self, skill_name: Optional[str] = None) -> List[Dict[str, Any]]:
        """Get learned triggers for a skill or all skills."""
        if skill_name:
            return self.learned_triggers.get(skill_name, [])
        else:
            all_triggers = []
            for skill, triggers in self.learned_triggers.items():
                for t in triggers:
                    all_triggers.append({"skill": skill, **t})
            return all_triggers

    def suggest_corrections(
        self,
        unmatched_input: str,
        available_skills: List[str],
    ) -> List[Dict[str, Any]]:
        """
        Suggest skill corrections for unmatched input.

        Uses fuzzy matching to find similar triggers.
        """
        suggestions = []

        for skill_name, triggers in self.learned_triggers.items():
            for trigger_data in triggers:
                existing_trigger = trigger_data["trigger"]

                # Simple similarity check
                similarity = self._string_similarity(unmatched_input.lower(), existing_trigger.lower())

                if similarity > 0.5:
                    suggestions.append({
                        "skill": skill_name,
                        "similarity": similarity,
                        "matched_trigger": existing_trigger,
                        "suggested_action": f"Did you mean '{existing_trigger}'? This triggers '{skill_name}'",
                    })

        # Also check against available skills
        for skill_name in available_skills:
            if skill_name in unmatched_input.lower():
                suggestions.append({
                    "skill": skill_name,
                    "similarity": 0.7,
                    "matched_trigger": skill_name,
                    "suggested_action": f"Say '{skill_name}' to activate this skill",
                })

        suggestions.sort(key=lambda x: x["similarity"], reverse=True)
        return suggestions[:5]  # Top 5 suggestions

    def _string_similarity(self, s1: str, s2: str) -> float:
        """Calculate string similarity (Levenshtein-based)."""
        if len(s1) < len(s2):
            s1, s2 = s2, s1

        if len(s2) == 0:
            return 0.0

        previous_row = range(len(s2) + 1)

        for i, c1 in enumerate(s1):
            current_row = [i + 1]
            for j, c2 in enumerate(s2):
                insertions = previous_row[j + 1] + 1
                deletions = current_row[j] + 1
                substitutions = previous_row[j] + (c1 != c2)
                current_row.append(min(insertions, deletions, substitutions))
            previous_row = current_row

        distance = previous_row[-1]
        max_len = max(len(s1), len(s2))
        return 1.0 - (distance / max_len)

    def analyze_patterns(self) -> Dict[str, Any]:
        """Analyze trigger history for learning opportunities."""
        patterns = {
            "unmatched_inputs": [],
            "low_confidence_triggers": [],
            "unused_triggers": [],
        }

        # Find unmatched inputs that appear frequently
        unmatched_counts: Dict[str, int] = {}
        for entry in self.trigger_history:
            if not entry.get("matched_skill"):
                input_text = entry.get("user_input", "")[:50]
                unmatched_counts[input_text] = unmatched_counts.get(input_text, 0) + 1

        # Inputs that failed 3+ times
        patterns["unmatched_inputs"] = [
            {"input": inp, "count": cnt}
            for inp, cnt in unmatched_counts.items()
            if cnt >= 3
        ]

        # Low confidence triggers
        for skill, triggers in self.learned_triggers.items():
            for t in triggers:
                if t.get("confidence", 1.0) < 0.7:
                    patterns["low_confidence_triggers"].append({
                        "skill": skill,
                        "trigger": t["trigger"],
                        "confidence": t["confidence"],
                    })

        # Unused triggers (learned but never used)
        for skill, triggers in self.learned_triggers.items():
            for t in triggers:
                if t.get("usage_count", 0) == 0:
                    patterns["unused_triggers"].append({
                        "skill": skill,
                        "trigger": t["trigger"],
                    })

        return patterns

    def export_learning_data(self) -> Dict[str, Any]:
        """Export all learning data for sharing."""
        return {
            "learned_triggers": self.learned_triggers,
            "total_history_entries": len(self.trigger_history),
            "skills_with_learned_triggers": len(self.learned_triggers),
            "exported_at": datetime.now().isoformat(),
        }


# Global learner instance
_learner: Optional[SkillLearner] = None


def get_learner() -> SkillLearner:
    """Get or create the global skill learner."""
    global _learner
    if _learner is None:
        _learner = SkillLearner()
    return _learner


def learn_trigger(skill_name: str, new_trigger: str, confidence: float = 1.0) -> bool:
    """Convenience function to learn a new trigger."""
    return get_learner().learn_new_trigger(skill_name, new_trigger, confidence)


def get_suggestions(unmatched_input: str, available_skills: List[str]) -> List[Dict[str, Any]]:
    """Get correction suggestions for unmatched input."""
    return get_learner().suggest_corrections(unmatched_input, available_skills)


if __name__ == "__main__":
    # Test skill learning
    logging.basicConfig(level=logging.INFO)

    print("Testing skill learning...")

    learner = get_learner()

    # Simulate some learning
    learner.learn_new_trigger("weather", "what's it like outside", confidence=0.9)
    learner.learn_new_trigger("weather", "should i bring an umbrella", confidence=0.8)
    learner.learn_new_trigger("morning_routine", "start my day jarvis", confidence=1.0)

    print(f"\nLearned triggers: {learner.get_learned_triggers()}")

    # Test suggestions
    suggestions = learner.suggest_corrections("whats the weather outside like", ["weather", "calendar"])
    print(f"\nSuggestions: {suggestions}")

    # Analyze patterns
    patterns = learner.analyze_patterns()
    print(f"\nPatterns: {patterns}")
