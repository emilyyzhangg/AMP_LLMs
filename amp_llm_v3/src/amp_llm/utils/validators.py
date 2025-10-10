# src/amp_llm/utils/validators.py
from typing import Any
import re

class Validator:
    """Input validation utilities."""
    
    @staticmethod
    def validate_nct_id(nct_id: str) -> str:
        """Validate NCT number format."""
        pattern = r'^NCT\d{8}$'
        nct_clean = nct_id.strip().upper()
        
        if not re.match(pattern, nct_clean):
            raise ValueError(
                f"Invalid NCT format: {nct_id}. "
                "Expected format: NCT########"
            )
        
        return nct_clean
    
    @staticmethod
    def validate_file_path(path: str, allowed_dirs: List[str] = None) -> Path:
        """Validate file path for security."""
        # Implementation from earlier security section