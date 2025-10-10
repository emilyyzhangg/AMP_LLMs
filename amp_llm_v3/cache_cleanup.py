'''This program will delete all pycache and env files to allow a clean install'''

import os
import shutil
from pathlib import Path

def delete_dirs(root: Path, dir_names):
    """Recursively delete directories matching dir_names."""
    deleted = []
    for dirpath, dirnames, _ in os.walk(root):
        for dirname in dirnames:
            if dirname in dir_names:
                target = Path(dirpath) / dirname
                try:
                    shutil.rmtree(target)
                    deleted.append(target)
                    print(f"🗑️  Deleted: {target}")
                except Exception as e:
                    print(f"⚠️  Could not delete {target}: {e}")
    return deleted

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

def main():
    root = Path(__file__).resolve().parent
    print(f"🧭 Starting cleanup in: {root}")

    deleted = delete_dirs(root, ["__pycache__", "llm_env"])
    if not deleted:
        print("✅ No pycache or llm_env directories found.")
    else:
        print(f"✅ Deleted {len(deleted)} directories.")

    # Handle .env deletion separately
    env_file = root / ".env"
    delete_file_if_confirmed(env_file)

    print("\n🎉 Cleanup complete!")

if __name__ == "__main__":
    main()
