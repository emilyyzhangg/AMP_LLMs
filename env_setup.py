import os
import sys
import subprocess
import shutil
import importlib.util
import platform

VENV_DIR = "llm_env"
REQUIREMENTS_FILE = "requirements.txt"

def get_python_path():
    if platform.system() == "Windows":
        return os.path.join(VENV_DIR, "Scripts", "python.exe")
    else:
        return os.path.join(VENV_DIR, "bin", "python")

def create_virtual_env():
    print("Creating virtual environment...")
    subprocess.check_call([sys.executable, "-m", "venv", VENV_DIR])
    print("Virtual environment created.")

def check_virtual_env():
    python_path = get_python_path()
    if os.path.exists(python_path):
        try:
            result = subprocess.run([python_path, "--version"], check=True, capture_output=True)
            print(f"Found virtual environment Python version: {result.stdout.decode().strip() or result.stderr.decode().strip()}")
            return True
        except Exception:
            shutil.rmtree(VENV_DIR, ignore_errors=True)
    return False

def install_package(package):
    python_path = get_python_path()
    subprocess.check_call([python_path, "-m", "pip", "install", "--upgrade", package])

def install_requirements():
    python_path = get_python_path()
    if not os.path.exists(REQUIREMENTS_FILE):
        open(REQUIREMENTS_FILE, "w").close()

    # Read packages from requirements.txt
    with open(REQUIREMENTS_FILE, "r") as f:
        packages = [line.strip() for line in f if line.strip() and not line.startswith("#")]

    # Check each package dynamically
    for pkg in packages:
        name = pkg.split("==")[0].split(">=")[0].split("<=")[0].strip()
        if importlib.util.find_spec(name) is None:
            print(f"Installing missing package: {pkg}")
            install_package(pkg)
        else:
            print(f"Package already installed: {name}")

import pathlib

def is_same_python(p1, p2):
    """Check if two python paths point to the same file."""
    return pathlib.Path(p1).resolve().samefile(pathlib.Path(p2).resolve())

def setup_environment():
    """Setup virtual environment, install requirements, and restart inside venv if needed."""
    python_path = get_python_path()
    current_python = os.path.abspath(sys.executable)
    venv_python = os.path.abspath(python_path)
    
    print("Current Python:", current_python)
    print("Venv Python   :", venv_python)
    # Check if we're already in the virtual environment
    if not is_same_python(current_python, venv_python):
        if not os.path.exists(venv_python):
            create_virtual_env()
        print(f"Restarting script inside virtual environment:\n  {venv_python}")
        subprocess.check_call([venv_python] + sys.argv)
        sys.exit(0)

    print("✅ Running inside the correct virtual environment.")

    # Upgrade pip and install requirements
    subprocess.check_call([venv_python, "-m", "pip", "install", "--upgrade", "pip"])

    if os.path.exists(REQUIREMENTS_FILE):
        subprocess.check_call([venv_python, "-m", "pip", "install", "-r", REQUIREMENTS_FILE])
    else:
        print("No requirements.txt found; skipping requirements install.")

    install_requirements()

