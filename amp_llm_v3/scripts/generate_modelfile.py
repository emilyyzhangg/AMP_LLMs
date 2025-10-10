"""
Dynamic Modelfile Generator
Generates Modelfile from validation_config.py to ensure single source of truth.

Usage:
    python generate_modelfile.py [--base llama3.2] [--output Modelfile]
"""
"""
Comprehensive test script for AMP_LLM v3.0
Verifies environment, structure, imports, and functionality.

Usage:
    python test_setup.py [--verbose] [--fix]
"""
import sys
import os
import importlib.util
import argparse
from pathlib import Path
from typing import List, Tuple


def main():
    """Main entry point."""
    parser = argparse.ArgumentParser(
        description="Test AMP_LLM v3.0 setup and environment"
    )
    parser.add_argument(
        "--verbose", "-v",
        action="store_true",
        help="Show detailed output"
    )
    parser.add_argument(
        "--fix",
        action="store_true",
        help="Attempt to fix issues automatically"
    )
    
    args = parser.parse_args()
    
    tester = V3Tester(verbose=args.verbose, fix=args.fix)
    
    try:
        success = tester.run_all_tests()
        return 0 if success else 1
    except KeyboardInterrupt:
        print(f"\n\n{Color.YELLOW}Test interrupted by user{Color.END}")
        return 1
    except Exception as e:
        print(f"\n{Color.RED}Test suite error: {e}{Color.END}")
        if args.verbose:
            import traceback
            traceback.print_exc()
        return 1

#!/usr/bin/env python3
"""
Quick setup verification script.
Checks if all required files and dependencies are in place.

Usage:
    python check_setup.py
"""
import sys
from pathlib import Path
from colorama import Fore, Style, init

init(autoreset=True)


def check_file(path: Path, description: str) -> bool:
    """Check if a file exists."""
    if path.exists():
        print(f"{Fore.GREEN}✅ {description}: {path}")
        return True
    else:
        print(f"{Fore.RED}❌ {description}: {path} (MISSING)")
        return False


def check_directory(path: Path, description: str) -> bool:
    """Check if a directory exists."""
    if path.is_dir():
        print(f"{Fore.GREEN}✅ {description}: {path}/")
        return True
    else:
        print(f"{Fore.YELLOW}⚠️  {description}: {path}/ (MISSING)")
        return False


def check_import(module_name: str) -> bool:
    """Check if a module can be imported."""
    try:
        __import__(module_name)
        print(f"{Fore.GREEN}✅ Import: {module_name}")
        return True
    except ImportError:
        print(f"{Fore.RED}❌ Import: {module_name} (FAILED)")
        return False


def main():
    """Run all checks."""
    print(f"\n{Fore.CYAN}{Style.BRIGHT}{'='*60}")
    print(f"{Fore.CYAN}AMP_LLM Setup Verification")
    print(f"{Fore.CYAN}{'='*60}{Style.RESET_ALL}\n")
    
    root = Path.cwd()
    all_good = True
    
    # Check main entry points
    print(f"{Fore.YELLOW}Main Entry Points:")
    all_good &= check_file(root / "main.py", "Root entry point")
    
    # Check scripts directory
    print(f"\n{Fore.YELLOW}Scripts Directory:")
    all_good &= check_directory(root / "scripts", "Scripts directory")
    all_good &= check_file(root / "scripts" / "setup_environment.py", "Environment setup")
    all_good &= check_file(root / "scripts" / "validate_setup.py", "Setup validation")
    all_good &= check_file(root / "scripts" / "generate_modelfile.py", "Modelfile generator")
    
    # Check src structure
    print(f"\n{Fore.YELLOW}Source Structure:")
    all_good &= check_directory(root / "src", "Source directory")
    all_good &= check_directory(root / "src" / "amp_llm", "Package directory")
    all_good &= check_file(root / "src" / "amp_llm" / "__init__.py", "Package init")
    all_good &= check_file(root / "src" / "amp_llm" / "__main__.py", "Package main")
    
    # Check core modules
    print(f"\n{Fore.YELLOW}Core Modules:")
    all_good &= check_directory(root / "src" / "amp_llm" / "core", "Core module")
    all_good &= check_file(root / "src" / "amp_llm" / "core" / "app.py", "Application class")
    all_good &= check_file(root / "src" / "amp_llm" / "core" / "menu.py", "Menu system")
    
    # Check config modules
    print(f"\n{Fore.YELLOW}Config Modules:")
    all_good &= check_directory(root / "src" / "amp_llm" / "config", "Config module")
    all_good &= check_file(root / "src" / "amp_llm" / "config" / "settings.py", "Settings")
    all_good &= check_file(root / "src" / "amp_llm" / "config" / "logging.py", "Logging")
    
    # Check LLM modules
    print(f"\n{Fore.YELLOW}LLM Modules:")
    all_good &= check_directory(root / "src" / "amp_llm" / "llm", "LLM module")
    all_good &= check_file(root / "src" / "amp_llm" / "llm" / "handlers.py", "LLM handlers")
    
    # Check data modules
    print(f"\n{Fore.YELLOW}Data Modules:")
    all_good &= check_directory(root / "src" / "amp_llm" / "data", "Data module")
    all_good &= check_file(root / "src" / "amp_llm" / "data" / "async_nct_lookup.py", "NCT lookup")
    
    # Check network modules
    print(f"\n{Fore.YELLOW}Network Modules:")
    all_good &= check_directory(root / "src" / "amp_llm" / "network", "Network module")
    all_good &= check_file(root / "src" / "amp_llm" / "network" / "shell.py", "Shell module")
    
    # Check dependencies
    print(f"\n{Fore.YELLOW}Python Dependencies:")
    deps = ['asyncssh', 'aiohttp', 'aioconsole', 'colorama', 'requests']
    for dep in deps:
        all_good &= check_import(dep)
    
    # Check optional files
    print(f"\n{Fore.YELLOW}Optional Files:")
    if check_file(root / "Modelfile", "Modelfile"):
        pass
    else:
        print(f"{Fore.CYAN}   ℹ️  Will be auto-generated on first run")
    
    if check_file(root / "requirements.txt", "Requirements"):
        pass
    else:
        print(f"{Fore.YELLOW}   ⚠️  Create requirements.txt for easy dependency management")
    
    # Summary
    print(f"\n{Fore.CYAN}{Style.BRIGHT}{'='*60}")
    if all_good:
        print(f"{Fore.GREEN}{Style.BRIGHT}✅ ALL CHECKS PASSED!")
        print(f"\n{Fore.GREEN}Your setup is ready. Run with:")
        print(f"{Fore.CYAN}  python main.py")
    else:
        print(f"{Fore.YELLOW}{Style.BRIGHT}⚠️  SOME CHECKS FAILED")
        print(f"\n{Fore.YELLOW}Fix the missing files above, then run:")
        print(f"{Fore.CYAN}  python check_setup.py")
    print(f"{Fore.CYAN}{'='*60}{Style.RESET_ALL}\n")
    
    return 0 if all_good else 1

if __name__ == "__main__":
    sys.exit(main())
