"""
AMP_LLM v3.0 — Unified Application Runner
-----------------------------------------
FULLY AUTOMATIC: Handles all setup without user intervention
SELF-HEALING: Detects and fixes corrupted virtual environments
"""

import os
import sys
from pathlib import Path

# ============================================================
#  FIX NON-BLOCKING I/O ISSUE (macOS/Unix) - MUST BE FIRST!
# ============================================================
def fix_all_io_blocking():
    """
    Fix non-blocking I/O issues on macOS/Unix.
    Prevents [Errno 35] and stdin read failures.
    MUST BE CALLED BEFORE asyncio starts!
    """
    try:
        import fcntl
        
        # Fix all standard streams
        for stream in [sys.stdin, sys.stdout, sys.stderr]:
            if hasattr(stream, 'fileno'):
                try:
                    fd = stream.fileno()
                    # Get current flags
                    flags = fcntl.fcntl(fd, fcntl.F_GETFL)
                    # Remove O_NONBLOCK if present
                    if flags & os.O_NONBLOCK:
                        fcntl.fcntl(fd, fcntl.F_SETFL, flags & ~os.O_NONBLOCK)
                except (OSError, ValueError, AttributeError):
                    pass
    except ImportError:
        pass  # Windows - fcntl not available
    
    # Set unbuffered mode
    os.environ['PYTHONUNBUFFERED'] = '1'
    
    # Reconfigure stdin if possible (Python 3.7+)
    try:
        if hasattr(sys.stdin, 'reconfigure'):
            sys.stdin.reconfigure(line_buffering=True)
    except:
        pass

# Apply fix IMMEDIATELY
fix_all_io_blocking()

print("✅ I/O streams configured for blocking mode")

# ============================================================
#  CRITICAL: SELF-HEAL CHECK BEFORE ANY OTHER IMPORTS
# ============================================================
# This MUST run before any other imports that might fail in corrupted venv

print("Starting AMP_LLM...")
print("Checking environment...\n")

# Ensure scripts/ is importable
project_root = Path(__file__).parent
scripts_dir = project_root / "scripts"
if str(scripts_dir) not in sys.path:
    sys.path.insert(0, str(scripts_dir))

# Run self-heal check (will restart script if venv is corrupted)
try:
    from self_heal import check_and_heal
    check_and_heal()  # This may not return if venv is corrupted
except ImportError:
    print("⚠️  Self-heal module not found, skipping venv check...")


# ============================================================
#  NOW SAFE TO CONTINUE WITH NORMAL IMPORTS
# ============================================================

import signal
import subprocess

# Ensure src/ is importable
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

def is_venv_valid():
    """Check if venv exists and is valid (has pyvenv.cfg)."""
    venv_dir = project_root / "llm_env"
    if not venv_dir.exists():
        return False
    
    # Critical: Check for pyvenv.cfg
    pyvenv_cfg = venv_dir / "pyvenv.cfg"
    if not pyvenv_cfg.exists():
        print("⚠️  Virtual environment is corrupted (missing pyvenv.cfg)")
        return False
    
    # Check if Python executable exists
    venv_python = get_venv_python()
    if not venv_python.exists():
        print("⚠️  Virtual environment is corrupted (missing Python executable)")
        return False
    
    return True

def delete_corrupted_venv():
    """Delete corrupted virtual environment."""
    venv_dir = project_root / "llm_env"
    print(f"🗑️  Deleting corrupted venv: {venv_dir}")
    
    import shutil
    try:
        shutil.rmtree(venv_dir, ignore_errors=True)
        print("✅ Corrupted venv deleted")
        return True
    except Exception as e:
        print(f"❌ Failed to delete corrupted venv: {e}")
        print("\n💡 Manual fix required:")
        print(f"   1. Close this terminal")
        print(f"   2. Run: Remove-Item -Path llm_env -Recurse -Force")
        print(f"   3. Run: python main.py")
        return False

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

def create_fresh_venv():
    """Create a fresh virtual environment."""
    venv_dir = project_root / "llm_env"
    print(f"🔧 Creating virtual environment at {venv_dir}...")
    
    try:
        subprocess.check_call(
            [sys.executable, "-m", "venv", "llm_env"],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL
        )
        print("✅ Virtual environment created")
        
        # Verify it's valid
        if not is_venv_valid():
            print("❌ Newly created venv is invalid!")
            return False
        
        return True
    except Exception as e:
        print(f"❌ Failed to create venv: {e}")
        return False

def setup_environment():
    """Fully automatic environment setup with corruption detection."""
    venv_python = get_venv_python()
    
    # Case 1: Not in venv at all
    if not is_in_venv():
        print("📁 No virtual environment detected")
        
        # Check if venv exists but is corrupted
        venv_dir = project_root / "llm_env"
        if venv_dir.exists() and not is_venv_valid():
            print("🔧 Detected corrupted virtual environment")
            if not delete_corrupted_venv():
                return False
        
        # Create venv if doesn't exist
        if not venv_python.exists():
            if not create_fresh_venv():
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
    
    # Case 2: In venv but it's corrupted (shouldn't happen due to self_heal, but check anyway)
    if is_in_venv() and not is_venv_valid():
        print("❌ Running in corrupted virtual environment")
        print("💡 This shouldn't happen - self-heal should have caught this!")
        print("   Please exit this terminal and run the cleanup script:")
        print("   python scripts/cache_cleanup.py")
        print("   Then run: python main.py")
        return False
    
    # Case 3: In venv but pip is broken
    if not check_pip_works():
        print("❌ pip is broken in this virtual environment")
        print("💡 Please exit this terminal and run:")
        print("   deactivate")
        print("   Remove-Item -Path llm_env -Recurse -Force")
        print("   python main.py")
        return False
    
    # Case 4: In venv, pip works, but packages missing
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