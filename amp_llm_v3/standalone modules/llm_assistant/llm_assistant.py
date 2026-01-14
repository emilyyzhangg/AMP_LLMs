"""
LLM Assistant API Service (Port 9004)
=====================================

RESTful API for clinical trial annotation using:
- json_parser.py for extracting annotation-relevant data
- prompt_generator.py for generating sophisticated LLM prompts
- Ollama for LLM inference

This service receives trial JSON data and returns structured annotations.
"""
import os
import logging
import json
import httpx
from pathlib import Path
from typing import Dict, Any, List, Optional
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field
import re
from typing import Dict, Set

# Setup logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# Import local modules
try:
    from json_parser import ClinicalTrialAnnotationParser
    HAS_JSON_PARSER = True
    logger.info("✅ ClinicalTrialAnnotationParser loaded")
except ImportError as e:
    logger.warning(f"⚠️ Could not load ClinicalTrialAnnotationParser: {e}")
    HAS_JSON_PARSER = False

try:
    from prompt_generator import PromptGenerator
    HAS_PROMPT_GEN = True
    logger.info("✅ PromptGenerator loaded")
except ImportError as e:
    logger.warning(f"⚠️ Could not load PromptGenerator: {e}")
    HAS_PROMPT_GEN = False


# ============================================================================
# Configuration
# ============================================================================

class AssistantConfig:
    """Configuration for the LLM Assistant"""
    OLLAMA_HOST = "localhost"
    OLLAMA_PORT = 11434
    
    @property
    def OLLAMA_BASE_URL(self):
        return f"http://{self.OLLAMA_HOST}:{self.OLLAMA_PORT}"
    
    API_VERSION = "1.0.0"
    SERVICE_NAME = "LLM Assistant API"
    SERVICE_PORT = 9004
    CORS_ORIGINS = ["*"]
    
    # Timeouts
    LLM_TIMEOUT = 300  # 5 minutes for annotation
    
    # Default model parameters
    DEFAULT_TEMPERATURE = 0.15
    DEFAULT_TOP_P = 0.9
    DEFAULT_TOP_K = 40

config = AssistantConfig()


# ============================================================================
# Initialize FastAPI app
# ============================================================================

app = FastAPI(
    title=config.SERVICE_NAME,
    description="RESTful API for clinical trial annotation using JSON parsing and LLM",
    version=config.API_VERSION,
    docs_url="/docs",
    redoc_url="/redoc"
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=config.CORS_ORIGINS,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ============================================================================
# Pydantic Models
# ============================================================================

class TrialData(BaseModel):
    """Input model for trial data"""
    nct_id: str
    data: Dict[str, Any]  # The JSON data from NCT API
    source: str = "unknown"  # "file" or "fetched"


class AnnotationRequest(BaseModel):
    """Request model for annotation"""
    trial_data: TrialData
    model: str = "llama3.2"
    temperature: float = Field(default=0.15, ge=0.0, le=2.0)
    use_extraction_prompt: bool = True  # Use sophisticated extraction prompt
    include_evidence: bool = True  # Include evidence in response


class BatchAnnotationRequest(BaseModel):
    """Request model for batch annotation"""
    trials: List[TrialData]
    model: str = "llama3.2"
    temperature: float = Field(default=0.15, ge=0.0, le=2.0)


class AnnotationResult(BaseModel):
    """Response model for a single annotation"""
    nct_id: str
    annotation: str
    parsed_data: Dict[str, str] = {}  # Parsed structured data for CSV export
    model: str
    status: str  # "success" or "error"
    processing_time_seconds: float
    sources_summary: Dict[str, Any] = {}
    error: Optional[str] = None


class BatchAnnotationResponse(BaseModel):
    """Response model for batch annotation"""
    results: List[AnnotationResult]
    total: int
    successful: int
    failed: int
    total_time_seconds: float


class ParsedTrialInfo(BaseModel):
    """Response model for parsed trial information"""
    nct_id: str
    classification_info: Dict[str, Any]
    delivery_mode_info: Dict[str, Any]
    outcome_info: Dict[str, Any]
    failure_reason_info: Dict[str, Any]
    peptide_info: Dict[str, Any]
    combined_text: str


# ============================================================================
# Core Annotation Functions
# ============================================================================


class AnnotationResponseParser:
    """Parse LLM annotation responses into structured data."""
    
    CSV_COLUMNS = [
        'NCT ID', 'Study Title', 'Study Status', 'Brief Summary', 'Conditions',
        'Drug', 'Phase', 'Enrollment', 'Start Date', 'Completion Date',
        'Classification', 'Classification Evidence',
        'Delivery Mode', 'Delivery Mode Evidence',
        'Outcome', 'Outcome Evidence',
        'Reason for Failure', 'Reason for Failure Evidence',
        'Peptide', 'Peptide Evidence',
        'Sequence', 'Sequence Evidence',
        'Study ID', 'Comments'
    ]
    
    # Valid values for validation
    VALID_VALUES = {
        'Classification': {'AMP', 'Other'},
        'Delivery Mode': {'Injection/Infusion', 'Topical', 'Oral', 'Other'},
        'Outcome': {'Positive', 'Withdrawn', 'Terminated', 'Failed - completed trial', 'Active', 'Unknown'},
        'Reason for Failure': {'Business reasons', 'Ineffective for purpose', 'Toxic/unsafe', 'Due to covid', 'Recruitment issues', 'N/A'},
        'Peptide': {'True', 'False'}
    }
    
    @classmethod
    def parse_response(cls, llm_response: str, nct_id: str) -> Dict[str, str]:
        """
        Parse LLM response text into structured dictionary.
        
        Handles both newline-separated and inline ** formatted output.
        """
        result = {col: '' for col in cls.CSV_COLUMNS}
        result['NCT ID'] = nct_id
        
        if not llm_response:
            return result
        
        # Normalize the response - convert ** format to newlines
        normalized = cls._normalize_response(llm_response)
        
        # Define patterns for each field
        patterns = {
            'Classification': r'Classification:\s*([^\n]+?)(?:\n|$)',
            'Delivery Mode': r'Delivery Mode:\s*([^\n]+?)(?:\n|$)',
            'Outcome': r'Outcome:\s*([^\n]+?)(?:\n|$)',
            'Reason for Failure': r'Reason for Failure:\s*([^\n]+?)(?:\n|$)',
            'Peptide': r'Peptide:\s*([^\n]+?)(?:\n|$)',
            'Sequence': r'Sequence:\s*([^\n]+?)(?:\n|$)',
            'Study ID': r'Study IDs?:\s*([^\n]+?)(?:\n|$)',
            'Comments': r'Comments:\s*([^\n]+?)(?:\n|$)',
        }
        
        # Evidence patterns
        evidence_patterns = {
            'Classification Evidence': r'Classification:[^\n]*\n\s*Evidence:\s*([^\n]+)',
            'Delivery Mode Evidence': r'Delivery Mode:[^\n]*\n\s*Evidence:\s*([^\n]+)',
            'Outcome Evidence': r'Outcome:[^\n]*\n\s*Evidence:\s*([^\n]+)',
            'Reason for Failure Evidence': r'Reason for Failure:[^\n]*\n\s*Evidence:\s*([^\n]+)',
            'Peptide Evidence': r'Peptide:[^\n]*\n\s*Evidence:\s*([^\n]+)',
            'Sequence Evidence': r'Sequence:[^\n]*\n\s*Evidence:\s*([^\n]+)',
        }
        
        # Extract main fields
        for field, pattern in patterns.items():
            match = re.search(pattern, normalized, re.IGNORECASE)
            if match:
                value = match.group(1).strip()
                value = re.sub(r'\s+', ' ', value)
                value = value.rstrip('.')
                
                if value.lower() in ['n/a', 'not available', 'none', 'unknown', 'na']:
                    value = 'N/A'
                
                # Validate against valid values
                if field in cls.VALID_VALUES:
                    value = cls._match_valid_value(value, cls.VALID_VALUES[field])
                
                result[field] = value
        
        # Extract evidence fields
        for field, pattern in evidence_patterns.items():
            match = re.search(pattern, normalized, re.IGNORECASE | re.DOTALL)
            if match:
                value = match.group(1).strip()
                value = re.sub(r'\s+', ' ', value)
                result[field] = value
        
        return result
    
    @classmethod
    def _normalize_response(cls, response: str) -> str:
        """
        Normalize LLM response to have consistent newline formatting.
        
        Converts: "AMP **Evidence:** reason **Delivery Mode:** ..."
        To:       "AMP\n  Evidence: reason\nDelivery Mode: ..."
        """
        # First, handle the ** format by converting to newlines
        # Pattern: **FieldName:** -> \nFieldName:
        normalized = re.sub(r'\s*\*\*([^*]+):\*\*\s*', r'\n\1: ', response)
        
        # Also handle *Field:* format (single asterisks)
        normalized = re.sub(r'\s*\*([^*]+):\*\s*', r'\n\1: ', normalized)
        
        # Handle case where Evidence comes right after value on same conceptual line
        # "Classification: AMP\nEvidence:" -> "Classification: AMP\n  Evidence:"
        normalized = re.sub(r'\n(Evidence:)', r'\n  \1', normalized)
        
        # Clean up multiple newlines
        normalized = re.sub(r'\n{3,}', '\n\n', normalized)
        
        # Clean up leading/trailing whitespace on lines
        lines = [line.strip() for line in normalized.split('\n')]
        normalized = '\n'.join(lines)
        
        return normalized
    
    @classmethod
    def _match_valid_value(cls, value: str, valid_set: Set[str]) -> str:
        """Try to match a value to the closest valid value."""
        # Exact match
        if value in valid_set:
            return value
        
        # Case-insensitive match
        value_lower = value.lower()
        for valid in valid_set:
            if valid.lower() == value_lower:
                return valid
        
        # Partial match
        for valid in valid_set:
            if valid.lower() in value_lower or value_lower in valid.lower():
                return valid
        
        # Special handling for common variations
        mappings = [
            (['injection', 'infusion', 'iv', 'subcutaneous', 'intramuscular', 'intravenous'], 'Injection/Infusion'),
            (['topical', 'cream', 'gel', 'ointment', 'skin', 'dermal'], 'Topical'),
            (['oral', 'tablet', 'capsule', 'pill', 'mouth'], 'Oral'),
            (['true', 'yes', 'peptide'], 'True'),
            (['false', 'no', 'antibody', 'small molecule'], 'False'),
            (['active', 'recruiting', 'ongoing'], 'Active'),
            (['positive', 'success', 'effective', 'met endpoint'], 'Positive'),
            (['failed', 'negative', 'ineffective', 'did not meet'], 'Failed - completed trial'),
            (['withdrawn'], 'Withdrawn'),
            (['terminated'], 'Terminated'),
            (['unknown', 'unclear'], 'Unknown'),
        ]
        
        for keywords, mapped_value in mappings:
            if mapped_value in valid_set:
                for keyword in keywords:
                    if keyword in value_lower:
                        return mapped_value
        
        return value
    
    @classmethod
    def validate_response(cls, parsed_data: Dict[str, str]) -> bool:
        """Check if we got valid annotations."""
        required_fields = ['Classification', 'Delivery Mode', 'Outcome', 'Peptide']
        
        for field in required_fields:
            value = parsed_data.get(field, '').strip()
            if not value:
                return False
        
        return True


class TrialAnnotator:
    """Core class for annotating clinical trials"""
    
    def __init__(self):
        self.prompt_generator = PromptGenerator() if HAS_PROMPT_GEN else None
    
    def parse_trial_data(self, trial_data: Dict[str, Any]) -> Dict[str, Any]:
        """
        Parse trial data using the JSON parser to extract annotation-relevant info.
        
        Args:
            trial_data: Raw trial data dictionary
            
        Returns:
            Dictionary with parsed information for each annotation field
        """
        if not HAS_JSON_PARSER:
            logger.warning("JSON parser not available, using raw data")
            return {
                "raw_data": trial_data,
                "parsed": False
            }
        
        # Create a temporary parser with the data
        # The parser expects a file, but we can adapt it for in-memory data
        parsed_info = {
            "nct_id": trial_data.get("nct_id", "Unknown"),
            "parsed": True
        }
        
        # Extract using parser logic adapted for dict input
        # Try multiple possible paths for the protocol section
        protocol = None
        
        # Path 1: results.sources.clinical_trials.data.protocolSection (NCT Lookup format)
        protocol = self._safe_get(
            trial_data, 
            'results', 'sources', 'clinical_trials', 'data', 'protocolSection',
            default={}
        )
        
        if not protocol:
            # Path 2: sources.clinical_trials.data.protocolSection
            protocol = self._safe_get(
                trial_data, 
                'sources', 'clinical_trials', 'data', 'protocolSection',
                default={}
            )
        
        if not protocol:
            # Path 3: results.sources.clinicaltrials (alternate naming)
            protocol = self._safe_get(
                trial_data,
                'results', 'sources', 'clinicaltrials', 'data', 'protocolSection',
                default={}
            )
        
        if not protocol:
            # Path 4: sources.clinicaltrials (alternate naming)
            protocol = self._safe_get(
                trial_data,
                'sources', 'clinicaltrials', 'data', 'protocolSection',
                default={}
            )
        
        logger.info(f"Protocol section found: {bool(protocol)}")
        
        # Classification info
        parsed_info["classification"] = self._extract_classification_info(trial_data, protocol)
        
        # Delivery mode info
        parsed_info["delivery_mode"] = self._extract_delivery_mode_info(trial_data, protocol)
        
        # Outcome info
        parsed_info["outcome"] = self._extract_outcome_info(trial_data, protocol)
        
        # Failure reason info
        parsed_info["failure_reason"] = self._extract_failure_reason_info(trial_data, protocol)
        
        # Peptide info
        parsed_info["peptide"] = self._extract_peptide_info(trial_data, protocol)
        
        return parsed_info
    
    def _safe_get(self, dictionary: Dict, *keys, default=None) -> Any:
        """Safely navigate nested dictionary keys."""
        current = dictionary
        for key in keys:
            if isinstance(current, dict) and key in current:
                current = current[key]
            else:
                return default
        return current if current is not None else default
    
    def _extract_classification_info(self, trial_data: Dict, protocol: Dict) -> Dict:
        """Extract classification-relevant information."""
        id_module = self._safe_get(protocol, 'identificationModule', default={})
        desc_module = self._safe_get(protocol, 'descriptionModule', default={})
        arms_module = self._safe_get(protocol, 'armsInterventionsModule', default={})
        conditions_module = self._safe_get(protocol, 'conditionsModule', default={})
        
        # Get NCT ID from multiple possible locations
        nct_id = trial_data.get("nct_id") or self._safe_get(id_module, 'nctId', default="Unknown")
        
        info = {
            "nct_id": nct_id,
            "brief_title": id_module.get("briefTitle", "Not available"),
            "official_title": id_module.get("officialTitle", "Not available"),
            "brief_summary": desc_module.get("briefSummary", "Not available"),
            "detailed_description": desc_module.get("detailedDescription", "Not available"),
            "conditions": conditions_module.get("conditions", []),
            "keywords": conditions_module.get("keywords", []),
            "interventions": []
        }
        
        for intervention in arms_module.get('interventions', []):
            info['interventions'].append({
                'type': intervention.get('type', 'Not specified'),
                'name': intervention.get('name', 'Not specified'),
                'description': intervention.get('description', 'Not specified')
            })
        
        return info
    
    def _extract_delivery_mode_info(self, trial_data: Dict, protocol: Dict) -> Dict:
        """Extract delivery mode-relevant information."""
        id_module = self._safe_get(protocol, 'identificationModule', default={})
        desc_module = self._safe_get(protocol, 'descriptionModule', default={})
        arms_module = self._safe_get(protocol, 'armsInterventionsModule', default={})
        
        info = {
            "nct_id": trial_data.get("nct_id"),
            "brief_title": id_module.get("briefTitle", "Not available"),
            "brief_summary": desc_module.get("briefSummary", "Not available"),
            "detailed_description": desc_module.get("detailedDescription", "Not available"),
            "interventions": [],
            "arm_groups": []
        }
        
        for intervention in arms_module.get('interventions', []):
            info['interventions'].append({
                'type': intervention.get('type', 'Not specified'),
                'name': intervention.get('name', 'Not specified'),
                'description': intervention.get('description', 'Not specified')
            })
        
        for arm in arms_module.get('armGroups', []):
            info['arm_groups'].append({
                'label': arm.get('label', 'Not specified'),
                'type': arm.get('type', 'Not specified'),
                'description': arm.get('description', 'Not specified')
            })
        
        return info
    
    def _extract_outcome_info(self, trial_data: Dict, protocol: Dict) -> Dict:
        """Extract outcome-relevant information."""
        id_module = self._safe_get(protocol, 'identificationModule', default={})
        status_module = self._safe_get(protocol, 'statusModule', default={})
        outcomes_module = self._safe_get(protocol, 'outcomesModule', default={})
        conditions_module = self._safe_get(protocol, 'conditionsModule', default={})
        
        # Try multiple paths for has_results
        has_results = self._safe_get(trial_data, 'results', 'sources', 'clinical_trials', 'data', 'hasResults', default=False)
        if not has_results:
            has_results = self._safe_get(trial_data, 'sources', 'clinical_trials', 'data', 'hasResults', default=False)
        
        info = {
            "nct_id": trial_data.get("nct_id"),
            "brief_title": id_module.get("briefTitle", "Not available"),
            "overall_status": status_module.get("overallStatus", "Not available"),
            "status_verified_date": status_module.get("statusVerifiedDate", "Not available"),
            "why_stopped": status_module.get("whyStopped", "Not available"),
            "start_date": self._safe_get(status_module, 'startDateStruct', 'date', default="Not available"),
            "completion_date": self._safe_get(status_module, 'completionDateStruct', 'date', default="Not available"),
            "primary_completion_date": self._safe_get(status_module, 'primaryCompletionDateStruct', 'date', default="Not available"),
            "has_results": has_results,
            "primary_outcomes": [],
            "secondary_outcomes": [],
            "conditions": conditions_module.get("conditions", [])
        }
        
        for outcome in outcomes_module.get('primaryOutcomes', []):
            info['primary_outcomes'].append({
                'measure': outcome.get('measure', 'Not specified'),
                'description': outcome.get('description', 'Not specified'),
                'timeFrame': outcome.get('timeFrame', 'Not specified')
            })
        
        for outcome in outcomes_module.get('secondaryOutcomes', []):
            info['secondary_outcomes'].append({
                'measure': outcome.get('measure', 'Not specified'),
                'description': outcome.get('description', 'Not specified'),
                'timeFrame': outcome.get('timeFrame', 'Not specified')
            })
        
        return info
    
    def _extract_failure_reason_info(self, trial_data: Dict, protocol: Dict) -> Dict:
        """Extract failure reason-relevant information."""
        id_module = self._safe_get(protocol, 'identificationModule', default={})
        status_module = self._safe_get(protocol, 'statusModule', default={})
        design_module = self._safe_get(protocol, 'designModule', default={})
        
        enrollment_info = design_module.get('enrollmentInfo', {})
        
        info = {
            "nct_id": trial_data.get("nct_id"),
            "brief_title": id_module.get("briefTitle", "Not available"),
            "overall_status": status_module.get("overallStatus", "Not available"),
            "why_stopped": status_module.get("whyStopped", "Not available"),
            "start_date": self._safe_get(status_module, 'startDateStruct', 'date', default="Not available"),
            "completion_date": self._safe_get(status_module, 'completionDateStruct', 'date', default="Not available"),
            "enrollment_count": enrollment_info.get('count', 'Not available'),
            "enrollment_type": enrollment_info.get('type', 'Not available')
        }
        
        return info
    
    def _extract_peptide_info(self, trial_data: Dict, protocol: Dict) -> Dict:
        """Extract peptide-relevant information."""
        id_module = self._safe_get(protocol, 'identificationModule', default={})
        desc_module = self._safe_get(protocol, 'descriptionModule', default={})
        arms_module = self._safe_get(protocol, 'armsInterventionsModule', default={})
        conditions_module = self._safe_get(protocol, 'conditionsModule', default={})
        
        info = {
            "nct_id": trial_data.get("nct_id"),
            "brief_title": id_module.get("briefTitle", "Not available"),
            "official_title": id_module.get("officialTitle", "Not available"),
            "brief_summary": desc_module.get("briefSummary", "Not available"),
            "conditions": conditions_module.get("conditions", []),
            "keywords": conditions_module.get("keywords", []),
            "interventions": []
        }
        
        for intervention in arms_module.get('interventions', []):
            info['interventions'].append({
                'type': intervention.get('type', 'Not specified'),
                'name': intervention.get('name', 'Not specified'),
                'description': intervention.get('description', 'Not specified')
            })
        
        # Handle nested sources structure (results.sources or sources)
        sources = trial_data.get("sources", {})
        if not sources and "results" in trial_data:
            sources = trial_data.get("results", {}).get("sources", {})
        
        # Add PubMed/PMC data if available
        pubmed_data = sources.get("pubmed", {})
        if pubmed_data.get("success"):
            info["pubmed_articles"] = pubmed_data.get("data", {}).get("pmids", [])
        
        pmc_data = sources.get("pmc", {})
        if pmc_data.get("success"):
            info["pmc_articles"] = pmc_data.get("data", {}).get("pmcids", [])
        
        pmc_bioc = sources.get("pmc_bioc", {})
        if pmc_bioc.get("success"):
            bioc_data = pmc_bioc.get("data", {})
            info["bioc_annotations"] = {
                "total_fetched": bioc_data.get("total_fetched", 0),
                "articles_processed": len(bioc_data.get("articles", []))
            }
        
        return info
    
    def generate_prompt(self, trial_data: Dict[str, Any], nct_id: str) -> str:
        """
        Generate annotation prompt using the PromptGenerator.
        
        Args:
            trial_data: Trial data dictionary
            nct_id: NCT ID
            
        Returns:
            Formatted prompt string
        """
        if not self.prompt_generator:
            logger.warning("PromptGenerator not available, using basic prompt")
            return self._generate_basic_prompt(trial_data, nct_id)
        
        # Format data for prompt generator
        # Handle both direct sources and nested results.sources structures
        sources = trial_data.get("sources", {})
        if not sources and "results" in trial_data:
            sources = trial_data.get("results", {}).get("sources", {})
        
        metadata = trial_data.get("metadata", {})
        if not metadata and "summary" in trial_data:
            # Extract metadata from summary if available
            summary = trial_data.get("summary", {})
            metadata = {
                "title": summary.get("title", ""),
                "status": summary.get("status", "")
            }
        
        search_results = {
            "nct_id": nct_id,
            "sources": sources,
            "metadata": metadata
        }
        
        logger.info(f"Generating prompt with sources: {list(sources.keys())}")
        
        return self.prompt_generator.generate_extraction_prompt(search_results, nct_id)
    
    def _generate_basic_prompt(self, trial_data: Dict[str, Any], nct_id: str) -> str:
        """Generate a basic annotation prompt when PromptGenerator is unavailable."""
        # Handle nested structure
        metadata = trial_data.get("metadata", {})
        if not metadata and "summary" in trial_data:
            summary = trial_data.get("summary", {})
            metadata = {
                "title": summary.get("title", "Unknown"),
                "status": summary.get("status", "Unknown")
            }
        
        sources = trial_data.get("sources", {})
        if not sources and "results" in trial_data:
            sources = trial_data.get("results", {}).get("sources", {})
        
        title = metadata.get("title", "Unknown")
        status = metadata.get("status", "Unknown")
        
        # Get protocol section for more details
        protocol = self._safe_get(
            trial_data, 'results', 'sources', 'clinical_trials', 'data', 'protocolSection',
            default={}
        )
        if not protocol:
            protocol = self._safe_get(
                trial_data, 'sources', 'clinical_trials', 'data', 'protocolSection',
                default={}
            )
        
        id_module = protocol.get('identificationModule', {})
        desc_module = protocol.get('descriptionModule', {})
        status_module = protocol.get('statusModule', {})
        conditions_module = protocol.get('conditionsModule', {})
        arms_module = protocol.get('armsInterventionsModule', {})
        
        brief_summary = desc_module.get('briefSummary', 'Not available')
        conditions = ', '.join(conditions_module.get('conditions', [])) or 'Not available'
        
        interventions = []
        for intv in arms_module.get('interventions', []):
            interventions.append(f"{intv.get('type', '')}: {intv.get('name', '')}")
        interventions_str = ', '.join(interventions) or 'Not available'
        
        prompt = f"""You are an expert clinical trial annotator. Extract structured data from this trial.

## TRIAL DATA:
NCT ID: {nct_id}
Title: {title}
Status: {status}
Conditions: {conditions}
Interventions: {interventions_str}
Brief Summary: {brief_summary[:500] if brief_summary else 'Not available'}

## AVAILABLE DATA SOURCES:
"""
        for source_name, source_data in sources.items():
            if source_name == "extended":
                continue
            if source_data and isinstance(source_data, dict) and source_data.get("success"):
                prompt += f"- {source_name}: Available\n"
        
        prompt += """
## REQUIRED OUTPUT FORMAT (use EXACTLY this structure):

NCT Number: {nct_id}
Study Title: {title}
Study Status: {status}
Brief Summary: [1-2 sentences]
Conditions: {conditions}
Interventions/Drug: {interventions}
Phases: [from data or N/A]
Enrollment: [number or N/A]
Start Date: [date or N/A]
Completion Date: [date or N/A]

Classification: [AMP or Other]
  Evidence: [brief reason]

Delivery Mode: [Injection/Infusion, Topical, Oral, or Other]
  Evidence: [brief reason]

Outcome: [Positive, Withdrawn, Terminated, Failed - completed trial, Active, or Unknown]
  Evidence: [brief reason]

Reason for Failure: [Business reasons, Ineffective for purpose, Toxic/unsafe, Due to covid, Recruitment issues, or N/A]
  Evidence: [brief reason]

Peptide: [True or False]
  Evidence: [brief reason]

Sequence: [amino acid sequence or N/A]
DRAMP Name: [name or N/A]
Study IDs: [PMIDs or N/A]
Comments: [any notes]

## VALID VALUES (use ONLY these):
- Classification: AMP | Other
- Delivery Mode: Injection/Infusion | Topical | Oral | Other  
- Outcome: Positive | Withdrawn | Terminated | Failed - completed trial | Active | Unknown
- Reason for Failure: Business reasons | Ineffective for purpose | Toxic/unsafe | Due to covid | Recruitment issues | N/A
- Peptide: True | False

## RULES:
- AMP = antimicrobial peptide (has antimicrobial activity)
- Status RECRUITING/ACTIVE → Outcome = Active
- Status WITHDRAWN → Outcome = Withdrawn
- Status TERMINATED → Outcome = Terminated  
- Status COMPLETED → Outcome = Positive or Failed - completed trial
- Peptide = True only if drug is a short peptide (<200 amino acids)

Now extract the data using the exact format above:
"""
        return prompt
    
    async def call_llm(
        self, 
        model: str, 
        prompt: str, 
        temperature: float = 0.1
    ) -> str:
        """Call Ollama LLM for annotation using chat endpoint."""
        logger.info(f"🤖 Calling LLM: {model} (temp={temperature})")
        
        system_prompt = self.get_system_prompt()
        
        try:
            async with httpx.AsyncClient(timeout=config.LLM_TIMEOUT) as client:
                response = await client.post(
                    f"{config.OLLAMA_BASE_URL}/api/chat",
                    json={
                        "model": model,
                        "messages": [
                            {"role": "system", "content": system_prompt},
                            {"role": "user", "content": prompt}
                        ],
                        "stream": False,
                        "options": {
                            "temperature": temperature,
                            "top_p": config.DEFAULT_TOP_P,
                            "num_ctx": config.DEFAULT_NUM_CTX,
                            "num_predict": config.DEFAULT_NUM_PREDICT,
                            "stop": ["TRIAL DATA:", "---", "\n\n\n"]
                        }
                    }
                )
                
                if response.status_code != 200:
                    error_text = response.text
                    logger.error(f"❌ LLM error: {response.status_code} - {error_text}")
                    raise HTTPException(status_code=503, detail=f"LLM error: {error_text}")
                
                data = response.json()
                annotation = data.get("message", {}).get("content", "")
                
                # Just log warnings, don't reject
                required_fields = ["Classification:", "Delivery Mode:", "Outcome:", "Peptide:"]
                missing = [f for f in required_fields if f not in annotation]
                if missing:
                    logger.warning(f"⚠️ Response missing fields: {missing}")
                
                logger.info(f"✅ Received annotation ({len(annotation)} chars)")
                return annotation
                
        except httpx.ConnectError:
            raise HTTPException(status_code=503, detail=f"Cannot connect to Ollama")
        except httpx.TimeoutException:
            raise HTTPException(status_code=504, detail="LLM request timed out")

# Global annotator instance
annotator = TrialAnnotator()


# ============================================================================
# API Endpoints
# ============================================================================

@app.get("/")
async def root():
    """Root endpoint with service info."""
    return {
        "service": config.SERVICE_NAME,
        "version": config.API_VERSION,
        "status": "running",
        "features": {
            "json_parser": "available" if HAS_JSON_PARSER else "unavailable",
            "prompt_generator": "available" if HAS_PROMPT_GEN else "unavailable"
        },
        "endpoints": {
            "annotate": "POST /annotate",
            "batch_annotate": "POST /batch-annotate",
            "parse_trial": "POST /parse",
            "generate_prompt": "POST /generate-prompt",
            "health": "GET /health",
            "models": "GET /models"
        }
    }


@app.get("/health")
async def health_check():
    """Health check with dependency status."""
    # Check Ollama
    ollama_connected = False
    ollama_models = []
    try:
        async with httpx.AsyncClient(timeout=5.0) as client:
            response = await client.get(f"{config.OLLAMA_BASE_URL}/api/tags")
            if response.status_code == 200:
                ollama_connected = True
                data = response.json()
                ollama_models = [m["name"] for m in data.get("models", [])]
    except Exception as e:
        logger.warning(f"Ollama health check failed: {e}")
    
    return {
        "status": "healthy",
        "service": config.SERVICE_NAME,
        "version": config.API_VERSION,
        "dependencies": {
            "json_parser": "available" if HAS_JSON_PARSER else "unavailable",
            "prompt_generator": "available" if HAS_PROMPT_GEN else "unavailable",
            "ollama": {
                "url": config.OLLAMA_BASE_URL,
                "connected": ollama_connected,
                "models_count": len(ollama_models)
            }
        }
    }


@app.get("/models")
async def list_models():
    """List available Ollama models."""
    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            response = await client.get(f"{config.OLLAMA_BASE_URL}/api/tags")
            if response.status_code == 200:
                return response.json()
            else:
                raise HTTPException(
                    status_code=503, 
                    detail="Cannot fetch models from Ollama"
                )
    except httpx.ConnectError:
        raise HTTPException(
            status_code=503,
            detail=f"Cannot connect to Ollama at {config.OLLAMA_BASE_URL}"
        )


@app.post("/parse", response_model=Dict[str, Any])
async def parse_trial(trial: TrialData):
    """
    Parse trial data and extract annotation-relevant information.
    
    This endpoint extracts structured information for each annotation field
    without calling the LLM.
    """
    logger.info(f"📋 Parsing trial data for {trial.nct_id}")
    
    parsed_info = annotator.parse_trial_data(trial.data)
    
    return {
        "nct_id": trial.nct_id,
        "parsed_info": parsed_info,
        "status": "success"
    }


@app.post("/generate-prompt")
async def generate_prompt(trial: TrialData):
    """
    Generate annotation prompt from trial data without calling LLM.
    
    Useful for debugging or review of prompts before annotation.
    """
    logger.info(f"📝 Generating prompt for {trial.nct_id}")
    
    prompt = annotator.generate_prompt(trial.data, trial.nct_id)
    
    return {
        "nct_id": trial.nct_id,
        "prompt": prompt,
        "prompt_length": len(prompt),
        "status": "success"
    }


@app.post("/annotate", response_model=AnnotationResult)
async def annotate_trial(request: AnnotationRequest):
    """
    Annotate a single clinical trial.
    
    This is the main annotation endpoint that:
    1. Parses trial data using json_parser
    2. Generates prompt using prompt_generator
    3. Calls LLM for annotation
    4. Parses response into structured data
    5. Returns structured result
    """
    import time
    start_time = time.time()
    
    trial = request.trial_data
    logger.info(f"🔬 Starting annotation for {trial.nct_id} with {request.model}")
    
    try:
        # Generate prompt
        if request.use_extraction_prompt and HAS_PROMPT_GEN:
            prompt = annotator.generate_prompt(trial.data, trial.nct_id)
        else:
            prompt = annotator._generate_basic_prompt(trial.data, trial.nct_id)
        
        logger.info(f"📝 Generated prompt ({len(prompt)} chars)")
        
        # Call LLM
        annotation = await annotator.call_llm(
            request.model,
            prompt,
            request.temperature
        )

        logger.info(f"DEBUG: annotation length = {len(annotation)}")
        logger.info(f"DEBUG: annotation preview = {annotation[:200] if annotation else 'EMPTY'}")
        
        # Parse the response into structured data
        parsed_data = AnnotationResponseParser.parse_response_regex(annotation, trial.nct_id)
        logger.info(f"📊 Parsed {len([v for v in parsed_data.values() if v])} fields from response")
        
        processing_time = time.time() - start_time
        
        # Build sources summary
        sources = trial.data.get("sources", {})
        if not sources and "results" in trial.data:
            sources = trial.data.get("results", {}).get("sources", {})
        
        sources_summary = {}
        for src_name, src_data in sources.items():
            if src_name == "extended":
                sources_summary["extended_sources"] = list(src_data.keys()) if isinstance(src_data, dict) else []
            elif isinstance(src_data, dict):
                sources_summary[src_name] = {
                    "success": src_data.get("success", False),
                    "has_data": bool(src_data.get("data"))
                }
        
        return AnnotationResult(
            nct_id=trial.nct_id,
            annotation=annotation,
            parsed_data=parsed_data,
            model=request.model,
            status="success",
            processing_time_seconds=round(processing_time, 2),
            sources_summary=sources_summary
        )
        
    except HTTPException:
        raise
    except Exception as e:
        processing_time = time.time() - start_time
        logger.error(f"❌ Annotation error for {trial.nct_id}: {e}", exc_info=True)
        
        return AnnotationResult(
            nct_id=trial.nct_id,
            annotation="",
            parsed_data={},
            model=request.model,
            status="error",
            processing_time_seconds=round(processing_time, 2),
            error=str(e)
        )


@app.post("/batch-annotate", response_model=BatchAnnotationResponse)
async def batch_annotate(request: BatchAnnotationRequest):
    """
    Annotate multiple clinical trials.
    
    Processes each trial sequentially and returns all results.
    """
    import time
    start_time = time.time()
    
    logger.info(f"🔬 Starting batch annotation for {len(request.trials)} trials")
    
    results = []
    successful = 0
    failed = 0
    
    for trial in request.trials:
        try:
            # Create single annotation request
            single_request = AnnotationRequest(
                trial_data=trial,
                model=request.model,
                temperature=request.temperature
            )
            
            result = await annotate_trial(single_request)
            results.append(result)
            
            if result.status == "success":
                successful += 1
            else:
                failed += 1
                
        except Exception as e:
            logger.error(f"❌ Error annotating {trial.nct_id}: {e}")
            results.append(AnnotationResult(
                nct_id=trial.nct_id,
                annotation="",
                parsed_data={},
                model=request.model,
                status="error",
                processing_time_seconds=0,
                error=str(e)
            ))
            failed += 1
    
    total_time = time.time() - start_time
    
    logger.info(f"✅ Batch complete: {successful} successful, {failed} failed in {total_time:.1f}s")
    
    return BatchAnnotationResponse(
        results=results,
        total=len(request.trials),
        successful=successful,
        failed=failed,
        total_time_seconds=round(total_time, 2)
    )


# ============================================================================
# Run standalone
# ============================================================================

if __name__ == "__main__":
    import uvicorn
    
    print("=" * 80)
    print(f"🚀 Starting {config.SERVICE_NAME} on port {config.SERVICE_PORT}...")
    print("=" * 80)
    print(f"🤖 Ollama: {config.OLLAMA_BASE_URL}")
    print(f"📋 JSON Parser: {'Available' if HAS_JSON_PARSER else 'Not Available'}")
    print(f"📝 Prompt Generator: {'Available' if HAS_PROMPT_GEN else 'Not Available'}")
    print(f"📚 API Docs: http://localhost:{config.SERVICE_PORT}/docs")
    print(f"🔍 Health Check: http://localhost:{config.SERVICE_PORT}/health")
    print("=" * 80)
    
    uvicorn.run(app, host="0.0.0.0", port=config.SERVICE_PORT, reload=True)