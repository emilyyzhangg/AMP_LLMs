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
    # Add other mappings here as needed
}


def get_python_path():
    """Return the Python interpreter path for the virtual environment."""
    if platform.system() == "Windows":
        return os.path.join(VENV_DIR, "Scripts", "python.exe")
    else:
        return os.path.join(VENV_DIR, "bin", "python")


def create_virtual_env():
    print("🧱 Creating virtual environment...")
    try:
        subprocess.check_call([sys.executable, "-m", "venv", VENV_DIR])
    except subprocess.CalledProcessError as e:
        print(f"❌ Failed to create virtual environment: {e}")
        sys.exit(1)
    print("✅ Virtual environment created.")


def check_virtual_env():
    """Verify that the virtual environment exists and works."""
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


def clear_pip_cache():
    print("🧹 Clearing pip cache to avoid permission issues...")
    try:
        subprocess.run([sys.executable, "-m", "pip", "cache", "purge"], check=True)
    except subprocess.CalledProcessError as e:
        print(f"⚠️ Could not clear pip cache: {e}")


def install_package(package):
    python_path = get_python_path()
    try:
        print(f"📦 Installing package: {package}")
        subprocess.check_call([python_path, "-m", "pip", "install", "--upgrade", package, "--no-cache-dir"])
    except subprocess.CalledProcessError as e:
        print(f"❌ Failed to install {package}: {e}")
        sys.exit(1)


def install_requirements():
    python_path = get_python_path()

    if not os.path.exists(REQUIREMENTS_FILE):
        print(f"⚠️ No {REQUIREMENTS_FILE} found. Skipping requirements installation.")
        return

    clear_pip_cache()

    with open(REQUIREMENTS_FILE, "r") as f:
        packages = [line.strip() for line in f if line.strip() and not line.startswith("#")]

    for pkg in packages:
        base_name = pkg.split("==")[0].split(">=")[0].split("<=")[0].strip()
        import_name = PACKAGE_IMPORT_MAPPING.get(base_name, base_name)

        if importlib.util.find_spec(import_name) is None:
            install_package(pkg)
        else:
            print(f"✅ Package already installed: {import_name}")


def is_same_python(p1, p2):
    try:
        return pathlib.Path(p1).resolve().samefile(pathlib.Path(p2).resolve())
    except FileNotFoundError:
        return False


def ensure_env():
    """
    Ensures that a virtual environment exists, is up-to-date, and the script is
    re-executed inside it if needed. Mirrors the robust behavior you liked before.
    """
    python_path = get_python_path()
    current_python = os.path.abspath(sys.executable)
    venv_python = os.path.abspath(python_path)

    print(f"🐍 Current Python: {current_python}")
    print(f"🔗 Venv Python   : {venv_python}")

    if not is_same_python(current_python, venv_python):
        if not os.path.exists(venv_python):
            print("⚠️ Virtual environment missing. Creating...")
            create_virtual_env()

        print(f"🔁 Relaunching inside virtual environment:\n   {venv_python}")
        try:
            subprocess.check_call([venv_python] + sys.argv)
        except subprocess.CalledProcessError as e:
            print(f"❌ Failed to restart inside virtual environment: {e}")
            sys.exit(1)
        sys.exit(0)

    print("✅ Running inside the correct virtual environment.")

    missing_packages = []
    if os.path.exists(REQUIREMENTS_FILE):
        with open(REQUIREMENTS_FILE, "r") as f:
            for line in f:
                pkg = line.strip()
                if not pkg or pkg.startswith("#"):
                    continue
                base_name = pkg.split("==")[0].split(">=")[0].split("<=")[0].strip()
                import_name = PACKAGE_IMPORT_MAPPING.get(base_name, base_name)
                if importlib.util.find_spec(import_name) is None:
                    missing_packages.append(pkg)

        if not missing_packages:
            print("✅ All required packages installed.")
            return

        print("🔧 Upgrading pip and setuptools...")
        try:
            subprocess.check_call([venv_python, "-m", "pip", "install", "--upgrade", "pip", "setuptools"])
        except subprocess.CalledProcessError as e:
            print(f"❌ Failed to upgrade pip/setuptools: {e}")
            sys.exit(1)

        print("📦 Installing missing packages...")
        clear_pip_cache()
        for pkg in missing_packages:
            install_package(pkg)
    else:
        print("⚠️ No requirements.txt found. Skipping dependency check.")


if __name__ == "__main__":
    ensure_env()
