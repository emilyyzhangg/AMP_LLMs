import os
import sys
import subprocess
import importlib.util
import platform
import pathlib

VENV_DIR = "llm_env"
REQUIREMENTS_FILE = "requirements.txt"

PACKAGE_IMPORT_MAPPING = {
    "beautifulsoup4": "bs4",
    "biopython": "Bio",
    "google-search-results": "serpapi",
    "pytest-cov": "pytest_cov",
    "python-dotenv": "dotenv",
}

def get_python_path():
    """Get path to venv Python executable."""
    if platform.system() == "Windows":
        return os.path.join(VENV_DIR, "Scripts", "python.exe")
    else:
        return os.path.join(VENV_DIR, "bin", "python")

def create_virtual_env():
    """Create virtual environment."""
    print("Creating virtual environment...")
    try:
        subprocess.check_call([sys.executable, "-m", "venv", VENV_DIR])
        print("✅ Virtual environment created successfully!")
    except subprocess.CalledProcessError as e:
        print(f"❌ Failed to create virtual environment: {e}")
        sys.exit(1)

def is_same_python(p1, p2):
    """Check if two paths point to the same Python executable."""
    try:
        return pathlib.Path(p1).resolve().samefile(pathlib.Path(p2).resolve())
    except Exception:
        return False

def install_requirements(venv_python):
    """Install all requirements from requirements.txt."""
    if not os.path.exists(REQUIREMENTS_FILE):
        print(f"⚠️ {REQUIREMENTS_FILE} not found, skipping package installation")
        return
    
    print(f"\n📦 Installing packages from {REQUIREMENTS_FILE}...")
    
    # First upgrade pip
    try:
        print("Upgrading pip...")
        subprocess.check_call(
            [venv_python, "-m", "pip", "install", "--upgrade", "pip", "--quiet"],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL
        )
    except Exception as e:
        print(f"⚠️ Could not upgrade pip: {e}")
    
    # Install all requirements at once
    try:
        print("Installing requirements...")
        result = subprocess.run(
            [venv_python, "-m", "pip", "install", "-r", REQUIREMENTS_FILE],
            capture_output=True,
            text=True
        )
        
        if result.returncode == 0:
            print("✅ All packages installed successfully!")
        else:
            print(f"⚠️ Some packages failed to install:")
            print(result.stderr)
            
            # Try installing individually
            print("\nTrying to install packages individually...")
            with open(REQUIREMENTS_FILE) as f:
                for line in f:
                    pkg = line.strip()
                    if not pkg or pkg.startswith('#'):
                        continue
                    
                    print(f"  Installing {pkg}...", end=" ")
                    try:
                        subprocess.check_call(
                            [venv_python, "-m", "pip", "install", pkg],
                            stdout=subprocess.DEVNULL,
                            stderr=subprocess.DEVNULL
                        )
                        print("✅")
                    except Exception as e:
                        print(f"❌ {e}")
    
    except Exception as e:
        print(f"❌ Error installing requirements: {e}")

def check_missing_packages():
    """Check which packages from requirements.txt are missing."""
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
            import_name = PACKAGE_IMPORT_MAPPING.get(base, base)
            
            # Check if installed
            if importlib.util.find_spec(import_name) is None:
                missing.append(pkg)
    
    return missing

def ensure_env():
    """
    Ensure virtual environment exists, has all packages, and restart if needed.
    Fully automatic - handles everything!
    """
    python_path = get_python_path()
    current_python = os.path.abspath(sys.executable)
    venv_python = os.path.abspath(python_path)
    
    print(f"Current Python: {current_python}")
    print(f"Venv Python   : {venv_python}")
    
    # Check if we're already in the venv
    in_venv = is_same_python(current_python, venv_python)
    
    if not in_venv:
        # Not in venv - need to create/use it
        
        # Create venv if it doesn't exist
        if not os.path.exists(venv_python):
            print("\n📁 Virtual environment doesn't exist.")
            create_virtual_env()
        else:
            print("\n✅ Virtual environment exists.")
        
        # Install requirements before relaunching
        print("\n📦 Checking/installing requirements...")
        install_requirements(venv_python)
        
        # Now relaunch inside venv
        print(f"\n🔄 Relaunching inside virtual environment...")
        print(f"   {venv_python}")
        
        try:
            # Use subprocess.run instead of os.execv to handle spaces in paths
            result = subprocess.run(
                [venv_python] + sys.argv,
                check=False
            )
            sys.exit(result.returncode)
            
        except Exception as e:
            print(f"❌ Failed to restart inside virtual environment: {e}")
            print(f"\n💡 You can manually run:")
            print(f"   {venv_python} main.py")
            sys.exit(1)
    
    # We're in the venv - check if packages are installed
    print("\n✅ Running inside virtual environment.")
    
    missing = check_missing_packages()
    
    if missing:
        print(f"\n⚠️ Found {len(missing)} missing package(s):")
        for pkg in missing:
            print(f"   - {pkg}")
        
        print("\n📦 Installing missing packages...")
        install_requirements(sys.executable)
        
        print("\n✅ All packages installed!")
    else:
        print("✅ All required packages are installed.")
    
    print()  # Empty line for cleaner output