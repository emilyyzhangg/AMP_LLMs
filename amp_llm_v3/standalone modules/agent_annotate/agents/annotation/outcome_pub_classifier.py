"""
Outcome agent — Tier 1a Trial-Specificity Classifier (v42 atomic redesign).

Replaces v41's 30-keyword list + default-to-trial-specific heuristic with three
structural questions that don't depend on prompt tuning or LLM judgment:

  Q1 (content):   Does the publication body/abstract contain the NCT ID literal?
  Q2 (metadata):  Is the publication's PMID listed in CT.gov's referencesModule
                  for this trial?
  Q3 (design):    Does the title contain a trial-design phrase AND a drug name?

Q1 and Q2 are deterministic structural checks — no keyword list, no prompt
tuning can flip them. Q3 is a minimal heuristic (only fires when both halves
match) and is only used when Q1/Q2 don't conclude.

Output: "trial_specific" | "general" | "ambiguous".

"general" is reserved for confident rejections (explicit review markers).
"ambiguous" means we couldn't decide — the Tier 1b LLM assessor will still
look at it, but the aggregator may weight the verdict lower.
"""

from __future__ import annotations

import logging
import re
from dataclasses import dataclass
from typing import Literal, Optional

from app.models.research import ResearchResult

logger = logging.getLogger("agent_annotate.annotation.outcome_pub")


# Explicit review/overview markers. When *only* these signals are present, we
# are confident the publication is not trial-specific. Kept deliberately tight
# — being cautious about calling something "general" because Tier 1b LLM can
# still redeem it if pressed.
_REVIEW_MARKERS = (
    "systematic review",
    "meta-analysis",
    "meta analysis",
    "narrative review",
    "mini-review",
    "scoping review",
    "editorial",
    "commentary",
    "perspective on",
    "a review of",
    "review of the",
    "overview of",
    "state of the art",
    "state-of-the-art",
    "current state",
    "landscape of",
    "recent advances",
    "recent developments",
    "advances in",
    "future directions",
    "next-generation",
    "next generation",
)

# Phrases that characterize a *primary* trial report. Combined with drug name
# match in Q3 to flag ambiguous-but-likely-trial-specific cases.
_TRIAL_DESIGN_PHRASES = (
    "randomized",
    "randomised",
    "phase i",
    "phase ii",
    "phase iii",
    "phase 1",
    "phase 2",
    "phase 3",
    "first-in-human",
    "first in human",
    "dose-escalation",
    "dose escalation",
    "open-label",
    "open label",
    "double-blind",
    "double blind",
    "single-arm",
    "single arm",
    "placebo-controlled",
    "placebo controlled",
    "interim results",
    "final results",
    "final analysis",
    "safety and efficacy of",
    "a study of",
    "a trial of",
)

Specificity = Literal["trial_specific", "general", "ambiguous"]


@dataclass
class PubCandidate:
    """A single publication candidate extracted from literature research results."""
    pmid: str = ""          # "PMID:12345" | "PMC:12345" | "DOI:..." | ""
    pmid_bare: str = ""     # Numeric PMID only ("12345"), empty if not a PMID
    title: str = ""
    snippet: str = ""       # Full citation text (often includes abstract)
    source: str = ""        # pubmed | pmc | openalex | crossref | europe_pmc | ...
    year: Optional[int] = None
    publication_type: str = ""  # Lowercase marker if any review/editorial type inferred

    @property
    def combined_text(self) -> str:
        """Lowercased concatenation of all searchable text."""
        return f"{self.title}\n{self.snippet}".lower()


_PMID_RE = re.compile(r"^PMID:(\d+)$", re.IGNORECASE)


def _parse_pmid_bare(identifier: str) -> str:
    """Extract the numeric PMID from 'PMID:12345' form. Empty otherwise."""
    if not identifier:
        return ""
    m = _PMID_RE.match(identifier.strip())
    return m.group(1) if m else ""


def _infer_publication_type(text: str) -> str:
    """Guess publication type from text. Returns 'review' only on confident signal."""
    lower = text.lower()
    for marker in _REVIEW_MARKERS:
        if marker in lower:
            return "review"
    return ""


def extract_pub_candidates(
    research_results: list[ResearchResult],
) -> list[PubCandidate]:
    """Collect publication candidates from literature research agents.

    Deduplicates by (PMID | title_prefix) across sources.
    """
    seen_keys: set[str] = set()
    pubs: list[PubCandidate] = []

    for result in research_results:
        if result.error or result.agent_name != "literature":
            continue
        for citation in result.citations or []:
            identifier = (citation.identifier or "").strip()
            title = (citation.title or "").strip()
            snippet = (citation.snippet or "").strip()

            pmid_bare = _parse_pmid_bare(identifier)
            # Primary dedup key: PMID if available, else title prefix.
            key = pmid_bare or (title[:80].lower() if title else snippet[:80].lower())
            if not key or key in seen_keys:
                continue
            seen_keys.add(key)

            pub_type = _infer_publication_type(title + " " + snippet[:500])

            pubs.append(
                PubCandidate(
                    pmid=identifier,
                    pmid_bare=pmid_bare,
                    title=title or snippet[:120],
                    snippet=snippet,
                    source=citation.source_name or "",
                    year=citation.retrieved_at and None,  # year not directly on SourceCitation
                    publication_type=pub_type,
                )
            )

    return pubs


def classify_pub_specificity(
    pub: PubCandidate,
    nct_id: str,
    ctgov_reference_pmids: set[str],
    drug_names: Optional[set[str]] = None,
) -> Specificity:
    """Classify one publication's relationship to this trial.

    Q1 (content): Does the pub text literally contain the NCT ID?
    Q2 (metadata): Is its PMID in CT.gov's referencesModule for this trial?
    Q3 (design): Does the title contain a trial-design phrase AND a drug name?

    Q1/Q2 → trial_specific (high confidence, structural).
    Q3    → trial_specific (medium confidence, positive heuristic).
    Explicit review marker, no trial signals → general.
    Otherwise → ambiguous.
    """
    nct_lower = (nct_id or "").lower().strip()

    # Q1: NCT in body text
    if nct_lower and nct_lower in pub.combined_text:
        return "trial_specific"

    # Q2: PMID in CT.gov references
    if pub.pmid_bare and pub.pmid_bare in ctgov_reference_pmids:
        return "trial_specific"

    # Q3: title has design signal AND at least one drug-name hit
    title_lower = pub.title.lower()
    has_design = any(phrase in title_lower for phrase in _TRIAL_DESIGN_PHRASES)
    has_drug = False
    if drug_names and has_design:
        for name in drug_names:
            nm = (name or "").lower().strip()
            if len(nm) >= 3 and nm in title_lower:
                has_drug = True
                break
    if has_design and has_drug:
        return "trial_specific"

    # Explicit review with no other trial signal → confident general.
    if pub.publication_type == "review":
        return "general"

    return "ambiguous"


def extract_drug_names(research_results: list[ResearchResult]) -> set[str]:
    """Pull intervention names from clinical_protocol raw_data for Q3 matching."""
    names: set[str] = set()
    for result in research_results:
        if result.error or result.agent_name != "clinical_protocol" or not result.raw_data:
            continue
        proto = result.raw_data.get(
            "protocol_section",
            result.raw_data.get("protocolSection", {}),
        )
        arms_mod = proto.get("armsInterventionsModule", {})
        for interv in arms_mod.get("interventions", []) or []:
            name = (interv.get("name") or "").strip()
            if name:
                names.add(name)
            for other in interv.get("otherNames", []) or []:
                other = (other or "").strip()
                if other:
                    names.add(other)
    return names


def classify_all_pubs(
    research_results: list[ResearchResult],
    nct_id: str,
) -> list[tuple[PubCandidate, Specificity]]:
    """Convenience: extract all pubs and classify them in one call."""
    pubs = extract_pub_candidates(research_results)
    ctgov_refs = set()
    drug_names = extract_drug_names(research_results)

    for result in research_results:
        if result.agent_name == "clinical_protocol" and result.raw_data:
            proto = result.raw_data.get(
                "protocol_section",
                result.raw_data.get("protocolSection", {}),
            )
            refs_mod = proto.get("referencesModule", {})
            for ref in refs_mod.get("references", []) or []:
                pmid = ref.get("pmid")
                if pmid:
                    ctgov_refs.add(str(pmid).strip())

    return [
        (pub, classify_pub_specificity(pub, nct_id, ctgov_refs, drug_names))
        for pub in pubs
    ]
