"""v42.8.4 Lever 4 — drug-code → biological-name resolver.

Many clinical-trial interventions are pharma research codes (PLG0206,
CBX129801, GT-001) rather than canonical drug names. UniProt/DRAMP
indexes don't recognize these codes, so the peptide_identity agent
returns "no_structured_match" and downstream sequence extraction emits
N/A. Slice-H sequence accuracy 1/9 = 11.1% is a direct consequence.

Resolution strategy (in order):
1. PubChem `compound/name/<code>/synonyms/JSON` — covers research-stage
   codes and exposes synonym lists that include the biological name
   (PLG0206 → WLBU2, CBX129801 → C-Peptide). PubChem is comprehensive
   for both marketed and pre-clinical drugs.
2. RxNorm `approximateTerm.json?term=<code>` — fuzzy match; primarily
   FDA-approved + late-stage. Used as cross-reference / cap on
   PubChem hits.
3. Empty list when neither source recognizes the code — downstream
   agents fall back to current behavior (LLM-based EDAM resolver,
   then no-resolution).

Output shape (raw_data):
    resolved_drug_names: {
        "<intervention_name>": [
            {"name": "<canonical>", "source": "pubchem|rxnorm",
             "confidence": 0.0-1.0, "id": "<external_id>"}
        ]
    }

Downstream consumption:
- orchestrator.py inserts these into shared_metadata["interventions"][i]
  ["resolved"] alongside EDAM-cached LLM resolutions
- peptide_identity._extract_resolved_names already iterates that list
  and tries each name against UniProt — zero-touch integration
- sequence agent's _KNOWN_SEQUENCES lookup also iterates resolved names
- outcome dossier displays the resolutions to the LLM for trial-drug
  identification context

Per `feedback_no_cheat_sheets.md` and `feedback_frozen_drug_lists.md`:
this module does NOT hardcode any code→name table. Every resolution
goes through PubChem/RxNorm; failures are silent and downstream
behavior is unchanged.
"""

from __future__ import annotations

import asyncio
import logging
import re
from typing import Optional

import httpx

from agents.base import BaseResearchAgent
from agents.research.drug_cache import drug_cache
from agents.research.http_utils import resilient_get
from app.models.research import ResearchResult, SourceCitation

logger = logging.getLogger("agent_annotate.research.drug_code_resolver")

PUBCHEM_NAME_URL = (
    "https://pubchem.ncbi.nlm.nih.gov/rest/pug/compound/name/{name}/synonyms/JSON"
)
RXNORM_APPROX_URL = (
    "https://rxnav.nlm.nih.gov/REST/approximateTerm.json"
)

# Common pharma-code shape: 2-6 letters + optional dash + 2-7 digits, or
# isotope-prefix + dash + letters (64Cu-SARTATE). The resolver still
# tries unrecognized strings — this regex is a fast-path heuristic only
# and is not used to GATE resolution.
_PHARMA_CODE_HINT = re.compile(
    r"^(?:\d{2,3}[A-Za-z]{1,3}-)?[A-Z]{2,6}-?\d{2,7}$"
)


def looks_like_pharma_code(name: str) -> bool:
    """Heuristic: looks like a drug code rather than a biological name.

    True for "PLG0206", "CBX129801", "64Cu-SARTATE", "GT-001"; False for
    "semaglutide", "Heat Shock Protein 70", "Whey".
    """
    if not name:
        return False
    s = name.strip().replace(" ", "")
    return bool(_PHARMA_CODE_HINT.match(s))


def _is_uninformative_synonym(syn: str) -> bool:
    """Filter out synonyms that aren't useful biological names.

    Drops: pure CAS numbers, IUPAC chemical names (very long), other
    pharma codes, ChEMBL/UNII/CID identifiers, internal lab codes,
    bare UNII codes (10-char uppercase alphanumeric), IUPAC stereo
    strings (parenthesized stereodescriptors), and lowercase
    amino-acid linkage notation. Slice-I audit (2026-05-08) revealed
    ~half of resolver output was noise of these shapes — wasted
    UniProt queries downstream.
    """
    s = (syn or "").strip()
    if not s:
        return True
    # CAS registry: 2-7 digits + dash + 2 digits + dash + 1 digit
    if re.match(r"^\d{2,7}-\d{2}-\d$", s):
        return True
    # Database identifier prefixes
    for prefix in ("CHEMBL", "DTXSID", "DTXCID", "UNII", "CID", "SCHEMBL", "GTPL"):
        if s.upper().startswith(prefix):
            return True
    # Bare UNII format: 10 alphanumeric uppercase characters with at
    # least one digit and one letter (e.g. 'J1J4P3PQZD', '17ZS80333G',
    # '33W7SJ9TBX'). The synonym list returns UNIIs without the prefix.
    if (len(s) == 10 and s.isalnum() and s == s.upper()
            and any(c.isdigit() for c in s) and any(c.isalpha() for c in s)):
        return True
    # IUPAC stereodescriptor pattern: parenthesized stereo markers like
    # "(2R)-", "(2S)-", "(3S,4R)-" appearing 2+ times. These never
    # appear in bio names (UniProt protein names, generic drug names).
    if len(re.findall(r"\(\d+[A-Z]\)", s)) >= 2:
        return True
    # IUPAC amino-acid linkage notation (lowercase 3-letter codes
    # connected by dashes): "sar-val-tyr-ile-his-pro-d-ala-oh"
    if re.search(r"\b[a-z]{3}-[a-z]{3}-[a-z]{3}-", s):
        return True
    # IUPAC/structural names with stereochemistry markers — repeated
    # "-L-" / "-D-" amino-acid linkages are unambiguous IUPAC regardless
    # of length.
    if s.count("-L-") >= 3 or s.count("-D-") >= 3:
        return True
    if len(s) > 120 and s.upper() == s:
        return True
    # Internal lab codes: 2-4 lowercase letters followed by 4+ digits
    # ('orb3142637', 'tp3849', etc.). Biological names rarely look like this.
    if re.match(r"^[a-z]{2,4}\d{4,}$", s):
        return True
    # Other pharma-code-shaped synonyms (we want biological names, not
    # other internal codes)
    if looks_like_pharma_code(s):
        return True
    return False


async def _resolve_pubchem(name: str, client: httpx.AsyncClient) -> list[dict]:
    """Query PubChem synonyms for a drug code; return informative names."""
    try:
        url = PUBCHEM_NAME_URL.format(name=name)
        resp = await resilient_get(url, client=client, headers={"Accept": "application/json"})
    except Exception as exc:
        logger.debug(f"pubchem resolve failed for {name!r}: {exc}")
        return []
    if resp.status_code != 200:
        return []
    try:
        data = resp.json()
    except ValueError:
        return []
    out = []
    for info in data.get("InformationList", {}).get("Information", []):
        cid = info.get("CID")
        synonyms = info.get("Synonym") or []
        for syn in synonyms[:30]:
            if syn.strip().lower() == name.strip().lower():
                continue
            if _is_uninformative_synonym(syn):
                continue
            out.append({
                "name": syn.strip(),
                "source": "pubchem",
                "confidence": 0.85,
                "id": f"CID{cid}" if cid else "",
            })
            if len(out) >= 6:
                break
        if out:
            break
    return out


async def _resolve_rxnorm(name: str, client: httpx.AsyncClient) -> list[dict]:
    """Query RxNorm approximateTerm; return candidate names with score."""
    try:
        resp = await resilient_get(
            RXNORM_APPROX_URL,
            client=client,
            params={"term": name, "maxEntries": "5"},
            headers={"Accept": "application/json"},
        )
    except Exception as exc:
        logger.debug(f"rxnorm resolve failed for {name!r}: {exc}")
        return []
    if resp.status_code != 200:
        return []
    try:
        data = resp.json()
    except ValueError:
        return []
    out = []
    for cand in data.get("approximateGroup", {}).get("candidate", []) or []:
        cname = (cand.get("name") or "").strip()
        if not cname or cname.lower() == name.strip().lower():
            continue
        try:
            score = float(cand.get("score", 0))
        except (TypeError, ValueError):
            score = 0.0
        # Drop low-score fuzzy matches — RxNorm returns near-anything if
        # asked. Empirically: score ≥ 8 = real match, < 8 = noise.
        # Smoke: FAKE-NONSENSE-12345 returns Consensi at score≈7 (false
        # positive); semaglutide returns Semaglutide at score≈12.6.
        if score < 8.0:
            continue
        # RxNorm scores are unbounded but typically 1-30; map to [0,1]
        confidence = min(0.5 + score / 40.0, 0.95)
        out.append({
            "name": cname,
            "source": "rxnorm",
            "confidence": confidence,
            "id": cand.get("rxcui", ""),
        })
        if len(out) >= 4:
            break
    return out


async def resolve(name: str, client: Optional[httpx.AsyncClient] = None) -> list[dict]:
    """Resolve a drug code to a list of canonical-name candidates.

    Public entry point. Returns a list of {name, source, confidence, id}
    dicts ordered by confidence (descending). Empty list = no resolution.
    """
    if not name:
        return []
    cache_key = name.strip().lower()

    async def _do_resolve() -> list[dict]:
        owns_client = client is None
        c = client or httpx.AsyncClient(timeout=15)
        try:
            # Slice-I audit (2026-05-08): PubChem indexes "AMG-334" but not
            # "AMG 334" (space variant). Try the original name plus dash/
            # no-dash variants when the original has a separator.
            variants = [name]
            if " " in name:
                variants.append(name.replace(" ", "-"))
                variants.append(name.replace(" ", ""))
            elif "-" in name:
                variants.append(name.replace("-", " "))
                variants.append(name.replace("-", ""))
            pubchem_results: list[dict] = []
            for v in variants:
                pubchem_results = await _resolve_pubchem(v, c)
                if pubchem_results:
                    break
            rxnorm_results: list[dict] = []
            if not pubchem_results:
                for v in variants:
                    rxnorm_results = await _resolve_rxnorm(v, c)
                    if rxnorm_results:
                        break
            combined = pubchem_results + rxnorm_results
            # Deduplicate by lowercased name; keep highest confidence
            best: dict[str, dict] = {}
            for r in combined:
                k = r["name"].strip().lower()
                if k not in best or r["confidence"] > best[k]["confidence"]:
                    best[k] = r
            return sorted(best.values(), key=lambda r: r["confidence"], reverse=True)
        finally:
            if owns_client:
                await c.aclose()

    return await drug_cache.get_or_compute(
        "drug_code_resolver", cache_key, _do_resolve,
    )


class DrugCodeResolverAgent(BaseResearchAgent):
    """Resolves intervention drug codes via PubChem + RxNorm.

    Run alongside other research agents in the orchestrator's parallel
    Phase-1 sweep. Output flows into shared_metadata so peptide_identity,
    sequence, and outcome agents see resolved names without per-agent
    wiring.
    """

    agent_name = "drug_code_resolver"
    sources = ["pubchem", "rxnorm"]

    async def research(
        self, nct_id: str, metadata: Optional[dict] = None
    ) -> ResearchResult:
        intervention_names: list[str] = []
        if metadata and isinstance(metadata.get("interventions"), list):
            for item in metadata["interventions"]:
                if isinstance(item, str):
                    intervention_names.append(item)
                elif isinstance(item, dict):
                    n = item.get("name") or item.get("intervention_name") or ""
                    if n:
                        intervention_names.append(str(n))

        if not intervention_names:
            return ResearchResult(
                agent_name=self.agent_name,
                nct_id=nct_id,
                citations=[],
                raw_data={"note": "no interventions to resolve"},
            )

        resolved_map: dict[str, list[dict]] = {}
        citations: list[SourceCitation] = []

        async with httpx.AsyncClient(timeout=15) as client:
            tasks = [resolve(n, client=client) for n in intervention_names[:5]]
            results = await asyncio.gather(*tasks, return_exceptions=True)

        for n, res in zip(intervention_names[:5], results):
            if isinstance(res, Exception):
                logger.warning(f"{nct_id} resolve {n!r} failed: {res}")
                continue
            if not res:
                continue
            resolved_map[n] = res
            top = res[0]
            citations.append(SourceCitation(
                source_name=top["source"],
                source_url=(
                    f"https://pubchem.ncbi.nlm.nih.gov/compound/{top['id'][3:]}"
                    if top.get("source") == "pubchem" and top.get("id", "").startswith("CID")
                    else f"https://rxnav.nlm.nih.gov/REST/rxcui/{top['id']}"
                    if top.get("source") == "rxnorm" and top.get("id")
                    else None
                ),
                identifier=top.get("id", ""),
                title=f"{n} → {top['name']}",
                snippet=(
                    f"Resolved {n} to {top['name']} "
                    f"(source={top['source']}, confidence={top['confidence']:.2f}). "
                    f"{len(res) - 1} additional candidate(s)."
                ),
                quality_score=self.compute_quality_score(top["source"]),
            ))

        return ResearchResult(
            agent_name=self.agent_name,
            nct_id=nct_id,
            citations=citations,
            raw_data={
                "resolved_drug_names": resolved_map,
                "intervention_count": len(intervention_names),
                "resolved_count": len(resolved_map),
            },
        )
