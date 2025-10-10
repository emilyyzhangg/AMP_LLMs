"""
Main entry point for AMP_LLM application.
Restructured for better modularity and cleaner imports.
Version: 3.0 - Modular Architecture with Auto-Modelfile Generation
"""
import sys
import os
from pathlib import Path

# CRITICAL: Setup environment FIRST, before ANY other imports
print("Starting AMP_LLM...")
print("Checking environment...\n")

try:
    from scripts.setup_environment import ensure_env, verify_critical_imports
    
    if not ensure_env():
        print("\n❌ Environment setup failed. Exiting.")
        sys.exit(1)
    
    if not verify_critical_imports():
        print("\n❌ Critical imports failed. Exiting.")
        sys.exit(1)
        
except ImportError as e:
    print(f"❌ Cannot import from scripts.setup_environment: {e}")
    print("Make sure scripts/setup_environment.py exists.")
    sys.exit(1)

print("\n" + "="*60)
print("✅ Environment ready! Checking Modelfile...")
print("="*60 + "\n")

# Check and auto-generate Modelfile if needed
try:
    # Try importing from scripts first, then fall back to root
    try:
        from scripts.generate_modelfile import generate_modelfile
        has_modelfile_gen = True
    except ImportError:
        try:
            from amp_llm.scripts.generate_modelfile import generate_modelfile
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
        
except Exception as e:
    print(f"\n⚠️  Warning: Modelfile check failed: {e}")
    print("Continuing anyway...\n")

print("="*60)
print("🚀 Starting application...")
print("="*60 + "\n")

# Add src to path if needed
src_dir = Path(__file__).parent / "src"
if src_dir.exists() and str(src_dir) not in sys.path:
    sys.path.insert(0, str(src_dir))
    print(f"✅ Added {src_dir} to Python path")

# NOW import everything else
import asyncio
from colorama import init

# Initialize colorama
init(autoreset=True)

# Import from the correct location (FIXED)
try:
    from amp_llm.core.app import Application
    from amp_llm.config import get_logger
    
    logger = get_logger(__name__)
    
except ImportError as e:
    print(f"\n❌ Import error: {e}")
    print("\nTroubleshooting:")
    print("  1. Make sure you're in the project root directory")
    print("  2. Check that src/amp_llm/ exists")
    print("  3. Verify all packages are installed:")
    print("     pip install -r requirements.txt")
    sys.exit(1)


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