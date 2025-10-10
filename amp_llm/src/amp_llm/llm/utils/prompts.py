# ============================================================================
# src/amp_llm/llm/utils/prompts.py
# ============================================================================
"""
Prompt templates for LLM interactions.
"""
from typing import Dict, Any


class PromptTemplate:
    """Template for constructing prompts."""
    
    def __init__(self, template: str):
        """
        Initialize template.
        
        Args:
            template: Template string with {variable} placeholders
        """
        self.template = template
    
    def format(self, **kwargs) -> str:
        """
        Format template with variables.
        
        Args:
            **kwargs: Variables to substitute
            
        Returns:
            Formatted prompt
        """
        return self.template.format(**kwargs)


class SystemPrompts:
    """Collection of system prompts."""
    
    CLINICAL_TRIAL_EXTRACTION = """You are a Clinical Trial Data Extraction Specialist.
Extract structured information from clinical trial JSON data.

Follow the exact format specified, using actual data from the trial.
For missing data, write exactly: N/A
Use EXACT values from validation lists provided.
Do NOT wrap response in markdown code blocks."""
    
    RESEARCH_ASSISTANT = """You are a clinical trial research assistant.
Use the provided trial data to answer questions accurately and concisely.

Provide clear, well-structured answers based on the data.
Cite specific trials when relevant.
If data is insufficient, say so clearly."""
    
    DATA_ANALYSIS = """You are a data analyst for clinical trials.
Analyze the provided trial data and extract meaningful insights.

Focus on:
- Key findings and trends
- Statistical significance
- Clinical relevance
- Safety considerations"""
    
    @staticmethod
    def get_extraction_prompt(trial_data: str) -> str:
        """
        Get extraction prompt with trial data.
        
        Args:
            trial_data: JSON or formatted trial data
            
        Returns:
            Complete prompt
        """
        template = PromptTemplate(
            SystemPrompts.CLINICAL_TRIAL_EXTRACTION + 
            "\n\nTrial Data:\n{trial_data}\n\n" +
            "Now provide a complete extraction following the format."
        )
        return template.format(trial_data=trial_data)
    
    @staticmethod
    def get_research_prompt(query: str, context: str) -> str:
        """
        Get research prompt with context.
        
        Args:
            query: User question
            context: Relevant trial data
            
        Returns:
            Complete prompt
        """
        template = PromptTemplate(
            SystemPrompts.RESEARCH_ASSISTANT + 
            "\n\nQuestion: {query}\n\n{context}\n\n" +
            "Provide a clear answer based on the trial data above."
        )
        return template.format(query=query, context=context)