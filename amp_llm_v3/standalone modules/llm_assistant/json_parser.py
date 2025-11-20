"""
Clinical Trial Annotation Parser
Extracts relevant information from ClinicalTrials.gov JSON data for LLM annotation.

Annotation fields:
- Classification: AMP or Other
- Delivery Mode: Injection/Infusion, Topical, Oral, Other
- Outcome: Positive, Withdrawn, Terminated, Failed - completed trial, Active, Unknown
- Reason for Failure: Business reasons, Ineffective for purpose, Toxic/unsafe, Due to covid, Recruitment issues
- Peptide: True or False
"""

import json
from typing import Dict, Any, List, Optional


class ClinicalTrialAnnotationParser:
    """Parser for extracting annotation-relevant data from clinical trial JSON."""
    
    def __init__(self, json_file_path: str):
        """
        Initialize parser with JSON file path.
        
        Args:
            json_file_path: Path to the clinical trial JSON file
        """
        with open(json_file_path, 'r', encoding='utf-8') as f:
            self.data = json.load(f)
        
        # Handle both single trial and list of trials
        if isinstance(self.data, list):
            self.trials = self.data
        else:
            self.trials = [self.data]
    
    def safe_get(self, dictionary: Dict, *keys, default="Not available") -> Any:
        """Safely navigate nested dictionary keys."""
        current = dictionary
        for key in keys:
            if isinstance(current, dict) and key in current:
                current = current[key]
            else:
                return default
        return current if current is not None else default
    
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
        protocol = self.safe_get(trial, 'sources', 'clinical_trials', 'data', 'protocolSection', default={})
        
        info = {

        }
        
        # Extract intervention information
        arms_interventions = self.safe_get(protocol, 'armsInterventionsModule', default={})
        interventions = arms_interventions.get('interventions', [])
        info['interventions'] = []
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
        protocol = self.safe_get(trial, 'sources', 'clinical_trials', 'data', 'protocolSection', default={})
        
        info = {
            'nct_id': self.safe_get(trial, 'nct_id'),
            'brief_title': self.safe_get(protocol, 'identificationModule', 'briefTitle'),
        }
        
        # Extract detailed intervention information
        arms_interventions = self.safe_get(protocol, 'armsInterventionsModule', default={})
        interventions = arms_interventions.get('interventions', [])
        info['interventions'] = []
        for intervention in interventions:
            info['interventions'].append({
                'type': intervention.get('type', 'Not specified'),
                'name': intervention.get('name', 'Not specified'),
                'description': intervention.get('description', 'Not specified')
            })
        
        # Extract arm group information for administration details
        arm_groups = arms_interventions.get('armGroups', [])
        info['arm_groups'] = []
        for arm in arm_groups:
            info['arm_groups'].append({
                'label': arm.get('label', 'Not specified'),
                'type': arm.get('type', 'Not specified'),
                'description': arm.get('description', 'Not specified')
            })
        
        # Include brief summary and detailed description as they often mention route
        info['brief_summary'] = self.safe_get(protocol, 'descriptionModule', 'briefSummary')
        info['detailed_description'] = self.safe_get(protocol, 'descriptionModule', 'detailedDescription')
        
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
        protocol = self.safe_get(trial, 'sources', 'clinical_trials', 'data', 'protocolSection', default={})
        derived = self.safe_get(trial, 'sources', 'clinical_trials', 'data', 'derivedSection', default={})
        
        status_module = self.safe_get(protocol, 'statusModule', default={})
        
        info = {
            'nct_id': self.safe_get(trial, 'nct_id'),
            'brief_title': self.safe_get(protocol, 'identificationModule', 'briefTitle'),
            'overall_status': status_module.get('overallStatus', 'Not available'),
            'status_verified_date': status_module.get('statusVerifiedDate', 'Not available'),
            'why_stopped': status_module.get('whyStopped', 'Not available'),
            'start_date': self.safe_get(status_module, 'startDateStruct', 'date'),
            'completion_date': self.safe_get(status_module, 'completionDateStruct', 'date'),
            'primary_completion_date': self.safe_get(status_module, 'primaryCompletionDateStruct', 'date'),
            'has_results': self.safe_get(trial, 'sources', 'clinical_trials', 'data', 'hasResults'),
        }
        
        # Extract outcome measures
        outcomes_module = self.safe_get(protocol, 'outcomesModule', default={})
        info['primary_outcomes'] = []
        for outcome in outcomes_module.get('primaryOutcomes', []):
            info['primary_outcomes'].append({
                'measure': outcome.get('measure', 'Not specified'),
                'description': outcome.get('description', 'Not specified'),
                'timeFrame': outcome.get('timeFrame', 'Not specified')
            })
        
        info['secondary_outcomes'] = []
        for outcome in outcomes_module.get('secondaryOutcomes', []):
            info['secondary_outcomes'].append({
                'measure': outcome.get('measure', 'Not specified'),
                'description': outcome.get('description', 'Not specified'),
                'timeFrame': outcome.get('timeFrame', 'Not specified')
            })
        
        # Include condition information
        info['conditions'] = self.safe_get(protocol, 'conditionsModule', 'conditions', default=[])
        
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
        protocol = self.safe_get(trial, 'sources', 'clinical_trials', 'data', 'protocolSection', default={})
        status_module = self.safe_get(protocol, 'statusModule', default={})
        
        info = {
            'nct_id': self.safe_get(trial, 'nct_id'),
            'brief_title': self.safe_get(protocol, 'identificationModule', 'briefTitle'),
            'overall_status': status_module.get('overallStatus', 'Not available'),
            'why_stopped': status_module.get('whyStopped', 'Not available'),
            'start_date': self.safe_get(status_module, 'startDateStruct', 'date'),
            'completion_date': self.safe_get(status_module, 'completionDateStruct', 'date'),
            'primary_completion_date': self.safe_get(status_module, 'primaryCompletionDateStruct', 'date'),
        }
        
        # Enrollment information can indicate recruitment issues
        design_module = self.safe_get(protocol, 'designModule', default={})
        enrollment_info = design_module.get('enrollmentInfo', {})
        info['enrollment_count'] = enrollment_info.get('count', 'Not available')
        info['enrollment_type'] = enrollment_info.get('type', 'Not available')
        
        # Extract adverse events if available
        # Note: Adverse events are typically in results section
        results_section = self.safe_get(trial, 'sources', 'clinical_trials', 'data', 'resultsSection', default={})
        adverse_events = results_section.get('adverseEventsModule', {})
        info['serious_events'] = adverse_events.get('seriousEvents', 'Not available')
        info['other_events'] = adverse_events.get('otherEvents', 'Not available')
        
        return info
    
    def extract_peptide_info(self, trial: Dict) -> Dict[str, Any]:
        """
        Extract information relevant for Peptide determination.
        
        Relevant factors:
        - Intervention names and descriptions
        - Keywords
        - Conditions
        - Brief and detailed descriptions
        - Chemical/biological terminology
        """
        protocol = self.safe_get(trial, 'sources', 'clinical_trials', 'data', 'protocolSection', default={})
        
        info = {
            'nct_id': self.safe_get(trial, 'nct_id'),
            'brief_title': self.safe_get(protocol, 'identificationModule', 'briefTitle'),
            'official_title': self.safe_get(protocol, 'identificationModule', 'officialTitle'),
            'keywords': self.safe_get(protocol, 'conditionsModule', 'keywords', default=[]),
            'conditions': self.safe_get(protocol, 'conditionsModule', 'conditions', default=[]),
            'brief_summary': self.safe_get(protocol, 'descriptionModule', 'briefSummary'),
            'detailed_description': self.safe_get(protocol, 'descriptionModule', 'detailedDescription'),
        }
        
        # Extract intervention information with detailed descriptions
        arms_interventions = self.safe_get(protocol, 'armsInterventionsModule', default={})
        interventions = arms_interventions.get('interventions', [])
        info['interventions'] = []
        for intervention in interventions:
            info['interventions'].append({
                'type': intervention.get('type', 'Not specified'),
                'name': intervention.get('name', 'Not specified'),
                'description': intervention.get('description', 'Not specified'),
                'other_names': intervention.get('otherNames', [])
            })
        
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
        if 'brief_title' in info_dict:
            lines.append(f"Brief Title: {info_dict['brief_title']}")
            lines.append("")
        
        if 'official_title' in info_dict:
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


def main():
    """Example usage of the parser."""
    import sys
    
    if len(sys.argv) < 2:
        print("Usage: python ct_annotation_parser.py <json_file_path> [output_dir] [trial_index]")
        sys.exit(1)
    
    json_file = sys.argv[1]
    output_dir = sys.argv[2] if len(sys.argv) > 2 else './annotation_outputs'
    trial_index = int(sys.argv[3]) if len(sys.argv) > 3 else 0
    
    # Create parser
    parser = ClinicalTrialAnnotationParser(json_file)
    
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