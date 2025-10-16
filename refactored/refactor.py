#!/usr/bin/env python3
"""
AMP LLM v3 Refactoring Script
Reorganizes codebase according to the improved architecture plan.

Usage:
    python refactor.py [--dry-run] [--backup]
    
Options:
    --dry-run    Show what would be done without making changes
    --backup     Create backup before refactoring
"""

import os
import shutil
import argparse
from pathlib import Path
from datetime import datetime
from typing import Dict, List, Tuple


class RefactorManager:
    """Manages the refactoring process."""
    
    def __init__(self, root_dir: Path, dry_run: bool = False, backup: bool = False):
        self.root = root_dir
        self.dry_run = dry_run
        self.backup = backup
        self.moves: List[Tuple[Path, Path]] = []
        self.creates: List[Path] = []
        self.deletes: List[Path] = []
        
    def log(self, message: str, indent: int = 0):
        """Log a message with optional indentation."""
        prefix = "  " * indent
        print(f"{prefix}{message}")
    
    def create_backup(self):
        """Create a backup of the current state."""
        if not self.backup:
            return
            
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        backup_dir = self.root / f"backup_{timestamp}"
        
        self.log(f"Creating backup: {backup_dir}")
        shutil.copytree(
            self.root / "src/amp_llm",
            backup_dir,
            ignore=shutil.ignore_patterns('__pycache__', '*.pyc', '.git')
        )
        self.log("✅ Backup created")
    
    def move_file(self, source: Path, dest: Path):
        """Move a file from source to destination."""
        self.moves.append((source, dest))
        
        if self.dry_run:
            self.log(f"MOVE: {source} → {dest}", 1)
        else:
            dest.parent.mkdir(parents=True, exist_ok=True)
            if source.exists():
                shutil.move(str(source), str(dest))
                self.log(f"✅ Moved: {source.name} → {dest}", 1)
    
    def create_file(self, path: Path, content: str = ""):
        """Create a new file with optional content."""
        self.creates.append(path)
        
        if self.dry_run:
            self.log(f"CREATE: {path}", 1)
        else:
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(content)
            self.log(f"✅ Created: {path}", 1)
    
    def delete_path(self, path: Path):
        """Delete a file or directory."""
        self.deletes.append(path)
        
        if self.dry_run:
            self.log(f"DELETE: {path}", 1)
        else:
            if path.is_dir():
                shutil.rmtree(path, ignore_errors=True)
            elif path.exists():
                path.unlink()
            self.log(f"✅ Deleted: {path}", 1)
    
    def update_imports_in_file(self, file_path: Path, replacements: Dict[str, str]):
        """Update import statements in a Python file."""
        if not file_path.exists() or self.dry_run:
            return
        
        # Try multiple encodings
        content = None
        encodings = ['utf-8', 'utf-8-sig', 'latin-1', 'cp1252']
        
        for encoding in encodings:
            try:
                content = file_path.read_text(encoding=encoding)
                break
            except (UnicodeDecodeError, LookupError):
                continue
        
        if content is None:
            self.log(f"⚠️  Could not read {file_path.name} (encoding issues)", 2)
            return
        
        modified = False
        
        for old_import, new_import in replacements.items():
            if old_import in content:
                content = content.replace(old_import, new_import)
                modified = True
        
        if modified:
            try:
                file_path.write_text(content, encoding='utf-8')
                self.log(f"✅ Updated imports: {file_path.name}", 2)
            except Exception as e:
                self.log(f"⚠️  Could not write {file_path.name}: {e}", 2)


# =============================================================================
# PHASE 1: Core Infrastructure
# =============================================================================

def phase1_consolidate_core(manager: RefactorManager):
    """Phase 1: Consolidate core infrastructure."""
    manager.log("\n" + "="*60)
    manager.log("PHASE 1: Consolidating Core Infrastructure")
    manager.log("="*60)
    
    src = manager.root / "src/amp_llm"
    
    # 1.1: Consolidate SSH management
    manager.log("\n📦 Consolidating SSH management...")
    manager.move_file(
        src / "network/ssh.py",
        src / "core/ssh_manager.py"
    )
    
    # 1.2: Clean up config imports - ensure validation.py exists
    manager.log("\n📦 Ensuring config/validation.py exists...")
    validation_content = '''"""
Single source of truth for validation enums.
All validation rules consolidated here.
"""
from enum import Enum

class StudyStatus(str, Enum):
    """Valid study status values."""
    NOT_YET_RECRUITING = "NOT_YET_RECRUITING"
    RECRUITING = "RECRUITING"
    ENROLLING_BY_INVITATION = "ENROLLING_BY_INVITATION"
    ACTIVE_NOT_RECRUITING = "ACTIVE_NOT_RECRUITING"
    COMPLETED = "COMPLETED"
    SUSPENDED = "SUSPENDED"
    TERMINATED = "TERMINATED"
    WITHDRAWN = "WITHDRAWN"
    UNKNOWN = "UNKNOWN"

class Phase(str, Enum):
    """Valid phase values."""
    EARLY_PHASE1 = "EARLY_PHASE1"
    PHASE1 = "PHASE1"
    PHASE1_PHASE2 = "PHASE1|PHASE2"
    PHASE2 = "PHASE2"
    PHASE2_PHASE3 = "PHASE2|PHASE3"
    PHASE3 = "PHASE3"
    PHASE4 = "PHASE4"

class Classification(str, Enum):
    """Valid classification values."""
    AMP = "AMP"
    OTHER = "Other"

class DeliveryMode(str, Enum):
    """Valid delivery mode values."""
    INJECTION_INFUSION = "Injection/Infusion"
    ORAL = "Oral"
    TOPICAL = "Topical"
    OTHER_UNSPECIFIED = "Other/Unspecified"

class Outcome(str, Enum):
    """Valid outcome values."""
    POSITIVE = "Positive"
    WITHDRAWN = "Withdrawn"
    TERMINATED = "Terminated"
    FAILED_COMPLETED = "Failed - completed trial"
    ACTIVE = "Active"
    UNKNOWN = "Unknown"

class FailureReason(str, Enum):
    """Valid failure reason values."""
    BUSINESS_REASON = "Business Reason"
    INEFFECTIVE = "Ineffective for purpose"
    TOXIC_UNSAFE = "Toxic/Unsafe"
    RECRUITMENT_ISSUES = "Recruitment issues"
    UNKNOWN = "Unknown"
    NOT_APPLICABLE = "N/A"
'''
    
    if not (src / "config/validation.py").exists():
        manager.create_file(src / "config/validation.py", validation_content)


# =============================================================================
# PHASE 2: Data Layer Reorganization
# =============================================================================

def phase2_reorganize_data_layer(manager: RefactorManager):
    """Phase 2: Reorganize data layer."""
    manager.log("\n" + "="*60)
    manager.log("PHASE 2: Reorganizing Data Layer")
    manager.log("="*60)
    
    src = manager.root / "src/amp_llm"
    
    # 2.1: Merge external_apis into api_clients/extended
    manager.log("\n📦 Merging external_apis into api_clients/extended...")
    
    # These files should already be in extended, just ensure structure
    extended_dir = src / "data/api_clients/extended"
    extended_dir.mkdir(parents=True, exist_ok=True)
    
    # 2.2: Extract RAG into separate package structure
    manager.log("\n📦 Organizing RAG system...")
    rag_dir = src / "data/rag"
    rag_dir.mkdir(parents=True, exist_ok=True)
    
    # RAG __init__.py
    rag_init = '''"""
RAG (Retrieval-Augmented Generation) system for clinical trials.
"""
from .system import ClinicalTrialRAG
from .database import ClinicalTrialDatabase

__all__ = ['ClinicalTrialRAG', 'ClinicalTrialDatabase']
'''
    manager.create_file(rag_dir / "__init__.py", rag_init)
    
    # 2.3: Move NCT lookup to workflows
    manager.log("\n📦 Moving NCT lookup to workflows...")
    workflows_dir = src / "data/workflows"
    workflows_dir.mkdir(parents=True, exist_ok=True)
    
    # Move nct_lookup workflow if it exists in old location
    old_nct = src / "data/nct_lookup"
    if old_nct.exists():
        manager.log("Moving NCT lookup files to workflows...", 1)
        for file in old_nct.glob("*.py"):
            if file.name != "__init__.py":
                manager.move_file(file, workflows_dir / file.name)


# =============================================================================
# PHASE 3: LLM Layer Simplification
# =============================================================================

def phase3_simplify_llm_layer(manager: RefactorManager):
    """Phase 3: Simplify LLM layer."""
    manager.log("\n" + "="*60)
    manager.log("PHASE 3: Simplifying LLM Layer")
    manager.log("="*60)
    
    src = manager.root / "src/amp_llm"
    
    # 3.1: Consolidate LLM clients
    manager.log("\n📦 Consolidating LLM clients...")
    
    # Create unified client.py
    client_content = '''"""
Unified Ollama client.
Combines functionality from clients/ollama_api.py and clients/ollama_ssh.py
"""
from amp_llm.llm.clients.ollama_api import OllamaAPIClient
from amp_llm.llm.clients.base import BaseLLMClient

__all__ = ['OllamaAPIClient', 'BaseLLMClient']
'''
    manager.create_file(src / "llm/client.py", client_content)
    
    # 3.2: Consolidate session management
    manager.log("\n📦 Creating unified session.py...")
    # Already exists at llm/utils/session.py
    
    # 3.3: Extract research assistant
    manager.log("\n📦 Organizing research assistant...")
    research_dir = src / "research"
    research_dir.mkdir(parents=True, exist_ok=True)
    
    research_init = '''"""
Research Assistant module.
"""
from .assistant import ClinicalTrialResearchAssistant
from .commands import CommandHandler
from .parser import ResponseParser

__all__ = [
    'ClinicalTrialResearchAssistant',
    'CommandHandler',
    'ResponseParser'
]
'''
    manager.create_file(research_dir / "__init__.py", research_init)


# =============================================================================
# PHASE 4: WebApp Decoupling
# =============================================================================

def phase4_decouple_webapp(manager: RefactorManager):
    """Phase 4: Decouple WebApp."""
    manager.log("\n" + "="*60)
    manager.log("PHASE 4: Decoupling WebApp")
    manager.log("="*60)
    
    webapp = manager.root / "webapp"
    
    # 4.1: Create API layer
    manager.log("\n📦 Creating WebApp API layer...")
    api_dir = webapp / "api"
    api_dir.mkdir(parents=True, exist_ok=True)
    
    api_init = '''"""
WebApp API endpoints.
"""
from .chat import router as chat_router
from .nct import router as nct_router
from .research import router as research_router
from .files import router as files_router

__all__ = [
    'chat_router',
    'nct_router', 
    'research_router',
    'files_router'
]
'''
    manager.create_file(api_dir / "__init__.py", api_init)
    
    # 4.2: Update webapp config to import from core
    manager.log("\n📦 Updating webapp config...")
    config_content = '''"""
WebApp configuration - imports from amp_llm.config
"""
from amp_llm.config import AppConfig
from typing import Set

class WebAppSettings(AppConfig):
    """WebApp-specific settings."""
    api_keys: Set[str]
    allowed_origins: list = ["https://llm.amphoraxe.ca"]
'''
    manager.create_file(webapp / "config.py", config_content)


# =============================================================================
# PHASE 5: Utilities & Common Code
# =============================================================================

def phase5_create_utils(manager: RefactorManager):
    """Phase 5: Create common utilities."""
    manager.log("\n" + "="*60)
    manager.log("PHASE 5: Creating Common Utilities")
    manager.log("="*60)
    
    src = manager.root / "src/amp_llm"
    utils_dir = src / "utils"
    utils_dir.mkdir(parents=True, exist_ok=True)
    
    # 5.1: File operations utility
    manager.log("\n📦 Creating file utilities...")
    files_content = '''"""
File operation utilities.
"""
from pathlib import Path
from typing import Optional

def safe_read_file(path: Path, encoding: str = 'utf-8') -> Optional[str]:
    """Safely read file with fallback encoding."""
    try:
        return path.read_text(encoding=encoding)
    except UnicodeDecodeError:
        return path.read_text(encoding='latin-1')
    except Exception:
        return None

def ensure_directory(path: Path) -> Path:
    """Ensure directory exists."""
    path.mkdir(parents=True, exist_ok=True)
    return path
'''
    manager.create_file(utils_dir / "files.py", files_content)
    
    # 5.2: Validators utility
    manager.log("\n📦 Creating validators...")
    validators_content = '''"""
Input validation utilities.
"""
import re
from pathlib import Path

def validate_nct_id(nct_id: str) -> str:
    """Validate NCT number format."""
    pattern = r'^NCT\\d{8}$'
    nct_clean = nct_id.strip().upper()
    
    if not re.match(pattern, nct_clean):
        raise ValueError(
            f"Invalid NCT format: {nct_id}. "
            "Expected format: NCT########"
        )
    
    return nct_clean

def validate_file_path(path: str, allowed_dir: Path) -> Path:
    """Validate file path is within allowed directory."""
    file_path = Path(path).resolve()
    allowed_dir = allowed_dir.resolve()
    
    if not file_path.is_relative_to(allowed_dir):
        raise ValueError(f"File path outside allowed directory: {path}")
    
    return file_path
'''
    manager.create_file(utils_dir / "validators.py", validators_content)


# =============================================================================
# PHASE 6: Update Imports
# =============================================================================

def phase6_update_imports(manager: RefactorManager):
    """Phase 6: Update import statements throughout codebase."""
    manager.log("\n" + "="*60)
    manager.log("PHASE 6: Updating Import Statements")
    manager.log("="*60)
    
    if manager.dry_run:
        manager.log("(Skipped in dry-run mode)")
        return
    
    src = manager.root / "src/amp_llm"
    
    # Import replacement mappings
    replacements = {
        # API clients
        "from amp_llm.data.api_clients.core.": "from amp_llm.data.clients.core.",
        "from amp_llm.data.api_clients.extended.": "from amp_llm.data.clients.extended.",
        
        # RAG system
        "from amp_llm.data.clinical_trials.rag": "from amp_llm.data.rag",
        
        # SSH management
        "from amp_llm.network.ssh": "from amp_llm.core.ssh_manager",
        
        # Research assistant
        "from amp_llm.llm.assistants.assistant": "from amp_llm.research.assistant",
        "from amp_llm.llm.assistants.commands": "from amp_llm.research.commands",
        
        # Validation
        "from amp_llm.data.clinical_trials.rag import StudyStatus": "from amp_llm.config.validation import StudyStatus",
    }
    
    manager.log("\n📦 Updating imports in Python files...")
    
    updated_count = 0
    error_count = 0
    
    # Update all Python files
    for py_file in src.rglob("*.py"):
        if "__pycache__" in str(py_file):
            continue
        
        try:
            manager.update_imports_in_file(py_file, replacements)
            updated_count += 1
        except Exception as e:
            error_count += 1
            manager.log(f"⚠️  Error updating {py_file.name}: {e}", 1)
    
    manager.log(f"\n✅ Processed {updated_count} files ({error_count} errors)", 1)


# =============================================================================
# PHASE 7: Cleanup
# =============================================================================

def phase7_cleanup(manager: RefactorManager):
    """Phase 7: Clean up old directories and files."""
    manager.log("\n" + "="*60)
    manager.log("PHASE 7: Cleanup")
    manager.log("="*60)
    
    src = manager.root / "src/amp_llm"
    
    # List of paths to remove (if empty)
    cleanup_candidates = [
        src / "llm/handlers",
        src / "llm/assistants",  # After moving to research/
        src / "data/nct_lookup",  # After moving to workflows/
        src / "data/external_apis",  # After merging with api_clients/
    ]
    
    manager.log("\n📦 Removing empty directories...")
    for path in cleanup_candidates:
        if path.exists() and path.is_dir():
            try:
                # Only remove if empty or only contains __pycache__
                contents = list(path.iterdir())
                if not contents or all(c.name == "__pycache__" for c in contents):
                    manager.delete_path(path)
            except Exception as e:
                manager.log(f"⚠️  Could not remove {path}: {e}", 1)


# =============================================================================
# Main Execution
# =============================================================================

def main():
    """Main refactoring process."""
    parser = argparse.ArgumentParser(
        description="Refactor AMP LLM v3 codebase"
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Show what would be done without making changes"
    )
    parser.add_argument(
        "--backup",
        action="store_true",
        help="Create backup before refactoring"
    )
    
    args = parser.parse_args()
    
    # Find project root
    current = Path.cwd()
    if (current / "src/amp_llm").exists():
        root = current
    elif (current / "amp_llm_v3_webonly").exists():
        root = current / "amp_llm_v3_webonly"
    else:
        print("❌ Could not find project root!")
        print("Please run from project directory.")
        return 1
    
    print("="*60)
    print("AMP LLM v3 REFACTORING SCRIPT")
    print("="*60)
    print(f"Root directory: {root}")
    print(f"Dry run: {args.dry_run}")
    print(f"Backup: {args.backup}")
    print("="*60)
    
    if not args.dry_run:
        confirm = input("\n⚠️  This will modify your codebase. Continue? (y/N): ")
        if confirm.lower() != 'y':
            print("Aborted.")
            return 0
    
    # Create manager
    manager = RefactorManager(root, dry_run=args.dry_run, backup=args.backup)
    
    # Create backup if requested
    if args.backup and not args.dry_run:
        manager.create_backup()
    
    # Execute refactoring phases
    try:
        phase1_consolidate_core(manager)
        phase2_reorganize_data_layer(manager)
        phase3_simplify_llm_layer(manager)
        phase4_decouple_webapp(manager)
        phase5_create_utils(manager)
        phase6_update_imports(manager)
        phase7_cleanup(manager)
        
        # Summary
        print("\n" + "="*60)
        print("REFACTORING SUMMARY")
        print("="*60)
        print(f"Files moved: {len(manager.moves)}")
        print(f"Files created: {len(manager.creates)}")
        print(f"Paths deleted: {len(manager.deletes)}")
        
        if args.dry_run:
            print("\n✅ Dry run complete. No changes made.")
            print("Run without --dry-run to apply changes.")
        else:
            print("\n✅ Refactoring complete!")
            print("\nNext steps:")
            print("  1. Run tests to verify nothing broke")
            print("  2. Update any remaining imports manually if needed")
            print("  3. Commit changes to version control")
        
        return 0
        
    except Exception as e:
        print(f"\n❌ Error during refactoring: {e}")
        import traceback
        traceback.print_exc()
        return 1


if __name__ == "__main__":
    exit(main())