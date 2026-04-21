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
}
