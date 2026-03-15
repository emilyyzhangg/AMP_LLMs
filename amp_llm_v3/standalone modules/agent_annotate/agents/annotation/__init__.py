from .classification import ClassificationAgent
from .delivery_mode import DeliveryModeAgent
from .outcome import OutcomeAgent
from .failure_reason import FailureReasonAgent
from .peptide import PeptideAgent

ANNOTATION_AGENTS = {
    "classification": ClassificationAgent,
    "delivery_mode": DeliveryModeAgent,
    "outcome": OutcomeAgent,
    "reason_for_failure": FailureReasonAgent,
    "peptide": PeptideAgent,
}
