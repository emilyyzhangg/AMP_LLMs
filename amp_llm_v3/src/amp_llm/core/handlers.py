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
    """Handler for Research Assistant."""
    
    async def execute(self, context: Any) -> None:
        from pathlib import Path
        from amp_llm.cli.async_io import aprint
        from colorama import Fore
        from amp_llm.llm.assistants.assistant import ClinicalTrialResearchAssistant
        
        db_path = Path("ct_database")
        if not db_path.exists():
            await aprint(Fore.YELLOW + "⚠️  Database not found: ct_database/")
            await aprint(Fore.YELLOW + "Creating directory...")
            db_path.mkdir(exist_ok=True)
            await aprint(Fore.YELLOW + "Please add JSON files to ct_database/")
            return
        
        assistant = ClinicalTrialResearchAssistant(db_path)
        
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