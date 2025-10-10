"""
SSH connection management with proper async cleanup.
FIXED: Proper async close handling + prevents recursion errors
"""

import asyncio
from typing import Optional, TYPE_CHECKING
if TYPE_CHECKING:
    import asyncssh
from colorama import Fore, Style
from amp_llm.cli.async_io import ainput, aprint
from amp_llm.config import get_config, get_logger
from amp_llm.network.ping import ping_host
from amp_llm.network.ssh import connect_ssh
from .exceptions import SSHConnectionError, SSHAuthenticationError

logger = get_logger(__name__)


class SSHManager:
    """
    Manages SSH connection lifecycle with proper async cleanup.
    
    FIXED: 
    - Ensures all close operations are properly awaited
    - Prevents recursive shutdown errors
    """
    
    def __init__(self):
        self.connection: Optional['asyncssh.SSHClientConnection'] = None
        self.host: Optional[str] = None
        self.username: Optional[str] = None
        self.port: int = 22
        self.settings = get_config()
        self._closing = False  # Prevent recursive closes
        self._close_task = None  # Track close task
    
    def is_connected(self) -> bool:
        """Check if SSH connection is active."""
        if not self.connection:
            return False
        
        try:
            return not self.connection.is_closed()
        except AttributeError:
            return True
        except Exception:
            return False
    
    async def connect_interactive(self) -> bool:
        """Connect to SSH host interactively."""
        await aprint(Fore.YELLOW + "\n=== 🔐 SSH Connection Setup ===")
        
        # Get host
        self.host = await self._prompt_host()
        
        # Get username
        self.username = await self._prompt_username()
        
        # Connect with password
        connected = await self._connect_with_password()
        
        if connected:
            logger.info(f"SSH connected: {self.username}@{self.host}")
            return True
        else:
            logger.error("SSH connection failed")
            return False
    
    async def _prompt_host(self) -> str:
        """Prompt for host and verify connectivity."""
        default_host = self.settings.network.default_ip
        
        while True:
            try:
                host = await ainput(
                    Fore.CYAN + f"Enter remote host IP [{default_host}]: " + Style.RESET_ALL
                )
                host = host.strip() or default_host
                
                await aprint(Fore.YELLOW + f"Pinging {host}...")
                
                reachable = await ping_host(
                    host,
                    timeout=self.settings.network.ping_timeout
                )
                
                if reachable:
                    await aprint(Fore.GREEN + f"✅ Successfully reached {host}")
                    return host
                
                await aprint(Fore.RED + f"❌ Could not reach {host}. Try again.")
                logger.warning(f"Failed to ping {host}")
                
            except KeyboardInterrupt:
                raise
            except Exception as e:
                logger.error(f"Error in host prompt: {e}")
                await aprint(Fore.RED + f"Error: {e}")
    
    async def _prompt_username(self) -> str:
        """Prompt for SSH username."""
        default_user = self.settings.network.default_username
        
        try:
            username = await ainput(
                Fore.CYAN + f"Enter SSH username [{default_user}]: " + Style.RESET_ALL
            )
            return username.strip() or default_user
        except Exception as e:
            logger.error(f"Error in username prompt: {e}")
            return default_user
    
    async def _connect_with_password(self) -> bool:
        """Connect with password authentication."""
        max_attempts = self.settings.network.max_auth_attempts
        
        for attempt in range(max_attempts):
            try:
                import getpass
                
                await aprint(
                    Fore.CYAN + f"Enter SSH password for {self.username}@{self.host}: ",
                    end=''
                )
                password = getpass.getpass('')
                
                await aprint(Fore.YELLOW + "Connecting...")
                
                self.connection = await connect_ssh(
                    self.host,
                    self.username,
                    password
                )
                
                if self.connection:
                    await aprint(
                        Fore.GREEN + 
                        f"✅ Successfully connected to {self.username}@{self.host}"
                    )
                    return True
                
                # Authentication failed
                remaining = max_attempts - attempt - 1
                
                if remaining > 0:
                    await aprint(
                        Fore.RED + 
                        f"❌ Authentication failed. {remaining} attempt(s) remaining."
                    )
                else:
                    await aprint(Fore.RED + "❌ Max authentication attempts reached.")
                    raise SSHAuthenticationError("Maximum authentication attempts exceeded")
                
            except KeyboardInterrupt:
                raise
            except SSHAuthenticationError:
                raise
            except Exception as e:
                logger.error(f"Connection error on attempt {attempt + 1}: {e}")
                await aprint(Fore.RED + f"Error: {e}")
        
        return False
    
    async def reconnect(self) -> bool:
        """Attempt to reconnect using stored credentials."""
        if not self.host or not self.username:
            logger.warning("Cannot reconnect: no previous connection info")
            await aprint(Fore.RED + "❌ No previous connection info available.")
            return False
        
        await aprint(Fore.YELLOW + f"Reconnecting to {self.username}@{self.host}...")
        logger.info(f"Attempting to reconnect to {self.host}")
        
        # Close existing connection if any
        if self.connection:
            try:
                await self.close()
            except Exception:
                pass
        
        # Try to reconnect
        connected = await self._connect_with_password()
        
        if connected:
            await aprint(Fore.GREEN + "✅ Reconnected successfully!")
            return True
        else:
            await aprint(Fore.RED + "❌ Reconnection failed")
            return False
    
    async def ensure_connected(self) -> bool:
        """Ensure SSH connection is active, reconnect if needed."""
        if self.is_connected():
            return True
        
        logger.warning("SSH connection lost, attempting reconnect...")
        await aprint(Fore.YELLOW + "⚠️  SSH connection lost, reconnecting...")
        
        return await self.reconnect()
    
    async def run_command(self, command: str, check: bool = True) -> any:
        """Run command on remote host."""
        if not self.is_connected():
            raise SSHConnectionError("Not connected to SSH server")
        
        logger.debug(f"Running SSH command: {command}")
        return await self.connection.run(command, check=check)
    
    async def close(self) -> None:
        """
        Close SSH connection gracefully.
        FIXED: Properly await the close operation and prevent recursion.
        """
        # Prevent recursive closes
        if self._closing:
            logger.debug("Close already in progress, skipping")
            return
        
        # If there's already a close task running, wait for it
        if self._close_task and not self._close_task.done():
            logger.debug("Waiting for existing close task")
            try:
                await asyncio.wait_for(self._close_task, timeout=3.0)
            except asyncio.TimeoutError:
                logger.warning("Existing close task timed out")
            return
        
        # Create new close task
        self._close_task = asyncio.create_task(self._close_internal())
        
        try:
            await asyncio.wait_for(self._close_task, timeout=5.0)
        except asyncio.TimeoutError:
            logger.warning("SSH close timeout")
        finally:
            self._close_task = None
    
    async def _close_internal(self) -> None:
        """Internal close method."""
        if not self.connection:
            return
        
        try:
            self._closing = True
            logger.info("Closing SSH connection...")
            
            # Close the connection (non-blocking)
            self.connection.close()
            
            # Wait for the connection to actually close
            try:
                await asyncio.wait_for(
                    self.connection.wait_closed(),
                    timeout=3.0
                )
                logger.info("SSH connection closed successfully")
            except asyncio.TimeoutError:
                logger.warning("SSH wait_closed() timeout, connection may not have closed cleanly")
            except Exception as e:
                logger.warning(f"Error during wait_closed(): {e}")
            
            self.connection = None
            
        except Exception as e:
            logger.error(f"Error closing SSH connection: {e}")
        finally:
            self._closing = False
    
    def get_connection_info(self) -> dict:
        """Get current connection information."""
        return {
            'host': self.host,
            'username': self.username,
            'port': self.port,
            'connected': self.is_connected(),
        }
    
    def __repr__(self) -> str:
        """String representation."""
        if self.is_connected():
            return f"SSHManager(connected={self.username}@{self.host}:{self.port})"
        else:
            return "SSHManager(disconnected)"