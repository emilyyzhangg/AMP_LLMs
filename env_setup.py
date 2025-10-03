import os
import sys
import subprocess
import shutil
import importlib.util
import platform
import pathlib

VENV_DIR = "llm_env"
REQUIREMENTS_FILE = "requirements.txt"

# Map PyPI package names to their Python import names
PACKAGE_IMPORT_MAPPING = {
    "beautifulsoup4": "bs4",
    "biopython": "Bio",
    "google-search-results": "serpapi",
    "pytest-cov": "pytest_cov",
    # Add other mappings here as needed
}

def get_python_path():
    if platform.system() == "Windows":
        return os.path.join(VENV_DIR, "Scripts", "python.exe")
    else:
        return os.path.join(VENV_DIR, "bin", "python")

def create_virtual_env():
    print("Creating virtual environment...")
    try:
        subprocess.check_call([sys.executable, "-m", "venv", VENV_DIR])
    except subprocess.CalledProcessError as e:
        print(f"Failed to create virtual environment: {e}")
        sys.exit(1)
    print("Virtual environment created.")

def check_virtual_env():
    python_path = get_python_path()
    if os.path.exists(python_path):
        try:
            result = subprocess.run([python_path, "--version"], check=True, capture_output=True)
            version = result.stdout.decode().strip() or result.stderr.decode().strip()
            print(f"Found virtual environment Python version: {version}")
            return True
        except Exception:
            shutil.rmtree(VENV_DIR, ignore_errors=True)
    return False

def install_package(package):
    python_path = get_python_path()
    try:
        print(f"Installing package: {package}")
        subprocess.check_call([python_path, "-m", "pip", "install", "--upgrade", package])
    except subprocess.CalledProcessError as e:
        print(f"Failed to install {package}: {e}")
        sys.exit(1)

def install_requirements():
    python_path = get_python_path()

    if not os.path.exists(REQUIREMENTS_FILE):
        print(f"No {REQUIREMENTS_FILE} found. Skipping requirements installation.")
        return

    with open(REQUIREMENTS_FILE, "r") as f:
        packages = [line.strip() for line in f if line.strip() and not line.startswith("#")]

    for pkg in packages:
        # Extract base package name without version specifiers
        base_name = pkg.split("==")[0].split(">=")[0].split("<=")[0].strip()

        # Get the import name from mapping or use base_name as fallback
        import_name = PACKAGE_IMPORT_MAPPING.get(base_name, base_name)

        # Check if package is already installed by import name
        if importlib.util.find_spec(import_name) is None:
            install_package(pkg)
        else:
            print(f"Package already installed: {import_name}")

def is_same_python(p1, p2):
    """Check if two python paths point to the same file."""
    try:
        return pathlib.Path(p1).resolve().samefile(pathlib.Path(p2).resolve())
    except FileNotFoundError:
        return False

def setup_environment():
    """Setup virtual environment, install requirements, and restart inside venv if needed."""
    python_path = get_python_path()
    current_python = os.path.abspath(sys.executable)
    venv_python = os.path.abspath(python_path)

    print("Current Python:", current_python)
    print("Venv Python   :", venv_python)

    # Restart script inside venv if not already inside it
    if not is_same_python(current_python, venv_python):
        if not os.path.exists(venv_python):
            create_virtual_env()
        print(f"Restarting script inside virtual environment:\n  {venv_python}")
        try:
            subprocess.check_call([venv_python] + sys.argv)
        except subprocess.CalledProcessError as e:
            print(f"Failed to restart script inside virtual environment: {e}")
            sys.exit(1)
        sys.exit(0)

    print("✅ Running inside the correct virtual environment.")

    # Upgrade pip and setuptools first
    try:
        subprocess.check_call([venv_python, "-m", "pip", "install", "--upgrade", "pip", "setuptools"])
    except subprocess.CalledProcessError as e:
        print(f"Failed to upgrade pip/setuptools: {e}")
        sys.exit(1)

    # Install all packages from requirements.txt if it exists
    if os.path.exists(REQUIREMENTS_FILE):
        print(f"Installing packages from {REQUIREMENTS_FILE} ...")
        install_requirements()
    else:
        print("No requirements.txt found; skipping requirements install.")


    # Optionally, check and install missing packages individually
    # Uncomment the following line if you want per-package checks
    # install_requirements()

if __name__ == "__main__":
    setup_environment()
