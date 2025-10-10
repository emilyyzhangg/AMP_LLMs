"""
AMP_LLM v3.0 — Unified Application Runner
-----------------------------------------
FIXED: Automatically repairs broken pip and installs dependencies
"""

import os
import sys
import signal
import subprocess
from pathlib import Path

print("Starting AMP_LLM...")
print("Checking environment...\n")

# Ensure src/ is importable
project_root = Path(__file__).parent
src_dir = project_root / "src"
for path in (project_root, src_dir):
    if str(path) not in sys.path:
        sys.path.insert(0, str(path))

# ============================================================
#  STEP 1: SETUP ENVIRONMENT VIA scripts/setup.py
# ============================================================
try:
    from scripts.setup import ensure_env, verify_critical_imports
except ImportError as e:
    print(f"❌ Cannot import setup utilities: {e}")
    sys.exit(1)

# Ensure virtualenv and required imports
if not ensure_env():
    print("\n❌ Environment setup failed")
    print("\n💡 Try manual setup:")
    print("   1. Delete the llm_env folder")
    print("   2. Run: python -m venv llm_env")
    print("   3. Activate it:")
    print("      - Windows: llm_env\\Scripts\\activate")
    print("      - Unix/Mac: source llm_env/bin/activate")
    print("   4. Run: pip install -r requirements.txt")
    sys.exit(1)

if not verify_critical_imports():
    print("\n❌ Critical packages missing")
    sys.exit(1)

# ============================================================
#  STEP 2: CHECK MODELFILE
# ============================================================
print("\n" + "=" * 60)
print("✅ Environment ready! Checking Modelfile...")
print("=" * 60 + "\n")

try:
    from scripts.generate_modelfile import generate_modelfile
    modelfile_path = Path("Modelfile")
    if not modelfile_path.exists():
        print("⚙️  Modelfile not found. Generating...")
        try:
            content = generate_modelfile(base_model="llama3.2")
            modelfile_path.write_text(content, encoding="utf-8")
            print("✅ Modelfile generated successfully")
        except Exception as e:
            print(f"⚠️  Failed to generate Modelfile: {e}")
            print("Research Assistant may not work correctly")
    else:
        print("✅ Modelfile exists")
except ImportError:
    print("⚠️  Modelfile generation script not found")
    print("Make sure Modelfile exists or create it manually")

print("\n" + "=" * 60)
print("🚀 Starting application...")
print("=" * 60 + "\n")

# ============================================================
#  STEP 3: IMPORT CORE MODULES
# ============================================================
from colorama import Fore, Style, init as colorama_init

colorama_init(autoreset=True)

try:
    from amp_llm.core.app import Application
    from amp_llm.config import get_logger
except ImportError:
    try:
        from amp_llm.core.app import Application
        from amp_llm.config import get_logger
    except ImportError as e:
        print(f"❌ Import error: {e}")
        print("\nTroubleshooting:")
        print("  1. Make sure you're in the project root directory")
        print("  2. Check that src/amp_llm/ exists")
        print("  3. Verify dependencies: pip install -r requirements.txt")
        sys.exit(1)

logger = get_logger(__name__)

# ============================================================
#  STEP 4: ASYNC APP RUNNER
# ============================================================

import asyncio

async def main_async():
    """Main async entrypoint with graceful lifecycle management."""
    app = Application()
    try:
        await app.run()
    except asyncio.CancelledError:
        print(Fore.YELLOW + "\n⚠️  Operation cancelled.")
    except Exception as e:
        print(Fore.RED + f"\n❌ Fatal error: {e}")
        logger.exception("Unhandled exception in main_async")
    finally:
        print(Fore.CYAN + Style.BRIGHT + "\n✅ Application exited cleanly." + Style.RESET_ALL)

# ============================================================
#  STEP 5: GRACEFUL SHUTDOWN (FIXED)
# ============================================================

async def cancel_all_tasks_gracefully(loop):
    """
    Gracefully cancel all running asyncio tasks.
    FIXED: Prevents recursion errors during cancellation.
    """
    current_task = asyncio.current_task(loop)
    tasks = [
        t for t in asyncio.all_tasks(loop) 
        if not t.done() and t is not current_task
    ]
    
    if not tasks:
        return
    
    logger.info(f"Cancelling {len(tasks)} pending task(s)...")
    
    for task in tasks:
        task.cancel()
    
    try:
        await asyncio.wait_for(
            asyncio.gather(*tasks, return_exceptions=True),
            timeout=3.0
        )
    except asyncio.TimeoutError:
        logger.warning("Some tasks did not cancel in time")

# ============================================================
#  STEP 6: MAIN ENTRY POINT (FIXED)
# ============================================================

def main():
    """Top-level entrypoint with robust signal handling."""
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    
    shutdown_event = asyncio.Event()
    
    def shutdown_handler(signum, frame):
        """Handle shutdown signals."""
        print(Fore.YELLOW + f"\n\n🛑 Received signal {signum}. Shutting down gracefully...")
        logger.info(f"Received signal {signum}")
        loop.call_soon_threadsafe(shutdown_event.set)
    
    # Register signal handlers (cross-platform safe)
    for sig in (signal.SIGINT, signal.SIGTERM):
        try:
            signal.signal(sig, shutdown_handler)
        except (ValueError, OSError):
            pass
    
    try:
        loop.run_until_complete(main_async())
        
    except KeyboardInterrupt:
        print(Fore.YELLOW + "\n\n👋 Keyboard interrupt detected. Exiting gracefully...")
        logger.info("Keyboard interrupt")
        
    except Exception as e:
        print(Fore.RED + f"\n❌ Fatal error: {e}")
        logger.exception("Fatal error in main()")
        
    finally:
        print(Fore.CYAN + "\n🧹 Cleaning up...")
        
        try:
            loop.run_until_complete(cancel_all_tasks_gracefully(loop))
        except Exception as e:
            logger.error(f"Error during cleanup: {e}")
        
        try:
            loop.run_until_complete(asyncio.sleep(0.5))
        except Exception:
            pass
        
        try:
            loop.close()
        except Exception as e:
            logger.error(f"Error closing loop: {e}")
        
        print(Fore.GREEN + "✅ Cleanup complete")

# ============================================================
#  STEP 7: ENTRYPOINT
# ============================================================

if __name__ == "__main__":
    main()