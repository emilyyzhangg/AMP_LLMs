"""
Main application orchestrator.

Simplified version that delegates to specialized managers.
"""

import asyncio
from colorama import Fore, Style, init

try:
    from aioconsole import aprint
except ImportError:
    async def aprint(*args, **kwargs):
        print(*args, **kwargs)

from amp_llm.config import get_logger, get_settings, setup_logging, LogConfig
from .context import ApplicationContext
from .lifecycle import LifecycleManager
from .signals import setup_signal_handlers
from .ssh_manager import SSHManager
from .menu import MenuSystem
from .exceptions import GracefulExit, ApplicationError

logger = get_logger(__name__)


class Application:
    """
    Main application orchestrator.
    
    Coordinates application components and manages lifecycle.
    Simplified from original AMPLLMApp with better separation of concerns.
    
    Example:
        >>> app = Application()
        >>> await app.run()
    """
    
    def __init__(self):
        """Initialize application."""
        # Initialize colorama
        init(autoreset=True)
        
        # Get settings
        self.settings = get_settings()
        
        # Setup logging
        log_config = LogConfig(
            log_file=self.settings.paths.log_file,
            log_level=self.settings.debug and 'DEBUG' or 'INFO',
        )
        setup_logging(log_config)
        
        logger.info("Initializing application...")
        
        # Create application context
        self.context = ApplicationContext(settings=self.settings)
        
        # Create managers
        self.ssh_manager = SSHManager()
        self.context.ssh_manager = self.ssh_manager
        
        self.lifecycle = LifecycleManager()
        self.menu = MenuSystem(self.context)
        
        # Setup signal handlers
        self.signal_handler = setup_signal_handlers()
        self.signal_handler.add_shutdown_callback(self._on_signal_shutdown)
        
        # Register lifecycle hooks
        self._register_hooks()
        
        logger.info("Application initialized")
    
    def _register_hooks(self) -> None:
        """Register lifecycle hooks."""
        
        @self.lifecycle.on_startup(priority=10)
        async def startup_banner():
            """Display startup banner."""
            await aprint(
                Fore.YELLOW + Style.BRIGHT + 
                "\n=== 🚀 AMP_LLM v3.0 ==="
            )
            await aprint(
                Fore.WHITE + 
                "Clinical Trial Research & LLM Integration Tool\n"
            )
        
        @self.lifecycle.on_startup(priority=20)
        async def connect_ssh():
            """Establish SSH connection."""
            connected = await self.ssh_manager.connect_interactive()
            if not connected:
                raise ApplicationError("Failed to establish SSH connection")
        
        @self.lifecycle.on_shutdown(priority=10)
        async def disconnect_ssh():
            """Close SSH connection."""
            await self.ssh_manager.close()
        
        @self.lifecycle.on_shutdown(priority=20)
        async def goodbye_message():
            """Display goodbye message."""
            await aprint(Fore.MAGENTA + "\n✨ Thank you for using AMP_LLM!")
            logger.info("Application shutdown complete")
    
    def _on_signal_shutdown(self) -> None:
        """Handle shutdown signal."""
        logger.info("Shutdown signal received")
        self.context.running = False
    
    async def run(self) -> None:
        """
        Run application.
        
        This is the main entry point that orchestrates startup,
        menu loop, and shutdown.
        """
        try:
            # Run startup hooks
            await self.lifecycle.run_startup_hooks()
            
            # Run menu loop
            await self.menu.run()
            
        except GracefulExit as e:
            logger.info(f"Graceful exit: {e.message}")
        
        except KeyboardInterrupt:
            logger.info("Keyboard interrupt received")
            await aprint(Fore.YELLOW + "\n\nShutting down gracefully...")
        
        except Exception as e:
            logger.error(f"Fatal error: {e}", exc_info=True)
            await aprint(Fore.RED + f"Fatal error: {e}")
        
        finally:
            # Always run shutdown hooks
            try:
                await self.lifecycle.run_shutdown_hooks()
            except Exception as e:
                logger.error(f"Error during shutdown: {e}", exc_info=True)
    
    def get_context(self) -> ApplicationContext:
        """Get application context."""
        return self.context
    
    def get_ssh_manager(self) -> SSHManager:
        """Get SSH manager."""
        return self.ssh_manager
    
    def get_menu(self) -> MenuSystem:
        """Get menu system."""
        return self.menu
    
    def __repr__(self) -> str:
        """String representation."""
        return f"Application(running={self.context.running}, ssh={self.ssh_manager.is_connected()})"