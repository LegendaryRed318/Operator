#!/usr/bin/env python3
"""
config.py - Mode-based configuration for Operator/JARVIS.
Controls whether the system runs in 'small' (current machine) or 'homelab' mode.

Set JARVIS_MODE=small or JARVIS_MODE=homelab in your .env or launch script.
Defaults to 'small' if not set.
"""

import os
import psutil
from pathlib import Path
from dataclasses import dataclass, field
from typing import Optional

# Detect mode from environment
_MODE = os.getenv("JARVIS_MODE", "small").lower()
IS_HOMELAB = _MODE == "homelab"
IS_SMALL = _MODE == "small"

# Remote access override (can be set in .env or shell)
_REMOTE_ENABLED = os.getenv("ENABLE_REMOTE_ACCESS", "false").lower() == "true"


@dataclass
class AIModelConfig:
    """AI model selection based on mode and available RAM."""
    fast_model: str = "llama3.2:3b"
    large_model: str = "qwen2.5-coder:7b"
    reasoning_model: str = "deepseek-r1:7b"
    fallback_model: str = "llama3.2:3b"

    # RAM thresholds (GB)
    large_model_ram_gb: float = 6.0
    medium_model_ram_gb: float = 4.0
    small_model_ram_gb: float = 2.0

    @property
    def recommended_model(self) -> str:
        """Select best model based on current RAM."""
        available_gb = psutil.virtual_memory().available / (1024 ** 3)
        if available_gb >= self.large_model_ram_gb:
            return self.large_model
        elif available_gb >= self.medium_model_ram_gb:
            return self.fallback_model
        return self.fast_model


@dataclass
class ResourceConfig:
    """Memory and performance settings."""
    max_history_turns: int = 4
    max_context_chars: int = 12000
    proactive_alerts_enabled: bool = True
    alert_polling_seconds: int = 10

    # TTS settings
    tts_rate: int = 165
    tts_volume: float = 0.9

    # Conversation follow-up window (seconds)
    follow_up_window_seconds: int = 20

    # Hotword timeout (minutes)
    hotword_timeout_minutes: int = 30


@dataclass
class FeatureConfig:
    """Feature flags based on mode."""
    gaming_mode: bool = False
    home_automation: bool = False
    tailscale_vpn: bool = False
    face_recognition: bool = False
    predictive_health: bool = False
    obsidian_rag: bool = True  # Works on both modes
    advanced_vision: bool = False
    financial_integration: bool = False


@dataclass
class HardwareConfig:
    """Hardware-specific settings."""
    gpu_acceleration: bool = False
    max_ram_for_ollama_gb: float = 1.5
    ollama_num_ctx: int = 2048
    ollama_num_predict: int = 4096


@dataclass
class NetworkConfig:
    """Network and remote access settings."""
    enable_remote_access: bool = False
    tailscale_auth_key: Optional[str] = None
    ngrok_enabled: bool = False
    ngrok_auth_token: Optional[str] = None


@dataclass
class PathsConfig:
    """Path configurations - all relative to project root."""
    project_root: Path = field(default_factory=lambda: Path(__file__).parent.parent)
    logs: Path = field(default_factory=lambda: Path(__file__).parent.parent / "logs")
    database: Path = field(default_factory=lambda: Path(__file__).parent.parent / "database")
    skills: Path = field(default_factory=lambda: Path(__file__).parent.parent / "skills")
    vault: Optional[Path] = None  # Uses external vault path in homelab mode
    models: Path = field(default_factory=lambda: Path(__file__).parent.parent / "models")


# ============================================================================
# MODE DEFINITIONS
# ============================================================================

_SMALL_MODE_CONFIG = {
    "ai": AIModelConfig(
        fast_model="llama3.2:3b",           # Default: good general conversation
        large_model="qwen2.5-coder:7b",      # Coding tasks (>6GB RAM)
        reasoning_model="deepseek-r1:7b",    # Reasoning tasks (>6GB RAM)
        fallback_model="llama3.2:3b",        # Fallback when preferred unavailable
        large_model_ram_gb=6.0,
        medium_model_ram_gb=4.0,
        small_model_ram_gb=2.0,
    ),
    "resources": ResourceConfig(
        max_history_turns=4,
        max_context_chars=12000,
        proactive_alerts_enabled=True,
    ),
    "features": FeatureConfig(
        gaming_mode=False,
        home_automation=False,
        tailscale_vpn=False,
        face_recognition=False,
        predictive_health=False,
        obsidian_rag=True,
        advanced_vision=False,
        financial_integration=False,
    ),
    "hardware": HardwareConfig(
        gpu_acceleration=False,
        max_ram_for_ollama_gb=1.5,
        ollama_num_ctx=2048,
        ollama_num_predict=4096,
    ),
    "network": NetworkConfig(
        enable_remote_access=_REMOTE_ENABLED,
        tailscale_auth_key=os.getenv("TAILSCALE_AUTHKEY"),
        ngrok_enabled=False,
    ),
}

_HOMELAB_MODE_CONFIG = {
    "ai": AIModelConfig(
        fast_model="qwen2.5-coder:7b",
        large_model="qwen2.5-coder:14b",
        reasoning_model="deepseek-r1:7b",
        fallback_model="llama3.2:3b",
        large_model_ram_gb=6.0,
        medium_model_ram_gb=4.0,
        small_model_ram_gb=2.0,
    ),
    "resources": ResourceConfig(
        max_history_turns=8,
        max_context_chars=32000,
        proactive_alerts_enabled=True,
    ),
    "features": FeatureConfig(
        gaming_mode=True,
        home_automation=True,
        tailscale_vpn=True,
        face_recognition=True,
        predictive_health=True,
        obsidian_rag=True,
        advanced_vision=True,
        financial_integration=True,
    ),
    "hardware": HardwareConfig(
        gpu_acceleration=True,
        max_ram_for_ollama_gb=8.0,
        ollama_num_ctx=8192,
        ollama_num_predict=8192,
    ),
    "network": NetworkConfig(
        enable_remote_access=True,
        ngrok_enabled=False,
    ),
}


# ============================================================================
# ACTIVE CONFIGURATION
# ============================================================================

def get_config() -> dict:
    """Get the active configuration based on JARVIS_MODE."""
    if IS_HOMELAB:
        return _HOMELAB_MODE_CONFIG
    return _SMALL_MODE_CONFIG


# Convenience accessors
ai_config: AIModelConfig = get_config()["ai"]
resources: ResourceConfig = get_config()["resources"]
features: FeatureConfig = get_config()["features"]
hardware: HardwareConfig = get_config()["hardware"]
network: NetworkConfig = get_config()["network"]


# ============================================================================
# UTILITY FUNCTIONS
# ============================================================================

def get_mode() -> str:
    """Return current mode string."""
    return "homelab" if IS_HOMELAB else "small"


def is_mode(modes: str | list[str]) -> bool:
    """Check if current mode matches given mode(s)."""
    if isinstance(modes, str):
        return _MODE == modes.lower()
    return _MODE in [m.lower() for m in modes]


def log_mode_info():
    """Log current mode configuration."""
    import logging
    logger = logging.getLogger(__name__)
    logger.info(f"[Config] JARVIS running in {get_mode().upper()} mode")
    logger.info(f"[Config]   Recommended model: {ai_config.recommended_model}")
    logger.info(f"[Config]   GPU acceleration: {hardware.gpu_acceleration}")
    logger.info(f"[Config]   Max RAM for AI: {hardware.max_ram_for_ollama_gb}GB")
    logger.info(f"[Config]   Features: gaming={features.gaming_mode}, home_auto={features.home_automation}, vpn={features.tailscale_vpn}")
