"""
Main entry point for AMP_LLM application.
Handles environment setup and launches the application.
"""
import sys
from pathlib import Path

print("Starting AMP_LLM...")
print("Checking environment...")

# Step 1: Ensure environment is set up
try:
    from env_setup import ensure_env, verify_critical_imports
    
    if not ensure_env():
        print("❌ Environment setup failed. Exiting.")
        sys.exit(1)
    
    if not verify_critical_imports():
        print("❌ Critical imports failed. Exiting.")
        sys.exit(1)

except ImportError as e:
    print(f"❌ Cannot import env_setup: {e}")
    print("Make sure env_setup.py is in the project root directory.")
    sys.exit(1)

# Step 2: Add src to path if needed
src_dir = Path(__file__).parent / "src"
if src_dir.exists() and str(src_dir) not in sys.path:
    sys.path.insert(0, str(src_dir))
    print(f"✅ Added {src_dir} to Python path")

# Step 3: Launch application
print("Launching application...\n")

try:
    # Import and run the application
    import asyncio
    from src.amp_llm.core.app import Application
    
    asyncio.run(Application().run())

except KeyboardInterrupt:
    print("\n\nApplication interrupted by user.")
    sys.exit(0)

except ImportError as e:
    print(f"\n❌ Import error: {e}")
    print("\nTroubleshooting:")
    print("  1. Make sure you're in the project root directory")
    print("  2. Check that src/amp_llm/ exists")
    print("  3. Verify all packages are installed:")
    print("     pip install -r requirements.txt")
    sys.exit(1)

except Exception as e:
    print(f"\n❌ Fatal error: {e}")
    import traceback
    traceback.print_exc()
    sys.exit(1)