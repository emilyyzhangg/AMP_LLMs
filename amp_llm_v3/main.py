"""
AMP_LLM v3.0 — Unified Application Runner
-----------------------------------------
Main entry point for AMP_LLM application.
Backward compatible with legacy structure.

Features:
- Auto environment + Modelfile validation
- Cross-platform graceful shutdown
- Clean asyncio lifecycle management
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
    # ✅ Preferred import path
    from src.amp_llm.core.app import Application
    from src.amp_llm.config import get_logger
except ImportError:
    # 🔄 Fallback to old structure
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

# Backward-compatible alias
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
#  STEP 5: SIGNAL + LOOP MANAGEMENT
# ============================================================

async def cancel_all_tasks(loop):
    """Gracefully cancel all running asyncio tasks."""
    tasks = [t for t in asyncio.all_tasks(loop) if not t.done()]
    for task in tasks:
        task.cancel()
    await asyncio.gather(*tasks, return_exceptions=True)

def main():
    """Top-level entrypoint with robust signal handling."""
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)

    # Register graceful shutdown signals (cross-platform safe)
    def shutdown():
        print(Fore.YELLOW + "\n\n🛑 Received termination signal. Shutting down...")
        asyncio.create_task(cancel_all_tasks(loop))

    for sig in (signal.SIGINT, signal.SIGTERM):
        try:
            loop.add_signal_handler(sig, shutdown)
        except NotImplementedError:
            # Windows fallback (no signal handler support)
            pass

    try:
        loop.run_until_complete(main_async())
    except KeyboardInterrupt:
        print(Fore.YELLOW + "\n\n👋 Keyboard interrupt detected. Exiting gracefully...")
    except Exception as e:
        print(Fore.RED + f"\n❌ Fatal error: {e}")
        logger.exception("Unhandled fatal error in main()")
    finally:
        # Ensure pending tasks are cancelled and loop closed
        loop.run_until_complete(cancel_all_tasks(loop))
        loop.close()

# ============================================================
#  STEP 6: ENTRYPOINT
# ============================================================

if __name__ == "__main__":
    main()
