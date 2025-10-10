"""
AMP_LLM v3.0 — Unified Application Runner
-----------------------------------------
FULLY AUTOMATIC: Handles all setup without user intervention
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
#  AUTOMATIC ENVIRONMENT SETUP
# ============================================================

def get_venv_python():
    """Get path to venv Python."""
    venv_dir = project_root / "llm_env"
    if sys.platform == "win32":
        return venv_dir / "Scripts" / "python.exe"
    else:
        return venv_dir / "bin" / "python"

def is_in_venv():
    """Check if running inside virtual environment."""
    return sys.prefix != sys.base_prefix

def check_pip_works():
    """Check if pip is available and working."""
    try:
        result = subprocess.run(
            [sys.executable, "-m", "pip", "--version"],
            capture_output=True,
            timeout=5
        )
        return result.returncode == 0
    except:
        return False

def auto_install_packages():
    """Automatically install missing packages."""
    print("📦 Installing required packages...")
    
    # Critical packages
    packages = [
        "asyncssh>=2.14.0",
        "aiohttp>=3.9.0",
        "aioconsole>=0.7.0",
        "colorama>=0.4.6",
        "python-dotenv>=1.0.0",
        "requests>=2.31.0"
    ]
    
    # Try to install all at once
    try:
        result = subprocess.run(
            [sys.executable, "-m", "pip", "install"] + packages,
            capture_output=True,
            text=True,
            timeout=300
        )
        
        if result.returncode == 0:
            print("✅ All packages installed")
            return True
        else:
            # Fall back to requirements.txt
            req_file = project_root / "requirements.txt"
            if req_file.exists():
                print("📦 Installing from requirements.txt...")
                result = subprocess.run(
                    [sys.executable, "-m", "pip", "install", "-r", str(req_file)],
                    capture_output=True,
                    text=True,
                    timeout=300
                )
                if result.returncode == 0:
                    print("✅ Packages installed from requirements.txt")
                    return True
            
            print(f"⚠️  Some packages may have failed: {result.stderr[:200]}")
            return False
            
    except Exception as e:
        print(f"⚠️  Installation error: {e}")
        return False

def verify_imports():
    """Verify critical packages can be imported."""
    critical = ['asyncssh', 'aiohttp', 'colorama']
    missing = []
    
    for pkg in critical:
        try:
            __import__(pkg)
        except ImportError:
            missing.append(pkg)
    
    return len(missing) == 0, missing

def setup_environment():
    """Fully automatic environment setup."""
    venv_python = get_venv_python()
    
    # Case 1: Not in venv at all
    if not is_in_venv():
        print("📁 No virtual environment detected")
        
        # Create venv if doesn't exist
        if not venv_python.exists():
            print("🔧 Creating virtual environment...")
            try:
                subprocess.check_call(
                    [sys.executable, "-m", "venv", "llm_env"],
                    stdout=subprocess.DEVNULL,
                    stderr=subprocess.DEVNULL
                )
                print("✅ Virtual environment created")
            except Exception as e:
                print(f"❌ Failed to create venv: {e}")
                return False
        
        # Install packages in venv
        print("📦 Installing packages in virtual environment...")
        try:
            # Install critical packages first
            packages = ["pip", "setuptools", "wheel"]
            subprocess.run(
                [str(venv_python), "-m", "pip", "install", "--upgrade"] + packages,
                capture_output=True,
                timeout=120
            )
            
            # Install requirements
            req_file = project_root / "requirements.txt"
            if req_file.exists():
                subprocess.run(
                    [str(venv_python), "-m", "pip", "install", "-r", str(req_file)],
                    capture_output=True,
                    timeout=300
                )
        except Exception as e:
            print(f"⚠️  Package installation warning: {e}")
        
        # Relaunch in venv
        print(f"\n🔄 Relaunching in virtual environment...")
        try:
            result = subprocess.run([str(venv_python)] + sys.argv)
            sys.exit(result.returncode)
        except Exception as e:
            print(f"❌ Failed to restart: {e}")
            return False
    
    # Case 2: In venv but pip is broken
    if not check_pip_works():
        print("❌ pip is broken in this virtual environment")
        print("🔧 Recreating virtual environment...")
        
        # Delete and recreate
        import shutil
        venv_dir = project_root / "llm_env"
        try:
            # Close current Python to avoid locks
            print("\n⚠️  Please close this terminal and run:")
            print(f"   Remove-Item -Path llm_env -Recurse -Force")
            print(f"   python main.py")
            return False
        except:
            pass
        
        return False
    
    # Case 3: In venv, pip works, but packages missing
    print("✅ Running in virtual environment")
    
    imports_ok, missing = verify_imports()
    
    if not imports_ok:
        print(f"📦 Missing packages: {', '.join(missing)}")
        if not auto_install_packages():
            print("⚠️  Continuing with partial installation...")
        
        # Verify again
        imports_ok, missing = verify_imports()
        if not imports_ok:
            print(f"❌ Still missing: {', '.join(missing)}")
            print("\n💡 Manual fix:")
            print(f"   pip install {' '.join(missing)}")
            return False
    
    print("✅ All critical packages available")
    return True

# Run automatic setup
if not setup_environment():
    print("\n❌ Setup failed. Please fix errors above and try again.")
    sys.exit(1)

# ============================================================
#  MODELFILE CHECK
# ============================================================
print("\n" + "=" * 60)
print("✅ Environment ready! Checking Modelfile...")
print("=" * 60 + "\n")

try:
    from scripts.generate_modelfile import generate_modelfile
    modelfile_path = Path("Modelfile")
    if not modelfile_path.exists():
        print("⚙️  Generating Modelfile...")
        try:
            content = generate_modelfile(base_model="llama3.2")
            modelfile_path.write_text(content, encoding="utf-8")
            print("✅ Modelfile generated")
        except Exception as e:
            print(f"⚠️  Modelfile generation warning: {e}")
    else:
        print("✅ Modelfile exists")
except ImportError as e:
    print(f"⚠️  Modelfile generation not available: {e}")

print("\n" + "=" * 60)
print("🚀 Starting application...")
print("=" * 60 + "\n")

# ============================================================
#  IMPORT AND RUN APPLICATION
# ============================================================
from colorama import Fore, Style, init as colorama_init
colorama_init(autoreset=True)

try:
    from amp_llm.core.app import Application
    from amp_llm.config import get_logger
except ImportError as e:
    print(Fore.RED + f"❌ Import error: {e}")
    print("\nCannot find amp_llm package. Make sure:")
    print("  1. You're in the project root directory")
    print("  2. src/amp_llm/ folder exists")
    sys.exit(1)

logger = get_logger(__name__)

import asyncio

async def main_async():
    """Main async entrypoint."""
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

async def cancel_all_tasks_gracefully(loop):
    """Gracefully cancel all running tasks."""
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

def main():
    """Main entry point with signal handling."""
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    
    shutdown_event = asyncio.Event()
    
    def shutdown_handler(signum, frame):
        print(Fore.YELLOW + f"\n\n🛑 Shutting down gracefully...")
        logger.info(f"Received signal {signum}")
        loop.call_soon_threadsafe(shutdown_event.set)
    
    # Register signal handlers
    for sig in (signal.SIGINT, signal.SIGTERM):
        try:
            signal.signal(sig, shutdown_handler)
        except (ValueError, OSError):
            pass
    
    try:
        loop.run_until_complete(main_async())
        
    except KeyboardInterrupt:
        print(Fore.YELLOW + "\n\n👋 Exiting gracefully...")
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

if __name__ == "__main__":
    main()