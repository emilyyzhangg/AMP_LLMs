"""
Centralized validation configuration for clinical trial data.
All controlled vocabularies and validation rules in one place.
"""
from enum import Enum
from typing import List, Dict, Any, Optional
from dataclasses import dataclass


# ============================================================================
# ENUMS - Valid Values for Each Field
# ============================================================================

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


# ============================================================================
# VALIDATION MAPPINGS
# ============================================================================

# Status to Outcome mapping
STATUS_TO_OUTCOME: Dict[str, str] = {
    'ongoing': 'Active, not recruiting',
    'active': 'Active, not recruiting',
    'active_not_recruiting': 'Active, not recruiting',
    'active not recruiting': 'Active, not recruiting',
    'recruiting': 'Recruiting',
    'enrolling': 'Recruiting',
    'enrolling_by_invitation': 'Recruiting',
    'not_yet_recruiting': 'Recruiting',
    'not yet recruiting': 'Recruiting',
    'completed': 'Positive',
    'complete': 'Positive',
    'finished': 'Positive',
    'terminated': 'Terminated',
    'stopped': 'Terminated',
    'suspended': 'Terminated',
    'halted': 'Terminated',
    'withdrawn': 'Withdrawn',
    'cancelled': 'Withdrawn',
    'canceled': 'Withdrawn',
    'unknown': 'Unknown',
    'unavailable': 'Unknown',
}

# Keywords for peptide detection
PEPTIDE_KEYWORDS: List[str] = [
    'peptide', 
    'amp', 
    'antimicrobial peptide', 
    'dramp',
    'polypeptide',
    'amino acid sequence'
]

# Keywords for infection classification
INFECTION_KEYWORDS: List[str] = [
    'infection',
    'sepsis',
    'bacterial',
    'fungal',
    'antimicrobial',
    'antibiotic',
    'pathogen',
    'septic',
    'bacteremia',
    'pneumonia'
]

# Keywords for delivery mode detection
DELIVERY_MODE_KEYWORDS: Dict[str, List[str]] = {
    'IV': ['intravenous', 'iv ', 'i.v.', 'infusion'],
    'Injection/Infusion - Intramuscular': ['intramuscular', 'i.m.', 'im injection'],
    'Injection/Infusion - Subcutaneous/Intradermal': ['subcutaneous', 'subq', 's.c.', 'sc injection', 'intradermal'],
    'Oral - Tablet': ['tablet', 'oral tablet'],
    'Oral - Capsule': ['capsule', 'oral capsule'],
    'Topical - Cream/Gel': ['topical', 'cream', 'gel', 'ointment'],
    'Intranasal': ['nasal', 'intranasal'],
    'Inhalation': ['inhal', 'nebuliz', 'inhaler'],
    'Oral - Unspecified': ['oral'],
}

# Keywords for failure reason detection
FAILURE_REASON_KEYWORDS: Dict[str, List[str]] = {
    'Toxic/Unsafe': ['safe', 'toxic', 'adverse', 'ae', 'safety'],
    'Recruitment issues': ['recruit', 'enroll', 'accru', 'enrollment'],
    'Due to covid': ['covid', 'pandemic', 'coronavirus'],
    'Business Reason': ['business', 'sponsor', 'fund', 'financial'],
    'Ineffective for purpose': ['ineffective', 'efficacy', 'futility', 'futile'],
}


# ============================================================================
# VALIDATION CONFIG
# ============================================================================

@dataclass
class ValidationConfig:
    """Configuration for data validation."""
    
    # Enum classes
    study_status_enum: type = StudyStatus
    phase_enum: type = Phase
    classification_enum: type = Classification
    delivery_mode_enum: type = DeliveryMode
    outcome_enum: type = Outcome
    failure_reason_enum: type = FailureReason
    
    # Mappings
    status_to_outcome: Dict[str, str] = None
    peptide_keywords: List[str] = None
    infection_keywords: List[str] = None
    delivery_mode_keywords: Dict[str, List[str]] = None
    failure_reason_keywords: Dict[str, List[str]] = None
    
    # Validation settings
    fuzzy_matching: bool = True
    case_sensitive: bool = False
    allow_unknown: bool = True
    
    def __post_init__(self):
        """Initialize default mappings."""
        if self.status_to_outcome is None:
            self.status_to_outcome = STATUS_TO_OUTCOME
        if self.peptide_keywords is None:
            self.peptide_keywords = PEPTIDE_KEYWORDS
        if self.infection_keywords is None:
            self.infection_keywords = INFECTION_KEYWORDS
        if self.delivery_mode_keywords is None:
            self.delivery_mode_keywords = DELIVERY_MODE_KEYWORDS
        if self.failure_reason_keywords is None:
            self.failure_reason_keywords = FAILURE_REASON_KEYWORDS
    
    def get_valid_values(self, field_name: str) -> List[str]:
        """Get list of valid values for a field."""
        enum_map = {
            'study_status': self.study_status_enum,
            'phase': self.phase_enum,
            'classification': self.classification_enum,
            'delivery_mode': self.delivery_mode_enum,
            'outcome': self.outcome_enum,
            'failure_reason': self.failure_reason_enum,
        }
        
        enum_class = enum_map.get(field_name)
        if enum_class:
            return [member.value for member in enum_class]
        return []
    
    def get_all_valid_values(self) -> Dict[str, List[str]]:
        """Get all valid values for all fields."""
        return {
            'Study Status': self.get_valid_values('study_status'),
            'Phases': self.get_valid_values('phase'),
            'Classification': self.get_valid_values('classification'),
            'Delivery Mode': self.get_valid_values('delivery_mode'),
            'Outcome': self.get_valid_values('outcome'),
            'Reason for Failure': self.get_valid_values('failure_reason'),
        }
    
    def format_valid_values_display(self) -> str:
        """Format valid values for display."""
        lines = ["📋 Valid Values for All Fields:\n"]
        
        for field_name, values in self.get_all_valid_values().items():
            lines.append(f"\n{field_name}:")
            for value in values:
                lines.append(f"  • {value}")
        
        return "\n".join(lines)


# ============================================================================
# VALIDATION FUNCTIONS
# ============================================================================

def normalize_for_comparison(text: str) -> str:
    """Normalize text for comparison."""
    return text.upper().replace(" ", "").replace("_", "").replace("|", "").replace("(", "").replace(")", "").replace("-", "")


def validate_enum_value(
    value: str,
    enum_class: type,
    field_name: str,
    config: Optional[ValidationConfig] = None,
    logger = None
) -> str:
    """
    Validate and normalize enum value.
    
    Args:
        value: Value to validate
        enum_class: Enum class to validate against
        field_name: Name of field (for logging)
        config: Validation configuration
        logger: Optional logger
        
    Returns:
        Valid enum value or closest match
    """
    if config is None:
        config = ValidationConfig()
    
    if not value or value == "N/A":
        return "N/A"
    
    value_clean = value.strip()
    
    # Exact match (case insensitive if configured)
    for member in enum_class:
        if config.case_sensitive:
            if value_clean == member.value:
                return member.value
        else:
            if value_clean.upper() == member.value.upper():
                return member.value
    
    if not config.fuzzy_matching:
        if logger:
            logger.warning(f"Invalid {field_name}: '{value}' (no match found)")
        return value_clean
    
    # Fuzzy matching - normalize both sides
    value_norm = normalize_for_comparison(value_clean)
    
    # Try normalized matching
    for member in enum_class:
        if value_norm == normalize_for_comparison(member.value):
            if logger:
                logger.info(f"Fuzzy matched '{value}' → '{member.value}' for {field_name}")
            return member.value
    
    # Try substring matching
    for member in enum_class:
        member_norm = normalize_for_comparison(member.value)
        if value_norm in member_norm or member_norm in value_norm:
            if logger:
                logger.info(f"Substring matched '{value}' → '{member.value}' for {field_name}")
            return member.value
    
    # No match found
    if logger:
        logger.warning(f"Could not validate '{value}' for {field_name}")
        logger.debug(f"Valid options: {[m.value for m in enum_class]}")
    
    return value_clean


def normalize_outcome(status: str, config: Optional[ValidationConfig] = None, logger = None) -> str:
    """
    Map study status to valid outcome value.
    
    Args:
        status: Raw status string
        config: Validation configuration
        logger: Optional logger
        
    Returns:
        Valid Outcome enum value
    """
    if config is None:
        config = ValidationConfig()
    
    if not status:
        return "Unknown"
    
    status_lower = status.lower().strip()
    
    # Try direct mapping
    if status_lower in config.status_to_outcome:
        outcome = config.status_to_outcome[status_lower]
        if logger:
            logger.debug(f"Mapped status '{status}' → '{outcome}'")
        return outcome
    
    # Try partial matching
    for key, value in config.status_to_outcome.items():
        if key in status_lower or status_lower in key:
            if logger:
                logger.info(f"Partial match: '{status}' → '{value}'")
            return value
    
    # Default to Unknown
    if logger:
        logger.warning(f"Could not map status '{status}' to outcome, using 'Unknown'")
    return 'Unknown'


# ============================================================================
# GLOBAL INSTANCE
# ============================================================================

_validation_config: Optional[ValidationConfig] = None


def get_validation_config() -> ValidationConfig:
    """Get global validation configuration (singleton pattern)."""
    global _validation_config
    if _validation_config is None:
        _validation_config = ValidationConfig()
    return _validation_config


def reload_validation_config() -> ValidationConfig:
    """Reload validation configuration."""
    global _validation_config
    _validation_config = ValidationConfig()
    return _validation_config