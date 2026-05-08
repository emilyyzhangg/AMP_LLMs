"""
Research agents registry.

v8: Removed 3 dead agents:
  - dbAMP: server (yylab.jnu.edu.cn) permanently unreachable
  - IntAct: 1/10 hit rate, mostly noise (generic protein interactions)
  - CARD: 0/10 hit rate, only relevant for antibiotic resistance trials

v8: Removed Semantic Scholar from literature agent (heavy rate limiting).
v31: Reintroduced as standalone agent with proper rate limiting. Added
     OpenAlex and CrossRef for broader literature coverage.
15 active agents remain, querying 20+ free databases.
"""

from agents.research.clinical_protocol import ClinicalProtocolAgent
from agents.research.literature import LiteratureAgent
from agents.research.peptide_identity import PeptideIdentityAgent
from agents.research.web_context import WebContextAgent
from agents.research.dbaasp_client import DBAASPClient
from agents.research.chembl_client import ChEMBLClient
from agents.research.rcsb_pdb_client import RCSBPDBClient
from agents.research.ebi_proteins_client import EBIProteinsClient
from agents.research.apd_client import APDClient
from agents.research.who_ictrp_client import WHOICTRPClient
from agents.research.iuphar_client import IUPHARClient
from agents.research.pdbe_client import PDBEClient
from agents.research.openalex_client import OpenAlexClient
from agents.research.semantic_scholar_client import SemanticScholarClient
from agents.research.crossref_client import CrossRefClient
from agents.research.biorxiv_client import BioRxivClient
# v42.7.0 (2026-04-25): two new free research APIs targeting outcome/RfF gap.
# SEC EDGAR surfaces sponsor-disclosed trial failures from 10-K/10-Q/8-K
# filings (closes the GT/registry divergence we saw in Job #83 — humans
# knew the trial failed because they read the press release, EDGAR is
# that press release as a primary source). FDA Drugs@FDA gives structured
# regulatory-approval evidence with application numbers, approval letters,
# and dates — strengthens the v42.6.14 "FDA approved" strong-efficacy gate.
from agents.research.sec_edgar_client import SECEdgarClient
from agents.research.fda_drugs_client import FDADrugsClient
# v42.7.6 (2026-04-26): NIH RePORTER federal-grants index. Orthogonal to
# SEC EDGAR (private sponsor) and FDA Drugs (regulator). A drug with NIH
# grant funding is the subject of academic/federally-funded research;
# project end dates without renewals are a weak discontinuation signal.
from agents.research.nih_reporter_client import NIHRePORTERClient
# v42.8.4 (2026-05-07) Lever 4: PubChem + RxNorm drug-code resolver.
# Resolves pharma codes (PLG0206 → WLBU2, CBX129801 → C-Peptide) so
# UniProt / DRAMP / ChEMBL queries downstream actually find the
# biological entity. Slice-H sequence accuracy 1/9 = 11.1% was
# directly caused by these codes returning no_structured_match.
from agents.research.drug_code_resolver import DrugCodeResolverAgent
# v42.8.5 (2026-05-07) Lever 5: sponsor press-release / news-aggregator
# agent. Surfaces trial-readout reporting that doesn't reach
# peer-reviewed literature within Phase I trial timelines via Google
# News RSS (aggregates PR Newswire, BusinessWire, sponsor newsrooms,
# trade pubs). Targets the dominant outcome miss class (positive→
# unknown) on the recent NCT05+ cohort where literature is sparse.
from agents.research.press_release_client import PressReleaseAgent

RESEARCH_AGENTS = {
    "clinical_protocol": ClinicalProtocolAgent,
    "literature": LiteratureAgent,
    "peptide_identity": PeptideIdentityAgent,
    "web_context": WebContextAgent,
    "dbaasp": DBAASPClient,
    "chembl": ChEMBLClient,
    "rcsb_pdb": RCSBPDBClient,
    "ebi_proteins": EBIProteinsClient,
    "apd": APDClient,
    "who_ictrp": WHOICTRPClient,
    "iuphar": IUPHARClient,
    "pdbe": PDBEClient,
    "openalex": OpenAlexClient,
    "semantic_scholar": SemanticScholarClient,
    "crossref": CrossRefClient,
    # v42 Phase 6: preprint server coverage for the Cat 1 evidence gaps
    # identified in the 94-NCT shadow run. Queries Europe PMC's SRC:PPR
    # corpus (bioRxiv + medRxiv + smaller preprint servers).
    "biorxiv": BioRxivClient,
    # v42.7.0: regulatory + sponsor disclosure evidence
    "sec_edgar": SECEdgarClient,
    "fda_drugs": FDADrugsClient,
    # v42.7.6: federal-grants funding context
    "nih_reporter": NIHRePORTERClient,
    # v42.8.4: drug-code → biological-name resolution
    "drug_code_resolver": DrugCodeResolverAgent,
    # v42.8.5: trial-readout press releases via Google News RSS
    "press_release": PressReleaseAgent,
}
