"""
AMP_LLM Cleanup Utility (Enhanced with Fixed Process Detection)
----------------------------------------------------------------
Deletes all __pycache__ and llm_env directories recursively.
Optionally deletes .env files (with confirmation).
Includes automatic detection and termination of locked venv processes.
"""

import os
import shutil
import sys
import subprocess
import time
from pathlib import Path


def kill_python_processes_in_path(target_path: Path):
    """Kill any Python processes running from inside target_path."""
    print(f"🔍 Checking for running Python processes in {target_path}...")
    try:
        if sys.platform == "win32":
            # Use tasklist instead of wmic for better compatibility
            result = subprocess.run(
                ["tasklist", "/FI", "IMAGENAME eq python.exe", "/FO", "CSV", "/V"],
                capture_output=True,
                text=True,
                timeout=10
            )
            
            if result.returncode == 0:
                killed = 0
                target_str = str(target_path).lower()
                
                # Parse CSV output
                lines = result.stdout.splitlines()
                for line in lines[1:]:  # Skip header
                    if "python.exe" in line.lower():
                        parts = [p.strip('"') for p in line.split('","')]
                        if len(parts) > 1:
                            pid = parts[1]
                            # Check if process command line contains our path
                            process_info = subprocess.run(
                                ["wmic", "process", "where", f"ProcessId={pid}", "get", "CommandLine"],
                                capture_output=True,
                                text=True,
                                timeout=5
                            )
                            if process_info.returncode == 0 and target_str in process_info.stdout.lower():
                                print(f"💀 Killing Python process PID {pid}")
                                subprocess.run(["taskkill", "/F", "/PID", pid], check=False)
                                killed += 1
                                time.sleep(0.5)  # Give it time to die
                
                # Alternative: Kill ALL python.exe processes if none matched
                if killed == 0:
                    print("⚠️  Couldn't match processes to path. Trying broader approach...")
                    result2 = subprocess.run(
                        ["tasklist", "/FI", "IMAGENAME eq python.exe", "/NH"],
                        capture_output=True,
                        text=True
                    )
                    if result2.returncode == 0:
                        for line in result2.stdout.splitlines():
                            if "python.exe" in line:
                                parts = line.split()
                                if len(parts) >= 2:
                                    pid = parts[1]
                                    print(f"💀 Killing Python process PID {pid}")
                                    subprocess.run(["taskkill", "/F", "/PID", pid], check=False)
                                    killed += 1
                                    time.sleep(0.5)
                
                if killed:
                    print(f"✅ Terminated {killed} process(es)")
                    time.sleep(1)  # Wait for file handles to release
                else:
                    print("✅ No Python processes found to terminate.")
            else:
                print("⚠️  Could not query Python processes with tasklist.")
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
    except subprocess.TimeoutExpired:
        print("⚠️  Process scan timed out")
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
        try:
            os.chmod(path, stat.S_IWRITE)
            func(path)
        except Exception:
            pass

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
        print("💡 Try closing all terminals and running as Administrator.")

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
            venv_path = root.parent / "llm_env"
            kill_python_processes_in_path(venv_path)
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