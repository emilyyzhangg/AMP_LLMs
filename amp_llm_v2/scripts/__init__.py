"""
Scripts package initialization.
Contains utility scripts for setup, validation, and maintenance.
"""

# Import commonly used functions for convenience
try:
    from .setup_environment import ensure_env, verify_critical_imports
    from .validate_setup import V3Tester
    from .generate_modelfile import generate_modelfile
    
    __all__ = [
        'ensure_env',
        'verify_critical_imports',
        'V3Tester',
        'generate_modelfile',
    ]
except ImportError:
    # Scripts not all present yet
    pass

__version__ = '3.0.0'