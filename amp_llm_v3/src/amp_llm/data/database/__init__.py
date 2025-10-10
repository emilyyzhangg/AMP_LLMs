# src/amp_llm/data/database/__init__.py
"""
Clinical Trial Database Management Module

Provides modular, robust management of clinical trial JSON data
stored in the ct_database/ directory.

Features:
- Save/load/delete operations
- Automatic backups with rotation
- Batch import/export
- Database validation
- Statistics and health checks

Example:
    >>> from amp_llm.data.database import DatabaseManager
    >>> db = DatabaseManager("ct_database")
    >>> db.save_trial("NCT12345678", trial_data)
    >>> trial = db.load_trial("NCT12345678")
    >>> stats = db.get_statistics()
"""

from .manager import DatabaseManager, DatabaseConfig

__all__