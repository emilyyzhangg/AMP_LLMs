"""
Clinical Trial Annotation Parser
================================

Extracts relevant information from ClinicalTrials.gov JSON data for LLM annotation.

Annotation fields:
- Classification: AMP or Other
- Delivery Mode: Injection/Infusion, Topical, Oral, Other
- Outcome: Positive, Withdrawn, Terminated, Failed - completed trial, Active, Unknown
- Reason for Failure: Business reasons, Ineffective for purpose, Toxic/unsafe, Due to covid, Recruitment issues
- Sequence: amino acid sequence of the peptide
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

    # Fields that are critical for annotation decisions
    CRITICAL_FIELDS = {
        'classification': ['brief_title', 'brief_summary', 'interventions'],
        'delivery_mode': ['interventions', 'arm_groups', 'brief_summary'],
        'outcome': ['overall_status', 'why_stopped', 'has_results'],
        'failure_reason': ['overall_status', 'why_stopped'],
        'peptide': ['interventions', 'brief_title', 'keywords'],
        'sequence': ['uniprot_sequences', 'dramp_sequences', 'interventions']
    }

    # Default field weights for quality scoring
    # See QUALITY_SCORES.md for detailed reasoning
    DEFAULT_FIELD_WEIGHTS = {
        'classification': {
            'nct_id': 0.05,
            'brief_title': 0.15,
            'official_title': 0.05,
            'brief_summary': 0.25,
            'detailed_description': 0.10,
            'conditions': 0.15,
            'keywords': 0.10,
            'study_type': 0.05,
            'phases': 0.05,
            'interventions': 0.05  # Lower because it's a list that may be empty
        },
        'delivery_mode': {
            'nct_id': 0.03,
            'brief_title': 0.07,
            'brief_summary': 0.10,
            'detailed_description': 0.08,
            'interventions': 0.30,  # Most important for delivery mode
            'arm_groups': 0.20,
            'derived_intervention_info': 0.07,  # MeSH classifications can help
            'openfda_routes': 0.15  # FDA route data is very reliable when available
        },
        'outcome': {
            'nct_id': 0.02,
            'brief_title': 0.03,
            'overall_status': 0.25,  # Primary determinant
            'status_verified_date': 0.02,
            'why_stopped': 0.10,
            'start_date': 0.02,
            'completion_date': 0.05,
            'primary_completion_date': 0.03,
            'has_results': 0.08,
            'primary_outcomes': 0.03,
            'secondary_outcomes': 0.02,
            # New results section fields
            'results_outcome_measures': 0.15,  # Critical for completed trials
            'results_p_values': 0.10,  # P-values help determine success/failure
            'results_limitations': 0.03,
            'results_adverse_events_summary': 0.04,
            'participant_flow_info': 0.03
        },
        'failure_reason': {
            'nct_id': 0.05,
            'brief_title': 0.05,
            'overall_status': 0.25,
            'why_stopped': 0.45,  # Primary source for failure reason
            'start_date': 0.05,
            'completion_date': 0.05,
            'primary_completion_date': 0.05,
            'enrollment_count': 0.03,
            'enrollment_type': 0.02
        },
        'peptide': {
            'nct_id': 0.05,
            'brief_title': 0.15,
            'official_title': 0.10,
            'brief_summary': 0.20,
            'conditions': 0.10,
            'keywords': 0.15,
            'interventions': 0.25  # Drug name is key for peptide determination
        },
        'sequence': {
            'nct_id': 0.02,
            'brief_title': 0.05,
            'interventions': 0.13,
            'uniprot_sequences': 0.40,  # Primary source for sequence data
            'dramp_sequences': 0.30,    # Secondary source for AMP sequences
            'pubmed_pmids': 0.05,
            'pmc_ids': 0.05
        }
    }

    def __init__(
        self,
        trials: List[Dict[str, Any]],
        field_weights: Optional[Dict[str, Dict[str, float]]] = None
    ):
        """
        Initialize parser with trial data and optional custom quality weights.

        Args:
            trials: List of trial dictionaries
            field_weights: Optional custom weights for quality scoring per field.
                          Structure: {field_name: {data_field: weight, ...}, ...}
                          Weights should sum to 1.0 for each field.
                          If None, uses DEFAULT_FIELD_WEIGHTS.
        """
        self.trials = trials
        self.field_weights = field_weights or self.DEFAULT_FIELD_WEIGHTS.copy()

    @classmethod
    def get_default_weights(cls) -> Dict[str, Dict[str, float]]:
        """
        Get the default field weights for quality scoring.

        Returns:
            Dictionary of default weights that can be modified and passed back.
        """
        import copy
        return copy.deepcopy(cls.DEFAULT_FIELD_WEIGHTS)

    def set_field_weights(self, field_weights: Dict[str, Dict[str, float]]) -> None:
        """
        Update the field weights used for quality scoring.

        Args:
            field_weights: New weights to use. Structure: {field_name: {data_field: weight}}
        """
        self.field_weights = field_weights

    def reset_weights_to_default(self) -> None:
        """Reset field weights to the default values."""
        self.field_weights = self.DEFAULT_FIELD_WEIGHTS.copy()
    
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

    def _is_empty_value(self, value: Any) -> bool:
        """Check if a value is considered empty/unavailable."""
        if value is None:
            return True
        if value == "Not available" or value == "N/A":
            return True
        if isinstance(value, str) and not value.strip():
            return True
        if isinstance(value, (list, dict)) and len(value) == 0:
            return True
        return False

    def validate_extraction(self, info_dict: Dict[str, Any], field_name: str) -> Dict[str, Any]:
        """
        Validate extracted information and identify missing critical fields.

        Args:
            info_dict: Dictionary containing extracted information
            field_name: Name of the annotation field (classification, outcome, etc.)

        Returns:
            Dictionary with validation results:
            - is_sufficient: bool indicating if data is sufficient for annotation
            - missing_fields: list of missing critical fields
            - available_fields: list of available fields with data
            - quality_score: float 0-1 indicating weighted data completeness
            - unweighted_score: float 0-1 simple ratio of available/total fields
            - warnings: list of warning messages
            - weights_used: the weights applied for this field
        """
        critical = self.CRITICAL_FIELDS.get(field_name, [])
        missing = []
        available = []
        warnings = []

        for field in critical:
            value = info_dict.get(field)
            if self._is_empty_value(value):
                missing.append(field)
            else:
                available.append(field)

        # Get weights for this field (or use equal weights if not defined)
        field_weights = self.field_weights.get(field_name, {})

        # Calculate weighted quality score
        weighted_score = 0.0
        total_weight = 0.0

        for data_field, value in info_dict.items():
            weight = field_weights.get(data_field, 0.1)  # Default weight if not specified
            total_weight += weight
            if not self._is_empty_value(value):
                weighted_score += weight

        # Normalize to 0-1 range
        quality_score = weighted_score / total_weight if total_weight > 0 else 0

        # Also calculate simple unweighted score for comparison
        total_fields = len(info_dict)
        non_empty_fields = sum(1 for v in info_dict.values() if not self._is_empty_value(v))
        unweighted_score = non_empty_fields / total_fields if total_fields > 0 else 0

        # Generate warnings
        if len(missing) >= len(critical) // 2 + 1:
            warnings.append(f"More than half of critical fields for {field_name} are missing")

        if quality_score < 0.3:
            warnings.append(f"Very low data quality ({quality_score:.0%}) - LLM annotation may be unreliable")

        # Specific field warnings
        if field_name == 'outcome' and 'overall_status' in missing:
            warnings.append("Overall status is missing - Outcome cannot be determined reliably")
        if field_name == 'peptide' and 'interventions' in missing:
            warnings.append("No intervention data - Peptide determination will be difficult")
        if field_name == 'delivery_mode' and all(f in missing for f in ['interventions', 'arm_groups']):
            warnings.append("No intervention or arm data - Delivery mode will default to 'Other'")

        return {
            'is_sufficient': len(missing) < len(critical),  # At least one critical field available
            'missing_fields': missing,
            'available_fields': available,
            'quality_score': quality_score,
            'unweighted_score': unweighted_score,
            'warnings': warnings,
            'weights_used': field_weights
        }

    def get_data_quality_summary(self, trial_index: int = 0) -> Dict[str, Any]:
        """
        Get a comprehensive data quality summary for all annotation fields.

        Args:
            trial_index: Index of the trial to analyze

        Returns:
            Dictionary with quality summary for each annotation field
        """
        if trial_index >= len(self.trials):
            return {'error': f'Trial index {trial_index} out of range'}

        trial = self.trials[trial_index]

        # Get extracted info for each field
        extractions = {
            'classification': self.extract_classification_info(trial),
            'delivery_mode': self.extract_delivery_mode_info(trial),
            'outcome': self.extract_outcome_info(trial),
            'failure_reason': self.extract_failure_reason_info(trial),
            'peptide': self.extract_peptide_info(trial),
            'sequence': self.extract_sequence_info(trial)
        }

        summary = {
            'nct_id': trial.get('nct_id', 'Unknown'),
            'fields': {},
            'overall_quality': 0,
            'critical_warnings': [],
            'annotation_guidance': []
        }

        quality_scores = []
        for field_name, info_dict in extractions.items():
            validation = self.validate_extraction(info_dict, field_name)
            summary['fields'][field_name] = validation
            quality_scores.append(validation['quality_score'])

            if not validation['is_sufficient']:
                summary['critical_warnings'].append(
                    f"{field_name}: Insufficient data (missing: {', '.join(validation['missing_fields'])})"
                )

            summary['critical_warnings'].extend(validation['warnings'])

        summary['overall_quality'] = sum(quality_scores) / len(quality_scores) if quality_scores else 0

        # Generate annotation guidance based on data quality
        if summary['overall_quality'] < 0.3:
            summary['annotation_guidance'].append(
                "DATA SEVERELY LIMITED: Many annotations will require educated guesses. "
                "Consider marking uncertain fields as 'Unknown' or 'Other'."
            )
        elif summary['overall_quality'] < 0.5:
            summary['annotation_guidance'].append(
                "DATA PARTIALLY AVAILABLE: Some fields may require inference from limited context. "
                "Provide reasoning with available evidence."
            )
        else:
            summary['annotation_guidance'].append(
                "DATA QUALITY ACCEPTABLE: Sufficient information available for annotation."
            )

        return summary
    
    def _get_protocol_section(self, trial: Dict) -> Dict:
        """Get the protocol section from trial data, handling different data structures."""
        # Try standard path: results.sources.clinical_trials.data.protocolSection
        protocol = self.safe_get(
            trial, 
            'results', 'sources', 'clinical_trials', 'data', 'protocolSection',
            default={}
        )
        
        if not protocol:
            # Try alternate path: sources.clinical_trials.data.protocolSection
            protocol = self.safe_get(
                trial,
                'sources', 'clinical_trials', 'data', 'protocolSection',
                default={}
            )
        
        if not protocol:
            # Try with alternate naming: results.sources.clinicaltrials
            protocol = self.safe_get(
                trial,
                'results', 'sources', 'clinicaltrials', 'data', 'protocolSection',
                default={}
            )
        
        if not protocol:
            # Try alternate naming without results wrapper
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
        - DerivedSection MeSH classifications (interventionBrowseModule)
        - OpenFDA route information (if available in extended sources)
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
            'arm_groups': [],
            'derived_intervention_info': [],
            'openfda_routes': []
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

        # Extract derivedSection intervention data (MeSH classifications)
        # Try multiple paths for derived section
        derived = self.safe_get(trial, 'results', 'sources', 'clinical_trials', 'data', 'derivedSection', default={})
        if not derived:
            derived = self.safe_get(trial, 'sources', 'clinical_trials', 'data', 'derivedSection', default={})
        if not derived:
            derived = self.safe_get(trial, 'derivedSection', default={})

        if derived:
            intervention_browse = derived.get('interventionBrowseModule', {})
            meshes = intervention_browse.get('meshes', [])
            for mesh in meshes:
                info['derived_intervention_info'].append({
                    'mesh_id': mesh.get('id', ''),
                    'mesh_term': mesh.get('term', '')
                })
            # Also get ancestors which provide broader categories
            ancestors = intervention_browse.get('ancestors', [])
            for ancestor in ancestors[:5]:  # Limit to 5
                info['derived_intervention_info'].append({
                    'mesh_id': ancestor.get('id', ''),
                    'mesh_term': ancestor.get('term', ''),
                    'is_ancestor': True
                })

        # Extract OpenFDA route information if available
        extended_sources = self.safe_get(trial, 'results', 'sources', 'extended', default={})
        if not extended_sources:
            extended_sources = self.safe_get(trial, 'sources', 'extended', default={})

        openfda_data = extended_sources.get('openfda', {})
        if openfda_data.get('success'):
            fda_results = openfda_data.get('data', {}).get('results', [])
            for result in fda_results[:3]:
                openfda_info = result.get('openfda', {})
                routes = openfda_info.get('route', [])
                if routes:
                    info['openfda_routes'].extend(routes)

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
        - Results section data (p-values, analyses, conclusions)
        - Participant flow (early termination info)
        """
        protocol = self._get_protocol_section(trial)

        id_module = self.safe_get(protocol, 'identificationModule', default={})
        status_module = self.safe_get(protocol, 'statusModule', default={})
        outcomes_module = self.safe_get(protocol, 'outcomesModule', default={})
        conditions_module = self.safe_get(protocol, 'conditionsModule', default={})

        # Try multiple paths for clinical trials data
        ct_data = self.safe_get(trial, 'results', 'sources', 'clinical_trials', 'data', default={})
        if not ct_data:
            ct_data = self.safe_get(trial, 'sources', 'clinical_trials', 'data', default={})
        if not ct_data:
            ct_data = trial  # Trial itself might be the ct_data

        has_results = ct_data.get('hasResults', False)
        results_section = ct_data.get('resultsSection', {})

        info = {
            'nct_id': trial.get('nct_id', self.safe_get(id_module, 'nctId')),
            'brief_title': id_module.get('briefTitle', 'Not available'),
            'overall_status': status_module.get('overallStatus', 'Not available'),
            'status_verified_date': status_module.get('statusVerifiedDate', 'Not available'),
            'why_stopped': status_module.get('whyStopped', 'Not available'),
            'start_date': self.safe_get(status_module, 'startDateStruct', 'date'),
            'completion_date': self.safe_get(status_module, 'completionDateStruct', 'date'),
            'primary_completion_date': self.safe_get(status_module, 'primaryCompletionDateStruct', 'date'),
            'has_results': has_results,
            'primary_outcomes': [],
            'secondary_outcomes': [],
            'conditions': conditions_module.get('conditions', []),
            # New fields for results analysis
            'results_outcome_measures': [],
            'results_p_values': [],
            'results_limitations': '',
            'results_adverse_events_summary': {},
            'participant_flow_info': {}
        }

        # Extract outcome measures from protocol
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

        # Extract results section data if available
        if has_results and results_section:
            # Outcome measures with analyses
            outcome_measures_module = results_section.get('outcomeMeasuresModule', {})
            outcome_list = outcome_measures_module.get('outcomeMeasures', [])

            for om in outcome_list[:5]:  # Limit to 5 outcome measures
                om_info = {
                    'type': om.get('type', ''),
                    'title': om.get('title', ''),
                    'description': om.get('description', '')[:500] if om.get('description') else '',
                    'analyses': []
                }

                # Extract analyses with p-values
                analyses = om.get('analyses', [])
                for analysis in analyses[:3]:  # Limit to 3 analyses per measure
                    analysis_info = {
                        'statistical_method': analysis.get('statisticalMethod', ''),
                        'p_value': analysis.get('pValue', ''),
                        'p_value_comment': analysis.get('pValueComment', ''),
                        'param_type': analysis.get('paramType', ''),
                        'ci_pct_value': analysis.get('ciPctValue', ''),
                        'ci_lower_limit': analysis.get('ciLowerLimit', ''),
                        'ci_upper_limit': analysis.get('ciUpperLimit', ''),
                        'estimate_comment': analysis.get('estimateComment', '')
                    }
                    om_info['analyses'].append(analysis_info)

                    # Collect p-values for easy access
                    if analysis.get('pValue'):
                        info['results_p_values'].append(analysis.get('pValue'))

                info['results_outcome_measures'].append(om_info)

            # Extract limitations and caveats
            more_info_module = results_section.get('moreInfoModule', {})
            limitations = more_info_module.get('limitationsAndCaveats', {})
            if limitations:
                info['results_limitations'] = limitations.get('description', '')

            # Extract adverse events summary
            adverse_events_module = results_section.get('adverseEventsModule', {})
            if adverse_events_module:
                info['results_adverse_events_summary'] = {
                    'serious_num_affected': adverse_events_module.get('seriousNumAffected', ''),
                    'serious_num_at_risk': adverse_events_module.get('seriousNumAtRisk', ''),
                    'other_num_affected': adverse_events_module.get('otherNumAffected', ''),
                    'other_num_at_risk': adverse_events_module.get('otherNumAtRisk', ''),
                    'frequency_threshold': adverse_events_module.get('frequencyThreshold', ''),
                    'time_frame': adverse_events_module.get('timeFrame', '')
                }

            # Extract participant flow info (useful for understanding early termination)
            participant_flow = results_section.get('participantFlowModule', {})
            if participant_flow:
                info['participant_flow_info'] = {
                    'recruitment_details': participant_flow.get('recruitmentDetails', ''),
                    'pre_assignment_details': participant_flow.get('preAssignmentDetails', '')
                }

                # Get flow groups to understand completion rates
                groups = participant_flow.get('groups', [])
                periods = participant_flow.get('periods', [])
                if periods:
                    for period in periods[:1]:  # Just first period
                        milestones = period.get('milestones', [])
                        for milestone in milestones:
                            if milestone.get('type') == 'COMPLETED' or 'complet' in milestone.get('type', '').lower():
                                info['participant_flow_info']['completion_milestone'] = {
                                    'type': milestone.get('type', ''),
                                    'achievements': milestone.get('achievements', [])
                                }
                            if milestone.get('type') == 'NOT_COMPLETED' or 'not complet' in milestone.get('type', '').lower():
                                info['participant_flow_info']['not_completed_milestone'] = {
                                    'type': milestone.get('type', ''),
                                    'achievements': milestone.get('achievements', [])
                                }

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
        
        # Handle nested sources structure (results.sources or sources)
        sources = trial.get('sources', {})
        if not sources and 'results' in trial:
            sources = trial.get('results', {}).get('sources', {})
        
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
    
    def extract_sequence_info(self, trial: Dict) -> Dict[str, Any]:
        """
        Extract sequence information from UniProt and DRAMP extended sources.

        Relevant factors:
        - UniProt protein sequences (accession, name, organism, sequence value)
        - DRAMP antimicrobial peptide sequences
        - Intervention names (to match drug to protein)
        - PubMed/PMC references for additional context
        """
        protocol = self._get_protocol_section(trial)

        id_module = self.safe_get(protocol, 'identificationModule', default={})
        desc_module = self.safe_get(protocol, 'descriptionModule', default={})
        arms_interventions = self.safe_get(protocol, 'armsInterventionsModule', default={})

        info = {
            'nct_id': trial.get('nct_id', self.safe_get(id_module, 'nctId')),
            'brief_title': id_module.get('briefTitle', 'Not available'),
            'interventions': [],
            'uniprot_sequences': [],
            'dramp_sequences': [],
            'pubmed_pmids': [],
            'pmc_ids': []
        }

        # Extract intervention names (helps LLM match drug to sequence)
        interventions = arms_interventions.get('interventions', [])
        for intervention in interventions:
            info['interventions'].append({
                'type': intervention.get('type', 'Not specified'),
                'name': intervention.get('name', 'Not specified'),
                'description': intervention.get('description', 'Not specified')
            })

        # Get extended sources
        extended_sources = self.safe_get(trial, 'results', 'sources', 'extended', default={})
        if not extended_sources:
            extended_sources = self.safe_get(trial, 'sources', 'extended', default={})

        # Extract UniProt sequences
        uniprot = extended_sources.get('uniprot', {})
        if uniprot.get('success'):
            uniprot_data = uniprot.get('data', {})
            for protein in uniprot_data.get('results', []):
                seq_info = protein.get('sequence', {})
                seq_value = seq_info.get('value', '') if isinstance(seq_info, dict) else ''
                if seq_value:
                    # Extract protein name
                    protein_name = ''
                    prot_desc = protein.get('proteinDescription', {})
                    rec_name = prot_desc.get('recommendedName', {})
                    if rec_name:
                        full_name = rec_name.get('fullName', {})
                        protein_name = full_name.get('value', '') if isinstance(full_name, dict) else str(full_name)
                    if not protein_name:
                        sub_names = prot_desc.get('submissionNames', [])
                        if sub_names:
                            full_name = sub_names[0].get('fullName', {})
                            protein_name = full_name.get('value', '') if isinstance(full_name, dict) else str(full_name)

                    info['uniprot_sequences'].append({
                        'accession': protein.get('primaryAccession', 'Unknown'),
                        'name': protein_name or 'Unknown',
                        'organism': protein.get('organism', {}).get('scientificName', 'Unknown'),
                        'sequence': seq_value,
                        'length': seq_info.get('length', len(seq_value))
                    })

        # Extract DRAMP sequences
        dramp = extended_sources.get('dramp', {})
        if dramp.get('success'):
            dramp_data = dramp.get('data', {})
            for entry in dramp_data.get('results', []):
                seq_value = entry.get('sequence', '')
                if seq_value:
                    info['dramp_sequences'].append({
                        'dramp_id': entry.get('dramp_id', 'Unknown'),
                        'name': entry.get('name', 'Unknown'),
                        'sequence': seq_value,
                        'length': len(seq_value)
                    })

        # Get supporting references
        sources = trial.get('sources', {})
        if not sources and 'results' in trial:
            sources = trial.get('results', {}).get('sources', {})

        pubmed_data = sources.get('pubmed', {})
        if pubmed_data.get('success'):
            pmids = pubmed_data.get('data', {}).get('pmids', [])
            if pmids:
                info['pubmed_pmids'] = pmids

        pmc_data = sources.get('pmc', {})
        if pmc_data.get('success'):
            pmcids = pmc_data.get('data', {}).get('pmcids', [])
            if pmcids:
                info['pmc_ids'] = pmcids

        return info

    def format_as_text(self, info_dict: Dict[str, Any], field_name: str, include_quality_warning: bool = True) -> str:
        """
        Format extracted information as human-readable text.

        Args:
            info_dict: Dictionary containing extracted information
            field_name: Name of the annotation field
            include_quality_warning: Whether to include data quality warnings

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

        # Validate data quality and add warnings if needed
        if include_quality_warning:
            validation = self.validate_extraction(info_dict, field_name.lower().replace(' ', '_'))
            if validation['warnings']:
                lines.append("-" * 40)
                lines.append("DATA QUALITY WARNINGS:")
                for warning in validation['warnings']:
                    lines.append(f"  ! {warning}")
                lines.append("-" * 40)
                lines.append("")

            if validation['missing_fields']:
                lines.append(f"MISSING DATA: {', '.join(validation['missing_fields'])}")
                lines.append("Note: LLM should use available context or mark as 'Unknown'/'Other' if insufficient data.")
                lines.append("")

        # Add title if available
        if 'brief_title' in info_dict and info_dict['brief_title'] != 'Not available':
            lines.append(f"Brief Title: {info_dict['brief_title']}")
            lines.append("")
        else:
            lines.append("Brief Title: [NOT AVAILABLE - use other fields for context]")
            lines.append("")

        if 'official_title' in info_dict and info_dict['official_title'] != 'Not available':
            lines.append(f"Official Title: {info_dict['official_title']}")
            lines.append("")

        # Count available vs missing fields for summary
        available_count = 0
        missing_count = 0

        # Format different fields based on type
        for key, value in info_dict.items():
            if key in ['nct_id', 'brief_title', 'official_title']:
                continue  # Already added

            if self._is_empty_value(value):
                missing_count += 1
                continue  # Skip empty fields

            available_count += 1

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

        # Add data availability summary
        lines.append("-" * 40)
        lines.append(f"Data Summary: {available_count} fields available, {missing_count} fields missing")
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
            ),
            'sequence': self.format_as_text(
                self.extract_sequence_info(trial),
                'Sequence'
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

        # Get data quality summary
        quality_summary = self.get_data_quality_summary(trial_index)

        combined = [
            "=" * 80,
            "CLINICAL TRIAL ANNOTATION REQUEST",
            "=" * 80,
            "",
        ]

        # Add data quality summary at the top
        combined.append("## DATA QUALITY ASSESSMENT")
        combined.append(f"Overall Data Quality: {quality_summary['overall_quality']:.0%}")
        combined.append("")

        if quality_summary['critical_warnings']:
            combined.append("CRITICAL WARNINGS:")
            for warning in quality_summary['critical_warnings']:
                combined.append(f"  ! {warning}")
            combined.append("")

        if quality_summary['annotation_guidance']:
            combined.append("ANNOTATION GUIDANCE:")
            for guidance in quality_summary['annotation_guidance']:
                combined.append(f"  > {guidance}")
            combined.append("")

        # Field-specific data availability
        combined.append("DATA AVAILABILITY BY FIELD:")
        for field_name, field_info in quality_summary['fields'].items():
            status = "✓ Sufficient" if field_info['is_sufficient'] else "✗ Insufficient"
            combined.append(f"  - {field_name}: {status} ({field_info['quality_score']:.0%})")
        combined.append("")

        combined.extend([
            "=" * 80,
            "",
            "Please annotate this clinical trial with the following fields:",
            "",
            "**Classification:** AMP or Other",
            "  - If insufficient data: default to 'Other' with reasoning",
            "",
            "**Delivery Mode:** Injection/Infusion, Topical, Oral, or Other",
            "  - If insufficient data: default to 'Other' with reasoning",
            "",
            "**Outcome:** Positive, Withdrawn, Terminated, Failed - completed trial, Active, or Unknown",
            "  - If insufficient data: use 'Unknown' with reasoning",
            "",
            "**Reason for Failure:** Business reasons, Ineffective for purpose, Toxic/unsafe, Due to covid, Recruitment issues, or N/A",
            "  - If outcome is not a failure/termination: use 'N/A'",
            "",
            "**Peptide:** True or False",
            "  - If insufficient data: use 'False' with reasoning",
            "",
            "**Sequence:** Amino acid sequence of the peptide drug",
            "  - Choose the sequence that best matches the trial's drug from available UniProt/DRAMP data",
            "  - If multiple candidates exist, select the one most relevant to the intervention",
            "  - If no sequence data available: use 'N/A'",
            "",
            "=" * 80,
            "",
        ])

        # Add each annotation field's relevant information
        for field_name in ['classification', 'delivery_mode', 'outcome', 'failure_reason', 'peptide', 'sequence']:
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
            'peptide': self.extract_peptide_info(trial),
            'sequence': self.extract_sequence_info(trial)
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