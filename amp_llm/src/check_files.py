"""
Check if all required files exist and show what needs to be created.
"""
from pathlib import Path

def check_files():
    """Check required files."""
    print("🔍 Checking file structure...\n")
    
    required_files = {
        'src/amp_llm/llm/handlers.py': 'CREATE - New file needed',
        'src/amp_llm/llm/__init__.py': 'UPDATE - Add handler exports',
        'src/amp_llm/llm/clients/ollama_api.py': 'Should exist',
        'src/amp_llm/llm/clients/ollama_ssh.py': 'Should exist',
        'src/amp_llm/core/menu.py': 'UPDATE - Fix imports',
        'src/amp_llm/network/shell.py': 'Should exist',
        'src/amp_llm/data/async_nct_lookup.py': 'Should exist',
    }
    
    missing = []
    exists = []
    
    for file_path, note in required_files.items():
        path = Path(file_path)
        if path.exists():
            print(f"✅ {file_path}")
            exists.append(file_path)
        else:
            print(f"❌ {file_path} - {note}")
            missing.append((file_path, note))
    
    print("\n" + "="*60)
    
    if not missing:
        print("🎉 All required files exist!")
        print("\nNext steps:")
        print("  1. Update src/amp_llm/llm/__init__.py")
        print("  2. Update src/amp_llm/core/menu.py")
        print("  3. Run: python main.py")
    else:
        print(f"⚠️  {len(missing)} file(s) need attention:\n")
        for file_path, note in missing:
            print(f"  📝 {file_path}")
            print(f"     {note}\n")
        
        if 'src/amp_llm/llm/handlers.py' in [f for f, _ in missing]:
            print("\n💡 Priority: Create handlers.py first!")
            print("   This is the new file that provides LLM entry points.")

if __name__ == "__main__":
    check_files()