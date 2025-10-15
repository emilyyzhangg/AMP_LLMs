"""
Handler interface for menu actions.
Allows pluggable handlers without tight coupling.
"""
from abc import ABC, abstractmethod
from typing import Any


class MenuHandler(ABC):
    """Abstract base class for menu handlers."""
    
    @abstractmethod
    async def execute(self, context: Any) -> None:
        """
        Execute the handler action.
        
        Args:
            context: Application context with ssh_manager, etc.
        """
        pass
    
    @property
    @abstractmethod
    def requires_ssh(self) -> bool:
        """Whether this handler requires SSH connection."""
        pass


class ShellHandler(MenuHandler):
    """Handler for interactive shell."""
    
    async def execute(self, context: Any) -> None:
        from amp_llm.network.shell import open_interactive_shell
        await open_interactive_shell(context.ssh_manager.connection)
    
    @property
    def requires_ssh(self) -> bool:
        return True


class LLMAPIHandler(MenuHandler):
    """Handler for LLM API mode."""
    
    async def execute(self, context: Any) -> None:
        from amp_llm.llm.handlers import run_llm_entrypoint_api
        await run_llm_entrypoint_api(context.ssh_manager)
    
    @property
    def requires_ssh(self) -> bool:
        return True


class LLMSSHHandler(MenuHandler):
    """Handler for LLM SSH terminal mode."""
    
    async def execute(self, context: Any) -> None:
        from amp_llm.llm.handlers import run_llm_entrypoint_ssh
        await run_llm_entrypoint_ssh(context.ssh_manager.connection)
    
    @property
    def requires_ssh(self) -> bool:
        return True


class NCTLookupHandler(MenuHandler):
    """Handler for NCT lookup."""
    
    async def execute(self, context: Any) -> None:
        from amp_llm.data.nct_lookup import run_nct_lookup
        await run_nct_lookup()
    
    @property
    def requires_ssh(self) -> bool:
        return False


class ResearchAssistantHandler(MenuHandler):
    """Handler for Research Assistant - Simple version."""
    
    async def execute(self, context: Any) -> None:
        from pathlib import Path
        from amp_llm.cli.async_io import aprint
        from colorama import Fore
        from amp_llm.llm.assistants.assistant import ClinicalTrialResearchAssistant
        import shutil
        
        db_path = Path("ct_database")
        output_path = Path("output")
        
        # Create directories
        db_path.mkdir(exist_ok=True)
        
        # Auto-copy from output/ to ct_database/ if needed
        if output_path.exists():
            for json_file in output_path.glob("*.json"):
                dest = db_path / json_file.name
                if not dest.exists():
                    try:
                        shutil.copy2(json_file, dest)
                    except:
                        pass
        
        # Check for trials
        trial_files = list(db_path.glob("*.json"))
        
        if not trial_files:
            await aprint(Fore.YELLOW + "⚠️  No trial files found")
            await aprint(Fore.CYAN + "\n💡 Use Option 4 (NCT Lookup) to fetch trials")
            await aprint(Fore.WHITE + "   Then save to ct_database/ or output/\n")
            return
        
        await aprint(Fore.GREEN + f"📂 Found {len(trial_files)} trial file(s)\n")
        
        # Initialize and run
        assistant = ClinicalTrialResearchAssistant(db_path)
        
        if len(assistant.rag.db.trials) == 0:
            await aprint(Fore.RED + "❌ Failed to load trials")
            return
        
        remote_host = (
            context.ssh_manager.host 
            if context.ssh_manager.is_connected() 
            else 'localhost'
        )
        
        await assistant.run(
            context.ssh_manager.connection,
            remote_host
        )
    
    @property
    def requires_ssh(self) -> bool:
        return True
