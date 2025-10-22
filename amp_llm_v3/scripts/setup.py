"""
Environment setup with better error reporting.
"""
import os
import sys
import subprocess
import importlib.util
import platform
import pathlib
from typing import List, Tuple

VENV_DIR = "llm_env"
REQUIREMENTS_FILE = "requirements.txt"

# Package name to import name mapping
PACKAGE_IMPORT_MAPPING = {
    "beautifulsoup4": "bs4",
    "python-dotenv": "dotenv",
    "duckduckgo-search": "duckduckgo_search",
}


def get_python_path() -> str:
    """Get path to venv Python executable."""
    if platform.system() == "Windows":
        return os.path.join(VENV_DIR, "Scripts", "python.exe")
    else:
        return os.path.join(VENV_DIR, "bin", "python")


def fix_venv_pip(venv_python: str) -> bool:
    """Fix missing pip in virtual environment."""
    print("🔧 Fixing pip in virtual environment...")
    
    # Method 1: Use ensurepip from system Python
    try:
        print("  Trying ensurepip...")
        result = subprocess.run(
            [sys.executable, "-m", "ensurepip", "--upgrade", "--default-pip"],
            capture_output=True,
            text=True,
            timeout=60
        )
        if result.returncode == 0:
            print("✅ pip installed via ensurepip")
            return True
    except Exception as e:
        print(f"  ensurepip failed: {e}")
    
    # Method 2: Try get-pip.py
    try:
        print("  Downloading get-pip.py...")
        import urllib.request
        get_pip_url = "https://bootstrap.pypa.io/get-pip.py"
        get_pip_path = os.path.join(VENV_DIR, "get-pip.py")
        
        urllib.request.urlretrieve(get_pip_url, get_pip_path)
        
        print("  Installing pip via get-pip.py...")
        result = subprocess.run(
            [venv_python, get_pip_path],
            capture_output=True,
            text=True,
            timeout=120
        )
        
        os.remove(get_pip_path)
        
        if result.returncode == 0:
            print("✅ pip installed via get-pip.py")
            return True
    except Exception as e:
        print(f"  get-pip.py failed: {e}")
    
    return False


def create_virtual_env() -> bool:
    """Create virtual environment with pip."""
    print("🔧 Creating virtual environment...")
    
    # Delete existing venv if it exists
    if os.path.exists(VENV_DIR):
        print("  Removing existing virtual environment...")
        import shutil
        try:
            shutil.rmtree(VENV_DIR)
        except Exception as e:
            print(f"  Warning: Could not remove old venv: {e}")
    
    try:
        # Create venv
        subprocess.check_call(
            [sys.executable, "-m", "venv", VENV_DIR],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.PIPE
        )
        print("✅ Virtual environment created")
        
        # Verify pip was installed
        venv_python = get_python_path()
        result = subprocess.run(
            [venv_python, "-m", "pip", "--version"],
            capture_output=True,
            text=True,
            timeout=10
        )
        
        if result.returncode != 0:
            print("⚠️  pip not found in venv, fixing...")
            if not fix_venv_pip(venv_python):
                print("❌ Could not install pip in virtual environment")
                print("\n💡 Your Python installation may be incomplete.")
                print("   Try reinstalling Python from python.org")
                return False
            
            # Verify pip again
            result = subprocess.run(
                [venv_python, "-m", "pip", "--version"],
                capture_output=True,
                text=True,
                timeout=10
            )
            if result.returncode != 0:
                print("❌ pip still not working after fix")
                return False
        
        print("✅ pip is available")
        return True
        
    except subprocess.CalledProcessError as e:
        print(f"❌ Failed to create virtual environment: {e}")
        return False
    except Exception as e:
        print(f"❌ Unexpected error: {e}")
        return False


def upgrade_pip(venv_python: str) -> bool:
    """Upgrade pip in virtual environment."""
    print("📦 Upgrading pip...")
    try:
        # Show output for debugging
        result = subprocess.run(
            [venv_python, "-m", "pip", "install", "--upgrade", "pip"],
            capture_output=True,
            text=True,
            timeout=120
        )
        if result.returncode == 0:
            print("✅ Pip upgraded")
            return True
        else:
            print(f"⚠️ Pip upgrade warning: {result.stderr}")
            return True  # Continue anyway
    except Exception as e:
        print(f"⚠️  Could not upgrade pip: {e}")
        return True  # Continue anyway


def install_package(venv_python: str, package: str) -> Tuple[bool, str]:
    """Install single package and return (success, error_message)."""
    try:
        result = subprocess.run(
            [venv_python, "-m", "pip", "install", package],
            capture_output=True,
            text=True,
            timeout=300
        )
        
        if result.returncode == 0:
            return True, ""
        else:
            # Return actual error message
            error_msg = result.stderr or result.stdout
            return False, error_msg
            
    except subprocess.TimeoutExpired:
        return False, "Installation timeout (5 minutes)"
    except Exception as e:
        return False, str(e)


def install_requirements(venv_python: str) -> bool:
    """Install all requirements from requirements.txt."""
    if not os.path.exists(REQUIREMENTS_FILE):
        print(f"⚠️  {REQUIREMENTS_FILE} not found")
        return create_minimal_requirements()
    
    print(f"📦 Installing packages from {REQUIREMENTS_FILE}...")
    
    # Read packages
    with open(REQUIREMENTS_FILE) as f:
        packages = [line.strip() for line in f if line.strip() and not line.startswith('#')]
    
    print(f"Found {len(packages)} package(s) to install\n")
    
    failed = []
    error_details = {}
    
    for i, pkg in enumerate(packages, 1):
        print(f"[{i}/{len(packages)}] Installing {pkg}...", end=" ", flush=True)
        
        success, error_msg = install_package(venv_python, pkg)
        
        if success:
            print("✅")
        else:
            print("❌")
            failed.append(pkg)
            error_details[pkg] = error_msg
            
            # Print first few lines of error
            error_lines = error_msg.split('\n')
            print(f"  Error preview: {error_lines[-3] if len(error_lines) > 3 else error_msg[:100]}")
    
    if failed:
        print(f"\n⚠️  Failed to install {len(failed)} package(s):")
        for pkg in failed:
            print(f"  • {pkg}")
            if pkg in error_details:
                # Show last line of error which usually has the key info
                error_lines = error_details[pkg].strip().split('\n')
                last_line = error_lines[-1] if error_lines else "Unknown error"
                print(f"    → {last_line}")
        
        print("\n💡 Troubleshooting:")
        print("  1. Check your internet connection")
        print("  2. Try: pip install --upgrade pip setuptools wheel")
        print("  3. Try manually: pip install colorama")
        print("  4. Check if you need to run as Administrator")
        return False
    
    print("\n✅ All packages installed successfully!")
    return True


def create_minimal_requirements() -> bool:
    """Create minimal requirements.txt if missing."""
    print("📝 Creating minimal requirements.txt...")
    
    minimal_requirements = """# Core async dependencies
asyncssh>=2.14.0
aiohttp>=3.9.0
aioconsole>=0.7.0

# HTTP requests
requests>=2.31.0

# UI and configuration
colorama>=0.4.6
python-dotenv>=1.0.0
"""
    
    try:
        with open(REQUIREMENTS_FILE, 'w') as f:
            f.write(minimal_requirements)
        print("✅ Created requirements.txt")
        return True
    except Exception as e:
        print(f"❌ Failed to create requirements.txt: {e}")
        return False


def check_missing_packages() -> List[str]:
    """Check which packages are missing."""
    if not os.path.exists(REQUIREMENTS_FILE):
        return []
    
    missing = []
    with open(REQUIREMENTS_FILE) as f:
        for line in f:
            pkg = line.strip()
            if not pkg or pkg.startswith('#'):
                continue
            
            # Extract base package name
            base = pkg.split('==')[0].split('>=')[0].split('<=')[0].strip()
            
            # Get import name
            import_name = PACKAGE_IMPORT_MAPPING.get(base, base.replace('-', '_'))
            
            # Check if importable
            spec = importlib.util.find_spec(import_name)
            if spec is None:
                missing.append(pkg)
    
    return missing


def ensure_env() -> bool:
    """
    Ensure virtual environment exists and has all packages.
    Returns True if ready, False if failed.
    """
    python_path = get_python_path()
    current_python = os.path.abspath(sys.executable)
    venv_python = os.path.abspath(python_path)
    
    # Check if we're already in venv
    in_venv = current_python == venv_python or VENV_DIR in current_python
    
    if not in_venv:
        # Not in venv - need to create/use it
        print("📁 Setting up virtual environment...")
        
        # Create venv if doesn't exist
        if not os.path.exists(venv_python):
            if not create_virtual_env():
                return False
        else:
            print("✅ Virtual environment exists")
        
        # Upgrade pip
        upgrade_pip(venv_python)
        
        # Install requirements
        if not install_requirements(venv_python):
            print("\n⚠️  Some packages failed to install")
            print("     You can try to continue, but the application may not work correctly")
            
            # Ask user if they want to continue
            try:
                response = input("\nContinue anyway? (y/n): ").strip().lower()
                if response != 'y':
                    return False
            except:
                return False
        
        # Relaunch inside venv
        print(f"\n🔄 Relaunching inside virtual environment...")
        print(f"   {venv_python}\n")
        
        try:
            result = subprocess.run([venv_python] + sys.argv)
            sys.exit(result.returncode)
        except Exception as e:
            print(f"❌ Failed to restart: {e}")
            print(f"\n💡 Manually run: {venv_python} main.py")
            return False
    
    # We're in the venv - check if pip works
    print("✅ Running inside virtual environment")
    
    # Check if pip is working in this venv
    result = subprocess.run(
        [sys.executable, "-m", "pip", "--version"],
        capture_output=True,
        text=True
    )
    
    if result.returncode != 0:
        print("❌ pip is broken in this virtual environment!")
        print("🔧 Recreating virtual environment...")
        
        # Exit venv and recreate
        print("\n⚠️  Please deactivate the virtual environment and run main.py again.")
        print("   Or delete the llm_env folder manually:\n")
        print("   rmdir /s /q llm_env")
        print("   python main.py\n")
        return False
    
    # Quick check for missing packages
    missing = check_missing_packages()
    
    if missing:
        print(f"\n⚠️  Found {len(missing)} missing package(s)")
        print("📦 Installing missing packages...")
        
        venv_python = sys.executable
        failed = []
        
        for pkg in missing:
            print(f"  Installing {pkg}...", end=" ", flush=True)
            success, error = install_package(venv_python, pkg)
            if success:
                print("✅")
            else:
                print("❌")
                failed.append(pkg)
                # Show brief error
                if "No module named pip" in error:
                    print("    → pip is broken!")
                    break
        
        if failed:
            print(f"\n❌ Failed to install: {', '.join(failed)}")
            
            if any("No module named pip" in str(e) for e in [error]):
                print("\n🔧 Your virtual environment's pip is broken.")
                print("   Fixing this requires recreating the venv.\n")
                print("   Run these commands:")
                print("   1. deactivate")
                print("   2. rmdir /s /q llm_env") 
                print("   3. python main.py\n")
            
            return False
    else:
        print("✅ All required packages are installed")
    
    return True


def verify_critical_imports() -> bool:
    """Verify critical packages can be imported."""
    critical = ['asyncssh', 'aiohttp', 'aioconsole', 'colorama']
    
    failed = []
    for pkg in critical:
        try:
            importlib.import_module(pkg)
        except ImportError:
            failed.append(pkg)
    
    if failed:
        print(f"\n❌ Critical packages cannot be imported: {', '.join(failed)}")
        print(f"   Current Python: {sys.executable}")
        print(f"   Try: pip install {' '.join(failed)}")
        return False
    
    return True


if __name__ == "__main__":
    print("=== Testing Environment Setup ===\n")
    
    if ensure_env():
        if verify_critical_imports():
            print("\n✅ Environment is ready!")
        else:
            print("\n❌ Import verification failed")
            sys.exit(1)
    else:
        print("\n❌ Environment setup failed")
        sys.exit(1)