"""
AMP_LLM — Clinical Trial Research & LLM Integration Framework
"""

__version__ = "3.0.0"
__author__ = "Uluc Birol"
__license__ = "Amphoraxe Life Sciences Inc."

from pathlib import Path

# Expose main Application class for convenience
try:
    from .core.app import Application
except ImportError:
    Application = None

# Root package path (useful for resource lookups)
PACKAGE_ROOT = Path(__file__).resolve().parent
