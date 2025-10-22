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
from src.amp_llm.config import StudyStatus, Phase, Classification


class Color:
    """ANSI color codes."""
    GREEN = '\033[92m'
    RED = '\033[91m'
    YELLOW = '\033[93m'
    BLUE = '\033[94m'
    CYAN = '\033[96m'
    BOLD = '\033[1m'
    END = '\033[0m'


class TestResult:
    """Represents test result."""
    def __init__(self, name: str, passed: bool, message: str = ""):
        self.name = name
        self.passed = passed
        self.message = message
    
    def __str__(self):
        status = f"{Color.GREEN}✅ PASS{Color.END}" if self.passed else f"{Color.RED}❌ FAIL{Color.END}"
        msg = f" - {self.message}" if self.message else ""
        return f"{status} - {self.name}{msg}"


class V3Tester:
    """Test suite for v3.0 structure."""
    
    def __init__(self, verbose=False, fix=False):
        self.verbose = verbose
        self.fix = fix
        self.root = Path.cwd()
        self.results: List[TestResult] = []
    
    def log(self, message: str, level="INFO"):
        """Log messages if verbose."""
        if self.verbose or level in ("ERROR", "WARNING"):
            prefix = {
                "INFO": f"{Color.BLUE}ℹ️{Color.END}",
                "SUCCESS": f"{Color.GREEN}✅{Color.END}",
                "WARNING": f"{Color.YELLOW}⚠️{Color.END}",
                "ERROR": f"{Color.RED}❌{Color.END}",
            }
            print(f"{prefix.get(level, '')} {message}")
    
    def add_result(self, name: str, passed: bool, message: str = ""):
        """Add test result."""
        result = TestResult(name, passed, message)
        self.results.append(result)
        if self.verbose:
            print(f"  {result}")
    
    def test_python_version(self):
        """Test Python version."""
        self.log("Testing Python version...")
        
        version = sys.version_info
        required = (3, 8)
        
        passed = version >= required
        message = f"Python {version.major}.{version.minor}.{version.micro}"
        
        if not passed:
            message += f" (requires >= {required[0]}.{required[1]})"
        
        self.add_result("Python Version", passed, message)
    
    def test_directory_structure(self):
        """Test directory structure."""
        self.log("Testing directory structure...")
        
        required_dirs = [
            "core",
            "llm",
            "data",
            "network",
        ]
        
        optional_dirs = [
            "ct_database",
            "output",
            "docs",
            "tests",
        ]
        
        all_good = True
        missing = []
        
        for dir_name in required_dirs:
            dir_path = self.root / dir_name
            if not dir_path.exists():
                all_good = False
                missing.append(dir_name)
                self.log(f"Missing required directory: {dir_name}", "ERROR")
            elif self.verbose:
                self.log(f"Found: {dir_name}", "SUCCESS")
        
        for dir_name in optional_dirs:
            dir_path = self.root / dir_name
            if not dir_path.exists():
                self.log(f"Optional directory missing: {dir_name}", "WARNING")
            elif self.verbose:
                self.log(f"Found: {dir_name}", "SUCCESS")
        
        message = f"Found all required directories" if all_good else f"Missing: {', '.join(missing)}"
        self.add_result("Directory Structure", all_good, message)
        
        # Offer to create missing directories
        if not all_good and self.fix:
            self.log("Creating missing directories...", "INFO")
            for dir_name in missing:
                (self.root / dir_name).mkdir(exist_ok=True)
                (self.root / dir_name / "__init__.py").touch()
            self.log("Directories created", "SUCCESS")
    
    def test_core_files(self):
        """Test core module files."""
        self.log("Testing core module files...")
        
        required_files = [
            "core/__init__.py",
            "core/app.py",
            "core/menu.py",
        ]
        
        all_good = True
        missing = []
        
        for file_path in required_files:
            full_path = self.root / file_path
            if not full_path.exists():
                all_good = False
                missing.append(file_path)
                self.log(f"Missing: {file_path}", "ERROR")
            elif self.verbose:
                # Check if file has content
                size = full_path.stat().st_size
                self.log(f"Found: {file_path} ({size} bytes)", "SUCCESS")
        
        message = "All core files present" if all_good else f"Missing: {', '.join(missing)}"
        self.add_result("Core Module Files", all_good, message)
    
    def test_required_packages(self):
        """Test required packages are installed."""
        self.log("Testing required packages...")
        
        required_packages = {
            'asyncssh': 'asyncssh',
            'aiohttp': 'aiohttp',
            'aioconsole': 'aioconsole',
            'colorama': 'colorama',
            'requests': 'requests',
            'dotenv': 'python-dotenv',
        }
        
        missing = []
        installed = []
        
        for import_name, package_name in required_packages.items():
            if importlib.util.find_spec(import_name) is None:
                missing.append(package_name)
                self.log(f"Missing package: {package_name}", "ERROR")
            else:
                installed.append(package_name)
                if self.verbose:
                    try:
                        module = importlib.import_module(import_name)
                        version = getattr(module, '__version__', 'unknown')
                        self.log(f"Installed: {package_name} ({version})", "SUCCESS")
                    except:
                        self.log(f"Installed: {package_name}", "SUCCESS")
        
        all_good = len(missing) == 0
        
        if missing:
            message = f"Missing: {', '.join(missing)}"
            if self.fix:
                self.log("Installing missing packages...", "INFO")
                import subprocess
                for pkg in missing:
                    try:
                        subprocess.check_call([sys.executable, "-m", "pip", "install", pkg])
                        self.log(f"Installed: {pkg}", "SUCCESS")
                    except:
                        self.log(f"Failed to install: {pkg}", "ERROR")
        else:
            message = f"All {len(installed)} packages installed"
        
        self.add_result("Required Packages", all_good, message)
    
    def test_imports(self):
        """Test critical imports."""
        self.log("Testing imports...")
        
        imports_to_test = [
            ("config", "get_config"),
            ("config", "get_logger"),
        ]
        
        # Only test core imports if core exists
        if (self.root / "core" / "app.py").exists():
            imports_to_test.extend([
                ("core.app", "AMPLLMApp"),
                ("core.menu", "MenuSystem"),
            ])
        
        all_good = True
        failures = []
        
        for module_name, attr_name in imports_to_test:
            try:
                module = importlib.import_module(module_name)
                if not hasattr(module, attr_name):
                    all_good = False
                    failures.append(f"{module_name}.{attr_name}")
                    self.log(f"Missing attribute: {module_name}.{attr_name}", "ERROR")
                elif self.verbose:
                    self.log(f"Import OK: {module_name}.{attr_name}", "SUCCESS")
            except ImportError as e:
                all_good = False
                failures.append(module_name)
                self.log(f"Import failed: {module_name} - {e}", "ERROR")
        
        message = "All imports successful" if all_good else f"Failed: {', '.join(failures)}"
        self.add_result("Critical Imports", all_good, message)
    
    def test_configuration(self):
        """Test configuration system."""
        self.log("Testing configuration...")
        
        try:
            from amp_llm.config import get_config
            config = get_config()
            
            # Check critical config attributes
            checks = [
                hasattr(config, 'network'),
                hasattr(config, 'api'),
                hasattr(config, 'llm'),
                hasattr(config, 'output'),
            ]
            
            all_good = all(checks)
            
            if all_good and self.verbose:
                self.log(f"Default IP: {config.network.default_ip}", "INFO")
                self.log(f"Output dir: {config.output.output_dir}", "INFO")
            
            message = "Configuration loaded successfully"
            
        except Exception as e:
            all_good = False
            message = f"Config error: {e}"
            self.log(message, "ERROR")
        
        self.add_result("Configuration System", all_good, message)
    
    def test_rag_system(self):
        """Test RAG system if database exists."""
        self.log("Testing RAG system...")
        
        db_path = self.root / "ct_database"
        
        if not db_path.exists():
            self.add_result("RAG System", True, "Skipped (no database)")
            return
        
        try:
            from amp_llm.data.rag import ClinicalTrialRAG
            
            rag = ClinicalTrialRAG(db_path)
            rag.db.build_index()
            
            trial_count = len(rag.db.trials)
            all_good = trial_count > 0
            
            message = f"Indexed {trial_count} trials" if all_good else "No trials found"
            
            if self.verbose and trial_count > 0:
                # Show first few trial IDs
                sample = list(rag.db.trials.keys())[:3]
                self.log(f"Sample trials: {', '.join(sample)}", "INFO")
            
        except Exception as e:
            all_good = False
            message = f"RAG error: {e}"
            self.log(message, "ERROR")
        
        self.add_result("RAG System", all_good, message)
    
    def test_modelfile(self):
        """Test Modelfile exists."""
        self.log("Testing Modelfile...")
        
        modelfile_path = self.root / "Modelfile"
        
        if not modelfile_path.exists():
            all_good = False
            message = "Modelfile not found"
        else:
            size = modelfile_path.stat().st_size
            all_good = size > 100  # Should be substantial
            
            if all_good:
                message = f"Found ({size} bytes)"
                
                # Check for critical content
                content = modelfile_path.read_text()
                if "FROM" not in content or "SYSTEM" not in content:
                    all_good = False
                    message = "Modelfile incomplete"
            else:
                message = "Modelfile too small"
        
        self.add_result("Modelfile", all_good, message)
    
    def test_env_setup(self):
        """Test env_setup.py."""
        self.log("Testing env_setup.py...")
        
        env_setup_path = self.root / "scripts/setup_environment.py"
        
        if not env_setup_path.exists():
            all_good = False
            message = "env_setup.py not found"
        else:
            try:
                from scripts.setup import ensure_env, verify_critical_imports
                
                all_good = True
                message = "env_setup.py functional"
                
                if self.verbose:
                    self.log("Functions: ensure_env, verify_critical_imports", "SUCCESS")
                
            except Exception as e:
                all_good = False
                message = f"Import error: {e}"
        
        self.add_result("Environment Setup", all_good, message)
    
    def test_requirements_file(self):
        """Test requirements.txt."""
        self.log("Testing requirements.txt...")
        
        req_path = self.root / "requirements.txt"
        
        if not req_path.exists():
            all_good = False
            message = "requirements.txt not found"
        else:
            content = req_path.read_text()
            lines = [l.strip() for l in content.split('\n') if l.strip() and not l.startswith('#')]
            
            required_packages = ['asyncssh', 'aiohttp', 'aioconsole', 'colorama']
            found_packages = [pkg.split('>=')[0].split('==')[0] for pkg in lines]
            
            missing = [pkg for pkg in required_packages if pkg not in found_packages]
            
            all_good = len(missing) == 0
            
            if all_good:
                message = f"{len(lines)} packages listed"
            else:
                message = f"Missing: {', '.join(missing)}"
        
        self.add_result("Requirements File", all_good, message)
    
    def test_file_permissions(self):
        """Test file permissions."""
        self.log("Testing file permissions...")
        
        critical_files = [
            "main.py",
            "config.py",
            "env_setup.py",
        ]
        
        all_good = True
        issues = []
        
        for file_name in critical_files:
            file_path = self.root / file_name
            
            if not file_path.exists():
                continue
            
            # Check if file is readable
            if not os.access(file_path, os.R_OK):
                all_good = False
                issues.append(f"{file_name} not readable")
            
            # Check if Python files are executable (Unix-like)
            if file_name.endswith('.py') and os.name != 'nt':
                if not os.access(file_path, os.X_OK):
                    self.log(f"Warning: {file_name} not executable", "WARNING")
        
        message = "All files accessible" if all_good else ", ".join(issues)
        self.add_result("File Permissions", all_good, message)
    
    def print_summary(self):
        """Print test summary."""
        print(f"\n{Color.BOLD}{'='*60}{Color.END}")
        print(f"{Color.BOLD}TEST SUMMARY{Color.END}")
        print(f"{Color.BOLD}{'='*60}{Color.END}\n")
        
        passed = sum(1 for r in self.results if r.passed)
        total = len(self.results)
        
        for result in self.results:
            print(result)
        
        print(f"\n{Color.BOLD}{'='*60}{Color.END}")
        
        if passed == total:
            print(f"{Color.GREEN}{Color.BOLD}✅ ALL TESTS PASSED ({passed}/{total}){Color.END}")
            print(f"{Color.GREEN}Your environment is ready to use!{Color.END}")
        else:
            failed = total - passed
            print(f"{Color.YELLOW}{Color.BOLD}⚠️  {failed} TEST(S) FAILED ({passed}/{total} passed){Color.END}")
            print(f"{Color.YELLOW}Some features may not work correctly.{Color.END}")
            
            if self.fix:
                print(f"\n{Color.CYAN}Some issues were automatically fixed.{Color.END}")
                print(f"{Color.CYAN}Run the test again to verify.{Color.END}")
            else:
                print(f"\n{Color.CYAN}Try running with --fix to auto-repair issues:{Color.END}")
                print(f"{Color.CYAN}  python test_setup.py --fix{Color.END}")
        
        print(f"{Color.BOLD}{'='*60}{Color.END}\n")
        
        return passed == total
    
    def run_all_tests(self):
        """Run all tests."""
        print(f"{Color.BOLD}{Color.CYAN}AMP_LLM v3.0 Test Suite{Color.END}")
        print(f"{Color.CYAN}Testing environment and structure...{Color.END}\n")
        
        # Core tests
        self.test_python_version()
        self.test_directory_structure()
        self.test_core_files()
        self.test_required_packages()
        
        # Import tests
        self.test_imports()
        self.test_configuration()
        
        # Feature tests
        self.test_rag_system()
        self.test_modelfile()
        
        # Setup tests
        self.test_env_setup()
        self.test_requirements_file()
        self.test_file_permissions()
        
        # Print summary
        return self.print_summary()


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


if __name__ == "__main__":
    sys.exit(main())