"""
Menu system with dynamic module loading.
Separates menu logic from application logic.
"""
from typing import Dict, Callable
from colorama import Fore, Style
from aioconsole import ainput, aprint

from config import get_logger

logger = get_logger(__name__)


class MenuItem:
    """Represents a single menu item."""
    
    def __init__(self, number: str, name: str, handler: Callable, description: str = "", badge: str = ""):
        self.number = number
        self.name = name
        self.handler = handler
        self.description = description
        self.badge = badge
    
    async def display(self):
        """Display menu item."""
        text = f"{Fore.CYAN}{self.number}.{Fore.WHITE} {self.name}"
        if self.badge:
            text += f" {self.badge}"
        await aprint(text)


class MenuSystem:
    """
    Manages menu display and routing.
    
    Responsibilities:
    - Menu display
    - User input handling
    - Module routing
    - Error handling
    """
    
    def __init__(self, app):
        self.app = app
        self.items: Dict[str, MenuItem] = {}
        self._register_menu_items()
    
    def _register_menu_items(self):
        """Register all menu items with their handlers."""
        # Import handlers lazily to avoid circular imports
        from network.ssh_shell import open_interactive_shell
        from llm.async_llm_runner_api import run_llm_entrypoint_api
        from llm.async_llm_runner import run_llm_entrypoint
        from data.async_nct_lookup import run_nct_lookup
        from llm.ct_research_runner import run_ct_research_assistant
        
        self.items = {
            "1": MenuItem(
                "1", 
                "Interactive Shell",
                lambda: open_interactive_shell(self.app.ssh_connection),
                "Direct SSH terminal access"
            ),
            "2": MenuItem(
                "2",
                "LLM Workflow (API Mode)",
                lambda: run_llm_entrypoint_api(self.app.ssh_connection),
                "Recommended: Uses HTTP API, most reliable"
            ),
            "3": MenuItem(
                "3",
                "LLM Workflow (SSH Terminal)",
                lambda: run_llm_entrypoint(self.app.ssh_connection),
                "Legacy: Direct terminal interaction"
            ),
            "4": MenuItem(
                "4",
                "NCT Lookup",
                run_nct_lookup,
                "Search and fetch clinical trial data"
            ),
            "5": MenuItem(
                "5",
                "Clinical Trial Research Assistant",
                lambda: run_ct_research_assistant(self.app.ssh_connection),
                "RAG-powered intelligent analysis",
                f"{Fore.GREEN}<- NEW!"
            ),
            "6": MenuItem(
                "6",
                "Exit",
                None,
                "Quit application"
            ),
        }
        
        # Add aliases
        self.aliases = {
            "interactive": "1",
            "shell": "1",
            "llm": "2",
            "api": "2",
            "terminal": "3",
            "ssh": "3",
            "nct": "4",
            "lookup": "4",
            "research": "5",
            "assistant": "5",
            "exit": "6",
            "quit": "6",
        }
    
    async def display_menu(self):
        """Display main menu."""
        await aprint(Fore.YELLOW + Style.BRIGHT + "\n=== AMP_LLM Main Menu ===")
        
        for key in sorted(self.items.keys()):
            await self.items[key].display()
    
    async def get_choice(self) -> str:
        """Get and normalize user choice."""
        choice = await ainput(Fore.GREEN + "\nSelect an option (1-6): ")
        choice = choice.strip().lower()
        
        # Check if it's an alias
        if choice in self.aliases:
            return self.aliases[choice]
        
        return choice
    
    async def run(self):
        """Main menu loop."""
        while self.app.running:
            try:
                await self.display_menu()
                choice = await self.get_choice()
                
                if choice not in self.items:
                    await aprint(Fore.RED + "Invalid option. Please choose 1-6.")
                    continue
                
                item = self.items[choice]
                
                # Exit option
                if item.handler is None:
                    await aprint(Fore.MAGENTA + "Exiting. Goodbye!")
                    break
                
                # Execute handler
                logger.info(f"User selected: {item.name}")
                
                # Check SSH connection before running modules that need it
                if choice in ("1", "2", "3", "5"):
                    if not await self.app.ensure_connected():
                        await aprint(Fore.RED + "SSH connection required but unavailable")
                        continue
                
                # Run the module
                await item.handler()
                
            except KeyboardInterrupt:
                await aprint(Fore.YELLOW + "\n\nInterrupted. Returning to menu...")
                continue
            except Exception as e:
                logger.error(f"Error in menu: {e}", exc_info=True)
                await aprint(Fore.RED + f"An error occurred: {e}")
                await aprint(Fore.YELLOW + "Returning to main menu...")
