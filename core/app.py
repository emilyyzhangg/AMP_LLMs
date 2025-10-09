"""
Core application class with improved separation of concerns.
Handles SSH lifecycle, menu system, and module coordination.
"""
import asyncio
import signal
import getpass
from typing import Optional
from colorama import Fore, Style
from aioconsole import ainput, aprint

from config import get_config, get_logger
from network.async_networking import ping_host
from network.ssh_connection import connect_ssh
from core.menu import MenuSystem

logger = get_logger(__name__)
config = get_config()


class GracefulExit(SystemExit):
    """Custom exception for graceful exit."""
    pass


class AMPLLMApp:
    """
    Main application class with proper lifecycle management.
    
    Responsibilities:
    - SSH connection management
    - Signal handling
    - Menu coordination
    - Graceful cleanup
    """
    
    def __init__(self):
        self.ssh_connection: Optional[object] = None
        self.ssh_ip: Optional[str] = None
        self.ssh_username: Optional[str] = None
        self.running = True
        self.menu_system = None
        self._setup_signal_handlers()
    
    def _setup_signal_handlers(self):
        """Setup handlers for graceful shutdown on SIGINT/SIGTERM."""
        def signal_handler(signum, frame):
            logger.info(f"Received signal {signum}, initiating graceful shutdown...")
            self.running = False
            raise GracefulExit()
        
        signal.signal(signal.SIGINT, signal_handler)
        signal.signal(signal.SIGTERM, signal_handler)
    
    async def cleanup(self):
        """Cleanup resources on exit."""
        if self.ssh_connection:
            try:
                logger.info("Closing SSH connection...")
                self.ssh_connection.close()
                await asyncio.sleep(0.1)
            except Exception as e:
                logger.error(f"Error closing SSH: {e}")
    
    def is_ssh_connected(self) -> bool:
        """Check if SSH connection is active."""
        if not self.ssh_connection:
            return False
        try:
            return not self.ssh_connection.is_closed()
        except AttributeError:
            return True
    
    async def ensure_connected(self) -> bool:
        """Check if SSH is still connected, reconnect if needed."""
        try:
            if self.ssh_connection and not self.ssh_connection.is_closed():
                return True
        except:
            pass
        
        logger.warning("SSH connection lost, attempting reconnect...")
        await aprint(Fore.YELLOW + "⚠️  SSH connection lost, reconnecting...")
        
        success = await self.reconnect_ssh()
        if success:
            await aprint(Fore.GREEN + "✅ Reconnected!")
            return True
        else:
            await aprint(Fore.RED + "❌ Reconnection failed")
            return False
    
    async def reconnect_ssh(self) -> bool:
        """Attempt to reconnect SSH using stored credentials."""
        if not self.ssh_ip or not self.ssh_username:
            await aprint(Fore.RED + "❌ No previous connection info available.")
            return False
        
        await aprint(Fore.YELLOW + f"Reconnecting to {self.ssh_username}@{self.ssh_ip}...")
        
        if self.ssh_connection:
            try:
                self.ssh_connection.close()
            except Exception:
                pass
        
        self.ssh_connection = await self.prompt_password_and_connect(
            self.ssh_username, 
            self.ssh_ip
        )
        
        return self.is_ssh_connected()
    
    async def prompt_ip(self) -> str:
        """Prompt for IP address with validation and ping check."""
        default = config.network.default_ip
        
        while self.running:
            try:
                ip = await ainput(
                    Fore.CYAN + f"Enter remote host IP [{default}]: " + Style.RESET_ALL
                )
                ip = ip.strip() or default
                
                await aprint(Fore.YELLOW + f"Pinging {ip}...")
                ok = await ping_host(ip, timeout=config.network.ping_timeout)
                
                if ok:
                    await aprint(Fore.GREEN + f"✅ Successfully reached {ip}")
                    logger.info(f"Connected to {ip}")
                    return ip
                
                await aprint(Fore.RED + f"❌ Could not reach {ip}. Try again.")
                logger.warning(f"Failed to ping {ip}")
                
            except GracefulExit:
                raise
            except Exception as e:
                logger.error(f"Error in IP prompt: {e}")
                await aprint(Fore.RED + f"Error: {e}")
        
        raise GracefulExit()
    
    async def prompt_username(self) -> str:
        """Prompt for SSH username."""
        default = config.network.default_username
        
        try:
            username = await ainput(
                Fore.CYAN + f"Enter SSH username [{default}]: " + Style.RESET_ALL
            )
            return username.strip() or default
        except GracefulExit:
            raise
        except Exception as e:
            logger.error(f"Error in username prompt: {e}")
            return default
    
    async def prompt_password_and_connect(self, username: str, ip: str) -> object:
        """Prompt for password and establish SSH connection."""
        attempt = 0
        
        while self.running and attempt < config.network.max_auth_attempts:
            try:
                await aprint(Fore.CYAN + f"Enter SSH password for {username}@{ip}: ", end='')
                password = getpass.getpass('')
                
                await aprint(Fore.YELLOW + "Connecting...")
                ssh = await connect_ssh(ip, username, password)
                
                if ssh:
                    await aprint(Fore.GREEN + f"✅ Successfully connected to {username}@{ip}")
                    logger.info(f"SSH connection established: {username}@{ip}")
                    self.ssh_ip = ip
                    self.ssh_username = username
                    return ssh
                
                attempt += 1
                remaining = config.network.max_auth_attempts - attempt
                
                if remaining > 0:
                    await aprint(
                        Fore.RED + 
                        f"❌ Authentication failed. {remaining} attempt(s) remaining."
                    )
                else:
                    await aprint(Fore.RED + "❌ Max authentication attempts reached.")
                    raise GracefulExit()
                
            except GracefulExit:
                raise
            except Exception as e:
                logger.error(f"Connection error: {e}")
                await aprint(Fore.RED + f"Error: {e}")
                attempt += 1
        
        raise GracefulExit()
    
    async def run(self):
        """Main application entry point."""
        try:
            await aprint(Fore.YELLOW + Style.BRIGHT + "\n=== 🚀 AMP_LLM v3.0 ===")
            await aprint(Fore.WHITE + "Clinical Trial Research & LLM Integration Tool\n")
            
            await aprint(Fore.YELLOW + "\n=== 🔐 SSH Connection Setup ===")
            
            # Get connection details
            ip = await self.prompt_ip()
            username = await self.prompt_username()
            
            # Establish connection
            self.ssh_connection = await self.prompt_password_and_connect(username, ip)
            
            # Initialize menu system
            self.menu_system = MenuSystem(self)
            
            # Run main menu
            await self.menu_system.run()
            
        except GracefulExit:
            logger.info("Graceful exit initiated")
        except KeyboardInterrupt:
            logger.info("Keyboard interrupt received")
            await aprint(Fore.YELLOW + "\n\nShutting down gracefully...")
        except Exception as e:
            logger.error(f"Fatal error: {e}", exc_info=True)
            await aprint(Fore.RED + f"Fatal error: {e}")
        finally:
            await self.cleanup()