"""
Response parser for LLM extraction outputs.
Converts unstructured LLM text to structured dictionaries.
"""
import re
from typing import Dict, Any
from amp_llm.config import get_logger

logger = get_logger(__name__)


def parse_extraction_to_dict(llm_response: str) -> Dict[str, Any]:
    """
    Parse LLM extraction response into structured dictionary.
    
    Args:
        llm_response: Raw LLM response text
        
    Returns:
        Dictionary with parsed fields
    """
    result = {
        "nct_number": "",
        "study_title": "",
        "study_status": "",
        "brief_summary": "",
        "conditions": [],
        "interventions": [],
        "phases": [],
        "enrollment": 0,
        "start_date": "",
        "completion_date": "",
        "classification": "",
        "classification_evidence": [],
        "delivery_mode": "",
        "sequence": "",
        "dramp_name": "",
        "dramp_evidence": [],
        "study_ids": [],
        "outcome": "",
        "failure_reason": "",
        "subsequent_trial_ids": [],
        "subsequent_evidence": [],
        "is_peptide": False,
        "comments": ""
    }
    
    # Remove markdown code blocks
    llm_response = re.sub(r'```[\w]*\n', '', llm_response)
    llm_response = re.sub(r'```', '', llm_response)
    
    # Define regex patterns
    patterns = {
        'nct_number': r'NCT Number:\s*(.+?)(?:\n|$)',
        'study_title': r'Study Title:\s*(.+?)(?:\n|$)',
        'study_status': r'Study Status:\s*(.+?)(?:\n|$)',
        'brief_summary': r'Brief Summary:\s*(.+?)(?:\nConditions:|$)',
        'conditions': r'Conditions:\s*(.+?)(?:\n|$)',
        'interventions': r'Interventions/Drug:\s*(.+?)(?:\n|$)',
        'phases': r'Phases:\s*(.+?)(?:\n|$)',
        'enrollment': r'Enrollment:\s*(\d+)',
        'start_date': r'Start Date:\s*(.+?)(?:\n|$)',
        'completion_date': r'Completion Date:\s*(.+?)(?:\n|$)',
        'classification': r'Classification:\s*(.+?)(?:\n|$)',
        'classification_evidence': r'Classification.*?Evidence:\s*(.+?)(?:\nDelivery Mode:|$)',
        'delivery_mode': r'Delivery Mode:\s*(.+?)(?:\n|$)',
        'sequence': r'Sequence:\s*(.+?)(?:\n|$)',
        'dramp_name': r'DRAMP Name:\s*(.+?)(?:\n|$)',
        'dramp_evidence': r'DRAMP.*?Evidence:\s*(.+?)(?:\nStudy IDs:|$)',
        'study_ids': r'Study IDs:\s*(.+?)(?:\n|$)',
        'outcome': r'Outcome:\s*(.+?)(?:\n|$)',
        'failure_reason': r'Reason for Failure:\s*(.+?)(?:\n|$)',
        'subsequent_trial_ids': r'Subsequent Trial IDs:\s*(.+?)(?:\n|$)',
        'subsequent_evidence': r'Subsequent.*?Evidence:\s*(.+?)(?:\nPeptide:|$)',
        'is_peptide': r'Peptide:\s*(.+?)(?:\n|$)',
        'comments': r'Comments:\s*(.+?)(?:\n```|$)',
    }
    
    # Extract each field
    for field, pattern in patterns.items():
        match = re.search(pattern, llm_response, re.DOTALL | re.IGNORECASE)
        if match:
            value = match.group(1).strip()
            value = value.strip('`').strip()
            
            # Filter placeholder text
            if _is_placeholder(value):
                result[field] = _get_default_value(field)
                continue
            
            # Parse based on field type
            result[field] = _parse_field_value(field, value)
    
    return result


def _is_placeholder(value: str) -> bool:
    """Check if value is a placeholder."""
    placeholder_patterns = [
        r'^\[.*\]$',
        r'NCT########',
        r'\[value from list\]',
        r'\[YYYY-MM-DD\]',
    ]
    
    return any(re.match(p, value) for p in placeholder_patterns)


def _get_default_value(field: str) -> Any:
    """Get default value for field type."""
    if field == 'is_peptide':
        return False
    elif field == 'enrollment':
        return 0
    elif field in ('conditions', 'interventions', 'phases', 'study_ids', 
                   'subsequent_trial_ids', 'classification_evidence', 
                   'dramp_evidence', 'subsequent_evidence'):
        return []
    else:
        return ""


def _parse_field_value(field: str, value: str) -> Any:
    """Parse value based on field type."""
    # Boolean field
    if field == 'is_peptide':
        return value.lower() in ('true', 'yes')
    
    # Integer field
    elif field == 'enrollment':
        try:
            return int(value)
        except:
            return 0
    
    # List fields (comma-separated)
    elif field in ('conditions', 'interventions', 'phases', 'study_ids', 
                   'subsequent_trial_ids'):
        if value and value.lower() != 'n/a':
            items = [item.strip() for item in value.split(',')]
            items = [item for item in items if item and item != 'N/A' and 
                    not item.startswith('[') and not item.endswith('...]')]
            return items
        else:
            return []
    
    # Evidence fields (can be list or single string)
    elif field in ('classification_evidence', 'dramp_evidence', 'subsequent_evidence'):
        if value and value.lower() != 'n/a' and not value.startswith('['):
            if ',' in value:
                return [item.strip() for item in value.split(',')]
            else:
                return [value] if value else []
        else:
            return []
    
    # String fields
    else:
        if value.lower() == 'n/a' or value.startswith('['):
            return ""
        else:
            return value