"""
NCT Search Combination Generator
=================================

Generates all possible search combinations for Step 2 extended API searches.
Handles multiple values per field and creates all permutations.
"""

from typing import Dict, List, Any, Tuple
from itertools import product
import logging

logger = logging.getLogger(__name__)


class SearchCombinationGenerator:
    """
    Generates search combinations for Step 2 extended API searches.
    
    Example:
        Input: {
            "title": ["Drug X Effect"],
            "intervention": ["Drug X", "Drug Y"],
            "condition": ["Cancer"]
        }
        
        Output: [
            {"title": "Drug X Effect", "intervention": "Drug X", "condition": "Cancer"},
            {"title": "Drug X Effect", "intervention": "Drug Y", "condition": "Cancer"}
        ]
    """
    
    @staticmethod
    def generate_combinations(
        search_fields: Dict[str, List[str]]
    ) -> List[Dict[str, str]]:
        """
        Generate all combinations of search field values.
        
        Args:
            search_fields: Dictionary mapping field names to lists of values
                Example: {
                    "title": ["Study of Drug X"],
                    "intervention": ["Drug X", "Drug Y"]
                }
        
        Returns:
            List of dictionaries, each representing one search combination
        """
        if not search_fields:
            return []
        
        # Filter out empty fields
        valid_fields = {
            field: values 
            for field, values in search_fields.items() 
            if values and any(v for v in values)
        }
        
        if not valid_fields:
            logger.warning("No valid search fields provided")
            return []
        
        # Get field names and their value lists
        field_names = list(valid_fields.keys())
        value_lists = [valid_fields[field] for field in field_names]
        
        # Generate all combinations using itertools.product
        combinations = []
        for value_combo in product(*value_lists):
            combination = dict(zip(field_names, value_combo))
            # Only include non-empty combinations
            if any(v for v in combination.values()):
                combinations.append(combination)
        
        logger.info(f"Generated {len(combinations)} search combinations from {len(field_names)} fields")
        
        return combinations
    
    @staticmethod
    def generate_single_field_searches(
        search_fields: Dict[str, List[str]]
    ) -> List[Tuple[str, str]]:
        """
        Generate individual searches for each field value (no combinations).
        
        Args:
            search_fields: Dictionary mapping field names to lists of values
        
        Returns:
            List of tuples (field_name, value)
        """
        searches = []
        
        for field_name, values in search_fields.items():
            if not values:
                continue
            
            for value in values:
                if value and str(value).strip():
                    searches.append((field_name, str(value).strip()))
        
        logger.info(f"Generated {len(searches)} individual field searches")
        
        return searches
    
    @staticmethod
    def build_search_query(
        combination: Dict[str, str],
        separator: str = " "
    ) -> str:
        """
        Build a search query string from a combination dictionary.
        
        Args:
            combination: Dictionary of field: value pairs
            separator: String to join values with (default: space)
        
        Returns:
            Combined search query string
        """
        values = [str(v) for v in combination.values() if v]
        query = separator.join(values)
        return query.strip()
    
    @staticmethod
    def format_search_description(
        combination: Dict[str, str]
    ) -> str:
        """
        Create a human-readable description of a search combination.
        
        Args:
            combination: Dictionary of field: value pairs
        
        Returns:
            Formatted description string
        """
        parts = []
        for field, value in combination.items():
            if value:
                parts.append(f"{field}='{value}'")
        
        return " AND ".join(parts)
    
    @staticmethod
    def extract_field_values(
        step1_results: Dict[str, Any],
        field_name: str
    ) -> List[str]:
        """
        Extract values for a specific field from Step 1 results.
        
        Args:
            step1_results: Complete Step 1 results dictionary
            field_name: Name of field to extract (e.g., 'title', 'intervention')
        
        Returns:
            List of unique values for that field
        """
        values = set()
        
        # Extract from metadata
        metadata = step1_results.get("metadata", {})
        
        if field_name == "title":
            title = metadata.get("title")
            if title:
                values.add(title)
        
        elif field_name == "nct_id":
            nct_id = step1_results.get("nct_id")
            if nct_id:
                values.add(nct_id)
        
        elif field_name == "condition":
            condition = metadata.get("condition")
            if condition:
                if isinstance(condition, list):
                    values.update(condition)
                else:
                    values.add(condition)
        
        elif field_name == "intervention" or field_name == "intervention_names":
            intervention = metadata.get("intervention")
            if intervention:
                if isinstance(intervention, list):
                    values.update(intervention)
                elif isinstance(intervention, dict):
                    # Extract intervention names from dict
                    names = intervention.get("names", [])
                    values.update(names)
                else:
                    values.add(intervention)
        
        elif field_name == "authors":
            # Extract authors from various sources
            sources = step1_results.get("sources", {})
            
            # From PubMed
            pubmed_data = sources.get("pubmed", {}).get("data", {})
            if isinstance(pubmed_data, dict):
                articles = pubmed_data.get("articles", [])
                for article in articles:
                    authors = article.get("authors", [])
                    values.update(authors[:3])  # Limit to first 3 authors
        
        elif field_name == "pmid" or field_name == "pmids":
            sources = step1_results.get("sources", {})
            pubmed_data = sources.get("pubmed", {}).get("data", {})
            if isinstance(pubmed_data, dict):
                pmids = pubmed_data.get("pmids", [])
                values.update(pmids)
        
        # Convert to list and filter out empty values
        result = [str(v).strip() for v in values if v and str(v).strip()]
        
        logger.debug(f"Extracted {len(result)} values for field '{field_name}'")
        
        return result
    
    @staticmethod
    def create_api_search_plan(
        step1_results: Dict[str, Any],
        selected_apis: List[str],
        field_selections: Dict[str, List[str]]
    ) -> Dict[str, List[Dict[str, Any]]]:
        """
        Create a complete search plan for Step 2.
        
        Args:
            step1_results: Complete Step 1 results
            selected_apis: List of API IDs to search (e.g., ['duckduckgo', 'openfda'])
            field_selections: Dict mapping API IDs to lists of field names to search
                Example: {
                    'duckduckgo': ['title', 'condition'],
                    'openfda': ['intervention_names']
                }
        
        Returns:
            Dictionary mapping API IDs to lists of search configurations
        """
        search_plan = {}
        
        for api_id in selected_apis:
            if api_id not in field_selections:
                logger.warning(f"No field selections for API: {api_id}")
                continue
            
            selected_fields = field_selections[api_id]
            
            # Extract field values from Step 1 results
            field_values = {}
            for field in selected_fields:
                values = SearchCombinationGenerator.extract_field_values(
                    step1_results, field
                )
                if values:
                    field_values[field] = values
            
            if not field_values:
                logger.warning(f"No values found for API {api_id} fields: {selected_fields}")
                continue
            
            # Generate combinations
            combinations = SearchCombinationGenerator.generate_combinations(field_values)
            
            # Create search configurations
            search_configs = []
            for combo in combinations:
                search_configs.append({
                    'fields': combo,
                    'query': SearchCombinationGenerator.build_search_query(combo),
                    'description': SearchCombinationGenerator.format_search_description(combo)
                })
            
            search_plan[api_id] = search_configs
            logger.info(f"Created {len(search_configs)} searches for {api_id}")
        
        return search_plan


# Export convenience function
def generate_step2_searches(
    step1_results: Dict[str, Any],
    selected_apis: List[str],
    field_selections: Dict[str, List[str]]
) -> Dict[str, List[Dict[str, Any]]]:
    """
    Convenience function to generate Step 2 search plan.
    
    Returns:
        Dictionary with search plan for each selected API
    """
    generator = SearchCombinationGenerator()
    return generator.create_api_search_plan(
        step1_results,
        selected_apis,
        field_selections
    )


__all__ = ['SearchCombinationGenerator', 'generate_step2_searches']