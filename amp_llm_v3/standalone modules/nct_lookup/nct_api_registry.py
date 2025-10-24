"""
NCT API Registry - Central Configuration for All Data Sources
=============================================================

This registry defines all available APIs and their metadata.
Adding a new API is as simple as adding an entry here and creating a client class.

Each API entry defines:
- id: Unique identifier (used in code)
- name: Display name (used in UI)
- description: Brief description for UI tooltips
- category: 'core' (always enabled) or 'extended' (optional)
- requires_key: Whether API key is needed
- client_class: Name of the client class to instantiate
- enabled_by_default: Whether to enable in UI by default
"""

from typing import List, Dict, Any, Optional
from dataclasses import dataclass, field


@dataclass
class APIDefinition:
    """Definition of a single API source."""
    id: str
    name: str
    description: str
    category: str  # 'core' or 'extended'
    requires_key: bool = False
    client_class: str = ""
    enabled_by_default: bool = False
    config: Dict[str, Any] = field(default_factory=dict)


class APIRegistry:
    """
    Central registry for all API sources.
    
    To add a new API:
    1. Add an APIDefinition entry below
    2. Create a client class in nct_clients.py
    3. Register the client in nct_core.py's _initialize_clients()
    4. That's it! UI will automatically update.
    """
    
    # Core APIs (always enabled, foundational data)
    CORE_APIS = [
        APIDefinition(
            id="clinicaltrials",
            name="ClinicalTrials.gov",
            description="Primary trial registry with comprehensive trial information",
            category="core",
            client_class="ClinicalTrialsClient",
            enabled_by_default=True
        ),
        APIDefinition(
            id="pubmed",
            name="PubMed",
            description="Biomedical literature database for published research",
            category="core",
            client_class="PubMedClient",
            enabled_by_default=True
        ),
        APIDefinition(
            id="pmc",
            name="PubMed Central",
            description="Free full-text archive of biomedical literature",
            category="core",
            client_class="PMCClient",
            enabled_by_default=True
        ),
        APIDefinition(
            id="pmc_bioc",
            name="PMC BioC (PubTator3)",
            description="Full-text articles with entity annotations via PubTator3",
            category="core",
            client_class="PMCBioClient",
            enabled_by_default=True
        ),
    ]
    
    # Extended APIs (optional, additional sources)
    EXTENDED_APIS = [
        APIDefinition(
            id="duckduckgo",
            name="DuckDuckGo Search",
            description="Web search for additional trial-related content",
            category="extended",
            client_class="DuckDuckGoClient",
            enabled_by_default=True
        ),
        APIDefinition(
            id="serpapi",
            name="Google Search (SERP API)",
            description="Google search results for comprehensive web coverage",
            category="extended",
            requires_key=True,
            client_class="SerpAPIClient",
            enabled_by_default=False,
            config={"env_var": "SERPAPI_KEY"}
        ),
        APIDefinition(
            id="scholar",
            name="Google Scholar",
            description="Academic papers and citations",
            category="extended",
            requires_key=True,
            client_class="GoogleScholarClient",
            enabled_by_default=False,
            config={"env_var": "SERPAPI_KEY"}
        ),
        APIDefinition(
            id="openfda",
            name="OpenFDA",
            description="FDA drug labels and adverse events",
            category="extended",
            client_class="OpenFDAClient",
            enabled_by_default=True
        ),
        # Example of how to add more APIs:
        # APIDefinition(
        #     id="eudract",
        #     name="EU Clinical Trials Register",
        #     description="European clinical trial database",
        #     category="extended",
        #     client_class="EudraCTClient",
        #     enabled_by_default=True
        # ),
        # APIDefinition(
        #     id="who_ictrp",
        #     name="WHO ICTRP",
        #     description="International Clinical Trials Registry Platform",
        #     category="extended",
        #     client_class="WHOICTRPClient",
        #     enabled_by_default=True
        # ),
    ]
    
    @classmethod
    def get_all_apis(cls) -> List[APIDefinition]:
        """Get all registered APIs (core + extended)."""
        return cls.CORE_APIS + cls.EXTENDED_APIS
    
    @classmethod
    def get_core_apis(cls) -> List[APIDefinition]:
        """Get only core APIs."""
        return cls.CORE_APIS
    
    @classmethod
    def get_extended_apis(cls) -> List[APIDefinition]:
        """Get only extended APIs."""
        return cls.EXTENDED_APIS
    
    @classmethod
    def get_api_by_id(cls, api_id: str) -> Optional[APIDefinition]:
        """Get API definition by ID."""
        for api in cls.get_all_apis():
            if api.id == api_id:
                return api
        return None
    
    @classmethod
    def get_api_categories(cls) -> Dict[str, List[APIDefinition]]:
        """Get APIs grouped by category."""
        return {
            "core": cls.CORE_APIS,
            "extended": cls.EXTENDED_APIS
        }
    
    @classmethod
    def get_default_enabled_apis(cls) -> List[str]:
        """Get IDs of APIs that should be enabled by default."""
        return [api.id for api in cls.get_all_apis() if api.enabled_by_default]
    
    @classmethod
    def get_apis_requiring_keys(cls) -> List[APIDefinition]:
        """Get APIs that require API keys."""
        return [api for api in cls.get_all_apis() if api.requires_key]
    
    @classmethod
    def validate_api_ids(cls, api_ids: List[str]) -> tuple[List[str], List[str]]:
        """
        Validate a list of API IDs.
        
        Returns:
            Tuple of (valid_ids, invalid_ids)
        """
        all_valid_ids = {api.id for api in cls.get_all_apis()}
        valid = [id for id in api_ids if id in all_valid_ids]
        invalid = [id for id in api_ids if id not in all_valid_ids]
        return valid, invalid
    
    @classmethod
    def to_dict(cls) -> Dict[str, Any]:
        """Export registry as dictionary for API responses."""
        return {
            "core": [
                {
                    "id": api.id,
                    "name": api.name,
                    "description": api.description,
                    "requires_key": api.requires_key,
                    "enabled_by_default": api.enabled_by_default
                }
                for api in cls.CORE_APIS
            ],
            "extended": [
                {
                    "id": api.id,
                    "name": api.name,
                    "description": api.description,
                    "requires_key": api.requires_key,
                    "enabled_by_default": api.enabled_by_default
                }
                for api in cls.EXTENDED_APIS
            ]
        }


# Convenience function for external use
def get_api_registry() -> APIRegistry:
    """Get the API registry instance."""
    return APIRegistry