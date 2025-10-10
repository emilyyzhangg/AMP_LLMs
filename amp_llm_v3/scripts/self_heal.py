"""
scripts/self_heal.py
--------------------
Detects corrupted virtual environments and automatically restarts
the script with system Python.

This module should be imported FIRST before any other imports to
catch venv corruption early.
"""

import sys
import subprocess
from pathlib import Path


def is_in_corrupted_venv():
    """
    Check if running inside a corrupted virtual environment.
    
    Returns:
        bool: True if in corrupted venv, False otherwise
    """
    # Check if we're in a venv
    in_venv = sys.prefix != sys.base_prefix
    
    if not in_venv:
        return False
    
    # Check if venv is corrupted (missing pyvenv.cfg)
    venv_root = Path(sys.prefix)
    pyvenv_cfg = venv_root / "pyvenv.cfg"
    
    if not pyvenv_cfg.exists():
        return True
    
    return False


def get_system_python():
    """
    Find system Python executable (not venv).
    
    Returns:
        Path: Path to system Python, or None if not found
    """
    if sys.platform == "win32":
        # Try sys.base_prefix first (most reliable)
        base_python = Path(sys.base_prefix) / "python.exe"
        if base_python.exists():
            return base_python
        
        # Try finding python in PATH
        try:
            result = subprocess.run(
                ["where", "python"],
                capture_output=True,
                text=True,
                timeout=5
            )
            if result.returncode == 0:
                # Get first non-venv python
                for line in result.stdout.splitlines():
                    py_path = Path(line.strip())
                    if py_path.exists() and "llm_env" not in str(py_path):
                        return py_path
        except:
            pass
    else:
        # Unix/Linux/Mac
        base_python = Path(sys.base_prefix) / "bin" / "python"
        if base_python.exists():
            return base_python
        
        # Try common locations
        for path in ["/usr/bin/python3", "/usr/local/bin/python3", "/usr/bin/python"]:
            if Path(path).exists():
                return Path(path)
    
    return None


def restart_with_system_python():
    """
    Restart the current script using system Python instead of venv Python.
    This function does NOT return - it replaces the current process.
    """
    system_python = get_system_python()
    
    if system_python is None:
        print("❌ Could not find system Python!")
        print("💡 Please run this script from outside the venv:")
        print("   1. Close this terminal")
        print("   2. Open a fresh terminal")
        print("   3. Run: python main.py")
        sys.exit(1)
    
    print(f"🔄 Restarting with system Python: {system_python}")
    print("   (Escaping corrupted venv...)\n")
    
    try:
        # Restart the script with system Python
        result = subprocess.run([str(system_python)] + sys.argv)
        sys.exit(result.returncode)
    except Exception as e:
        print(f"❌ Failed to restart: {e}")
        print("💡 Manual fix:")
        print("   1. Close this terminal")
        print("   2. Open fresh terminal")
        print("   3. Run: python main.py")
        sys.exit(1)


def check_and_heal():
    """
    Main entry point: Check for corrupted venv and heal if needed.
    
    This function should be called at the very beginning of any script
    that might run inside a venv.
    
    If corruption is detected, this function will NOT return - it will
    restart the script with system Python.
    """
    if is_in_corrupted_venv():
        print("=" * 60)
        print("⚠️  CORRUPTED VIRTUAL ENVIRONMENT DETECTED")
        print("=" * 60)
        print("Missing pyvenv.cfg - virtual environment is broken")
        print("Automatically restarting with system Python...\n")
        restart_with_system_python()
        # If we get here, restart failed and we exit in restart_with_system_python()


# Auto-heal if imported directly
if __name__ == "__main__":
    check_and_heal()
    print("✅ Virtual environment is healthy (or not in venv)")