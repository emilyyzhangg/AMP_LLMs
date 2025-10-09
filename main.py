"""
Main entry point for AMP_LLM application.
Restructured for better modularity and cleaner imports.

Version: 3.0 - Modular Architecture
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
print("Environment ready! Starting application...")
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