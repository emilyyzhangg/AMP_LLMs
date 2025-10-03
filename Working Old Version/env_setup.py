import os
import sys
import platform
import subprocess
import shutil

VENV_DIR = "llm_env"

def get_python_path():
    """Return the path to the python executable inside the virtual env."""
    if platform.system() == "Windows":
        return os.path.join(VENV_DIR, "Scripts", "python.exe")
    else:
        return os.path.join(VENV_DIR, "bin", "python")

def create_virtual_env():
    """Create a virtual environment."""
    print("Creating virtual environment...")
    try:
        subprocess.check_call([sys.executable, "-m", "venv", VENV_DIR])
        print("Virtual environment created.")
    except subprocess.CalledProcessError as e:
        print(f"Failed to create virtual environment: {e}")
        sys.exit(1)

def check_virtual_env():
    """Check if the virtual environment is present and usable."""
    python_path = get_python_path()
    if os.path.exists(python_path):
        try:
            result = subprocess.run([python_path, "--version"], check=True, capture_output=True)
            print(f"Found virtual environment Python version: {result.stdout.decode().strip() or result.stderr.decode().strip()}")
            return True
        except Exception:
            print("Existing virtual environment is broken. Removing...")
            try:
                shutil.rmtree(VENV_DIR)
                print("Removed broken virtual environment.")
            except Exception as e:
                print(f"Failed to remove broken virtual environment: {e}")
                sys.exit(1)
    return False

def ensure_requirements():
    """Ensure dependencies are installed."""
    requirements_file = "requirements.txt"
    python_path = get_python_path()

    if not os.path.exists(requirements_file):
        print(f"'{requirements_file}' not found, creating with default dependencies.")
        with open(requirements_file, "w") as f:
            f.write("paramiko\npandas\nopenpyxl\n")

    print("Installing/upgrading dependencies...")
    try:
        subprocess.check_call([python_path, "-m", "pip", "install", "--upgrade", "pip"])
        subprocess.check_call([python_path, "-m", "pip", "install", "-r", requirements_file])
        print("Dependencies installed.")
    except subprocess.CalledProcessError as e:
        print(f"Failed to install dependencies: {e}")
        sys.exit(1)

def setup_environment():
    """Check/setup virtual env, install requirements, and restart if needed."""
    if not check_virtual_env():
        create_virtual_env()

    python_path = get_python_path()
    current_python = os.path.abspath(sys.executable)
    venv_python = os.path.abspath(python_path)

    # Restart script inside virtualenv if not already running there
    if current_python != venv_python:
        print("Restarting inside virtual environment...")
        try:
            subprocess.check_call([venv_python] + sys.argv)
        except subprocess.CalledProcessError as e:
            print(f"Failed to restart inside virtual environment: {e}")
            sys.exit(1)
        sys.exit(0)

    ensure_requirements()
