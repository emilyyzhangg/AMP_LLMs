# src/amp_llm/data/database/manager.py
"""
Clinical Trial Database Manager
Handles storage, retrieval, and management of clinical trial JSON data.
"""
import json
import shutil
from pathlib import Path
from typing import Dict, List, Optional, Union
from datetime import datetime
from dataclasses import dataclass, asdict

from amp_llm.config import get_logger

logger = get_logger(__name__)


@dataclass
class DatabaseConfig:
    """Database configuration."""
    base_path: Path
    backup_enabled: bool = True
    backup_dir: Optional[Path] = None
    max_backups: int = 5
    
    def __post_init__(self):
        """Initialize paths."""
        self.base_path = Path(self.base_path)
        if self.backup_enabled and not self.backup_dir:
            self.backup_dir = self.base_path / "backups"


class DatabaseManager:
    """
    Manages clinical trial database operations.
    
    Responsibilities:
    - Save trial data to ct_database/
    - Load trial data from ct_database/
    - Backup and restore operations
    - Database integrity checks
    - Batch import/export
    
    Example:
        >>> db = DatabaseManager("ct_database")
        >>> db.save_trial("NCT12345678", trial_data)
        >>> trial = db.load_trial("NCT12345678")
    """
    
    def __init__(self, config: Union[Path, str, DatabaseConfig]):
        """
        Initialize database manager.
        
        Args:
            config: Path to database or DatabaseConfig
        """
        if isinstance(config, (Path, str)):
            self.config = DatabaseConfig(base_path=Path(config))
        else:
            self.config = config
        
        self._ensure_directories()
    
    def _ensure_directories(self):
        """Create database directories if they don't exist."""
        self.config.base_path.mkdir(exist_ok=True, parents=True)
        
        if self.config.backup_enabled and self.config.backup_dir:
            self.config.backup_dir.mkdir(exist_ok=True, parents=True)
        
        logger.info(f"Database initialized at: {self.config.base_path}")
    
    # ========================================================================
    # Core Operations
    # ========================================================================
    
    def save_trial(
        self, 
        nct_id: str, 
        data: Dict, 
        overwrite: bool = True,
        backup: bool = True
    ) -> Path:
        """
        Save trial data to database.
        
        Args:
            nct_id: NCT number
            data: Trial data dictionary
            overwrite: Whether to overwrite existing file
            backup: Whether to backup existing file
            
        Returns:
            Path to saved file
            
        Raises:
            FileExistsError: If file exists and overwrite=False
        """
        nct_id = nct_id.upper().strip()
        file_path = self._get_trial_path(nct_id)
        
        # Check if file exists
        if file_path.exists():
            if not overwrite:
                raise FileExistsError(f"Trial {nct_id} already exists. Use overwrite=True to replace.")
            
            if backup and self.config.backup_enabled:
                self._backup_trial(nct_id)
        
        # Ensure nct_id is in data
        if 'nct_id' not in data:
            data['nct_id'] = nct_id
        
        # Add metadata
        if 'metadata' not in data:
            data['metadata'] = {}
        
        data['metadata']['saved_at'] = datetime.now().isoformat()
        data['metadata']['saved_by'] = 'amp_llm'
        
        # Save
        try:
            with open(file_path, 'w', encoding='utf-8') as f:
                json.dump(data, f, indent=2, ensure_ascii=False)
            
            logger.info(f"Saved trial {nct_id} to {file_path}")
            return file_path
            
        except Exception as e:
            logger.error(f"Error saving trial {nct_id}: {e}", exc_info=True)
            raise
    
    def load_trial(self, nct_id: str) -> Optional[Dict]:
        """
        Load trial data from database.
        
        Args:
            nct_id: NCT number
            
        Returns:
            Trial data or None if not found
        """
        nct_id = nct_id.upper().strip()
        file_path = self._get_trial_path(nct_id)
        
        if not file_path.exists():
            logger.warning(f"Trial {nct_id} not found in database")
            return None
        
        try:
            with open(file_path, 'r', encoding='utf-8') as f:
                data = json.load(f)
            
            logger.debug(f"Loaded trial {nct_id}")
            return data
            
        except Exception as e:
            logger.error(f"Error loading trial {nct_id}: {e}", exc_info=True)
            return None
    
    def delete_trial(self, nct_id: str, backup: bool = True) -> bool:
        """
        Delete trial from database.
        
        Args:
            nct_id: NCT number
            backup: Whether to backup before deletion
            
        Returns:
            True if deleted, False if not found
        """
        nct_id = nct_id.upper().strip()
        file_path = self._get_trial_path(nct_id)
        
        if not file_path.exists():
            logger.warning(f"Trial {nct_id} not found for deletion")
            return False
        
        # Backup if requested
        if backup and self.config.backup_enabled:
            self._backup_trial(nct_id)
        
        try:
            file_path.unlink()
            logger.info(f"Deleted trial {nct_id}")
            return True
            
        except Exception as e:
            logger.error(f"Error deleting trial {nct_id}: {e}")
            return False
    
    def exists(self, nct_id: str) -> bool:
        """Check if trial exists in database."""
        nct_id = nct_id.upper().strip()
        return self._get_trial_path(nct_id).exists()
    
    # ========================================================================
    # Batch Operations
    # ========================================================================
    
    def save_trials_batch(
        self, 
        trials: Dict[str, Dict],
        overwrite: bool = True
    ) -> Dict[str, bool]:
        """
        Save multiple trials at once.
        
        Args:
            trials: Dictionary of {nct_id: trial_data}
            overwrite: Whether to overwrite existing
            
        Returns:
            Dictionary of {nct_id: success_status}
        """
        results = {}
        
        for nct_id, data in trials.items():
            try:
                self.save_trial(nct_id, data, overwrite=overwrite)
                results[nct_id] = True
            except Exception as e:
                logger.error(f"Failed to save {nct_id}: {e}")
                results[nct_id] = False
        
        success_count = sum(results.values())
        logger.info(f"Batch save: {success_count}/{len(trials)} successful")
        
        return results
    
    def load_all_trials(self) -> Dict[str, Dict]:
        """
        Load all trials from database.
        
        Returns:
            Dictionary of {nct_id: trial_data}
        """
        trials = {}
        
        for file_path in self.config.base_path.glob("NCT*.json"):
            nct_id = file_path.stem
            trial = self.load_trial(nct_id)
            
            if trial:
                trials[nct_id] = trial
        
        logger.info(f"Loaded {len(trials)} trials from database")
        return trials
    
    def list_trials(self) -> List[str]:
        """
        List all NCT IDs in database.
        
        Returns:
            List of NCT numbers
        """
        nct_ids = [
            f.stem for f in self.config.base_path.glob("NCT*.json")
        ]
        nct_ids.sort()
        return nct_ids
    
    # ========================================================================
    # Import/Export
    # ========================================================================
    
    def export_to_directory(
        self, 
        output_dir: Path, 
        nct_ids: Optional[List[str]] = None
    ) -> int:
        """
        Export trials to another directory.
        
        Args:
            output_dir: Destination directory
            nct_ids: Specific trials to export (None = all)
            
        Returns:
            Number of trials exported
        """
        output_dir = Path(output_dir)
        output_dir.mkdir(exist_ok=True, parents=True)
        
        if nct_ids is None:
            nct_ids = self.list_trials()
        
        exported = 0
        
        for nct_id in nct_ids:
            trial = self.load_trial(nct_id)
            if trial:
                dest_path = output_dir / f"{nct_id}.json"
                
                with open(dest_path, 'w', encoding='utf-8') as f:
                    json.dump(trial, f, indent=2, ensure_ascii=False)
                
                exported += 1
        
        logger.info(f"Exported {exported} trials to {output_dir}")
        return exported
    
    def import_from_directory(
        self, 
        source_dir: Path,
        overwrite: bool = False
    ) -> Dict[str, bool]:
        """
        Import trials from another directory.
        
        Args:
            source_dir: Source directory with JSON files
            overwrite: Whether to overwrite existing trials
            
        Returns:
            Dictionary of {nct_id: success_status}
        """
        source_dir = Path(source_dir)
        
        if not source_dir.exists():
            raise FileNotFoundError(f"Source directory not found: {source_dir}")
        
        results = {}
        
        for file_path in source_dir.glob("NCT*.json"):
            try:
                with open(file_path, 'r', encoding='utf-8') as f:
                    data = json.load(f)
                
                nct_id = file_path.stem
                self.save_trial(nct_id, data, overwrite=overwrite, backup=False)
                results[nct_id] = True
                
            except Exception as e:
                logger.error(f"Failed to import {file_path.name}: {e}")
                results[nct_id] = False
        
        success_count = sum(results.values())
        logger.info(f"Imported {success_count}/{len(results)} trials")
        
        return results
    
    # ========================================================================
    # Backup Operations
    # ========================================================================
    
    def _backup_trial(self, nct_id: str) -> Optional[Path]:
        """Create backup of trial."""
        if not self.config.backup_enabled:
            return None
        
        source_path = self._get_trial_path(nct_id)
        
        if not source_path.exists():
            return None
        
        # Create timestamped backup
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        backup_name = f"{nct_id}_{timestamp}.json"
        backup_path = self.config.backup_dir / backup_name
        
        try:
            shutil.copy2(source_path, backup_path)
            logger.debug(f"Backed up {nct_id} to {backup_path}")
            
            # Clean old backups
            self._cleanup_old_backups(nct_id)
            
            return backup_path
            
        except Exception as e:
            logger.error(f"Error backing up {nct_id}: {e}")
            return None
    
    def _cleanup_old_backups(self, nct_id: str):
        """Remove old backups exceeding max_backups."""
        if not self.config.backup_enabled:
            return
        
        # Get all backups for this trial
        backups = sorted(
            self.config.backup_dir.glob(f"{nct_id}_*.json"),
            key=lambda p: p.stat().st_mtime,
            reverse=True
        )
        
        # Remove old backups
        for backup in backups[self.config.max_backups:]:
            try:
                backup.unlink()
                logger.debug(f"Removed old backup: {backup.name}")
            except Exception as e:
                logger.error(f"Error removing backup {backup.name}: {e}")
    
    def restore_from_backup(
        self, 
        nct_id: str, 
        backup_timestamp: Optional[str] = None
    ) -> bool:
        """
        Restore trial from backup.
        
        Args:
            nct_id: NCT number
            backup_timestamp: Specific backup timestamp (None = latest)
            
        Returns:
            True if restored successfully
        """
        if not self.config.backup_enabled:
            logger.error("Backups are disabled")
            return False
        
        # Find backup
        if backup_timestamp:
            backup_path = self.config.backup_dir / f"{nct_id}_{backup_timestamp}.json"
        else:
            # Get latest backup
            backups = sorted(
                self.config.backup_dir.glob(f"{nct_id}_*.json"),
                key=lambda p: p.stat().st_mtime,
                reverse=True
            )
            
            if not backups:
                logger.error(f"No backups found for {nct_id}")
                return False
            
            backup_path = backups[0]
        
        if not backup_path.exists():
            logger.error(f"Backup not found: {backup_path}")
            return False
        
        # Restore
        try:
            with open(backup_path, 'r', encoding='utf-8') as f:
                data = json.load(f)
            
            self.save_trial(nct_id, data, overwrite=True, backup=False)
            logger.info(f"Restored {nct_id} from {backup_path.name}")
            return True
            
        except Exception as e:
            logger.error(f"Error restoring {nct_id}: {e}", exc_info=True)
            return False
    
    # ========================================================================
    # Statistics & Maintenance
    # ========================================================================
    
    def get_statistics(self) -> Dict:
        """Get database statistics."""
        trials = self.list_trials()
        
        stats = {
            'total_trials': len(trials),
            'database_path': str(self.config.base_path),
            'database_size_mb': self._get_directory_size() / (1024 * 1024),
        }
        
        if self.config.backup_enabled:
            backup_count = len(list(self.config.backup_dir.glob("NCT*.json")))
            backup_size = self._get_directory_size(self.config.backup_dir) / (1024 * 1024)
            
            stats.update({
                'backup_count': backup_count,
                'backup_size_mb': backup_size,
                'backup_path': str(self.config.backup_dir),
            })
        
        return stats
    
    def _get_directory_size(self, directory: Optional[Path] = None) -> int:
        """Get total size of directory in bytes."""
        if directory is None:
            directory = self.config.base_path
        
        return sum(
            f.stat().st_size 
            for f in directory.rglob('*') 
            if f.is_file()
        )
    
    def validate_database(self) -> Dict[str, List[str]]:
        """
        Validate all trials in database.
        
        Returns:
            Dictionary with validation results:
            - 'valid': List of valid NCT IDs
            - 'invalid': List of invalid/corrupted files
            - 'errors': List of files with errors
        """
        results = {
            'valid': [],
            'invalid': [],
            'errors': []
        }
        
        for file_path in self.config.base_path.glob("NCT*.json"):
            nct_id = file_path.stem
            
            try:
                with open(file_path, 'r', encoding='utf-8') as f:
                    data = json.load(f)
                
                # Basic validation
                if 'nct_id' in data or 'sources' in data:
                    results['valid'].append(nct_id)
                else:
                    results['invalid'].append(nct_id)
                    logger.warning(f"Invalid structure: {nct_id}")
                    
            except json.JSONDecodeError:
                results['errors'].append(nct_id)
                logger.error(f"JSON decode error: {nct_id}")
            except Exception as e:
                results['errors'].append(nct_id)
                logger.error(f"Error validating {nct_id}: {e}")
        
        logger.info(
            f"Validation complete: {len(results['valid'])} valid, "
            f"{len(results['invalid'])} invalid, {len(results['errors'])} errors"
        )
        
        return results
    
    # ========================================================================
    # Helper Methods
    # ========================================================================
    
    def _get_trial_path(self, nct_id: str) -> Path:
        """Get file path for trial."""
        return self.config.base_path / f"{nct_id}.json"
    
    def __repr__(self) -> str:
        """String representation."""
        trial_count = len(self.list_trials())
        return f"DatabaseManager(path={self.config.base_path}, trials={trial_count})"