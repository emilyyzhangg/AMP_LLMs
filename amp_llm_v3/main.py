"""
AMP_LLM v3.0 — Unified Application Runner
-----------------------------------------
FIXED: Graceful shutdown without recursion errors
"""

import os
import sys
import signal
import asyncio
import logging
from pathlib import Path
from colorama import Fore, Style, init as colorama_init

logger = logging.getLogger("amp_llm.main")

# ============================================================
#  STEP 1: INITIALIZE ENVIRONMENT BEFORE ANY OTHER IMPORTS
# ============================================================
print("Starting AMP_LLM...")
print("Checking environment...\n")

# Ensure src/ is importable
project_root = Path(__file__).parent
src_dir = project_root / "src"
for path in (project_root, src_dir):
    if str(path) not in sys.path:
        sys.path.insert(0, str(path))

# Environment setup
try:
    from scripts.setup import ensure_env, verify_critical_imports
except ImportError as e:
    print(f"❌ Cannot import setup utilities: {e}")
    sys.exit(1)

# Ensure virtualenv and required imports
if not ensure_env():
    sys.exit(1)
if not verify_critical_imports():
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

AMPLLMApp = Application
logger = get_logger(__name__)

# ============================================================
#  STEP 4: ASYNC APP RUNNER
# ============================================================

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
    # Get all pending tasks (excluding current task)
    current_task = asyncio.current_task(loop)
    tasks = [
        t for t in asyncio.all_tasks(loop) 
        if not t.done() and t is not current_task
    ]
    
    if not tasks:
        return
    
    logger.info(f"Cancelling {len(tasks)} pending task(s)...")
    
    # Cancel all tasks
    for task in tasks:
        task.cancel()
    
    # Wait for all tasks to complete cancellation (with timeout)
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
        
        # Set shutdown event (thread-safe)
        loop.call_soon_threadsafe(shutdown_event.set)
    
    # Register signal handlers (cross-platform safe)
    for sig in (signal.SIGINT, signal.SIGTERM):
        try:
            signal.signal(sig, shutdown_handler)
        except (ValueError, OSError):
            # Windows doesn't support all signals
            pass
    
    try:
        # Run main application
        loop.run_until_complete(main_async())
        
    except KeyboardInterrupt:
        print(Fore.YELLOW + "\n\n👋 Keyboard interrupt detected. Exiting gracefully...")
        logger.info("Keyboard interrupt")
        
    except Exception as e:
        print(Fore.RED + f"\n❌ Fatal error: {e}")
        logger.exception("Fatal error in main()")
        
    finally:
        # Graceful cleanup
        print(Fore.CYAN + "\n🧹 Cleaning up...")
        
        try:
            # Cancel all pending tasks
            loop.run_until_complete(cancel_all_tasks_gracefully(loop))
        except Exception as e:
            logger.error(f"Error during cleanup: {e}")
        
        # Give connections time to close
        try:
            loop.run_until_complete(asyncio.sleep(0.5))
        except Exception:
            pass
        
        # Close loop
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