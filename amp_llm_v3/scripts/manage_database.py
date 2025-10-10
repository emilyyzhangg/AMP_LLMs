# scripts/manage_database.py
"""
CLI tool for managing the clinical trials database.

Usage:
    python scripts/manage_database.py stats
    python scripts/manage_database.py list
    python scripts/manage_database.py validate
    python scripts/manage_database.py export output/export_dir
    python scripts/manage_database.py import source_dir
    python scripts/manage_database.py backup NCT12345678
    python scripts/manage_database.py restore NCT12345678
"""
import sys
import argparse
from pathlib import Path
from colorama import init, Fore, Style

# Add src to path
src_dir = Path(__file__).parent.parent / "src"
sys.path.insert(0, str(src_dir))

from amp_llm.data.database.manager import DatabaseManager

init(autoreset=True)


def print_header(text: str):
    """Print formatted header."""
    print(f"\n{Fore.YELLOW}{Style.BRIGHT}{'='*60}")
    print(f"{text}")
    print(f"{'='*60}{Style.RESET_ALL}\n")


def cmd_stats(db: DatabaseManager, args):
    """Show database statistics."""
    print_header("📊 Database Statistics")
    
    stats = db.get_statistics()
    
    print(f"{Fore.CYAN}Database Path: {Fore.WHITE}{stats['database_path']}")
    print(f"{Fore.CYAN}Total Trials: {Fore.WHITE}{stats['total_trials']}")
    print(f"{Fore.CYAN}Database Size: {Fore.WHITE}{stats['database_size_mb']:.2f} MB")
    
    if 'backup_count' in stats:
        print(f"\n{Fore.YELLOW}Backups:")
        print(f"{Fore.CYAN}  Backup Path: {Fore.WHITE}{stats['backup_path']}")
        print(f"{Fore.CYAN}  Backup Count: {Fore.WHITE}{stats['backup_count']}")
        print(f"{Fore.CYAN}  Backup Size: {Fore.WHITE}{stats['backup_size_mb']:.2f} MB")


def cmd_list(db: DatabaseManager, args):
    """List all trials in database."""
    print_header("📋 Trials in Database")
    
    trials = db.list_trials()
    
    if not trials:
        print(f"{Fore.YELLOW}No trials found in database")
        return
    
    print(f"{Fore.GREEN}Found {len(trials)} trial(s):\n")
    
    # Print in columns
    for i, nct in enumerate(trials, 1):
        print(f"  {i:3d}. {nct}", end="")
        if i % 3 == 0:
            print()
    print()


def cmd_validate(db: DatabaseManager, args):
    """Validate all trials."""
    print_header("🔍 Validating Database")
    
    print(f"{Fore.CYAN}Running validation...")
    results = db.validate_database()
    
    print(f"\n{Fore.GREEN}✅ Valid: {len(results['valid'])}")
    print(f"{Fore.YELLOW}⚠️  Invalid: {len(results['invalid'])}")
    print(f"{Fore.RED}❌ Errors: {len(results['errors'])}")
    
    if results['invalid']:
        print(f"\n{Fore.YELLOW}Invalid trials:")
        for nct in results['invalid']:
            print(f"  • {nct}")
    
    if results['errors']:
        print(f"\n{Fore.RED}Errors:")
        for nct in results['errors']:
            print(f"  • {nct}")


def cmd_export(db: DatabaseManager, args):
    """Export trials to directory."""
    output_dir = Path(args.output_dir)
    
    print_header(f"📤 Exporting to {output_dir}")
    
    if args.nct_ids:
        nct_ids = [nct.strip().upper() for nct in args.nct_ids.split(',')]
        print(f"{Fore.CYAN}Exporting {len(nct_ids)} specific trial(s)...")
    else:
        nct_ids = None
        print(f"{Fore.CYAN}Exporting all trials...")
    
    count = db.export_to_directory(output_dir, nct_ids)
    
    print(f"{Fore.GREEN}✅ Exported {count} trial(s) to {output_dir}")


def cmd_import(db: DatabaseManager, args):
    """Import trials from directory."""
    source_dir = Path(args.source_dir)
    
    print_header(f"📥 Importing from {source_dir}")
    
    if not source_dir.exists():
        print(f"{Fore.RED}❌ Source directory not found: {source_dir}")
        return
    
    print(f"{Fore.CYAN}Importing trials...")
    results = db.import_from_directory(source_dir, overwrite=args.overwrite)
    
    success = sum(results.values())
    total = len(results)
    
    print(f"{Fore.GREEN}✅ Imported {success}/{total} trial(s)")
    
    if success < total:
        failed = [nct for nct, status in results.items() if not status]
        print(f"\n{Fore.RED}Failed:")
        for nct in failed:
            print(f"  • {nct}")


def cmd_backup(db: DatabaseManager, args):
    """Create backup of trial."""
    nct_id = args.nct_id.upper().strip()
    
    print_header(f"💾 Backing up {nct_id}")
    
    if not db.exists(nct_id):
        print(f"{Fore.RED}❌ Trial {nct_id} not found in database")
        return
    
    backup_path = db._backup_trial(nct_id)
    
    if backup_path:
        print(f"{Fore.GREEN}✅ Backup created: {backup_path}")
    else:
        print(f"{Fore.RED}❌ Backup failed")


def cmd_restore(db: DatabaseManager, args):
    """Restore trial from backup."""
    nct_id = args.nct_id.upper().strip()
    
    print_header(f"♻️  Restoring {nct_id}")
    
    if db.restore_from_backup(nct_id, args.timestamp):
        print(f"{Fore.GREEN}✅ Restored {nct_id} successfully")
    else:
        print(f"{Fore.RED}❌ Restore failed")


def cmd_delete(db: DatabaseManager, args):
    """Delete trial from database."""
    nct_id = args.nct_id.upper().strip()
    
    print_header(f"🗑️  Deleting {nct_id}")
    
    if not db.exists(nct_id):
        print(f"{Fore.RED}❌ Trial {nct_id} not found")
        return
    
    if not args.force:
        confirm = input(f"{Fore.YELLOW}Are you sure? (yes/no): ")
        if confirm.lower() != 'yes':
            print(f"{Fore.CYAN}Cancelled")
            return
    
    if db.delete_trial(nct_id, backup=args.backup):
        print(f"{Fore.GREEN}✅ Deleted {nct_id}")
    else:
        print(f"{Fore.RED}❌ Delete failed")


def cmd_info(db: DatabaseManager, args):
    """Show info about specific trial."""
    nct_id = args.nct_id.upper().strip()
    
    print_header(f"ℹ️  Trial Info: {nct_id}")
    
    trial = db.load_trial(nct_id)
    
    if not trial:
        print(f"{Fore.RED}❌ Trial {nct_id} not found")
        return
    
    # Extract key info
    sources = trial.get('sources', {})
    ct_data = sources.get('clinical_trials', {}).get('data', {})
    protocol = ct_data.get('protocolSection', {})
    
    ident = protocol.get('identificationModule', {})
    status_mod = protocol.get('statusModule', {})
    
    print(f"{Fore.CYAN}Title: {Fore.WHITE}{ident.get('officialTitle', 'N/A')}")
    print(f"{Fore.CYAN}Status: {Fore.WHITE}{status_mod.get('overallStatus', 'N/A')}")
    
    # PubMed/PMC
    pubmed = sources.get('pubmed', {})
    pmc = sources.get('pmc', {})
    
    pmid_count = len(pubmed.get('pmids', []))
    pmc_count = len(pmc.get('pmcids', []))
    
    print(f"{Fore.CYAN}PubMed: {Fore.WHITE}{pmid_count} article(s)")
    print(f"{Fore.CYAN}PMC: {Fore.WHITE}{pmc_count} article(s)")
    
    # Extended APIs
    if 'extended_apis' in trial:
        print(f"\n{Fore.YELLOW}Extended API Data: {Fore.GREEN}Yes")
    
    # Metadata
    if 'metadata' in trial:
        meta = trial['metadata']
        print(f"\n{Fore.YELLOW}Metadata:")
        if 'saved_at' in meta:
            print(f"{Fore.CYAN}  Saved: {Fore.WHITE}{meta['saved_at']}")
        if 'saved_by' in meta:
            print(f"{Fore.CYAN}  Source: {Fore.WHITE}{meta['saved_by']}")


def main():
    """Main CLI entry point."""
    parser = argparse.ArgumentParser(
        description="Manage clinical trials database",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # Show statistics
  python scripts/manage_database.py stats
  
  # List all trials
  python scripts/manage_database.py list
  
  # Validate database
  python scripts/manage_database.py validate
  
  # Export all trials
  python scripts/manage_database.py export output/export_dir
  
  # Export specific trials
  python scripts/manage_database.py export output/export_dir --nct NCT123,NCT456
  
  # Import trials
  python scripts/manage_database.py import source_dir --overwrite
  
  # Backup specific trial
  python scripts/manage_database.py backup NCT12345678
  
  # Restore from backup
  python scripts/manage_database.py restore NCT12345678
  
  # Delete trial
  python scripts/manage_database.py delete NCT12345678 --force
  
  # Show trial info
  python scripts/manage_database.py info NCT12345678
        """
    )
    
    parser.add_argument(
        '--db-path',
        default='ct_database',
        help='Path to database directory (default: ct_database)'
    )
    
    subparsers = parser.add_subparsers(dest='command', required=True)
    
    # Stats command
    subparsers.add_parser('stats', help='Show database statistics')
    
    # List command
    subparsers.add_parser('list', help='List all trials')
    
    # Validate command
    subparsers.add_parser('validate', help='Validate all trials')
    
    # Export command
    export_parser = subparsers.add_parser('export', help='Export trials')
    export_parser.add_argument('output_dir', help='Output directory')
    export_parser.add_argument('--nct', dest='nct_ids', help='Comma-separated NCT IDs')
    
    # Import command
    import_parser = subparsers.add_parser('import', help='Import trials')
    import_parser.add_argument('source_dir', help='Source directory')
    import_parser.add_argument('--overwrite', action='store_true', help='Overwrite existing')
    
    # Backup command
    backup_parser = subparsers.add_parser('backup', help='Backup trial')
    backup_parser.add_argument('nct_id', help='NCT number')
    
    # Restore command
    restore_parser = subparsers.add_parser('restore', help='Restore trial')
    restore_parser.add_argument('nct_id', help='NCT number')
    restore_parser.add_argument('--timestamp', help='Specific backup timestamp')
    
    # Delete command
    delete_parser = subparsers.add_parser('delete', help='Delete trial')
    delete_parser.add_argument('nct_id', help='NCT number')
    delete_parser.add_argument('--force', action='store_true', help='Skip confirmation')
    delete_parser.add_argument('--backup', action='store_true', default=True, help='Backup before delete')
    
    # Info command
    info_parser = subparsers.add_parser('info', help='Show trial info')
    info_parser.add_argument('nct_id', help='NCT number')
    
    args = parser.parse_args()
    
    # Initialize database
    db = DatabaseManager(args.db_path)
    
    # Route to command
    commands = {
        'stats': cmd_stats,
        'list': cmd_list,
        'validate': cmd_validate,
        'export': cmd_export,
        'import': cmd_import,
        'backup': cmd_backup,
        'restore': cmd_restore,
        'delete': cmd_delete,
        'info': cmd_info,
    }
    
    try:
        commands[args.command](db, args)
    except KeyboardInterrupt:
        print(f"\n{Fore.YELLOW}Interrupted")
        sys.exit(1)
    except Exception as e:
        print(f"\n{Fore.RED}❌ Error: {e}")
        sys.exit(1)


if __name__ == '__main__':
    main()