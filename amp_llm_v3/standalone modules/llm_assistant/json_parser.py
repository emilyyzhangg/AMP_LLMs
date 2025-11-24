"""
Clinical Trial Annotation Parser
================================

Extracts relevant information from ClinicalTrials.gov JSON data for LLM annotation.

Annotation fields:
- Classification: AMP or Other
- Delivery Mode: Injection/Infusion, Topical, Oral, Other
- Outcome: Positive, Withdrawn, Terminated, Failed - completed trial, Active, Unknown
- Reason for Failure: Business reasons, Ineffective for purpose, Toxic/unsafe, Due to covid, Recruitment issues
- Peptide: True or False

Usage:
    # From file
    parser = ClinicalTrialAnnotationParser.from_file("path/to/trial.json")
    
    # From dictionary
    parser = ClinicalTrialAnnotationParser.from_dict(trial_data)
    
    # Get combined annotation text
    text = parser.get_combined_annotation_text()
"""

import json
from typing import Dict, Any, List, Optional, Union
from pathlib import Path


class ClinicalTrialAnnotationParser:
    """Parser for extracting annotation-relevant data from clinical trial JSON."""
    
    def __init__(self, trials: List[Dict[str, Any]]):
        """
        Initialize parser with trial data.
        
        Args:
            trials: List of trial dictionaries
        """
        self.trials = trials
    
    @classmethod
    def from_file(cls, json_file_path: Union[str, Path]) -> 'ClinicalTrialAnnotationParser':
        """
        Create parser from JSON file path.
        
        Args:
            json_file_path: Path to the clinical trial JSON file
            
        Returns:
            ClinicalTrialAnnotationParser instance
        """
        with open(json_file_path, 'r', encoding='utf-8') as f:
            data = json.load(f)
        
        # Handle both single trial and list of trials
        if isinstance(data, list):
            trials = data
        else:
            trials = [data]
        
        return cls(trials)
    
    @classmethod
    def from_dict(cls, data: Union[Dict[str, Any], List[Dict[str, Any]]]) -> 'ClinicalTrialAnnotationParser':
        """
        Create parser from dictionary or list of dictionaries.
        
        Args:
            data: Trial data dictionary or list of trial dictionaries
            
        Returns:
            ClinicalTrialAnnotationParser instance
        """
        if isinstance(data, list):
            trials = data
        else:
            trials = [data]
        
        return cls(trials)
    
    def safe_get(self, dictionary: Dict, *keys, default="Not available") -> Any:
        """Safely navigate nested dictionary keys."""
        current = dictionary
        for key in keys:
            if isinstance(current, dict) and key in current:
                current = current[key]
            else:
                return default
        return current if current is not None else default
    
    def _get_protocol_section(self, trial: Dict) -> Dict:
        """Get the protocol section from trial data, handling different data structures."""
        # Try standard path
        protocol = self.safe_get(
            trial, 
            'sources', 'clinical_trials', 'data', 'protocolSection',
            default={}
        )
        
        if not protocol:
            # Try alternate path (clinicaltrials vs clinical_trials)
            protocol = self.safe_get(
                trial,
                'sources', 'clinicaltrials', 'data', 'protocolSection',
                default={}
            )
        
        if not protocol:
            # Try direct path (if trial is the protocol section itself)
            protocol = self.safe_get(trial, 'protocolSection', default={})
        
        return protocol if isinstance(protocol, dict) else {}
    
    def extract_classification_info(self, trial: Dict) -> Dict[str, Any]:
        """
        Extract information relevant for Classification (AMP vs Other).
        
        Relevant factors:
        - Study type and phase
        - Conditions being treated
        - Keywords mentioning antimicrobial
        - Brief and detailed descriptions
        - Intervention descriptions
        """
        protocol = self._get_protocol_section(trial)
        
        id_module = self.safe_get(protocol, 'identificationModule', default={})
        desc_module = self.safe_get(protocol, 'descriptionModule', default={})
        conditions_module = self.safe_get(protocol, 'conditionsModule', default={})
        design_module = self.safe_get(protocol, 'designModule', default={})
        arms_interventions = self.safe_get(protocol, 'armsInterventionsModule', default={})
        
        info = {
            'nct_id': trial.get('nct_id', self.safe_get(id_module, 'nctId')),
            'brief_title': id_module.get('briefTitle', 'Not available'),
            'official_title': id_module.get('officialTitle', 'Not available'),
            'brief_summary': desc_module.get('briefSummary', 'Not available'),
            'detailed_description': desc_module.get('detailedDescription', 'Not available'),
            'conditions': conditions_module.get('conditions', []),
            'keywords': conditions_module.get('keywords', []),
            'study_type': design_module.get('studyType', 'Not available'),
            'phases': design_module.get('phases', []),
            'interventions': []
        }
        
        # Extract intervention information
        interventions = arms_interventions.get('interventions', [])
        for intervention in interventions:
            info['interventions'].append({
                'type': intervention.get('type', 'Not specified'),
                'name': intervention.get('name', 'Not specified'),
                'description': intervention.get('description', 'Not specified')
            })
        
        return info
    
    def extract_delivery_mode_info(self, trial: Dict) -> Dict[str, Any]:
        """
        Extract information relevant for Delivery Mode.
        
        Relevant factors:
        - Intervention types and descriptions
        - Administration routes mentioned in descriptions
        - Arm group descriptions
        """
        protocol = self._get_protocol_section(trial)
        
        id_module = self.safe_get(protocol, 'identificationModule', default={})
        desc_module = self.safe_get(protocol, 'descriptionModule', default={})
        arms_interventions = self.safe_get(protocol, 'armsInterventionsModule', default={})
        
        info = {
            'nct_id': trial.get('nct_id', self.safe_get(id_module, 'nctId')),
            'brief_title': id_module.get('briefTitle', 'Not available'),
            'brief_summary': desc_module.get('briefSummary', 'Not available'),
            'detailed_description': desc_module.get('detailedDescription', 'Not available'),
            'interventions': [],
            'arm_groups': []
        }
        
        # Extract detailed intervention information
        interventions = arms_interventions.get('interventions', [])
        for intervention in interventions:
            info['interventions'].append({
                'type': intervention.get('type', 'Not specified'),
                'name': intervention.get('name', 'Not specified'),
                'description': intervention.get('description', 'Not specified')
            })
        
        # Extract arm group information for administration details
        arm_groups = arms_interventions.get('armGroups', [])
        for arm in arm_groups:
            info['arm_groups'].append({
                'label': arm.get('label', 'Not specified'),
                'type': arm.get('type', 'Not specified'),
                'description': arm.get('description', 'Not specified')
            })
        
        return info
    
    def extract_outcome_info(self, trial: Dict) -> Dict[str, Any]:
        """
        Extract information relevant for Outcome determination.
        
        Relevant factors:
        - Overall status
        - Completion dates
        - Why stopped (if applicable)
        - Study results availability
        - Primary and secondary outcomes
        """
        protocol = self._get_protocol_section(trial)
        
        id_module = self.safe_get(protocol, 'identificationModule', default={})
        status_module = self.safe_get(protocol, 'statusModule', default={})
        outcomes_module = self.safe_get(protocol, 'outcomesModule', default={})
        conditions_module = self.safe_get(protocol, 'conditionsModule', default={})
        
        info = {
            'nct_id': trial.get('nct_id', self.safe_get(id_module, 'nctId')),
            'brief_title': id_module.get('briefTitle', 'Not available'),
            'overall_status': status_module.get('overallStatus', 'Not available'),
            'status_verified_date': status_module.get('statusVerifiedDate', 'Not available'),
            'why_stopped': status_module.get('whyStopped', 'Not available'),
            'start_date': self.safe_get(status_module, 'startDateStruct', 'date'),
            'completion_date': self.safe_get(status_module, 'completionDateStruct', 'date'),
            'primary_completion_date': self.safe_get(status_module, 'primaryCompletionDateStruct', 'date'),
            'has_results': self.safe_get(trial, 'sources', 'clinical_trials', 'data', 'hasResults', default=False),
            'primary_outcomes': [],
            'secondary_outcomes': [],
            'conditions': conditions_module.get('conditions', [])
        }
        
        # Extract outcome measures
        for outcome in outcomes_module.get('primaryOutcomes', []):
            info['primary_outcomes'].append({
                'measure': outcome.get('measure', 'Not specified'),
                'description': outcome.get('description', 'Not specified'),
                'timeFrame': outcome.get('timeFrame', 'Not specified')
            })
        
        for outcome in outcomes_module.get('secondaryOutcomes', []):
            info['secondary_outcomes'].append({
                'measure': outcome.get('measure', 'Not specified'),
                'description': outcome.get('description', 'Not specified'),
                'timeFrame': outcome.get('timeFrame', 'Not specified')
            })
        
        return info
    
    def extract_failure_reason_info(self, trial: Dict) -> Dict[str, Any]:
        """
        Extract information relevant for Reason for Failure.
        
        Relevant factors:
        - Why stopped field
        - Overall status
        - Status descriptions
        - Adverse events (if available)
        - Completion information
        """
        protocol = self._get_protocol_section(trial)
        
        id_module = self.safe_get(protocol, 'identificationModule', default={})
        status_module = self.safe_get(protocol, 'statusModule', default={})
        design_module = self.safe_get(protocol, 'designModule', default={})
        
        enrollment_info = design_module.get('enrollmentInfo', {})
        
        info = {
            'nct_id': trial.get('nct_id', self.safe_get(id_module, 'nctId')),
            'brief_title': id_module.get('briefTitle', 'Not available'),
            'overall_status': status_module.get('overallStatus', 'Not available'),
            'why_stopped': status_module.get('whyStopped', 'Not available'),
            'start_date': self.safe_get(status_module, 'startDateStruct', 'date'),
            'completion_date': self.safe_get(status_module, 'completionDateStruct', 'date'),
            'primary_completion_date': self.safe_get(status_module, 'primaryCompletionDateStruct', 'date'),
            'enrollment_count': enrollment_info.get('count', 'Not available'),
            'enrollment_type': enrollment_info.get('type', 'Not available')
        }
        
        return info
    
    def extract_peptide_info(self, trial: Dict) -> Dict[str, Any]:
        """
        Extract information relevant for Peptide determination.
        
        Relevant factors:
        - Intervention names and descriptions
        - Drug/treatment details
        - Keywords mentioning peptide
        - PubMed/PMC references
        - DRAMP database matches
        """
        protocol = self._get_protocol_section(trial)
        
        id_module = self.safe_get(protocol, 'identificationModule', default={})
        desc_module = self.safe_get(protocol, 'descriptionModule', default={})
        conditions_module = self.safe_get(protocol, 'conditionsModule', default={})
        arms_interventions = self.safe_get(protocol, 'armsInterventionsModule', default={})
        
        info = {
            'nct_id': trial.get('nct_id', self.safe_get(id_module, 'nctId')),
            'brief_title': id_module.get('briefTitle', 'Not available'),
            'official_title': id_module.get('officialTitle', 'Not available'),
            'brief_summary': desc_module.get('briefSummary', 'Not available'),
            'conditions': conditions_module.get('conditions', []),
            'keywords': conditions_module.get('keywords', []),
            'interventions': []
        }
        
        # Extract intervention information
        interventions = arms_interventions.get('interventions', [])
        for intervention in interventions:
            info['interventions'].append({
                'type': intervention.get('type', 'Not specified'),
                'name': intervention.get('name', 'Not specified'),
                'description': intervention.get('description', 'Not specified')
            })
        
        # Add external data sources if available
        sources = trial.get('sources', {})
        
        # PubMed data
        pubmed_data = sources.get('pubmed', {})
        if pubmed_data.get('success'):
            pmids = pubmed_data.get('data', {}).get('pmids', [])
            if pmids:
                info['pubmed_pmids'] = pmids
        
        # PMC data
        pmc_data = sources.get('pmc', {})
        if pmc_data.get('success'):
            pmcids = pmc_data.get('data', {}).get('pmcids', [])
            if pmcids:
                info['pmc_ids'] = pmcids
        
        # PMC BioC data
        pmc_bioc = sources.get('pmc_bioc', {})
        if pmc_bioc.get('success'):
            bioc_data = pmc_bioc.get('data', {})
            info['bioc_data'] = {
                'total_fetched': bioc_data.get('total_fetched', 0),
                'articles': len(bioc_data.get('articles', []))
            }
        
        return info
    
    def format_as_text(self, info_dict: Dict[str, Any], field_name: str) -> str:
        """
        Format extracted information as human-readable text.
        
        Args:
            info_dict: Dictionary containing extracted information
            field_name: Name of the annotation field
            
        Returns:
            Formatted text string
        """
        lines = [
            f"=" * 80,
            f"CLINICAL TRIAL ANNOTATION: {field_name.upper()}",
            f"=" * 80,
            f"NCT ID: {info_dict.get('nct_id', 'Not available')}",
            ""
        ]
        
        # Add title if available
        if 'brief_title' in info_dict and info_dict['brief_title'] != 'Not available':
            lines.append(f"Brief Title: {info_dict['brief_title']}")
            lines.append("")
        
        if 'official_title' in info_dict and info_dict['official_title'] != 'Not available':
            lines.append(f"Official Title: {info_dict['official_title']}")
            lines.append("")
        
        # Format different fields based on type
        for key, value in info_dict.items():
            if key in ['nct_id', 'brief_title', 'official_title']:
                continue  # Already added
            
            if value == "Not available" or value == [] or value == {}:
                continue  # Skip empty fields
            
            if isinstance(value, list):
                if value:  # Only show if not empty
                    lines.append(f"{key.replace('_', ' ').title()}:")
                    for item in value:
                        if isinstance(item, dict):
                            lines.append(f"  - {json.dumps(item, indent=4)}")
                        else:
                            lines.append(f"  - {item}")
                    lines.append("")
            elif isinstance(value, dict):
                if value:  # Only show if not empty
                    lines.append(f"{key.replace('_', ' ').title()}:")
                    lines.append(f"  {json.dumps(value, indent=2)}")
                    lines.append("")
            else:
                lines.append(f"{key.replace('_', ' ').title()}: {value}")
                lines.append("")
        
        lines.append("=" * 80)
        lines.append("")
        
        return "\n".join(lines)
    
    def generate_annotation_text(self, trial_index: int = 0) -> Dict[str, str]:
        """
        Generate all annotation texts for a specific trial.
        
        Args:
            trial_index: Index of the trial in the list (default: 0)
            
        Returns:
            Dictionary with annotation field names as keys and formatted text as values
        """
        if trial_index >= len(self.trials):
            raise IndexError(f"Trial index {trial_index} out of range. Only {len(self.trials)} trials available.")
        
        trial = self.trials[trial_index]
        
        annotation_texts = {
            'classification': self.format_as_text(
                self.extract_classification_info(trial),
                'Classification'
            ),
            'delivery_mode': self.format_as_text(
                self.extract_delivery_mode_info(trial),
                'Delivery Mode'
            ),
            'outcome': self.format_as_text(
                self.extract_outcome_info(trial),
                'Outcome'
            ),
            'failure_reason': self.format_as_text(
                self.extract_failure_reason_info(trial),
                'Reason for Failure'
            ),
            'peptide': self.format_as_text(
                self.extract_peptide_info(trial),
                'Peptide'
            )
        }
        
        return annotation_texts
    
    def get_combined_annotation_text(self, trial_index: int = 0) -> str:
        """
        Get all annotation fields combined into a single text for LLM processing.
        
        Args:
            trial_index: Index of the trial to process
            
        Returns:
            Combined text with all annotation fields
        """
        annotation_texts = self.generate_annotation_text(trial_index)
        
        combined = [
            "=" * 80,
            "CLINICAL TRIAL ANNOTATION REQUEST",
            "=" * 80,
            "",
            "Please annotate this clinical trial with the following fields:",
            "",
            "**Classification:** AMP or Other",
            "**Delivery Mode:** Injection/Infusion, Topical, Oral, or Other",
            "**Outcome:** Positive, Withdrawn, Terminated, Failed - completed trial, Active, or Unknown",
            "**Reason for Failure:** Business reasons, Ineffective for purpose, Toxic/unsafe, Due to covid, Recruitment issues, or N/A",
            "**Peptide:** True or False",
            "",
            "=" * 80,
            "",
        ]
        
        # Add each annotation field's relevant information
        for field_name in ['classification', 'delivery_mode', 'outcome', 'failure_reason', 'peptide']:
            combined.append(annotation_texts[field_name])
            combined.append("")
        
        return "\n".join(combined)
    
    def get_extracted_info(self, trial_index: int = 0) -> Dict[str, Dict[str, Any]]:
        """
        Get all extracted information as dictionaries (not formatted text).
        
        Args:
            trial_index: Index of the trial to process
            
        Returns:
            Dictionary with field names as keys and extracted info dicts as values
        """
        if trial_index >= len(self.trials):
            raise IndexError(f"Trial index {trial_index} out of range.")
        
        trial = self.trials[trial_index]
        
        return {
            'classification': self.extract_classification_info(trial),
            'delivery_mode': self.extract_delivery_mode_info(trial),
            'outcome': self.extract_outcome_info(trial),
            'failure_reason': self.extract_failure_reason_info(trial),
            'peptide': self.extract_peptide_info(trial)
        }
    
    def save_annotation_texts(self, output_dir: str = '.', trial_index: int = 0):
        """
        Save all annotation texts to separate files.
        
        Args:
            output_dir: Directory to save the files
            trial_index: Index of the trial to process
        """
        import os
        
        os.makedirs(output_dir, exist_ok=True)
        
        annotation_texts = self.generate_annotation_text(trial_index)
        nct_id = self.trials[trial_index].get('nct_id', f'trial_{trial_index}')
        
        for field_name, text in annotation_texts.items():
            filename = f"{nct_id}_{field_name}.txt"
            filepath = os.path.join(output_dir, filename)
            
            with open(filepath, 'w', encoding='utf-8') as f:
                f.write(text)
            
            print(f"Saved: {filepath}")


def main():
    """Example usage of the parser."""
    import sys
    
    if len(sys.argv) < 2:
        print("Usage: python json_parser.py <json_file_path> [output_dir] [trial_index]")
        print("\nExamples:")
        print("  python json_parser.py NCT12345678.json")
        print("  python json_parser.py NCT12345678.json ./output 0")
        sys.exit(1)
    
    json_file = sys.argv[1]
    output_dir = sys.argv[2] if len(sys.argv) > 2 else './annotation_outputs'
    trial_index = int(sys.argv[3]) if len(sys.argv) > 3 else 0
    
    # Create parser from file
    parser = ClinicalTrialAnnotationParser.from_file(json_file)
    
    print(f"Loaded {len(parser.trials)} trial(s) from {json_file}")
    print(f"Processing trial index {trial_index}")
    print()
    
    # Save individual annotation texts
    parser.save_annotation_texts(output_dir, trial_index)
    
    # Also create a combined file for LLM
    combined_text = parser.get_combined_annotation_text(trial_index)
    nct_id = parser.trials[trial_index].get('nct_id', f'trial_{trial_index}')
    combined_filepath = f"{output_dir}/{nct_id}_combined_annotation.txt"
    
    with open(combined_filepath, 'w', encoding='utf-8') as f:
        f.write(combined_text)
    
    print(f"\nSaved combined annotation text: {combined_filepath}")
    print("\nYou can now pass this combined text to your LLM for annotation!")


if __name__ == '__main__':
    main()