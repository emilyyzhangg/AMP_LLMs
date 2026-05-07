"""v42.8.3 Lever 3 — pub-to-trial matcher.

Classifies a publication's relevance to a clinical trial using four
independent signals: NCT-ID mention, sponsor-affiliation match,
intervention-drug match, year-window match. 2-of-4 = "matched"
trial-specific evidence even when the pub is not in
protocolSection.referencesModule.references[].

Designed to close the slice-G sourcing gap (failed-completed-trial 0/8)
where the existing pipeline finds 0 trial-specific pubs because
sponsors don't always register their primary publications. The
v42.7.20 _classify_publication heuristic defaults general; this matcher
provides explicit-evidence-driven trial specificity that the LLM and
deterministic overrides can rely on.

The 2-of-4 threshold protects against the v42.7.13 over-call class:
a review article on a drug class might match intervention + year, but
will not contain NCT mention AND sponsor affiliation for the specific
trial under evaluation.
"""

from __future__ import annotations

import re

_NCT_RE = re.compile(r"NCT\d{8}", re.IGNORECASE)

# Corporate-form suffixes stripped before sponsor substring match.
# We keep informative tokens like "therapeutics" / "pharmaceuticals" /
# "biotech" — those are part of how sponsors are written in author
# affiliations and stripping them collapses too many sponsors onto
# generic single-word matches.
_SPONSOR_SUFFIXES = (
    " incorporated", " inc", " llc", " l l c", " ltd", " limited",
    " corporation", " corp", " company", " co",
    " gmbh", " ag", " s a", " sa", " plc", " holdings",
)


def _normalize(s: str) -> str:
    s = (s or "").lower()
    s = re.sub(r"[^\w\s]", " ", s)
    s = re.sub(r"\s+", " ", s).strip()
    changed = True
    while changed:
        changed = False
        for suf in _SPONSOR_SUFFIXES:
            if s.endswith(suf):
                s = s[: -len(suf)].strip()
                changed = True
                break
    return s


def nct_in_pub(pub_text: str, nct_id: str) -> bool:
    """Exact NCT\\d{8} regex match against publication text."""
    if not pub_text or not nct_id:
        return False
    target = nct_id.strip().upper()
    for m in _NCT_RE.finditer(pub_text):
        if m.group(0).upper() == target:
            return True
    return False


def sponsor_match(sponsor_name: str, pub_text: str) -> bool:
    """Substring match of normalized sponsor name in normalized pub text.

    Min-length guard: normalized sponsor must be ≥5 chars (mirrors the
    DBAASP word-boundary lesson — guards against 2-letter false positives
    like "BMS" → matching "BMS" in "BMSY measurements").
    """
    if not sponsor_name or not pub_text:
        return False
    norm = _normalize(sponsor_name)
    if len(norm) < 5:
        return False
    return norm in _normalize(pub_text)


def intervention_match(interventions: list[str], pub_text: str) -> bool:
    """Word-boundary match of any intervention name (≥4 chars) in pub text."""
    if not interventions or not pub_text:
        return False
    text_lc = pub_text.lower()
    for intv in interventions:
        name = (intv or "").strip().lower()
        if not name or len(name) < 4:
            continue
        try:
            if re.search(rf"\b{re.escape(name)}\b", text_lc):
                return True
        except re.error:
            if name in text_lc:
                return True
    return False


def year_window_match(trial_start_year, pub_year) -> bool:
    """Pub published 0-7 years after trial start = plausible primary publication.

    Asymmetric window: pubs BEFORE trial start are excluded (cannot be primary
    readout); 7-year cap covers Phase I→Phase III readout timelines. Closes
    the false-positive risk of matching a review published a decade later.
    """
    if not trial_start_year or not pub_year:
        return False
    try:
        delta = int(pub_year) - int(trial_start_year)
    except (ValueError, TypeError):
        return False
    return 0 <= delta <= 7


def classify_pub_relevance(pub: dict, trial_meta: dict) -> str:
    """Return one of: registered | matched | candidate | unrelated.

    pub:        {pmid, text, year}
    trial_meta: {nct_id, sponsor_name, interventions, start_year, registered_pmids}
    """
    pmid = (pub.get("pmid") or "").strip()
    if pmid and pmid in (trial_meta.get("registered_pmids") or []):
        return "registered"

    text = pub.get("text") or ""
    signals = (
        nct_in_pub(text, trial_meta.get("nct_id", "")),
        sponsor_match(trial_meta.get("sponsor_name", ""), text),
        intervention_match(trial_meta.get("interventions") or [], text),
        year_window_match(trial_meta.get("start_year"), pub.get("year")),
    )
    n = sum(1 for s in signals if s)
    if n >= 2:
        return "matched"
    if n == 1:
        return "candidate"
    return "unrelated"
