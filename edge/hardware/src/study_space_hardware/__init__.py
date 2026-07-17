"""Sensor and edge-hardware acquisition for the study-space advisor."""

from .config import HardwareConfig, load_config
from .models import SensorHealth, SensorSample
from .orchestrator import SensorOrchestrator
from .session_validation import SessionValidationReport, validate_session

__all__ = [
    "HardwareConfig",
    "SensorHealth",
    "SensorOrchestrator",
    "SensorSample",
    "SessionValidationReport",
    "load_config",
    "validate_session",
]

__version__ = "0.1.0"
