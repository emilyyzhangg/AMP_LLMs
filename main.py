"""
Main entry point for AMP_LLM application.
Restructured for better modularity and cleaner imports.

Version: 3.0 - Modular Architecture with Auto-Modelfile Generation
"""
import sys
import os

# CRITICAL: Setup environment FIRST, before ANY other imports
print("Starting AMP_LLM...")
print("Checking environment...\n")

from env_setup import ensure_env, verify_critical_imports

if not ensure_env():
    print("\nEnvironment setup failed. Exiting.")
    sys.exit(1)

if not verify_critical_imports():
    print("\nCritical imports failed. Exiting.")
    sys.exit(1)

print("\n" + "="*50)
print("Environment ready! Checking Modelfile...")
print("="*50 + "\n")

# Check and auto-generate Modelfile if needed
try:
    from modelfile_utils import ensure_modelfile_exists
    
    if not ensure_modelfile_exists(verbose=True):
        print("\n⚠️  Warning: Modelfile generation failed")
        print("Research Assistant may not work correctly")
        print("You can manually generate with: python generate_modelfile.py\n")
    else:
        print()  # Blank line for spacing
        
except ImportError:
    print("\n⚠️  Warning: modelfile_utils.py not found")
    print("Modelfile auto-generation disabled")
    print("Make sure Modelfile exists or create it manually\n")
except Exception as e:
    print(f"\n⚠️  Warning: Modelfile check failed: {e}")
    print("Continuing anyway...\n")

print("="*50)
print("Starting application...")
print("="*50 + "\n")

# NOW import everything else
import asyncio
from colorama import init

# Initialize colorama
init(autoreset=True)

# Import configuration and core app
from config import get_logger
from core.app import AMPLLMApp

logger = get_logger(__name__)


async def main():
    """Application entry point wrapper."""
    app = AMPLLMApp()
    await app.run()


if __name__ == '__main__':
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("\nApplication terminated by user.")
    except Exception as e:
        logger.error(f"Unhandled exception: {e}", exc_info=True)
        print(f"Fatal error: {e}")
        sys.exit(1)