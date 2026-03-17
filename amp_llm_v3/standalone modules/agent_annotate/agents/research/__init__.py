"""
Research agents registry.
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
from agents.research.dbamp_client import DbAMPClient
from agents.research.who_ictrp_client import WHOICTRPClient
from agents.research.iuphar_client import IUPHARClient
from agents.research.intact_client import IntActClient
from agents.research.card_client import CARDClient
from agents.research.pdbe_client import PDBEClient

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
    "dbamp": DbAMPClient,
    "who_ictrp": WHOICTRPClient,
    "iuphar": IUPHARClient,
    "intact": IntActClient,
    "card": CARDClient,
    "pdbe": PDBEClient,
}
