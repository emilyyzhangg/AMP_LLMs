"""
Main entry point for AMP_LLM application.
Backward compatible with old structure.

Version: 3.0 - Modular Architecture with Auto-Modelfile Generation
"""
import sys
import os
from pathlib import Path

# CRITICAL: Setup environment FIRST, before ANY other imports
print("Starting AMP_LLM...")
print("Checking environment...\n")

# Add project root to path
project_root = Path(__file__).parent
if str(project_root) not in sys.path:
    sys.path.insert(0, str(project_root))

# Add src to path for amp_llm imports
src_dir = project_root / "src"
if str(src_dir) not in sys.path:
    sys.path.insert(0, str(src_dir))

try:
    from scripts.setup_environment import ensure_env, verify_critical_imports
    
    if not ensure_env():
        print("\n❌ Environment setup failed. Exiting.")
        sys.exit(1)
    
    if not verify_critical_imports():
        print("\n❌ Critical imports failed. Exiting.")
        sys.exit(1)
        
except ImportError as e:
    print(f"❌ Cannot import environment setup: {e}")
    print("Make sure scripts/setup_environment.py exists.")
    sys.exit(1)

print("\n" + "="*60)
print("✅ Environment ready! Checking Modelfile...")
print("="*60 + "\n")

# Check and auto-generate Modelfile if needed
try:
    from scripts.generate_modelfile import generate_modelfile
    has_modelfile_gen = True
except ImportError:
    has_modelfile_gen = False

if has_modelfile_gen:
    modelfile_path = Path("Modelfile")
    
    if not modelfile_path.exists():
        print("⚙️  Modelfile not found. Generating...")
        try:
            modelfile_content = generate_modelfile(base_model="llama3.2")
            modelfile_path.write_text(modelfile_content, encoding='utf-8')
            print("✅ Modelfile generated successfully")
        except Exception as e:
            print(f"⚠️  Failed to generate Modelfile: {e}")
            print("Research Assistant may not work correctly")
    else:
        print("✅ Modelfile exists")
else:
    print("⚠️  Modelfile generation script not found")
    print("Make sure Modelfile exists or create it manually")

print()  # Blank line for spacing

print("="*60)
print("🚀 Starting application...")
print("="*60 + "\n")

# NOW import everything else
import asyncio
from colorama import init

# Initialize colorama
init(autoreset=True)

# Import from the modular structure
# Support both old (core.app) and new (amp_llm.core.app) import styles
try:
    # Try new structure first
    from amp_llm.src.amp_llm.core.app import Application
    from amp_llm.src.amp_llm.config import get_logger
except ImportError:
    # Fallback to old structure for backward compatibility
    try:
        from amp_llm.core.app import Application
        from amp_llm.config import get_logger
    except ImportError as e:
        print(f"❌ Import error: {e}")
        print("\nTroubleshooting:")
        print("  1. Make sure you're in the project root directory")
        print("  2. Check that src/amp_llm/ exists")
        print("  3. Verify all packages are installed:")
        print("     pip install -r requirements.txt")
        sys.exit(1)

# Backward compatibility alias
AMPLLMApp = Application

logger = get_logger(__name__)


async def main():
    """Application entry point wrapper."""
    try:
        logger.info("Initializing AMP_LLM application")
        app = Application()
        await app.run()
    except KeyboardInterrupt:
        logger.info("Application interrupted by user")
        print("\n\n✨ Application terminated by user.")
    except Exception as e:
        logger.error(f"Fatal error in main: {e}", exc_info=True)
        print(f"\n❌ Fatal error: {e}")
        raise


if __name__ == '__main__':
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("\n\n✨ Goodbye!")
    except Exception as e:
        print(f"\n❌ Unhandled exception: {e}")
        sys.exit(1)