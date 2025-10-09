"""
Modelfile utilities for automatic generation and sync checking.
Ensures Modelfile is always up-to-date with validation_config.py
"""
import hashlib
from pathlib import Path
from typing import Optional, Tuple
from colorama import Fore


def get_validation_config_hash() -> str:
    """
    Get hash of validation_config.py content.
    Used to detect if Modelfile needs regeneration.
    
    Returns:
        MD5 hash of validation_config.py
    """
    config_path = Path("validation_config.py")
    
    if not config_path.exists():
        return ""
    
    try:
        content = config_path.read_text(encoding='utf-8')
        return hashlib.md5(content.encode()).hexdigest()
    except Exception:
        return ""


def get_modelfile_hash() -> str:
    """
    Get stored hash from Modelfile metadata comment.
    
    Returns:
        Hash stored in Modelfile or empty string if not found
    """
    modelfile_path = Path("Modelfile")
    
    if not modelfile_path.exists():
        return ""
    
    try:
        content = modelfile_path.read_text(encoding='utf-8')
        
        # Look for hash comment: # validation_config_hash: <hash>
        for line in content.split('\n'):
            if line.startswith('# validation_config_hash:'):
                return line.split(':', 1)[1].strip()
        
        return ""
    except Exception:
        return ""


def modelfile_needs_generation() -> Tuple[bool, str]:
    """
    Check if Modelfile needs to be generated.
    
    Returns:
        Tuple of (needs_generation, reason)
    """
    modelfile_path = Path("Modelfile")
    config_path = Path("validation_config.py")
    
    # Check if validation_config.py exists
    if not config_path.exists():
        return False, "validation_config.py not found"
    
    # Check if Modelfile exists
    if not modelfile_path.exists():
        return True, "Modelfile does not exist"
    
    # Check if Modelfile is auto-generated
    try:
        content = modelfile_path.read_text(encoding='utf-8')
        if "AUTO-GENERATED" not in content:
            return False, "Modelfile is manually maintained"
    except Exception:
        return True, "Cannot read Modelfile"
    
    # Check hash match
    current_hash = get_validation_config_hash()
    stored_hash = get_modelfile_hash()
    
    if not stored_hash:
        return True, "Modelfile missing hash metadata"
    
    if current_hash != stored_hash:
        return True, "validation_config.py has changed"
    
    return False, "Modelfile is up-to-date"


def ensure_modelfile_exists(verbose: bool = True) -> bool:
    """
    Ensure Modelfile exists and is up-to-date.
    Automatically generates if needed.
    
    Args:
        verbose: Print status messages
        
    Returns:
        True if Modelfile ready, False if generation failed
    """
    needs_gen, reason = modelfile_needs_generation()
    
    if not needs_gen:
        if verbose:
            print(f"{Fore.GREEN}✅ Modelfile is up-to-date")
        return True
    
    # Need to generate
    if verbose:
        print(f"{Fore.YELLOW}⚙️  Modelfile needs generation: {reason}")
        print(f"{Fore.CYAN}📝 Generating Modelfile from validation_config.py...")
    
    try:
        # Import here to avoid circular dependency
        from generate_modelfile import generate_modelfile
        
        # Get current hash before generation
        current_hash = get_validation_config_hash()
        
        # Generate Modelfile
        modelfile_content = generate_modelfile(base_model="llama3.2")
        
        # Add hash comment at top (after first line)
        lines = modelfile_content.split('\n')
        
        # Insert hash after first comment line
        hash_comment = f"# validation_config_hash: {current_hash}"
        lines.insert(1, hash_comment)
        
        modelfile_content = '\n'.join(lines)
        
        # Save
        modelfile_path = Path("Modelfile")
        modelfile_path.write_text(modelfile_content, encoding='utf-8')
        
        if verbose:
            print(f"{Fore.GREEN}✅ Modelfile generated successfully")
            print(f"{Fore.WHITE}   Size: {len(modelfile_content):,} bytes")
            print(f"{Fore.WHITE}   Hash: {current_hash[:8]}...")
        
        return True
        
    except ImportError as e:
        if verbose:
            print(f"{Fore.RED}❌ Cannot import generate_modelfile: {e}")
            print(f"{Fore.YELLOW}   Make sure generate_modelfile.py exists")
        return False
    
    except Exception as e:
        if verbose:
            print(f"{Fore.RED}❌ Failed to generate Modelfile: {e}")
        return False


def force_regenerate_modelfile(verbose: bool = True) -> bool:
    """
    Force regeneration of Modelfile regardless of hash.
    
    Args:
        verbose: Print status messages
        
    Returns:
        True if successful
    """
    if verbose:
        print(f"{Fore.CYAN}🔄 Force regenerating Modelfile...")
    
    # Delete existing Modelfile
    modelfile_path = Path("Modelfile")
    if modelfile_path.exists():
        modelfile_path.unlink()
    
    # Generate new one
    return ensure_modelfile_exists(verbose=verbose)


def get_modelfile_info() -> dict:
    """
    Get information about current Modelfile.
    
    Returns:
        Dictionary with Modelfile metadata
    """
    modelfile_path = Path("Modelfile")
    
    info = {
        "exists": modelfile_path.exists(),
        "path": str(modelfile_path.absolute()),
        "size": 0,
        "auto_generated": False,
        "hash": "",
        "config_hash": get_validation_config_hash(),
        "in_sync": False,
    }
    
    if not modelfile_path.exists():
        return info
    
    try:
        content = modelfile_path.read_text(encoding='utf-8')
        info["size"] = len(content)
        info["auto_generated"] = "AUTO-GENERATED" in content
        info["hash"] = get_modelfile_hash()
        info["in_sync"] = info["hash"] == info["config_hash"]
    except Exception:
        pass
    
    return info


def print_modelfile_status():
    """Print detailed Modelfile status."""
    info = get_modelfile_info()
    
    print(f"\n{Fore.CYAN}{'='*60}")
    print(f"{Fore.CYAN}Modelfile Status")
    print(f"{Fore.CYAN}{'='*60}")
    
    if not info["exists"]:
        print(f"{Fore.RED}❌ Modelfile: Not found")
        print(f"{Fore.YELLOW}   Will be auto-generated on startup")
        return
    
    print(f"{Fore.GREEN}✅ Modelfile: Found")
    print(f"{Fore.WHITE}   Path: {info['path']}")
    print(f"{Fore.WHITE}   Size: {info['size']:,} bytes")
    print(f"{Fore.WHITE}   Auto-generated: {info['auto_generated']}")
    
    if info["auto_generated"]:
        if info["in_sync"]:
            print(f"{Fore.GREEN}   ✅ In sync with validation_config.py")
            print(f"{Fore.WHITE}   Hash: {info['hash'][:16]}...")
        else:
            print(f"{Fore.YELLOW}   ⚠️  Out of sync with validation_config.py")
            print(f"{Fore.WHITE}   Modelfile hash: {info['hash'][:16]}...")
            print(f"{Fore.WHITE}   Config hash:    {info['config_hash'][:16]}...")
            print(f"{Fore.YELLOW}   Will regenerate on next startup")
    else:
        print(f"{Fore.YELLOW}   ℹ️  Manually maintained (won't auto-regenerate)")
    
    print(f"{Fore.CYAN}{'='*60}\n")


if __name__ == "__main__":
    """CLI for testing and manual operations."""
    import sys
    
    if len(sys.argv) > 1:
        command = sys.argv[1].lower()
        
        if command == "check":
            needs_gen, reason = modelfile_needs_generation()
            if needs_gen:
                print(f"{Fore.YELLOW}Needs generation: {reason}")
                sys.exit(1)
            else:
                print(f"{Fore.GREEN}Up-to-date: {reason}")
                sys.exit(0)
        
        elif command == "status":
            print_modelfile_status()
        
        elif command == "generate":
            success = ensure_modelfile_exists(verbose=True)
            sys.exit(0 if success else 1)
        
        elif command == "force":
            success = force_regenerate_modelfile(verbose=True)
            sys.exit(0 if success else 1)
        
        else:
            print(f"{Fore.RED}Unknown command: {command}")
            print(f"{Fore.CYAN}Usage: python modelfile_utils.py [check|status|generate|force]")
            sys.exit(1)
    else:
        # Default: show status
        print_modelfile_status()