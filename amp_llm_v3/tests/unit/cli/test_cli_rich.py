"""
Tests for Rich CLI formatters.
"""
import pytest
from amp_llm.cli.rich_formatters import RichFormatter, HAS_RICH


@pytest.mark.skipif(not HAS_RICH, reason="Rich not installed")
def test_display_trial_results():
    """Test trial results display."""
    results = [
        {
            "nct_id": "NCT12345678",
            "sources": {
                "clinical_trials": {
                    "data": {
                        "protocolSection": {
                            "identificationModule": {
                                "briefTitle": "Test Study"
                            },
                            "statusModule": {
                                "overallStatus": "RECRUITING"
                            },
                            "designModule": {
                                "phases": ["PHASE2"]
                            }
                        }
                    }
                },
                "pubmed": {"pmids": ["12345"]},
                "pmc": {"pmcids": ["67890"]}
            }
        }
    ]
    
    # Should not raise exception
    RichFormatter.display_trial_results(results)


@pytest.mark.skipif(not HAS_RICH, reason="Rich not installed")
def test_print_methods():
    """Test print utility methods."""
    RichFormatter.print_success("Test success")
    RichFormatter.print_error("Test error")
    RichFormatter.print_warning("Test warning")
    RichFormatter.print_info("Test info")