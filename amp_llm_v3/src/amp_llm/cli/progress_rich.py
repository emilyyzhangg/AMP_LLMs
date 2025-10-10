"""
Rich-based progress indicators.
"""
from typing import List, Callable, Any
from rich.progress import Progress, SpinnerColumn, TextColumn, BarColumn, TimeElapsedColumn
from amp_llm.cli.rich_formatters import console


class RichProgress:
    """Progress tracking with Rich."""
    
    @staticmethod
    async def with_progress(
        tasks: List[tuple[str, Callable]],
        description: str = "Processing"
    ) -> List[Any]:
        """
        Execute tasks with progress bar.
        
        Args:
            tasks: List of (task_name, async_function) tuples
            description: Overall progress description
            
        Returns:
            List of results
        """
        results = []
        
        with Progress(
            SpinnerColumn(),
            TextColumn("[progress.description]{task.description}"),
            BarColumn(),
            TextColumn("[progress.percentage]{task.percentage:>3.0f}%"),
            TimeElapsedColumn(),
            console=console
        ) as progress:
            
            overall = progress.add_task(f"[cyan]{description}", total=len(tasks))
            
            for task_name, task_func in tasks:
                progress.update(overall, description=f"[cyan]{task_name}")
                
                try:
                    result = await task_func()
                    results.append(result)
                except Exception as e:
                    results.append({"error": str(e)})
                
                progress.advance(overall)
        
        return results


# Example usage in workflows:
async def fetch_multiple_trials(nct_ids: List[str]):
    """Fetch multiple trials with progress bar."""
    from amp_llm.data.workflows.core_fetch import fetch_clinical_trial_and_pubmed_pmc
    
    tasks = [
        (f"Fetching {nct}", lambda nct=nct: fetch_clinical_trial_and_pubmed_pmc(nct))
        for nct in nct_ids
    ]
    
    return await RichProgress.with_progress(tasks, "Fetching Trials")