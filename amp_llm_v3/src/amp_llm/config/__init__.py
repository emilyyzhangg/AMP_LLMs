"""
Configuration management for AMP_LLM.

This module provides centralized configuration with environment variable support.
"""

# In src/amp_llm/config/__init__.py
from functools import lru_cache
# from src.amp_llm.config import get_logger

@lru_cache(maxsize=None)
def get_logger(name: str):
    """Cached logger retrieval."""
    return logging.getLogger(name)

# Usage remains the same, but cached

from .settings import (
    get_config,
    get_logger,
    reload_config,
    AppConfig,
    NetworkConfig,
    APIConfig,
    LLMConfig,
    OutputConfig,
)
from .logging import (
    setup_logging,
    LogConfig,
    set_log_level,
    TemporaryLogLevel,
    disable_library_logging,
)
from .validation import (
    get_validation_config,
    reload_validation_config,
    ValidationConfig,
    validate_enum_value,
    normalize_outcome,
    StudyStatus,
    Phase,
    Classification,
    DeliveryMode,
    Outcome,
    FailureReason,
)

# Backward compatibility alias
get_settings = get_config
Settings = AppConfig

__all__ = [
    # Settings
    'get_config',
    'get_settings',  # Alias for backward compatibility
    'get_logger',
    'reload_config',
    'AppConfig',
    'Settings',  # Alias
    'NetworkConfig',
    'APIConfig',
    'LLMConfig',
    'OutputConfig',
    
    # Logging
    'setup_logging',
    'LogConfig',
    'set_log_level',
    'TemporaryLogLevel',
    'disable_library_logging',
    
    # Validation
    'get_validation_config',
    'reload_validation_config',
    'ValidationConfig',
    'validate_enum_value',
    'normalize_outcome',
    'StudyStatus',
    'Phase',
    'Classification',
    'DeliveryMode',
    'Outcome',
    'FailureReason',
]