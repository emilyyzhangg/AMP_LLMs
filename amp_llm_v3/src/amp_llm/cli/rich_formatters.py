"""
Rich-based formatters for enhanced CLI output.
Uses rich library for beautiful terminal formatting.
"""
from typing import List, Dict, Any, Optional
from rich.console import Console
from rich.table import Table
from rich.panel import Panel
from rich.progress import Progress, SpinnerColumn, TextColumn, BarColumn
from rich.syntax import Syntax
from rich.tree import Tree
from rich import box

console = Console()


class RichFormatter:
    """Rich-based formatters for CLI output."""
    
    @staticmethod
    def display_trial_results(results: List[Dict[str, Any]]) -> None:
        """
        Display clinical trial results in a formatted table.
        
        Args:
            results: List of trial result dictionaries
            
        Example:
            >>> results = [
            ...     {"nct_id": "NCT123", "title": "Study A", "status": "RECRUITING"},
            ...     {"nct_id": "NCT456", "title": "Study B", "status": "COMPLETED"}
            ... ]
            >>> RichFormatter.display_trial_results(results)
        """
        table = Table(
            title="Clinical Trial Results",
            box=box.ROUNDED,
            show_header=True,
            header_style="bold cyan"
        )
        
        table.add_column("NCT ID", style="cyan", no_wrap=True)
        table.add_column("Title", style="white")
        table.add_column("Status", justify="center")
        table.add_column("Phase", justify="center")
        table.add_column("PubMed", justify="right", style="green")
        table.add_column("PMC", justify="right", style="blue")
        
        for result in results:
            # Get data safely
            nct_id = result.get("nct_id", "N/A")
            
            # Extract from nested structure
            sources = result.get("sources", {})
            ct_data = sources.get("clinical_trials", {}).get("data", {})
            protocol = ct_data.get("protocolSection", {})
            
            # Get title
            ident = protocol.get("identificationModule", {})
            title = (ident.get("officialTitle") or 
                    ident.get("briefTitle") or "Untitled")
            title = title[:50] + "..." if len(title) > 50 else title
            
            # Get status
            status_mod = protocol.get("statusModule", {})
            status = status_mod.get("overallStatus", "UNKNOWN")
            
            # Color-code status
            if status == "RECRUITING":
                status_display = f"[green]{status}[/green]"
            elif status == "COMPLETED":
                status_display = f"[blue]{status}[/blue]"
            elif status in ("TERMINATED", "WITHDRAWN"):
                status_display = f"[red]{status}[/red]"
            else:
                status_display = f"[yellow]{status}[/yellow]"
            
            # Get phase
            design = protocol.get("designModule", {})
            phases = design.get("phases", [])
            phase_str = ", ".join(phases) if phases else "N/A"
            
            # Get counts
            pubmed = sources.get("pubmed", {})
            pmc = sources.get("pmc", {})
            pubmed_count = len(pubmed.get("pmids", []))
            pmc_count = len(pmc.get("pmcids", []))
            
            table.add_row(
                nct_id,
                title,
                status_display,
                phase_str,
                str(pubmed_count),
                str(pmc_count)
            )
        
        console.print(table)
    
    @staticmethod
    def display_extraction(extraction: Dict[str, Any]) -> None:
        """
        Display structured extraction in a beautiful format.
        
        Args:
            extraction: Extraction dictionary
        """
        # Create panels for different sections
        
        # Basic Info Panel
        basic_info = Table.grid(padding=(0, 2))
        basic_info.add_column(style="bold cyan", justify="right")
        basic_info.add_column(style="white")
        
        basic_info.add_row("NCT Number:", extraction.get("nct_number", "N/A"))
        basic_info.add_row("Study Title:", extraction.get("study_title", "N/A"))
        basic_info.add_row("Status:", extraction.get("study_status", "N/A"))
        basic_info.add_row("Phase:", ", ".join(extraction.get("phases", [])))
        basic_info.add_row("Enrollment:", str(extraction.get("enrollment", 0)))
        
        console.print(Panel(basic_info, title="[bold]Basic Information[/bold]", border_style="cyan"))
        
        # Clinical Details Panel
        clinical = Table.grid(padding=(0, 2))
        clinical.add_column(style="bold green", justify="right")
        clinical.add_column(style="white")
        
        conditions = extraction.get("conditions", [])
        clinical.add_row("Conditions:", ", ".join(conditions) if conditions else "N/A")
        
        interventions = extraction.get("interventions", [])
        clinical.add_row("Interventions:", ", ".join(interventions) if interventions else "N/A")
        
        clinical.add_row("Classification:", extraction.get("classification", "N/A"))
        clinical.add_row("Delivery Mode:", extraction.get("delivery_mode", "N/A"))
        
        console.print(Panel(clinical, title="[bold]Clinical Details[/bold]", border_style="green"))
        
        # Outcome Panel
        outcome = Table.grid(padding=(0, 2))
        outcome.add_column(style="bold yellow", justify="right")
        outcome.add_column(style="white")
        
        outcome_status = extraction.get("outcome", "N/A")
        outcome.add_row("Outcome:", outcome_status)
        
        if outcome_status in ("Terminated", "Withdrawn", "Failed - completed trial"):
            failure_reason = extraction.get("failure_reason", "N/A")
            outcome.add_row("Failure Reason:", failure_reason)
        
        console.print(Panel(outcome, title="[bold]Outcome[/bold]", border_style="yellow"))
    
    @staticmethod
    def display_api_summary(api_results: Dict[str, Any]) -> None:
        """
        Display summary of API search results.
        
        Args:
            api_results: Dictionary with results from each API
        """
        table = Table(
            title="Extended API Search Results",
            box=box.ROUNDED,
            show_header=True,
            header_style="bold magenta"
        )
        
        table.add_column("API", style="cyan")
        table.add_column("Status", justify="center")
        table.add_column("Results", justify="right", style="green")
        table.add_column("Details", style="white")
        
        for api_name, result in api_results.items():
            # Determine status
            if "error" in result:
                status = "[red]✗ Error[/red]"
                count = "0"
                details = str(result["error"])[:50]
            else:
                status = "[green]✓ Success[/green]"
                
                # Get count based on API type