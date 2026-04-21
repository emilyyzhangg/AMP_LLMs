from .classification import ClassificationAgent
from .classification_atomic import ClassificationAtomicAgent
from .delivery_mode import DeliveryModeAgent
from .outcome import OutcomeAgent
from .outcome_atomic import OutcomeAtomicAgent
from .failure_reason import FailureReasonAgent
from .failure_reason_atomic import FailureReasonAtomicAgent
from .peptide import PeptideAgent
from .sequence import SequenceAgent

ANNOTATION_AGENTS = {
    "classification": ClassificationAgent,
    # v42 B2 shadow-mode sibling. Gated by
    # config.orchestrator.classification_atomic_shadow (default OFF).
    "classification_atomic": ClassificationAtomicAgent,
    "delivery_mode": DeliveryModeAgent,
    "outcome": OutcomeAgent,
    # v42 shadow-mode sibling. The orchestrator skips this unless
    # config.orchestrator.outcome_atomic_shadow is True. Stored under a distinct
    # field_name so the legacy outcome annotation remains authoritative
    # downstream during Phase 5 validation.
    "outcome_atomic": OutcomeAtomicAgent,
    "reason_for_failure": FailureReasonAgent,
    # v42 B3 shadow-mode sibling. Gated by
    # config.orchestrator.failure_reason_atomic_shadow (default OFF).
    # Depends on outcome_atomic in the orchestrator step 3 (ran after outcome).
    "reason_for_failure_atomic": FailureReasonAtomicAgent,
    "peptide": PeptideAgent,
    "sequence": SequenceAgent,
}
