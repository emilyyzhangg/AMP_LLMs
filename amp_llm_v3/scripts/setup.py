'''Enhanced cleanup program with force delete capabilities'''
import os
import shutil
import sys
import subprocess
from pathlib import Path


def force_delete_windows(target: Path) -> bool:
    """
    Force delete directory on Windows using PowerShell.
    More reliable than shutil.rmtree for locked/in-use files.
    """
    try:
        # Use PowerShell's Remove-Item with -Force
        cmd = [
            'powershell',
            '-Command',
            f'Remove-Item -Path "{target}" -Recurse -Force -ErrorAction Stop'
        ]
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=30)
        
        if result.returncode == 0:
            return True
        else:
            print(f"⚠️  PowerShell error: {result.stderr}")
            return False
    except Exception as e:
        print(f"⚠️  PowerShell command failed: {e}")
        return False


def delete_directory_aggressive(target: Path) -> bool:
    """
    Try multiple methods to delete a directory.
    
    1. Try shutil.rmtree (standard)
    2. Try shutil.rmtree with error handler (handles read-only)
    3. On Windows: Try PowerShell force delete
    4. On Unix: Try rm -rf
    """
    if not target.exists():
        return True
    
    # Method 1: Standard deletion
    try:
        shutil.rmtree(target)
        return True
    except PermissionError:
        print(f"⚠️  Permission denied, trying alternative method...")
    except Exception as e:
        print(f"⚠️  Standard deletion failed: {e}")
    
    # Method 2: Delete with error handler (fixes read-only files)
    def handle_remove_readonly(func, path, exc):
        """Error handler for Windows read-only files."""
        import stat
        if not os.access(path, os.W_OK):
            os.chmod(path, stat.S_IWUSR | stat.S_IRUSR)
            func(path)
        else:
            raise
    
    try:
        shutil.rmtree(target, onerror=handle_remove_readonly)
        return True
    except Exception as e:
        print(f"⚠️  Read-only handler failed: {e}")
    
    # Method 3: Platform-specific force delete
    if sys.platform == 'win32':
        print(f"🔧 Attempting PowerShell force delete...")
        return force_delete_windows(target)
    else:
        # Unix/Linux/Mac: try rm -rf
        try:
            print(f"🔧 Attempting rm -rf...")
            subprocess.run(['rm', '-rf', str(target)], check=True, timeout=30)
            return True
        except Exception as e:
            print(f"⚠️  rm -rf failed: {e}")
    
    return False


def delete_dirs(root: Path, dir_names):
    """Recursively delete directories matching dir_names."""
    deleted = []
    failed = []
    
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
        print("✅ No .env file found.")
        return
    
    resp = input(f"⚠️  Found {file_path}. Delete it? [y/N]: ").strip().lower()
    if resp == "y":
        try:
            file_path.unlink()
            print(f"🗑️  Deleted: {file_path}")
        except Exception as e:
            print(f"⚠️  Could not delete {file_path}: {e}")
    else:
        print("✅ Kept .env file.")


def clean_pycache_only(root: Path):
    """Quick cleanup of just __pycache__ directories."""
    print("🧹 Quick cleanup: Removing __pycache__ only...")
    deleted, failed = delete_dirs(root, ["__pycache__"])
    
    if deleted:
        print(f"✅ Deleted {len(deleted)} __pycache__ director(ies)")
    if failed:
        print(f"⚠️  Failed to delete {len(failed)} director(ies)")
    if not deleted and not failed:
        print("✅ No __pycache__ directories found.")


def clean_all(root: Path):
    """Full cleanup: __pycache__ + llm_env + .env prompt."""
    print("🧹 Full cleanup: Removing __pycache__ and llm_env...")
    deleted, failed = delete_dirs(root, ["__pycache__", "llm_env"])
    
    if deleted:
        print(f"✅ Deleted {len(deleted)} director(ies):")
        for d in deleted:
            print(f"   • {d.name}")
    
    if failed:
        print(f"⚠️  Failed to delete {len(failed)} director(ies):")
        for d in failed:
            print(f"   • {d}")
        print("\n💡 Try running as Administrator/sudo if directories are in use")
    
    if not deleted and not failed:
        print("✅ No directories to clean.")
    
    # Handle .env deletion
    env_file = root / ".env"
    delete_file_if_confirmed(env_file)


def show_menu():
    """Show interactive cleanup menu."""
    print("\n" + "="*60)
    print("🧹 AMP_LLM Cleanup Utility")
    print("="*60)
    print("\nOptions:")
    print("  1) Quick cleanup (__pycache__ only)")
    print("  2) Full cleanup (__pycache__ + llm_env + .env)")
    print("  3) Force delete llm_env only")
    print("  4) Exit")
    print()


def main():
    root = Path(__file__).resolve().parent
    
    # Check if running from within virtual environment
    in_venv = sys.prefix != sys.base_prefix
    if in_venv:
        print("⚠️  WARNING: You are running from within a virtual environment!")
        print("   This may prevent deletion of llm_env/")
        print("   Recommend: Deactivate venv first, then run this script.\n")
        resp = input("Continue anyway? [y/N]: ").strip().lower()
        if resp != 'y':
            print("Aborted.")
            return
    
    print(f"🧭 Cleanup root: {root}\n")
    
    # Check for command line arguments
    if len(sys.argv) > 1:
        arg = sys.argv[1].lower()
        
        if arg in ('--quick', '-q'):
            clean_pycache_only(root)
        elif arg in ('--full', '-f'):
            clean_all(root)
        elif arg in ('--env', '-e'):
            print("🗑️  Force deleting llm_env...")
            target = root / "llm_env"
            if delete_directory_aggressive(target):
                print("✅ Successfully deleted llm_env/")
            else:
                print("❌ Failed to delete llm_env/")
        else:
            print(f"Unknown argument: {arg}")
            print("\nUsage:")
            print("  python cache_cleanup.py          # Interactive menu")
            print("  python cache_cleanup.py --quick  # Quick cleanup")
            print("  python cache_cleanup.py --full   # Full cleanup")
            print("  python cache_cleanup.py --env    # Delete llm_env only")
        
        print("\n🎉 Cleanup complete!")
        return
    
    # Interactive menu
    while True:
        show_menu()
        choice = input("Select option [1-4]: ").strip()
        
        if choice == '1':
            clean_pycache_only(root)
            break
        elif choice == '2':
            clean_all(root)
            break
        elif choice == '3':
            print("🗑️  Force deleting llm_env...")
            target = root / "llm_env"
            if delete_directory_aggressive(target):
                print("✅ Successfully deleted llm_env/")
            else:
                print("❌ Failed to delete llm_env/")
            break
        elif choice == '4':
            print("Exiting.")
            return
        else:
            print("❌ Invalid choice. Please select 1-4.\n")
    
    print("\n🎉 Cleanup complete!")


if __name__ == "__main__":
    main()