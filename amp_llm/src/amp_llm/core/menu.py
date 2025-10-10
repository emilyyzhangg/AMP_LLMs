"""
Enhanced menu system with better routing and error handling.
FIXED: Corrected SSH manager passing to handlers.
"""

from typing import Dict, Callable, Awaitable, Optional
from dataclasses import dataclass
from enum import Enum
from colorama import Fore, Style

try:
    from aioconsole import ainput, aprint
except ImportError:
    async def ainput(prompt):
        return input(prompt)
    async def aprint(*args, **kwargs):
        print(*args, **kwargs)

from amp_llm.config import get_logger
from .exceptions import MenuError

logger = get_logger(__name__)


class MenuAction(Enum):
    """Menu action types."""
    CONTINUE = "continue"
    EXIT = "exit"
    BACK = "back"


@dataclass
class MenuItem:
    """Represents a single menu item."""
    key: str
    name: str
    handler: Optional[Callable[[], Awaitable[MenuAction]]]
    description: str = ""
    badge: str = ""
    enabled: bool = True
    requires_ssh: bool = False
    
    async def display(self, number: Optional[int] = None) -> None:
        """Display menu item."""
        display_key = str(number) if number is not None else self.key
        
        # Build display text
        text = f"{Fore.CYAN}{display_key}.{Fore.WHITE} {self.name}"
        
        if self.badge:
            text += f" {self.badge}"
        
        if not self.enabled:
            text += f" {Fore.RED}(disabled){Style.RESET_ALL}"
        
        if self.requires_ssh:
            text += f" {Fore.YELLOW}[SSH]{Style.RESET_ALL}"
        
        await aprint(text)
        
        if self.description:
            await aprint(f"   {Fore.WHITE}{self.description}{Style.RESET_ALL}")


class MenuSystem:
    """Enhanced menu system with better routing and state management."""
    
    def __init__(self, app_context):
        """Initialize menu system."""
        self.context = app_context
        self.items: Dict[str, MenuItem] = {}
        self.aliases: Dict[str, str] = {}
        self.title: str = "Main Menu"
        self._register_default_items()
    
    def _register_default_items(self) -> None:
        """Register default menu items with FIXED SSH manager passing."""
        # FIXED: Use correct import paths
        from amp_llm.network.shell import open_interactive_shell
        from amp_llm.llm.handlers import run_llm_entrypoint_api, run_llm_entrypoint_ssh
        from amp_llm.data.async_nct_lookup import run_nct_lookup
        
        # Try to import research assistant (may not exist yet)
        try:
            from amp_llm.llm.research.assistant import ClinicalTrialResearchAssistant
            has_research = True
        except ImportError:
            has_research = False
            logger.warning("Research assistant not available")
        
        # Interactive Shell
        self.add_item(
            "1",
            "Interactive Shell",
            self._wrap_handler(
                lambda: open_interactive_shell(self.context.ssh_manager.connection)
            ),
            description="Direct SSH terminal access",
            requires_ssh=True,
        )
        
        # LLM Workflow (API) - FIXED: Pass SSHManager instead of connection
        self.add_item(
            "2",
            "LLM Workflow (API Mode)",
            self._wrap_handler(
                lambda: run_llm_entrypoint_api(self.context.ssh_manager)
            ),
            description="Recommended: Uses HTTP API, most reliable",
            requires_ssh=True,
        )
        
        # LLM Workflow (SSH) - FIXED: Pass connection (this one is correct)
        self.add_item(
            "3",
            "LLM Workflow (SSH Terminal)",
            self._wrap_handler(
                lambda: run_llm_entrypoint_ssh(self.context.ssh_manager.connection)
            ),
            description="Legacy: Direct terminal interaction",
            requires_ssh=True,
        )
        
        # NCT Lookup
        self.add_item(
            "4",
            "NCT Lookup",
            self._wrap_handler(run_nct_lookup),
            description="Search and fetch clinical trial data",
            requires_ssh=False,
        )
        
        # Research Assistant (if available)
        if has_research:
            async def run_research_wrapper():
                """Wrapper to run research assistant."""
                from pathlib import Path
                from amp_llm.llm.research.assistant import ClinicalTrialResearchAssistant
                
                db_path = Path("ct_database")
                if not db_path.exists():
                    await aprint(Fore.YELLOW + "⚠️  Database not found: ct_database/")
                    await aprint(Fore.YELLOW + "Creating directory...")
                    db_path.mkdir(exist_ok=True)
                    await aprint(Fore.YELLOW + "Please add JSON files to ct_database/")
                    return
                
                assistant = ClinicalTrialResearchAssistant(db_path)
                
                # FIXED: Get remote host from SSHManager
                remote_host = (
                    self.context.ssh_manager.host 
                    if self.context.ssh_manager.is_connected() 
                    else 'localhost'
                )
                
                await assistant.run(
                    self.context.ssh_manager.connection,
                    remote_host
                )
            
            self.add_item(
                "5",
                "Clinical Trial Research Assistant",
                self._wrap_handler(run_research_wrapper),
                description="RAG-powered intelligent analysis",
                badge=f"{Fore.GREEN}← RECOMMENDED",
                requires_ssh=True,
            )
        
        # Exit
        self.add_item(
            "6" if has_research else "5",
            "Exit",
            None,
            description="Quit application",
        )
        
        # Register aliases
        self.register_alias("shell", "1")
        self.register_alias("interactive", "1")
        self.register_alias("llm", "2")
        self.register_alias("api", "2")
        self.register_alias("terminal", "3")
        self.register_alias("ssh", "3")
        self.register_alias("nct", "4")
        self.register_alias("lookup", "4")
        if has_research:
            self.register_alias("research", "5")
            self.register_alias("assistant", "5")
            self.register_alias("exit", "6")
            self.register_alias("quit", "6")
        else:
            self.register_alias("exit", "5")
            self.register_alias("quit", "5")
    
    def _wrap_handler(
        self,
        handler: Callable[[], Awaitable[None]]
    ) -> Callable[[], Awaitable[MenuAction]]:
        """Wrap handler to return MenuAction."""
        async def wrapper() -> MenuAction:
            try:
                await handler()
                return MenuAction.CONTINUE
            except KeyboardInterrupt:
                await aprint(Fore.YELLOW + "\n\nInterrupted. Returning to menu...")
                return MenuAction.CONTINUE
            except Exception as e:
                logger.error(f"Error in menu handler: {e}", exc_info=True)
                await aprint(Fore.RED + f"Error: {e}")
                return MenuAction.CONTINUE
        
        return wrapper
    
    def add_item(
        self,
        key: str,
        name: str,
        handler: Optional[Callable[[], Awaitable[MenuAction]]],
        description: str = "",
        badge: str = "",
        enabled: bool = True,
        requires_ssh: bool = False,
    ) -> None:
        """Add menu item."""
        item = MenuItem(
            key=key,
            name=name,
            handler=handler,
            description=description,
            badge=badge,
            enabled=enabled,
            requires_ssh=requires_ssh,
        )
        
        self.items[key] = item
        logger.debug(f"Added menu item: {key} - {name}")
    
    def register_alias(self, alias: str, key: str) -> None:
        """Register alias for menu item."""
        self.aliases[alias.lower()] = key
    
    async def display(self) -> None:
        """Display menu."""
        await aprint(
            Fore.YELLOW + Style.BRIGHT + 
            f"\n=== {self.title} ==="
        )
        
        # Display items in order
        for key in sorted(self.items.keys()):
            item = self.items[key]
            if item.enabled:
                await item.display()
    
    async def get_choice(self) -> str:
        """Get and normalize user choice."""
        choice = await ainput(Fore.GREEN + "\nSelect an option: " + Style.RESET_ALL)
        choice = choice.strip().lower()
        
        # Check aliases
        if choice in self.aliases:
            return self.aliases[choice]
        
        return choice
    
    async def handle_choice(self, choice: str) -> MenuAction:
        """Handle user choice."""
        # Check if valid choice
        if choice not in self.items:
            await aprint(
                Fore.RED + 
                f"Invalid option: '{choice}'. Please choose from available options."
            )
            return MenuAction.CONTINUE
        
        item = self.items[choice]
        
        # Check if enabled
        if not item.enabled:
            await aprint(Fore.RED + f"Option '{item.name}' is currently disabled.")
            return MenuAction.CONTINUE
        
        # Check if SSH required
        if item.requires_ssh and not self.context.ssh_manager.is_connected():
            await aprint(
                Fore.YELLOW + 
                "⚠️  This option requires SSH connection. Reconnecting..."
            )
            
            connected = await self.context.ssh_manager.ensure_connected()
            if not connected:
                await aprint(
                    Fore.RED + 
                    "❌ SSH connection required but unavailable. Please try again."
                )
                return MenuAction.CONTINUE
        
        # Handle exit
        if item.handler is None:
            await aprint(Fore.MAGENTA + "Exiting. Goodbye!")
            return MenuAction.EXIT
        
        # Run handler
        logger.info(f"User selected: {item.name}")
        
        try:
            action = await item.handler()
            return action
        except Exception as e:
            logger.error(f"Error executing menu item '{item.name}': {e}", exc_info=True)
            await aprint(Fore.RED + f"An error occurred: {e}")
            await aprint(Fore.YELLOW + "Returning to menu...")
            return MenuAction.CONTINUE
    
    async def run(self) -> None:
        """Run menu loop."""
        while self.context.running:
            try:
                # Display menu
                await self.display()
                
                # Get choice
                choice = await self.get_choice()
                
                # Handle choice
                action = await self.handle_choice(choice)
                
                # Process action
                if action == MenuAction.EXIT:
                    self.context.running = False
                    break
                elif action == MenuAction.BACK:
                    continue
                else:  # CONTINUE
                    continue
                
            except KeyboardInterrupt:
                await aprint(Fore.YELLOW + "\n\nInterrupted. Type 'exit' to quit.")
                continue
            except Exception as e:
                logger.error(f"Error in menu loop: {e}", exc_info=True)
                await aprint(Fore.RED + f"Menu error: {e}")
                await aprint(Fore.YELLOW + "Press Enter to continue...")
                await ainput("")
    
    def set_title(self, title: str) -> None:
        """Set menu title."""
        self.title = title
    
    def get_item(self, key: str) -> Optional[MenuItem]:
        """Get menu item by key."""
        return self.items.get(key)
    
    def enable_item(self, key: str) -> None:
        """Enable menu item."""
        if key in self.items:
            self.items[key].enabled = True
    
    def disable_item(self, key: str) -> None:
        """Disable menu item."""
        if key in self.items:
            self.items[key].enabled = False