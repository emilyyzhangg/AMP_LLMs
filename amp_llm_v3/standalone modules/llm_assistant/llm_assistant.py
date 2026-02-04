"""
LLM Assistant API Service
=========================

RESTful API for clinical trial annotation using:
- json_parser.py for extracting annotation-relevant data
- prompt_generator.py for generating sophisticated LLM prompts
- Ollama for LLM inference

This service receives trial JSON data and returns structured annotations.

UPDATED: Now extracts ClinicalTrials.gov metadata fields directly from trial data
UPDATED: Now loads all port configuration from .env file.
NEW: Two-stage annotation with verification by a second LLM model.
"""
import os
from pathlib import Path
from dotenv import load_dotenv

# Load environment variables from .env file
current_dir = Path(__file__).parent
for parent in [current_dir, current_dir.parent, current_dir.parent.parent]:
    env_file = parent / "webapp" / ".env"
    if env_file.exists():
        load_dotenv(env_file)
        break
    env_file = parent / ".env"
    if env_file.exists():
        load_dotenv(env_file)
        break
else:
    load_dotenv()

import logging
import json
import httpx
import subprocess
import csv
import io
from pathlib import Path
from datetime import datetime
from typing import Dict, Any, List, Optional
from fastapi import FastAPI, HTTPException
from fastapi.responses import StreamingResponse
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
    """Configuration for the LLM Assistant - loaded from .env"""
    
    # Ollama configuration
    OLLAMA_HOST = os.getenv("ollama_host", "localhost")
    OLLAMA_PORT = int(os.getenv("ollama_port", "11434"))
    
    @property
    def OLLAMA_BASE_URL(self):
        return f"http://{self.OLLAMA_HOST}:{self.OLLAMA_PORT}"
    
    # Service configuration
    API_VERSION = "1.2.0"  # Updated version with verification support
    SERVICE_NAME = "LLM Assistant API"
    SERVICE_PORT = int(os.getenv("LLM_ASSISTANT_PORT", "9004"))
    CORS_ORIGINS = ["*"]
    
    # Related service ports
    CHAT_SERVICE_PORT = int(os.getenv("CHAT_SERVICE_PORT", "9001"))
    NCT_SERVICE_PORT = int(os.getenv("NCT_SERVICE_PORT", "9002"))
    RUNNER_SERVICE_PORT = int(os.getenv("RUNNER_SERVICE_PORT", "9003"))
    
    # ========================================================================
    # VERIFICATION MODEL CONFIGURATION (NEW)
    # ========================================================================
    # The model used for the second-stage verification pass
    # Change this to use a different model for verification
    VERIFICATION_MODEL = os.getenv("VERIFICATION_MODEL", "gemma3:12b")
    
    # Whether verification is enabled by default
    VERIFICATION_ENABLED = os.getenv("VERIFICATION_ENABLED", "true").lower() == "true"
    
    # Timeouts
    LLM_TIMEOUT = 300  # 5 minutes for annotation
    VERIFICATION_TIMEOUT = 300  # 5 minutes for verification
    
    # Default model parameters
    DEFAULT_TEMPERATURE = 0.15
    DEFAULT_TOP_P = 0.9
    DEFAULT_TOP_K = 40
    DEFAULT_NUM_CTX = 4096
    DEFAULT_NUM_PREDICT = 600
    
    # Verification parameters (can be tuned separately)
    VERIFICATION_TEMPERATURE = float(os.getenv("VERIFICATION_TEMPERATURE", "0.1"))
    VERIFICATION_NUM_PREDICT = 800  # May need more tokens for corrections

config = AssistantConfig()


# ============================================================================
# Metadata Utilities
# ============================================================================

def get_git_commit_id() -> str:
    """Get the current git commit ID."""
    try:
        result = subprocess.run(
            ['git', 'rev-parse', '--short', 'HEAD'],
            capture_output=True,
            text=True,
            timeout=5,
            cwd=os.path.dirname(os.path.abspath(__file__)) or '.'
        )
        if result.returncode == 0:
            return result.stdout.strip()
    except (subprocess.TimeoutExpired, FileNotFoundError, Exception) as e:
        logger.debug(f"Could not get git commit ID: {e}")
    
    env_commit = os.environ.get('GIT_COMMIT_ID') or os.environ.get('GIT_SHA') or os.environ.get('COMMIT_SHA')
    if env_commit:
        return env_commit[:8]
    
    return 'unknown'


def get_git_commit_full() -> str:
    """Get the full git commit ID."""
    try:
        result = subprocess.run(
            ['git', 'rev-parse', 'HEAD'],
            capture_output=True,
            text=True,
            timeout=5,
            cwd=os.path.dirname(os.path.abspath(__file__)) or '.'
        )
        if result.returncode == 0:
            return result.stdout.strip()
    except Exception:
        pass
    
    env_commit = os.environ.get('GIT_COMMIT_ID') or os.environ.get('GIT_SHA') or os.environ.get('COMMIT_SHA')
    return env_commit or 'unknown'


async def get_ollama_model_info(model_name: str) -> Dict[str, Any]:
    """Get detailed model information from Ollama."""
    model_info = {
        "name": model_name,
        "details": {},
        "modified_at": None,
        "size": None,
        "digest": None,
        "version_string": model_name,
    }
    
    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            response = await client.post(
                f"{config.OLLAMA_BASE_URL}/api/show",
                json={"name": model_name}
            )
            if response.status_code == 200:
                data = response.json()
                model_info["details"] = data.get("details", {})
                model_info["modified_at"] = data.get("modified_at")
                model_info["modelfile"] = data.get("modelfile", "")[:500]
                model_info["parameters"] = data.get("parameters", "")
                model_info["template"] = data.get("template", "")[:200]
                
            response = await client.get(f"{config.OLLAMA_BASE_URL}/api/tags")
            if response.status_code == 200:
                models = response.json().get("models", [])
                for m in models:
                    if m.get("name") == model_name or m.get("name", "").startswith(model_name):
                        model_info["size"] = m.get("size")
                        model_info["digest"] = m.get("digest")
                        model_info["modified_at"] = model_info["modified_at"] or m.get("modified_at")
                        break
        
        model_info["version_string"] = format_model_version_string(model_name, model_info)
                        
    except Exception as e:
        logger.warning(f"Could not fetch model info for {model_name}: {e}")
    
    return model_info


def format_model_version_string(model_name: str, model_info: Dict[str, Any]) -> str:
    """Format a human-readable model version string."""
    parts = [model_name]
    
    details = model_info.get("details", {})
    detail_parts = []
    
    param_size = details.get("parameter_size", "")
    if param_size:
        detail_parts.append(param_size)
    
    quant = details.get("quantization_level", "")
    if quant:
        detail_parts.append(quant)
    
    if detail_parts:
        parts.append(f"({', '.join(detail_parts)})")
    
    digest = model_info.get("digest", "")
    if digest:
        if ":" in digest:
            short_hash = digest.split(":")[-1][:7]
        else:
            short_hash = digest[:7]
        parts.append(f"[{short_hash}]")
    
    return " ".join(parts)


class AnnotationMetadata(BaseModel):
    """Metadata about the annotation process."""
    git_commit_id: str = ""
    git_commit_full: str = ""
    llm_model: str = ""
    llm_model_details: Dict[str, Any] = {}
    annotation_timestamp: str = ""
    service_version: str = ""
    
    @classmethod
    def create(cls, model_name: str, model_info: Optional[Dict] = None) -> "AnnotationMetadata":
        return cls(
            git_commit_id=get_git_commit_id(),
            git_commit_full=get_git_commit_full(),
            llm_model=model_name,
            llm_model_details=model_info or {},
            annotation_timestamp=datetime.utcnow().isoformat() + "Z",
            service_version=config.API_VERSION
        )


# ============================================================================
# Initialize FastAPI app
# ============================================================================

app = FastAPI(
    title=config.SERVICE_NAME,
    description="RESTful API for clinical trial annotation using JSON parsing and LLM with verification support",
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
    data: Dict[str, Any]
    source: str = "unknown"


class AnnotationRequest(BaseModel):
    """Request model for annotation"""
    trial_data: TrialData
    model: str = "llama3.2"
    temperature: float = Field(default=0.15, ge=0.0, le=2.0)
    use_extraction_prompt: bool = True
    include_evidence: bool = True
    # NEW: Verification options
    enable_verification: bool = Field(default=True, description="Enable second-stage verification")
    verification_model: Optional[str] = Field(default=None, description="Model for verification (defaults to VERIFICATION_MODEL env var)")


class BatchAnnotationRequest(BaseModel):
    """Request model for batch annotation"""
    trials: List[TrialData]
    model: str = "llama3.2"
    temperature: float = Field(default=0.15, ge=0.0, le=2.0)
    # NEW: Verification options
    enable_verification: bool = Field(default=True, description="Enable second-stage verification")
    verification_model: Optional[str] = Field(default=None, description="Model for verification")


class VerificationRequest(BaseModel):
    """Request model for standalone verification"""
    nct_id: str
    original_annotation: str
    parsed_data: Dict[str, str] = {}
    trial_data: Dict[str, Any]
    primary_model: str
    verification_model: Optional[str] = None
    temperature: float = Field(default=0.1, ge=0.0, le=2.0)


class VerificationResult(BaseModel):
    """Result of verification"""
    nct_id: str
    verification_model: str
    verified_annotation: str
    verified_parsed_data: Dict[str, str] = {}
    corrections_made: int = 0
    fields_reviewed: int = 0
    fields_correct: int = 0
    verification_report: str = ""
    processing_time_seconds: float = 0
    status: str = "success"
    error: Optional[str] = None


class AnnotationResult(BaseModel):
    """Response model for a single annotation"""
    nct_id: str
    annotation: str
    parsed_data: Dict[str, str] = {}
    model: str
    status: str
    processing_time_seconds: float
    sources_summary: Dict[str, Any] = {}
    error: Optional[str] = None
    metadata: Optional[Dict[str, Any]] = None
    # NEW: Verification fields
    verification: Optional[VerificationResult] = None
    verified: bool = False


class BatchAnnotationResponse(BaseModel):
    """Response model for batch annotation"""
    results: List[AnnotationResult]
    total: int
    successful: int
    failed: int
    total_time_seconds: float
    metadata: Optional[Dict[str, Any]] = None
    # NEW: Verification stats
    verification_enabled: bool = False
    verification_model: Optional[str] = None
    verified_count: int = 0


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
    
    VALID_VALUES = {
        'Classification': {'AMP', 'Other'},
        'Delivery Mode': {'Injection/Infusion', 'Topical', 'Oral', 'Other'},
        'Outcome': {'Positive', 'Withdrawn', 'Terminated', 'Failed - completed trial', 'Active', 'Unknown'},
        'Reason for Failure': {'Business reasons', 'Ineffective for purpose', 'Toxic/unsafe', 'Due to covid', 'Recruitment issues', 'N/A'},
        'Peptide': {'True', 'False'}
    }
    
    @classmethod
    def _safe_get(cls, dictionary: Dict, *keys, default=None) -> Any:
        """Safely navigate nested dictionary keys."""
        current = dictionary
        for key in keys:
            if isinstance(current, dict) and key in current:
                current = current[key]
            else:
                return default
        return current if current is not None else default
    
    @classmethod
    def _get_protocol_section(cls, trial_data: Dict) -> Dict:
        """Extract the protocol section from trial data."""
        paths = [
            ('results', 'sources', 'clinical_trials', 'data', 'protocolSection'),
            ('sources', 'clinical_trials', 'data', 'protocolSection'),
            ('results', 'sources', 'clinicaltrials', 'data', 'protocolSection'),
            ('sources', 'clinicaltrials', 'data', 'protocolSection'),
            ('protocolSection',),
        ]
        
        for path in paths:
            protocol = cls._safe_get(trial_data, *path, default={})
            if protocol:
                return protocol
        
        return {}
    
    @classmethod
    def extract_trial_metadata(cls, trial_data: Dict, nct_id: str) -> Dict[str, str]:
        """Extract ClinicalTrials.gov metadata fields directly from trial data."""
        metadata = {}
        
        protocol = cls._get_protocol_section(trial_data)
        
        has_results = cls._safe_get(trial_data, 'results', 'sources', 'clinical_trials', 'data', 'hasResults', default=False)
        if not has_results:
            has_results = cls._safe_get(trial_data, 'sources', 'clinical_trials', 'data', 'hasResults', default=False)
        
        id_module = cls._safe_get(protocol, 'identificationModule', default={})
        metadata['NCT ID'] = nct_id
        
        official_title = id_module.get('officialTitle', '')
        brief_title = id_module.get('briefTitle', '')
        metadata['Study Title'] = official_title or brief_title or ''
        
        status_module = cls._safe_get(protocol, 'statusModule', default={})
        metadata['Study Status'] = status_module.get('overallStatus', '')
        
        start_date_struct = status_module.get('startDateStruct', {})
        completion_date_struct = status_module.get('completionDateStruct', {})
        metadata['Start Date'] = start_date_struct.get('date', '')
        metadata['Completion Date'] = completion_date_struct.get('date', '')
        
        desc_module = cls._safe_get(protocol, 'descriptionModule', default={})
        brief_summary = desc_module.get('briefSummary', '')
        if len(brief_summary) > 500:
            brief_summary = brief_summary[:497] + '...'
        metadata['Brief Summary'] = brief_summary
        
        conditions_module = cls._safe_get(protocol, 'conditionsModule', default={})
        conditions = conditions_module.get('conditions', [])
        metadata['Conditions'] = ', '.join(conditions) if conditions else ''
        
        design_module = cls._safe_get(protocol, 'designModule', default={})
        phases = design_module.get('phases', [])
        metadata['Phase'] = ', '.join(phases) if phases else ''
        
        enrollment_info = design_module.get('enrollmentInfo', {})
        enrollment_count = enrollment_info.get('count', '')
        metadata['Enrollment'] = str(enrollment_count) if enrollment_count else ''
        
        arms_module = cls._safe_get(protocol, 'armsInterventionsModule', default={})
        interventions = arms_module.get('interventions', [])
        
        intervention_strs = []
        for intv in interventions:
            intv_type = intv.get('type', '')
            intv_name = intv.get('name', '')
            if intv_name:
                if intv_type:
                    intervention_strs.append(f"{intv_type}: {intv_name}")
                else:
                    intervention_strs.append(intv_name)
        
        metadata['Drug'] = ', '.join(intervention_strs) if intervention_strs else ''
        
        return metadata
    
    @classmethod
    def parse_response(cls, llm_response: str, nct_id: str, trial_data: Optional[Dict] = None) -> Dict[str, str]:
        """Parse LLM response text into structured dictionary."""
        result = {col: '' for col in cls.CSV_COLUMNS}
        result['NCT ID'] = nct_id
        
        if trial_data:
            metadata = cls.extract_trial_metadata(trial_data, nct_id)
            result.update(metadata)
            logger.info(f"📋 Extracted metadata fields: {[k for k, v in metadata.items() if v]}")
        
        if not llm_response:
            return result
        
        normalized = cls._normalize_response(llm_response)
        
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
        
        evidence_patterns = {
            'Classification Evidence': r'Classification:[^\n]*\n\s*Evidence:\s*([^\n]+)',
            'Delivery Mode Evidence': r'Delivery Mode:[^\n]*\n\s*Evidence:\s*([^\n]+)',
            'Outcome Evidence': r'Outcome:[^\n]*\n\s*Evidence:\s*([^\n]+)',
            'Reason for Failure Evidence': r'Reason for Failure:[^\n]*\n\s*Evidence:\s*([^\n]+)',
            'Peptide Evidence': r'Peptide:[^\n]*\n\s*Evidence:\s*([^\n]+)',
            'Sequence Evidence': r'Sequence:[^\n]*\n\s*Evidence:\s*([^\n]+)',
        }
        
        for field, pattern in patterns.items():
            match = re.search(pattern, normalized, re.IGNORECASE)
            if match:
                value = match.group(1).strip()
                value = re.sub(r'\s+', ' ', value)
                value = value.rstrip('.')
                
                if value.lower() in ['n/a', 'not available', 'none', 'unknown', 'na']:
                    value = 'N/A'
                
                if field in cls.VALID_VALUES:
                    value = cls._match_valid_value(value, cls.VALID_VALUES[field])
                
                result[field] = value
        
        for field, pattern in evidence_patterns.items():
            match = re.search(pattern, normalized, re.IGNORECASE | re.DOTALL)
            if match:
                value = match.group(1).strip()
                value = re.sub(r'\s+', ' ', value)
                result[field] = value
        
        return result
    
    @classmethod
    def _normalize_response(cls, response: str) -> str:
        """Normalize LLM response to have consistent newline formatting."""
        normalized = re.sub(r'\s*\*\*([^*]+):\*\*\s*', r'\n\1: ', response)
        normalized = re.sub(r'\s*\*([^*]+):\*\s*', r'\n\1: ', normalized)
        normalized = re.sub(r'\n(Evidence:)', r'\n  \1', normalized)
        normalized = re.sub(r'\n{3,}', '\n\n', normalized)
        lines = [line.strip() for line in normalized.split('\n')]
        normalized = '\n'.join(lines)
        return normalized
    
    @classmethod
    def _match_valid_value(cls, value: str, valid_set: Set[str]) -> str:
        """Try to match a value to the closest valid value."""
        if value in valid_set:
            return value
        
        value_lower = value.lower()
        for valid in valid_set:
            if valid.lower() == value_lower:
                return valid
        
        for valid in valid_set:
            if valid.lower() in value_lower or value_lower in valid.lower():
                return valid
        
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
    
    @classmethod
    def parse_verification_response(cls, verification_text: str, nct_id: str) -> Dict[str, str]:
        """
        Parse verification response to extract corrected values.
        
        Looks for the "FINAL VERIFIED ANNOTATION" section.
        """
        result = {col: '' for col in cls.CSV_COLUMNS}
        result['NCT ID'] = nct_id
        
        if not verification_text:
            return result
        
        # Try to find the FINAL VERIFIED ANNOTATION section
        final_section_match = re.search(
            r'(?:FINAL VERIFIED ANNOTATION|## FINAL|Final Verified).*?(?:Classification:)',
            verification_text,
            re.IGNORECASE | re.DOTALL
        )
        
        if final_section_match:
            # Parse from the final section onwards
            start_idx = final_section_match.start()
            final_section = verification_text[start_idx:]
            return cls.parse_response(final_section, nct_id)
        else:
            # Fall back to parsing the whole response
            return cls.parse_response(verification_text, nct_id)
    
    @classmethod
    def count_corrections(cls, original: Dict[str, str], verified: Dict[str, str]) -> tuple[int, int, int]:
        """
        Count corrections made during verification.
        
        Returns: (corrections_made, fields_reviewed, fields_correct)
        """
        key_fields = ['Classification', 'Delivery Mode', 'Outcome', 'Reason for Failure', 'Peptide', 'Sequence']
        
        corrections = 0
        reviewed = 0
        correct = 0
        
        for field in key_fields:
            orig_val = original.get(field, '').strip().lower()
            verif_val = verified.get(field, '').strip().lower()
            
            if orig_val or verif_val:  # Only count if at least one has a value
                reviewed += 1
                if orig_val != verif_val and verif_val:  # Different and verified has a value
                    corrections += 1
                else:
                    correct += 1
        
        return corrections, reviewed, correct


class TrialAnnotator:
    """Core class for annotating clinical trials"""
    
    def __init__(self):
        self.prompt_generator = PromptGenerator() if HAS_PROMPT_GEN else None
    
    def parse_trial_data(self, trial_data: Dict[str, Any]) -> Dict[str, Any]:
        """Parse trial data using the JSON parser to extract annotation-relevant info."""
        if not HAS_JSON_PARSER:
            logger.warning("JSON parser not available, using raw data")
            return {
                "raw_data": trial_data,
                "parsed": False
            }
        
        parsed_info = {
            "nct_id": trial_data.get("nct_id", "Unknown"),
            "parsed": True
        }
        
        protocol = None
        
        protocol = self._safe_get(
            trial_data, 
            'results', 'sources', 'clinical_trials', 'data', 'protocolSection',
            default={}
        )
        
        if not protocol:
            protocol = self._safe_get(
                trial_data, 
                'sources', 'clinical_trials', 'data', 'protocolSection',
                default={}
            )
        
        if not protocol:
            protocol = self._safe_get(
                trial_data,
                'results', 'sources', 'clinicaltrials', 'data', 'protocolSection',
                default={}
            )
        
        if not protocol:
            protocol = self._safe_get(
                trial_data,
                'sources', 'clinicaltrials', 'data', 'protocolSection',
                default={}
            )
        
        logger.info(f"Protocol section found: {bool(protocol)}")
        
        parsed_info["classification"] = self._extract_classification_info(trial_data, protocol)
        parsed_info["delivery_mode"] = self._extract_delivery_mode_info(trial_data, protocol)
        parsed_info["outcome"] = self._extract_outcome_info(trial_data, protocol)
        parsed_info["failure_reason"] = self._extract_failure_reason_info(trial_data, protocol)
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
        
        sources = trial_data.get("sources", {})
        if not sources and "results" in trial_data:
            sources = trial_data.get("results", {}).get("sources", {})
        
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
        """Generate annotation prompt using the PromptGenerator."""
        if not self.prompt_generator:
            logger.warning("PromptGenerator not available, using basic prompt")
            return self._generate_basic_prompt(trial_data, nct_id)
        
        sources = trial_data.get("sources", {})
        if not sources and "results" in trial_data:
            sources = trial_data.get("results", {}).get("sources", {})
        
        metadata = trial_data.get("metadata", {})
        if not metadata and "summary" in trial_data:
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
## REQUIRED OUTPUT FORMAT:

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

Now extract the data:
"""
        return prompt
    
    async def call_llm(
        self, 
        model: str, 
        prompt: str, 
        temperature: float = 0.1,
        system_prompt: Optional[str] = None,
        timeout: float = None
    ) -> str:
        """Call Ollama LLM for annotation using chat endpoint."""
        logger.info(f"🤖 Calling LLM: {model} (temp={temperature})")
        
        if system_prompt is None:
            system_prompt = self.get_system_prompt()
        
        if timeout is None:
            timeout = config.LLM_TIMEOUT
        
        try:
            async with httpx.AsyncClient(timeout=timeout) as client:
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
    
    async def verify_annotation(
        self,
        nct_id: str,
        original_annotation: str,
        parsed_data: Dict[str, str],
        trial_data: Dict[str, Any],
        primary_model: str,
        verification_model: str = None,
        temperature: float = None
    ) -> VerificationResult:
        """
        Verify an annotation using a second LLM.
        
        Args:
            nct_id: NCT identifier
            original_annotation: The annotation text from the primary model
            parsed_data: Structured data from the original annotation
            trial_data: The trial data used for annotation
            primary_model: Name of the model that made the original annotation
            verification_model: Model to use for verification (defaults to config)
            temperature: Temperature for verification (defaults to config)
            
        Returns:
            VerificationResult with corrections and verified data
        """
        import time
        start_time = time.time()
        
        # Use defaults from config if not specified
        if verification_model is None:
            verification_model = config.VERIFICATION_MODEL
        if temperature is None:
            temperature = config.VERIFICATION_TEMPERATURE
        
        logger.info(f"🔍 Starting verification for {nct_id} using {verification_model}")
        
        try:
            # Generate verification prompt
            if self.prompt_generator:
                verification_prompt = self.prompt_generator.generate_verification_prompt(
                    nct_id=nct_id,
                    original_annotation=original_annotation,
                    parsed_data=parsed_data,
                    trial_data=trial_data,
                    primary_model=primary_model
                )
                verification_system_prompt = self.prompt_generator.get_verification_system_prompt()
            else:
                verification_prompt = self._generate_basic_verification_prompt(
                    nct_id, original_annotation, parsed_data, trial_data, primary_model
                )
                verification_system_prompt = self._get_basic_verification_system_prompt()
            
            # Call verification LLM
            verification_response = await self.call_llm(
                model=verification_model,
                prompt=verification_prompt,
                temperature=temperature,
                system_prompt=verification_system_prompt,
                timeout=config.VERIFICATION_TIMEOUT
            )
            
            # Parse the verification response
            verified_parsed = AnnotationResponseParser.parse_verification_response(
                verification_response, nct_id
            )
            
            # Also keep metadata from original if available in trial_data
            if trial_data:
                metadata = AnnotationResponseParser.extract_trial_metadata(trial_data, nct_id)
                for key, value in metadata.items():
                    if key not in verified_parsed or not verified_parsed[key]:
                        verified_parsed[key] = value
            
            # Count corrections
            corrections, reviewed, correct = AnnotationResponseParser.count_corrections(
                parsed_data, verified_parsed
            )
            
            processing_time = time.time() - start_time
            
            logger.info(f"✅ Verification complete: {corrections} corrections in {reviewed} fields")
            
            return VerificationResult(
                nct_id=nct_id,
                verification_model=verification_model,
                verified_annotation=verification_response,
                verified_parsed_data=verified_parsed,
                corrections_made=corrections,
                fields_reviewed=reviewed,
                fields_correct=correct,
                verification_report=verification_response,
                processing_time_seconds=round(processing_time, 2),
                status="success"
            )
            
        except Exception as e:
            logger.error(f"❌ Verification error for {nct_id}: {e}", exc_info=True)
            return VerificationResult(
                nct_id=nct_id,
                verification_model=verification_model or config.VERIFICATION_MODEL,
                verified_annotation="",
                verified_parsed_data=parsed_data,  # Return original on error
                processing_time_seconds=time.time() - start_time,
                status="error",
                error=str(e)
            )
    
    def _generate_basic_verification_prompt(
        self,
        nct_id: str,
        original_annotation: str,
        parsed_data: Dict[str, str],
        trial_data: Dict[str, Any],
        primary_model: str
    ) -> str:
        """Generate a basic verification prompt without the full PromptGenerator."""
        return f"""# VERIFICATION TASK: {nct_id}

You are reviewing an annotation made by {primary_model}.

## ORIGINAL ANNOTATION:
{original_annotation}

## PARSED VALUES:
{json.dumps(parsed_data, indent=2)}

## YOUR TASK:
1. Review each field (Classification, Delivery Mode, Outcome, Reason for Failure, Peptide)
2. Identify any errors or inconsistencies
3. Provide corrections where needed

## OUTPUT FORMAT:

VERIFICATION REPORT
==================

Classification: [CORRECT/INCORRECT]
  Original: {parsed_data.get('Classification', 'N/A')}
  Verified: [your value]
  Reasoning: [explanation]

Delivery Mode: [CORRECT/INCORRECT]
  Original: {parsed_data.get('Delivery Mode', 'N/A')}
  Verified: [your value]
  Reasoning: [explanation]

Outcome: [CORRECT/INCORRECT]
  Original: {parsed_data.get('Outcome', 'N/A')}
  Verified: [your value]
  Reasoning: [explanation]

Reason for Failure: [CORRECT/INCORRECT/N/A]
  Original: {parsed_data.get('Reason for Failure', 'N/A')}
  Verified: [your value]
  Reasoning: [explanation]

Peptide: [CORRECT/INCORRECT]
  Original: {parsed_data.get('Peptide', 'N/A')}
  Verified: [your value]
  Reasoning: [explanation]

## FINAL VERIFIED ANNOTATION:

Classification: [value]
  Evidence: [evidence]
Delivery Mode: [value]
  Evidence: [evidence]
Outcome: [value]
  Evidence: [evidence]
Reason for Failure: [value or N/A]
  Evidence: [evidence]
Peptide: [value]
  Evidence: [evidence]
Sequence: [value or N/A]
Study IDs: [value or N/A]
Comments: [any notes]
"""
    
    def _get_basic_verification_system_prompt(self) -> str:
        """Basic system prompt for verification."""
        return """You are a Clinical Trial Annotation Reviewer. Your task is to verify and correct annotations made by another AI model.

Key rules:
- Classification: AMP = peptide that DIRECTLY kills pathogens. Other = everything else.
- Delivery Mode: Look for keywords - injection/IV/SC = Injection/Infusion, topical/cream/gel = Topical, oral/tablet = Oral
- Outcome: Must match the Overall Status field from the trial
- Peptide: True = amino acid chain <200aa, False = antibody/protein/small molecule

Be thorough but concise. Focus on accuracy."""
        
    def get_system_prompt(self) -> str:
        """Get the system prompt for annotation."""
        if self.prompt_generator and hasattr(self.prompt_generator, 'get_system_prompt'):
            return self.prompt_generator.get_system_prompt()
        return self._get_default_system_prompt()

    def _get_default_system_prompt(self) -> str:
        """Fallback system prompt."""
        return """You are a clinical trial annotator. Follow these STRICT rules:

CLASSIFICATION (AMP vs Other):
- AMP = peptide that DIRECTLY KILLS bacteria/fungi/viruses
- Other = cancer drugs, metabolic drugs, immunomodulators, hormones

DELIVERY MODE:
- Injection/Infusion: injection, IV, SC, IM, infusion
- Topical: topical, cream, gel, wound application
- Oral: oral, tablet, capsule

OUTCOME:
- RECRUITING/ACTIVE_NOT_RECRUITING → Active
- WITHDRAWN → Withdrawn  
- TERMINATED → Terminated
- COMPLETED + positive results → Positive
- COMPLETED + negative results → Failed - completed trial

Output format:
Classification: [AMP or Other]
  Evidence: [reason]
Delivery Mode: [Injection/Infusion, Topical, Oral, or Other]
  Evidence: [reason]
Outcome: [Positive, Withdrawn, Terminated, Failed - completed trial, Active, or Unknown]
  Evidence: [reason]
Reason for Failure: [N/A or category]
  Evidence: [reason]
Peptide: [True or False]
  Evidence: [reason]
Sequence: [sequence or N/A]
Study IDs: [PMIDs or N/A]
Comments: [notes]

Start your annotation:"""


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
        "git_commit": get_git_commit_id(),
        "features": {
            "json_parser": "available" if HAS_JSON_PARSER else "unavailable",
            "prompt_generator": "available" if HAS_PROMPT_GEN else "unavailable",
            "metadata_extraction": "enabled",
            "csv_export_with_metadata": "enabled",
            "two_stage_verification": "enabled"
        },
        "verification": {
            "enabled": config.VERIFICATION_ENABLED,
            "model": config.VERIFICATION_MODEL,
            "temperature": config.VERIFICATION_TEMPERATURE
        },
        "endpoints": {
            "annotate": "POST /annotate",
            "batch_annotate": "POST /batch-annotate",
            "verify": "POST /verify",
            "parse_trial": "POST /parse",
            "generate_prompt": "POST /generate-prompt",
            "export_csv": "POST /export-csv",
            "health": "GET /health",
            "models": "GET /models",
            "verification_config": "GET /verification-config"
        }
    }


@app.get("/health")
async def health_check():
    """Health check with dependency status."""
    ollama_connected = False
    ollama_models = []
    verification_model_available = False
    
    try:
        async with httpx.AsyncClient(timeout=5.0) as client:
            response = await client.get(f"{config.OLLAMA_BASE_URL}/api/tags")
            if response.status_code == 200:
                ollama_connected = True
                data = response.json()
                ollama_models = [m["name"] for m in data.get("models", [])]
                verification_model_available = any(
                    config.VERIFICATION_MODEL in m or m.startswith(config.VERIFICATION_MODEL.split(':')[0])
                    for m in ollama_models
                )
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
        },
        "verification": {
            "enabled": config.VERIFICATION_ENABLED,
            "model": config.VERIFICATION_MODEL,
            "model_available": verification_model_available
        }
    }


@app.get("/verification-config")
async def get_verification_config():
    """Get current verification configuration."""
    # Check if verification model is available
    model_available = False
    model_info = {}
    
    try:
        model_info = await get_ollama_model_info(config.VERIFICATION_MODEL)
        model_available = bool(model_info.get("digest"))
    except Exception:
        pass
    
    return {
        "enabled": config.VERIFICATION_ENABLED,
        "model": config.VERIFICATION_MODEL,
        "model_available": model_available,
        "model_info": model_info,
        "temperature": config.VERIFICATION_TEMPERATURE,
        "timeout_seconds": config.VERIFICATION_TIMEOUT,
        "env_vars": {
            "VERIFICATION_MODEL": "Model name for verification (default: gemma3:12b)",
            "VERIFICATION_ENABLED": "Enable/disable verification (default: true)",
            "VERIFICATION_TEMPERATURE": "Temperature for verification (default: 0.1)"
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
    """Parse trial data and extract annotation-relevant information."""
    logger.info(f"📋 Parsing trial data for {trial.nct_id}")
    parsed_info = annotator.parse_trial_data(trial.data)
    return {
        "nct_id": trial.nct_id,
        "parsed_info": parsed_info,
        "status": "success"
    }


@app.post("/generate-prompt")
async def generate_prompt(trial: TrialData):
    """Generate annotation prompt from trial data without calling LLM."""
    logger.info(f"📝 Generating prompt for {trial.nct_id}")
    prompt = annotator.generate_prompt(trial.data, trial.nct_id)
    return {
        "nct_id": trial.nct_id,
        "prompt": prompt,
        "prompt_length": len(prompt),
        "status": "success"
    }


@app.post("/verify", response_model=VerificationResult)
async def verify_annotation(request: VerificationRequest):
    """
    Verify an existing annotation using a second LLM.
    
    This endpoint can be used standalone to verify annotations
    that were made without the two-stage process.
    """
    logger.info(f"🔍 Verification request for {request.nct_id}")
    
    result = await annotator.verify_annotation(
        nct_id=request.nct_id,
        original_annotation=request.original_annotation,
        parsed_data=request.parsed_data,
        trial_data=request.trial_data,
        primary_model=request.primary_model,
        verification_model=request.verification_model,
        temperature=request.temperature
    )
    
    return result


@app.post("/annotate", response_model=AnnotationResult)
async def annotate_trial(request: AnnotationRequest):
    """
    Annotate a single clinical trial.
    
    With verification enabled (default), this performs two stages:
    1. Primary annotation using the specified model
    2. Verification using the verification model (gemma by default)
    
    The final result includes both the original and verified annotations.
    """
    import time
    start_time = time.time()
    
    trial = request.trial_data
    logger.info(f"🔬 Starting annotation for {trial.nct_id} with {request.model}")
    
    # Determine if verification should run
    enable_verification = request.enable_verification and config.VERIFICATION_ENABLED
    verification_model = request.verification_model or config.VERIFICATION_MODEL
    
    try:
        # Get model info for metadata
        model_info = await get_ollama_model_info(request.model)
        
        # Generate prompt
        if request.use_extraction_prompt and HAS_PROMPT_GEN:
            prompt = annotator.generate_prompt(trial.data, trial.nct_id)
        else:
            prompt = annotator._generate_basic_prompt(trial.data, trial.nct_id)
        
        logger.info(f"📝 Generated prompt ({len(prompt)} chars)")
        
        # Stage 1: Primary annotation
        annotation = await annotator.call_llm(
            request.model,
            prompt,
            request.temperature
        )

        logger.info(f"DEBUG: annotation length = {len(annotation)}")
        
        # Parse the response
        parsed_data = AnnotationResponseParser.parse_response(
            annotation, 
            trial.nct_id,
            trial_data=trial.data
        )
        
        populated_fields = [k for k, v in parsed_data.items() if v]
        logger.info(f"📊 Parsed {len(populated_fields)} fields from response")
        
        # Stage 2: Verification (if enabled)
        verification_result = None
        final_parsed_data = parsed_data
        
        if enable_verification:
            logger.info(f"🔍 Starting verification with {verification_model}")
            
            verification_result = await annotator.verify_annotation(
                nct_id=trial.nct_id,
                original_annotation=annotation,
                parsed_data=parsed_data,
                trial_data=trial.data,
                primary_model=request.model,
                verification_model=verification_model
            )
            
            if verification_result.status == "success":
                # Use verified data if verification succeeded
                final_parsed_data = verification_result.verified_parsed_data
                logger.info(f"✅ Verification complete: {verification_result.corrections_made} corrections")
            else:
                logger.warning(f"⚠️ Verification failed, using original annotation")
        
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
        
        # Build annotation metadata
        model_details = model_info.get("details", {})
        annotation_timestamp = datetime.utcnow().isoformat() + "Z"
        git_commit = get_git_commit_id()
        
        annotation_metadata = {
            "git_commit_id": git_commit,
            "git_commit_full": get_git_commit_full(),
            "llm_model": request.model,
            "llm_model_version": model_info.get("version_string", request.model),
            "llm_model_details": {
                "family": model_details.get("family", ""),
                "parameter_size": model_details.get("parameter_size", ""),
                "quantization_level": model_details.get("quantization_level", ""),
                "format": model_details.get("format", ""),
                "digest": model_info.get("digest", ""),
                "modified_at": model_info.get("modified_at", ""),
            },
            "annotation_timestamp": annotation_timestamp,
            "service_version": config.API_VERSION,
            "temperature": request.temperature,
            "verification_enabled": enable_verification,
            "verification_model": verification_model if enable_verification else None,
        }
        
        return AnnotationResult(
            nct_id=trial.nct_id,
            annotation=annotation,
            parsed_data=final_parsed_data,  # Use verified data if available
            model=request.model,
            status="success",
            processing_time_seconds=round(processing_time, 2),
            sources_summary=sources_summary,
            metadata=annotation_metadata,
            verification=verification_result,
            verified=verification_result is not None and verification_result.status == "success"
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
            error=str(e),
            metadata={
                "git_commit_id": get_git_commit_id(),
                "annotation_timestamp": datetime.utcnow().isoformat() + "Z",
                "service_version": config.API_VERSION,
            }
        )


@app.post("/batch-annotate", response_model=BatchAnnotationResponse)
async def batch_annotate(request: BatchAnnotationRequest):
    """
    Annotate multiple clinical trials with optional verification.
    """
    import time
    start_time = time.time()
    
    logger.info(f"🔬 Starting batch annotation for {len(request.trials)} trials")
    
    # Get model info once for the batch
    model_info = await get_ollama_model_info(request.model)
    
    # Determine verification settings
    enable_verification = request.enable_verification and config.VERIFICATION_ENABLED
    verification_model = request.verification_model or config.VERIFICATION_MODEL
    
    results = []
    successful = 0
    failed = 0
    verified_count = 0
    
    for trial in request.trials:
        try:
            single_request = AnnotationRequest(
                trial_data=trial,
                model=request.model,
                temperature=request.temperature,
                enable_verification=enable_verification,
                verification_model=verification_model
            )
            
            result = await annotate_trial(single_request)
            results.append(result)
            
            if result.status == "success":
                successful += 1
                if result.verified:
                    verified_count += 1
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
    
    logger.info(f"✅ Batch complete: {successful} successful, {failed} failed, {verified_count} verified in {total_time:.1f}s")
    
    # Build batch metadata
    batch_metadata = {
        "git_commit_id": get_git_commit_id(),
        "git_commit_full": get_git_commit_full(),
        "llm_model": request.model,
        "llm_model_details": {
            "family": model_info.get("details", {}).get("family", ""),
            "parameter_size": model_info.get("details", {}).get("parameter_size", ""),
            "quantization_level": model_info.get("details", {}).get("quantization_level", ""),
            "format": model_info.get("details", {}).get("format", ""),
            "digest": model_info.get("digest", ""),
        },
        "batch_start_timestamp": datetime.utcfromtimestamp(start_time).isoformat() + "Z",
        "batch_end_timestamp": datetime.utcnow().isoformat() + "Z",
        "service_version": config.API_VERSION,
        "temperature": request.temperature,
    }
    
    return BatchAnnotationResponse(
        results=results,
        total=len(request.trials),
        successful=successful,
        failed=failed,
        total_time_seconds=round(total_time, 2),
        metadata=batch_metadata,
        verification_enabled=enable_verification,
        verification_model=verification_model if enable_verification else None,
        verified_count=verified_count
    )


# ============================================================================
# CSV Export Endpoints
# ============================================================================

def generate_csv_header_comment(
    model_name: str,
    total_trials: int,
    successful: int,
    failed: int,
    git_commit: Optional[str] = None,
    timestamp: Optional[str] = None,
    model_version: Optional[str] = None,
    verification_model: Optional[str] = None,
    verified_count: int = 0
) -> str:
    """Generate the CSV header comment string."""
    if git_commit is None:
        git_commit = get_git_commit_id()
    if timestamp is None:
        timestamp = datetime.utcnow().strftime("%Y-%m-%d %H:%M:%S")
    
    model_display = model_version if model_version else model_name
    
    lines = [
        f"# Generated by AMP LLM Annotation System",
        f"# Model: {model_display}",
        f"# Git Commit: {git_commit}",
        f"# Timestamp: {timestamp}",
        f"# Total trials: {total_trials} (Successful: {successful}, Failed: {failed})",
    ]
    
    if verification_model:
        lines.append(f"# Verification Model: {verification_model}")
        lines.append(f"# Verified: {verified_count}/{successful}")
    
    return "\n".join(lines)


class CSVExportRequest(BaseModel):
    """Request model for CSV export."""
    results: List[AnnotationResult]
    include_header_metadata: bool = True


@app.post("/export-csv")
async def export_csv(request: CSVExportRequest):
    """Export annotation results as CSV with metadata header."""
    output = io.StringIO()
    
    if request.include_header_metadata and request.results:
        metadata = None
        for r in request.results:
            if r.metadata:
                metadata = r.metadata
                break
        
        successful = sum(1 for r in request.results if r.status == "success")
        failed = len(request.results) - successful
        verified_count = sum(1 for r in request.results if r.verified)
        timestamp = datetime.utcnow().strftime("%Y-%m-%d %H:%M:%S")
        
        git_commit = metadata.get('git_commit_id', get_git_commit_id()) if metadata else get_git_commit_id()
        verification_model = metadata.get('verification_model') if metadata else None
        
        if metadata:
            model_version = metadata.get('llm_model_version', '')
            if not model_version:
                model_name = metadata.get('llm_model', 'unknown')
                model_version = model_name
        else:
            model_version = 'unknown'
        
        output.write(f"# Generated by AMP LLM Annotation System\n")
        output.write(f"# Model: {model_version}\n")
        output.write(f"# Git Commit: {git_commit}\n")
        output.write(f"# Timestamp: {timestamp}\n")
        output.write(f"# Total trials: {len(request.results)} (Successful: {successful}, Failed: {failed})\n")
        if verification_model:
            output.write(f"# Verification Model: {verification_model}\n")
            output.write(f"# Verified: {verified_count}/{successful}\n")
    
    writer = csv.writer(output)
    writer.writerow(AnnotationResponseParser.CSV_COLUMNS)
    
    for result in request.results:
        if result.parsed_data:
            row = [result.parsed_data.get(col, '') for col in AnnotationResponseParser.CSV_COLUMNS]
            writer.writerow(row)
    
    timestamp = datetime.utcnow().strftime("%Y%m%d_%H%M%S")
    filename = f"amp_llm_annotations_{timestamp}.csv"
    
    return StreamingResponse(
        iter([output.getvalue()]),
        media_type="text/csv",
        headers={
            "Content-Disposition": f"attachment; filename={filename}"
        }
    )


@app.get("/csv-header-info")
async def get_csv_header_info(model_name: Optional[str] = None):
    """Get the current git commit, timestamp, and optionally model version for CSV headers."""
    result = {
        "git_commit": get_git_commit_id(),
        "git_commit_full": get_git_commit_full(),
        "timestamp": datetime.utcnow().strftime("%Y-%m-%d %H:%M:%S"),
        "service_version": config.API_VERSION,
        "verification_model": config.VERIFICATION_MODEL,
    }
    
    if model_name:
        model_info = await get_ollama_model_info(model_name)
        result["model_name"] = model_name
        result["model_version"] = model_info.get("version_string", model_name)
        result["model_details"] = {
            "family": model_info.get("details", {}).get("family", ""),
            "parameter_size": model_info.get("details", {}).get("parameter_size", ""),
            "quantization_level": model_info.get("details", {}).get("quantization_level", ""),
            "digest": model_info.get("digest", ""),
        }
    
    return result


@app.get("/model-version/{model_name}")
async def get_model_version(model_name: str):
    """Get the full version string for a specific model."""
    model_info = await get_ollama_model_info(model_name)
    
    return {
        "model_name": model_name,
        "version_string": model_info.get("version_string", model_name),
        "details": {
            "family": model_info.get("details", {}).get("family", ""),
            "parameter_size": model_info.get("details", {}).get("parameter_size", ""),
            "quantization_level": model_info.get("details", {}).get("quantization_level", ""),
            "format": model_info.get("details", {}).get("format", ""),
        },
        "digest": model_info.get("digest", ""),
        "size_bytes": model_info.get("size", ""),
        "modified_at": model_info.get("modified_at", ""),
    }


# ============================================================================
# Run standalone
# ============================================================================

if __name__ == "__main__":
    import uvicorn
    
    git_commit = get_git_commit_id()
    git_commit_full = get_git_commit_full()
    
    print("=" * 80)
    print(f"🚀 Starting {config.SERVICE_NAME} v{config.API_VERSION}")
    print("=" * 80)
    print(f"🔖 Git Commit: {git_commit}")
    if git_commit_full != git_commit:
        print(f"   Full SHA: {git_commit_full}")
    print(f"🤖 Ollama: {config.OLLAMA_BASE_URL}")
    print(f"📋 JSON Parser: {'Available' if HAS_JSON_PARSER else 'Not Available'}")
    print(f"📝 Prompt Generator: {'Available' if HAS_PROMPT_GEN else 'Not Available'}")
    print("-" * 80)
    print(f"🔍 TWO-STAGE VERIFICATION:")
    print(f"   Enabled: {config.VERIFICATION_ENABLED}")
    print(f"   Verification Model: {config.VERIFICATION_MODEL}")
    print(f"   Temperature: {config.VERIFICATION_TEMPERATURE}")
    print("-" * 80)
    print(f"📚 API Docs: http://localhost:{config.SERVICE_PORT}/docs")
    print(f"🔍 Health Check: http://localhost:{config.SERVICE_PORT}/health")
    print(f"⚙️  Verification Config: http://localhost:{config.SERVICE_PORT}/verification-config")
    print("-" * 80)
    print(f"✨ Port configuration loaded from .env")
    print(f"   LLM Assistant: {config.SERVICE_PORT}")
    print(f"   Ollama: {config.OLLAMA_PORT}")
    print("=" * 80)
    
    uvicorn.run(app, host="0.0.0.0", port=config.SERVICE_PORT, reload=True)