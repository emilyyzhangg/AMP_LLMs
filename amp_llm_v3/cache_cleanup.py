"""
AMP_LLM Cleanup Utility (Enhanced)
----------------------------------
Deletes all __pycache__ and llm_env directories recursively.
Optionally deletes .env files (with confirmation).
Now includes automatic detection and termination of locked venv processes.
"""

import os
import shutil
import sys
import subprocess
from pathlib import Path


def kill_python_processes_in_path(target_path: Path):
    """Kill any Python processes running from inside target_path."""
    print(f"🔍 Checking for running Python processes in {target_path}...")
    try:
        if sys.platform == "win32":
            result = subprocess.run(
                ["wmic", "process", "where", "name='python.exe'", "get", "ExecutablePath,ProcessId"],
                capture_output=True,
                text=True,
            )
            if result.returncode == 0:
                lines = [l.strip() for l in result.stdout.splitlines() if l.strip()]
                killed = 0
                for line in lines:
                    if target_path.as_posix().lower() in line.lower():
                        parts = line.split()
                        if parts and parts[-1].isdigit():
                            pid = parts[-1]
                            print(f"💀 Killing Python process {pid} using {line}")
                            subprocess.run(["taskkill", "/F", "/PID", pid], check=False)
                            killed += 1
                if killed:
                    print(f"✅ Terminated {killed} process(es) in {target_path}")
                else:
                    print("✅ No running Python processes found.")
            else:
                print("⚠️  Could not query Python processes.")
        else:
            # Unix/macOS version
            result = subprocess.run(["ps", "-A", "-o", "pid,command"], capture_output=True, text=True)
            if result.returncode == 0:
                lines = [l.strip() for l in result.stdout.splitlines() if "python" in l]
                killed = 0
                for line in lines:
                    if target_path.as_posix() in line:
                        pid = line.split()[0]
                        print(f"💀 Killing Python process {pid} -> {line}")
                        subprocess.run(["kill", "-9", pid], check=False)
                        killed += 1
                if killed:
                    print(f"✅ Terminated {killed} process(es) in {target_path}")
                else:
                    print("✅ No running Python processes found.")
    except Exception as e:
        print(f"⚠️  Failed to scan/kill processes: {e}")


def force_delete_windows(target: Path) -> bool:
    """Force delete directory on Windows using PowerShell."""
    try:
        cmd = [
            "powershell",
            "-Command",
            f'Remove-Item -Path "{target}" -Recurse -Force -ErrorAction Stop'
        ]
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=30)
        return result.returncode == 0
    except Exception as e:
        print(f"⚠️  PowerShell command failed: {e}")
        return False


def delete_directory_aggressive(target: Path) -> bool:
    """Try multiple deletion strategies for stubborn directories."""
    if not target.exists():
        return True

    # Try standard deletion
    try:
        shutil.rmtree(target)
        return True
    except PermissionError:
        print("⚠️  Permission denied, retrying...")
    except Exception as e:
        print(f"⚠️  Standard deletion failed: {e}")

    # Fix read-only
    def handle_remove_readonly(func, path, exc):
        import stat
        os.chmod(path, stat.S_IWRITE)
        func(path)

    try:
        shutil.rmtree(target, onerror=handle_remove_readonly)
        return True
    except Exception as e:
        print(f"⚠️  Read-only handler failed: {e}")

    # Last resort — OS-specific force delete
    if sys.platform == "win32":
        print("🔧 Attempting PowerShell force delete...")
        return force_delete_windows(target)
    else:
        print("🔧 Attempting rm -rf...")
        subprocess.run(["rm", "-rf", str(target)], check=False)
        return not target.exists()


def delete_dirs(root: Path, dir_names):
    """Recursively delete directories by name."""
    deleted, failed = [], []
    for dirpath, dirnames, _ in os.walk(root):
        for dirname in dirnames:
            if dirname in dir_names:
                target = Path(dirpath) / dirname
                print(f"🗑️  Deleting: {target}")
                if delete_directory_aggressive(target):
                    deleted.append(target)
                    print(f"✅ Deleted: {target}")
                else:
                    failed.append(target)
                    print(f"❌ Failed: {target}")
    return deleted, failed


def delete_file_if_confirmed(file_path: Path):
    """Prompt to delete .env file."""
    if not file_path.exists():
        return
    resp = input(f"⚠️  Delete {file_path.name}? [y/N]: ").strip().lower()
    if resp == "y":
        try:
            file_path.unlink()
            print(f"🗑️  Deleted: {file_path}")
        except Exception as e:
            print(f"⚠️  Could not delete: {e}")
    else:
        print("✅ Kept .env file.")


def clean_all(root: Path):
    """Full cleanup: kills venv processes, removes llm_env + __pycache__."""
    llm_env = root / "llm_env"
    if llm_env.exists():
        kill_python_processes_in_path(llm_env)

    print("🧹 Cleaning __pycache__ and llm_env...")
    deleted, failed = delete_dirs(root, ["__pycache__", "llm_env"])

    if deleted:
        print(f"✅ Deleted {len(deleted)} folder(s).")
    if failed:
        print(f"⚠️  Failed to delete {len(failed)} folder(s).")
        print("💡 Try running as Administrator if they remain locked.")

    delete_file_if_confirmed(root / ".env")


def show_menu():
    print("\n" + "=" * 60)
    print("🧹 AMP_LLM Cleanup Utility")
    print("=" * 60)
    print("  1) Clean __pycache__ + llm_env")
    print("  2) Delete only llm_env (force)")
    print("  3) Exit\n")


def main():
    root = Path(__file__).resolve().parent
    print(f"🧭 Root: {root}")

    while True:
        show_menu()
        choice = input("Select option [1-3]: ").strip()
        if choice == "1":
            clean_all(root)
            break
        elif choice == "2":
            kill_python_processes_in_path(root / "llm_env")
            target = root / "llm_env"
            print("🗑️  Force deleting llm_env...")
            if delete_directory_aggressive(target):
                print("✅ Successfully deleted llm_env/")
            else:
                print("❌ Failed to delete llm_env/")
            break
        elif choice == "3":
            print("👋 Exiting.")
            return
        else:
            print("❌ Invalid choice.")


if __name__ == "__main__":
    main()
