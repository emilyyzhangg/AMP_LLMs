import os
import sys
import subprocess
import shutil
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

def is_same_python(p1, p2):
    try:
        return pathlib.Path(p1).resolve().samefile(pathlib.Path(p2).resolve())
    except Exception:
        return False

def ensure_env():
    """Ensure virtualenv exists and relaunch inside it if needed. Preserves original functionality."""
    python_path = get_python_path()
    current_python = os.path.abspath(sys.executable)
    venv_python = os.path.abspath(python_path)
    print(f"Current Python: {current_python}")
    print(f"Venv Python   : {venv_python}")
    if not is_same_python(current_python, venv_python):
        if not os.path.exists(venv_python):
            print("Virtual environment missing. Creating...")
            create_virtual_env()
        print(f"Relaunching inside virtual environment: {venv_python}")
        try:
            os.execv(venv_python, [venv_python] + sys.argv)
        except Exception as e:
            print(f"Failed to restart inside virtual environment: {e}")
            sys.exit(1)
    print("Running inside the correct virtual environment.")
    # Install missing packages if requirements exists
    missing = []
    if os.path.exists(REQUIREMENTS_FILE):
        with open(REQUIREMENTS_FILE) as f:
            for line in f:
                pkg = line.strip()
                if not pkg or pkg.startswith('#'): continue
                base = pkg.split('==')[0].split('>=')[0].split('<=')[0].strip()
                import_name = PACKAGE_IMPORT_MAPPING.get(base, base)
                if importlib.util.find_spec(import_name) is None:
                    missing.append(pkg)
        if missing:
            try:
                subprocess.check_call([venv_python, "-m", "pip", "install", "--upgrade", "pip", "setuptools"])
            except Exception as e:
                print(f"Failed to upgrade pip: {e}")
            for pkg in missing:
                try:
                    subprocess.check_call([venv_python, "-m", "pip", "install", pkg])
                except Exception as e:
                    print(f"Failed to install {pkg}: {e}")
