"""
Environment setup with improved reliability and error handling.
Ensures all dependencies are installed before application starts.
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
    "biopython": "Bio",
    "google-search-results": "serpapi",
    "pytest-cov": "pytest_cov",
    "python-dotenv": "dotenv",
    "aiohttp": "aiohttp",
    "aioconsole": "aioconsole",
    "asyncssh": "asyncssh",
    "colorama": "colorama",
    "openai": "openai",
}


def get_python_path() -> str:
    """Get path to venv Python executable."""
    if platform.system() == "Windows":
        return os.path.join(VENV_DIR, "Scripts", "python.exe")
    else:
        return os.path.join(VENV_DIR, "bin", "python")


def create_virtual_env() -> bool:
    """Create virtual environment."""
    print("🔧 Creating virtual environment...")
    try:
        subprocess.check_call(
            [sys.executable, "-m", "venv", VENV_DIR],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.PIPE
        )
        print("✅ Virtual environment created successfully!")
        return True
    except subprocess.CalledProcessError as e:
        print(f"❌ Failed to create virtual environment: {e}")
        return False


def is_same_python(p1: str, p2: str) -> bool:
    """Check if two paths point to the same Python executable."""
    try:
        return pathlib.Path(p1).resolve().samefile(pathlib.Path(p2).resolve())
    except Exception:
        return False


def upgrade_pip(venv_python: str) -> bool:
    """Upgrade pip in virtual environment."""
    print("📦 Upgrading pip...")
    try:
        subprocess.check_call(
            [venv_python, "-m", "pip", "install", "--upgrade", "pip"],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL
        )
        return True
    except Exception as e:
        print(f"⚠️  Could not upgrade pip: {e}")
        return False


def install_requirements(venv_python: str) -> bool:
    """Install all requirements from requirements.txt."""
    if not os.path.exists(REQUIREMENTS_FILE):
        print(f"⚠️  {REQUIREMENTS_FILE} not found")
        return create_minimal_requirements()
    
    print(f"📦 Installing packages from {REQUIREMENTS_FILE}...")
    
    # Try to install all at once
    try:
        result = subprocess.run(
            [venv_python, "-m", "pip", "install", "-r", REQUIREMENTS_FILE],
            capture_output=True,
            text=True,
            timeout=300  # 5 minute timeout
        )
        
        if result.returncode == 0:
            print("✅ All packages installed successfully!")
            return True
        else:
            print(f"⚠️  Batch install had issues, trying individually...")
            return install_individually(venv_python)
            
    except subprocess.TimeoutExpired:
        print("⚠️  Installation timed out, trying individually...")
        return install_individually(venv_python)
    except Exception as e:
        print(f"❌ Error installing requirements: {e}")
        return False


def install_individually(venv_python: str) -> bool:
    """Install packages one by one."""
    with open(REQUIREMENTS_FILE) as f:
        packages = [line.strip() for line in f if line.strip() and not line.startswith('#')]
    
    failed = []
    for pkg in packages:
        print(f"  Installing {pkg}...", end=" ")
        try:
            subprocess.check_call(
                [venv_python, "-m", "pip", "install", pkg],
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                timeout=120
            )
            print("✅")
        except Exception as e:
            print(f"❌ {e}")
            failed.append(pkg)
    
    if failed:
        print(f"\n⚠️  Failed to install: {', '.join(failed)}")
        return False
    
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

# Optional: OpenAI
openai>=1.0.0
"""
    
    try:
        with open(REQUIREMENTS_FILE, 'w') as f:
            f.write(minimal_requirements)
        print("✅ Created requirements.txt")
        return True
    except Exception as e:
        print(f"❌ Failed to create requirements.txt: {e}")
        return False


def check_missing_packages() -> Tuple[List[str], List[str]]:
    """
    Check which packages are missing.
    Returns: (missing_packages, missing_import_names)
    """
    if not os.path.exists(REQUIREMENTS_FILE):
        return [], []
    
    missing_packages = []
    missing_imports = []
    
    with open(REQUIREMENTS_FILE) as f:
        for line in f:
            pkg = line.strip()
            if not pkg or pkg.startswith('#'):
                continue
            
            # Extract base package name
            base = pkg.split('==')[0].split('>=')[0].split('<=')[0].strip()
            
            # Get import name
            import_name = PACKAGE_IMPORT_MAPPING.get(base, base)
            
            # Check if installed
            if importlib.util.find_spec(import_name) is None:
                missing_packages.append(pkg)
                missing_imports.append(import_name)
    
    return missing_packages, missing_imports


def ensure_env() -> bool:
    """
    Ensure virtual environment exists and has all packages.
    Returns True if ready, False if failed.
    """
    python_path = get_python_path()
    current_python = os.path.abspath(sys.executable)
    venv_python = os.path.abspath(python_path)
    
    in_venv = is_same_python(current_python, venv_python)
    
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
            print("⚠️  Some packages failed to install")
            print("     The application may not work correctly")
        
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
    
    # We're in the venv - check packages
    print("✅ Running inside virtual environment")
    
    missing_packages, missing_imports = check_missing_packages()
    
    if missing_packages:
        print(f"\n⚠️  Found {len(missing_packages)} missing package(s):")
        for pkg in missing_packages:
            print(f"   - {pkg}")
        
        print("\n📦 Installing missing packages...")
        if not install_requirements(sys.executable):
            print("⚠️  Installation incomplete")
            return False
        
        print("✅ All packages installed!")
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
        print("   Run: pip install " + " ".join(failed))
        return False
    
    return True


if __name__ == "__main__":
    # Test the environment setup
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