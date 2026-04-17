from .classification import ClassificationAgent
from .delivery_mode import DeliveryModeAgent
from .outcome import OutcomeAgent
from .outcome_atomic import OutcomeAtomicAgent
from .failure_reason import FailureReasonAgent
from .peptide import PeptideAgent
from .sequence import SequenceAgent

ANNOTATION_AGENTS = {
    "classification": ClassificationAgent,
    "delivery_mode": DeliveryModeAgent,
    "outcome": OutcomeAgent,
    # v42 shadow-mode sibling. The orchestrator skips this unless
    # config.orchestrator.outcome_atomic_shadow is True. Stored under a distinct
    # field_name so the legacy outcome annotation remains authoritative
    # downstream during Phase 5 validation.
    "outcome_atomic": OutcomeAtomicAgent,
    "reason_for_failure": FailureReasonAgent,
    "peptide": PeptideAgent,
    "sequence": SequenceAgent,
}
