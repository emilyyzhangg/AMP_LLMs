# ============================================================================
# src/amp_llm/llm/research/parser.py
# ============================================================================
"""
Response parser for LLM extractions.
"""
import re
from typing import Dict, Any
from amp_llm.config.settings import get_logger

logger = get_logger(__name__)


class ResponseParser:
    """Parses LLM extraction responses into structured data."""
    
    @staticmethod
    def parse_extraction(llm_response: str) -> Dict[str, Any]:
        """
        Parse LLM extraction response.
        
        Args:
            llm_response: Raw LLM response
            
        Returns:
            Structured dictionary
        """
        # Remove markdown code blocks
        llm_response = re.sub(r'```[\w]*\n', '', llm_response)
        llm_response = re.sub(r'```', '', llm_response)
        
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
        
        # Define patterns
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
            'delivery_mode': r'Delivery Mode:\s*(.+?)(?:\n|$)',
            'outcome': r'Outcome:\s*(.+?)(?:\n|$)',
            'failure_reason': r'Reason for Failure:\s*(.+?)(?:\n|$)',
            'is_peptide': r'Peptide:\s*(.+?)(?:\n|$)',
            'comments': r'Comments:\s*(.+?)(?:\n|$)',
        }
        
        # Extract fields
        for field, pattern in patterns.items():
            match = re.search(pattern, llm_response, re.DOTALL | re.IGNORECASE)
            if match:
                value = match.group(1).strip()
                
                # Parse based on field type
                if field == 'is_peptide':
                    result[field] = value.lower() in ('true', 'yes')
                elif field == 'enrollment':
                    try:
                        result[field] = int(value)
                    except:
                        result[field] = 0
                elif field in ('conditions', 'interventions', 'phases', 'study_ids'):
                    if value and value.lower() != 'n/a':
                        result[field] = [
                            item.strip() 
                            for item in value.split(',')
                            if item.strip()
                        ]
                else:
                    result[field] = value if value.lower() != 'n/a' else ""
        
        return result
    
    @staticmethod
    def format_extraction_display(extraction_dict: Dict[str, Any]) -> str:
        """
        Format extraction for display.
        
        Args:
            extraction_dict: Parsed extraction
            
        Returns:
            Formatted string
        """
        lines = [
            f"NCT Number: {extraction_dict.get('nct_number', 'N/A')}",
            f"Title: {extraction_dict.get('study_title', 'N/A')}",
            f"Status: {extraction_dict.get('study_status', 'N/A')}",
            f"Phase: {', '.join(extraction_dict.get('phases', []))}",
            f"Enrollment: {extraction_dict.get('enrollment', 0)}",
            f"Classification: {extraction_dict.get('classification', 'N/A')}",
            f"Outcome: {extraction_dict.get('outcome', 'N/A')}",
            f"Peptide: {extraction_dict.get('is_peptide', False)}",
        ]
        
        return "\n".join(lines)