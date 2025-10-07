"""
Clinical Trial RAG (Retrieval-Augmented Generation) System
Indexes JSON database of clinical trials and provides structured extraction.
"""
import json
import re
from pathlib import Path
from typing import Dict, List, Optional, Any, Literal
from dataclasses import dataclass, asdict
from datetime import datetime
from enum import Enum
import logging

logger = logging.getLogger(__name__)


# Validation Enums
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
    AMP_INFECTION = "AMP(infection)"
    AMP_OTHER = "AMP(other)"
    OTHER = "Other"


class DeliveryMode(str, Enum):
    """Valid delivery mode values."""
    INJECTION_INTRAMUSCULAR = "Injection/Infusion - Intramuscular"
    INJECTION_OTHER = "Injection/Infusion - Other/Unspecified"
    INJECTION_SUBCUTANEOUS = "Injection/Infusion - Subcutaneous/Intradermal"
    IV = "IV"
    INTRANASAL = "Intranasal"
    ORAL_TABLET = "Oral - Tablet"
    ORAL_CAPSULE = "Oral - Capsule"
    ORAL_FOOD = "Oral - Food"
    ORAL_DRINK = "Oral - Drink"
    ORAL_UNSPECIFIED = "Oral - Unspecified"
    TOPICAL_CREAM = "Topical - Cream/Gel"
    TOPICAL_POWDER = "Topical - Powder"
    TOPICAL_SPRAY = "Topical - Spray"
    TOPICAL_STRIP = "Topical - Strip/Covering"
    TOPICAL_WASH = "Topical - Wash"
    TOPICAL_UNSPECIFIED = "Topical - Unspecified"
    OTHER_UNSPECIFIED = "Other/Unspecified"
    INHALATION = "Inhalation"


class Outcome(str, Enum):
    """Valid outcome values."""
    POSITIVE = "Positive"
    WITHDRAWN = "Withdrawn"
    TERMINATED = "Terminated"
    FAILED_COMPLETED = "Failed - completed trial"
    RECRUITING = "Recruiting"
    UNKNOWN = "Unknown"
    ACTIVE_NOT_RECRUITING = "Active, not recruiting"


class FailureReason(str, Enum):
    """Valid failure/withdrawal reason values."""
    BUSINESS_REASON = "Business Reason"
    INEFFECTIVE = "Ineffective for purpose"
    TOXIC_UNSAFE = "Toxic/Unsafe"
    COVID = "Due to covid"
    RECRUITMENT_ISSUES = "Recruitment issues"
    NOT_APPLICABLE = "N/A"


# Helper function for validation
def validate_enum_value(value: str, enum_class, field_name: str) -> str:
    """
    Validate a value against an enum class.
    
    Args:
        value: Value to validate
        enum_class: Enum class to validate against
        field_name: Name of field (for logging)
        
    Returns:
        Valid enum value or closest match
    """
    if not value or value == "N/A":
        return "N/A"
    
    # Direct match
    try:
        for member in enum_class:
            if value.upper() == member.value.upper():
                return member.value
            # Also try without spaces/special chars
            if value.upper().replace(" ", "").replace("_", "") == member.value.upper().replace(" ", "").replace("_", "").replace("|", "").replace("(", "").replace(")", ""):
                return member.value
    except Exception:
        pass
    
    # Fuzzy matching
    value_lower = value.lower()
    for member in enum_class:
        if value_lower in member.value.lower() or member.value.lower() in value_lower:
            logger.info(f"Fuzzy matched '{value}' to '{member.value}' for {field_name}")
            return member.value
    
    # No match found
    logger.warning(f"Could not validate '{value}' for {field_name}, using as-is")
    return value


@dataclass
class ClinicalTrialExtraction:
    """Structured extraction of clinical trial data."""
    nct_number: str
    study_title: str = ""
    study_status: str = ""
    brief_summary: str = ""
    conditions: List[str] = None
    interventions: List[str] = None
    phases: List[str] = None
    enrollment: int = 0
    start_date: str = ""
    completion_date: str = ""
    classification: str = ""
    classification_evidence: List[str] = None
    delivery_mode: str = ""
    sequence: str = ""
    dramp_name: str = ""
    dramp_evidence: List[str] = None
    study_ids: List[str] = None  # PMIDs, DOIs
    outcome: str = ""
    failure_reason: str = ""
    subsequent_trial_ids: List[str] = None
    subsequent_evidence: List[str] = None
    is_peptide: bool = False
    comments: str = ""
    
    def __post_init__(self):
        """Initialize list fields if None."""
        if self.conditions is None:
            self.conditions = []
        if self.interventions is None:
            self.interventions = []
        if self.phases is None:
            self.phases = []
        if self.classification_evidence is None:
            self.classification_evidence = []
        if self.dramp_evidence is None:
            self.dramp_evidence = []
        if self.study_ids is None:
            self.study_ids = []
        if self.subsequent_trial_ids is None:
            self.subsequent_trial_ids = []
        if self.subsequent_evidence is None:
            self.subsequent_evidence = []
    
    def to_formatted_string(self) -> str:
        """Convert to formatted string for display."""
        lines = [
            f"NCT Number: {self.nct_number}",
            f"Study Title: {self.study_title}",
            f"Study Status: {self.study_status}",
            f"Brief Summary: {self.brief_summary}",
            f"Conditions: {', '.join(self.conditions) if self.conditions else 'N/A'}",
            f"Interventions/Drug: {', '.join(self.interventions) if self.interventions else 'N/A'}",
            f"Phases: {', '.join(self.phases) if self.phases else 'N/A'}",
            f"Enrollment: {self.enrollment}",
            f"Start Date: {self.start_date}",
            f"Completion Date: {self.completion_date}",
            f"Classification: {self.classification}",
            f"  Evidence: {', '.join(self.classification_evidence) if self.classification_evidence else 'N/A'}",
            f"Delivery Mode: {self.delivery_mode}",
            f"Sequence: {self.sequence}",
            f"DRAMP Name: {self.dramp_name}",
            f"  Evidence: {', '.join(self.dramp_evidence) if self.dramp_evidence else 'N/A'}",
            f"Study IDs: {', '.join(self.study_ids) if self.study_ids else 'N/A'}",
            f"Outcome: {self.outcome}",
            f"Reason for Failure: {self.failure_reason}",
            f"Subsequent Trial IDs: {', '.join(self.subsequent_trial_ids) if self.subsequent_trial_ids else 'N/A'}",
            f"  Evidence: {', '.join(self.subsequent_evidence) if self.subsequent_evidence else 'N/A'}",
            f"Peptide: {'Yes' if self.is_peptide else 'No'}",
            f"Comments: {self.comments}",
        ]
        return "\n".join(lines)


class ClinicalTrialDatabase:
    """Manages indexed clinical trial database."""
    
    def __init__(self, database_path: Path):
        """
        Initialize database.
        
        Args:
            database_path: Path to directory containing JSON files or single JSON file
        """
        self.database_path = Path(database_path)
        self.trials: Dict[str, Dict] = {}
        self.index_built = False
    
    def build_index(self):
        """Build index of all clinical trials by NCT number."""
        logger.info(f"Building index from {self.database_path}")
        
        if self.database_path.is_file():
            # Single JSON file
            self._index_file(self.database_path)
        elif self.database_path.is_dir():
            # Directory of JSON files
            for json_file in self.database_path.glob("*.json"):
                self._index_file(json_file)
            for json_file in self.database_path.glob("**/*.json"):
                self._index_file(json_file)
        
        logger.info(f"Indexed {len(self.trials)} clinical trials")
        self.index_built = True
    
    def _index_file(self, filepath: Path):
        """Index a single JSON file."""
        try:
            with open(filepath, 'r', encoding='utf-8') as f:
                data = json.load(f)
            
            # Handle different JSON structures
            if isinstance(data, dict):
                nct_id = data.get('nct_id')
                if nct_id:
                    self.trials[nct_id] = data
                elif 'sources' in data:
                    # May be wrapped structure
                    nct_id = self._extract_nct_from_data(data)
                    if nct_id:
                        self.trials[nct_id] = data
            elif isinstance(data, list):
                # Array of trials
                for trial in data:
                    nct_id = trial.get('nct_id') or self._extract_nct_from_data(trial)
                    if nct_id:
                        self.trials[nct_id] = trial
            
        except Exception as e:
            logger.error(f"Error indexing {filepath}: {e}")
    
    def _extract_nct_from_data(self, data: Dict) -> Optional[str]:
        """Extract NCT ID from various data structures."""
        # Try common locations
        if 'nct_id' in data:
            return data['nct_id']
        
        # Check in sources
        sources = data.get('sources', {})
        ct_data = sources.get('clinical_trials', {}).get('data', {})
        
        if 'protocolSection' in ct_data:
            return ct_data['protocolSection'].get('identificationModule', {}).get('nctId')
        
        return None
    
    def search(self, query: str) -> List[str]:
        """
        Search for trials matching query.
        
        Args:
            query: Search query (NCT number, condition, drug name, etc.)
            
        Returns:
            List of matching NCT numbers
        """
        if not self.index_built:
            self.build_index()
        
        query_lower = query.lower().strip()
        matches = []
        
        # Direct NCT number match
        nct_pattern = r'NCT\d+'
        nct_matches = re.findall(nct_pattern, query.upper())
        for nct in nct_matches:
            if nct in self.trials:
                matches.append(nct)
        
        if matches:
            return matches
        
        # Search in trial data
        for nct_id, trial_data in self.trials.items():
            trial_str = json.dumps(trial_data).lower()
            if query_lower in trial_str:
                matches.append(nct_id)
        
        return matches[:10]  # Limit to 10 matches
    
    def get_trial(self, nct_id: str) -> Optional[Dict]:
        """Get trial data by NCT number."""
        if not self.index_built:
            self.build_index()
        
        return self.trials.get(nct_id.upper())
    
    def extract_structured_data(self, nct_id: str) -> Optional[ClinicalTrialExtraction]:
        """
        Extract structured data from trial.
        
        Args:
            nct_id: NCT number
            
        Returns:
            ClinicalTrialExtraction object or None if not found
        """
        trial = self.get_trial(nct_id)
        if not trial:
            return None
        
        extraction = ClinicalTrialExtraction(nct_number=nct_id.upper())
        
        try:
            # Navigate the nested structure based on your sample
            sources = trial.get('sources', {})
            ct_source = sources.get('clinical_trials', {})
            ct_data = ct_source.get('data', {})
            protocol = ct_data.get('protocolSection', {})
            
            # Identification
            ident = protocol.get('identificationModule', {})
            extraction.study_title = (
                ident.get('officialTitle') or 
                ident.get('briefTitle') or 
                ""
            )
            
            # Status
            status_mod = protocol.get('statusModule', {})
            extraction.study_status = status_mod.get('overallStatus', '')
            extraction.start_date = status_mod.get('startDateStruct', {}).get('date', '')
            extraction.completion_date = status_mod.get('completionDateStruct', {}).get('date', '')
            
            # Description
            desc = protocol.get('descriptionModule', {})
            extraction.brief_summary = desc.get('briefSummary', '')
            
            # Conditions
            cond_mod = protocol.get('conditionsModule', {})
            extraction.conditions = cond_mod.get('conditions', [])
            
            # Design (phases)
            design = protocol.get('designModule', {})
            extraction.phases = design.get('phases', [])
            extraction.enrollment = design.get('enrollmentInfo', {}).get('count', 0)
            
            # Interventions
            arms_int = protocol.get('armsInterventionsModule', {})
            interventions = arms_int.get('interventions', [])
            extraction.interventions = [
                f"{i.get('type', '')}: {i.get('name', '')}" 
                for i in interventions
            ]
            
            # Study IDs from PubMed/PMC
            pubmed = sources.get('pubmed', {})
            extraction.study_ids = [f"PMID:{pmid}" for pmid in pubmed.get('pmids', [])]
            
            pmc = sources.get('pmc', {})
            for pmcid in pmc.get('pmcids', []):
                extraction.study_ids.append(f"PMC:{pmcid}")
            
            # Check if peptide-related
            full_text = json.dumps(trial).lower()
            peptide_keywords = ['peptide', 'amp', 'antimicrobial peptide']
            extraction.is_peptide = any(kw in full_text for kw in peptide_keywords)
            
            # Determine outcome from status
            status = extraction.study_status.upper()
            if status == 'COMPLETED':
                extraction.outcome = 'Completed'
            elif status in ('TERMINATED', 'WITHDRAWN', 'SUSPENDED'):
                extraction.outcome = 'Failed/Terminated'
                extraction.failure_reason = f"Study {status.lower()}"
            elif status in ('RECRUITING', 'ACTIVE_NOT_RECRUITING', 'ENROLLING_BY_INVITATION'):
                extraction.outcome = 'Ongoing'
            else:
                extraction.outcome = status
            
        except Exception as e:
            logger.error(f"Error extracting data for {nct_id}: {e}")
        
        return extraction


class ClinicalTrialRAG:
    """RAG system for clinical trial research."""
    
    def __init__(self, database_path: Path):
        """
        Initialize RAG system.
        
        Args:
            database_path: Path to clinical trial database
        """
        self.db = ClinicalTrialDatabase(database_path)
    
    def retrieve(self, query: str) -> List[ClinicalTrialExtraction]:
        """
        Retrieve relevant trials and extract structured data.
        
        Args:
            query: User query
            
        Returns:
            List of structured extractions
        """
        # Search for matching trials
        nct_ids = self.db.search(query)
        
        # Extract structured data
        extractions = []
        for nct_id in nct_ids:
            extraction = self.db.extract_structured_data(nct_id)
            if extraction:
                extractions.append(extraction)
        
        return extractions
    
    def get_context_for_llm(self, query: str, max_trials: int = 5) -> str:
        """
        Get formatted context to provide to LLM.
        
        Args:
            query: User query
            max_trials: Maximum number of trials to include
            
        Returns:
            Formatted context string
        """
        extractions = self.retrieve(query)[:max_trials]
        
        if not extractions:
            return "No clinical trials found matching the query."
        
        context_parts = [
            f"Found {len(extractions)} clinical trial(s):\n"
        ]
        
        for i, extraction in enumerate(extractions, 1):
            context_parts.append(f"\n{'='*80}")
            context_parts.append(f"TRIAL {i}:")
            context_parts.append('='*80)
            context_parts.append(extraction.to_formatted_string())
        
        return "\n".join(context_parts)
    
    def extract_to_dict(self, nct_id: str) -> Optional[Dict[str, Any]]:
        """Extract trial data as dictionary."""
        extraction = self.db.extract_structured_data(nct_id)
        if extraction:
            return asdict(extraction)
        return None
    
    def export_extractions(
        self, 
        nct_ids: List[str], 
        output_path: Path,
        format: str = 'json'
    ):
        """
        Export multiple extractions to file.
        
        Args:
            nct_ids: List of NCT numbers
            output_path: Output file path
            format: 'json' or 'csv'
        """
        extractions = []
        for nct_id in nct_ids:
            extraction = self.db.extract_structured_data(nct_id)
            if extraction:
                extractions.append(asdict(extraction))
        
        if format == 'json':
            with open(output_path, 'w', encoding='utf-8') as f:
                json.dump(extractions, f, indent=2, ensure_ascii=False)
        
        elif format == 'csv':
            import csv
            if extractions:
                with open(output_path, 'w', newline='', encoding='utf-8') as f:
                    # Flatten lists for CSV
                    fieldnames = list(extractions[0].keys())
                    writer = csv.DictWriter(f, fieldnames=fieldnames)
                    writer.writeheader()
                    
                    for ext in extractions:
                        # Convert lists to comma-separated strings
                        row = {}
                        for key, value in ext.items():
                            if isinstance(value, list):
                                row[key] = ', '.join(map(str, value))
                            else:
                                row[key] = value
                        writer.writerow(row)
        
        logger.info(f"Exported {len(extractions)} trials to {output_path}")