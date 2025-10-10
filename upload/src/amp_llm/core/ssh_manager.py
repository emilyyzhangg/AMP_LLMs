"""
SSH connection management.

Extracted from app.py for better modularity and testability.
"""

import asyncio
from typing import Optional
from colorama import Fore, Style

try:
    from aioconsole import ainput, aprint
except ImportError:
    async def ainput(prompt):
        return input(prompt)
    async def aprint(*args, **kwargs):
        print(*args, **kwargs)

from amp_llm.config import get_settings, get_logger
from amp_llm.network import ping_host, connect_ssh
from .exceptions import SSHConnectionError, SSHAuthenticationError

logger = get_logger(__name__)


class SSHManager:
    """
    Manages SSH connection lifecycle.
    
    Handles connection, authentication, reconnection, and cleanup.
    
    Attributes:
        connection: Active SSH connection (None if not connected)
        host: Remote host IP/hostname
        username: SSH username
        port: SSH port
    
    Example:
        >>> manager = SSHManager()
        >>> await manager.connect_interactive()
        >>> if manager.is_connected():
        ...     result = await manager.run_command("ls")
    """
    
    def __init__(self):
        self.connection: Optional[any] = None  # asyncssh.SSHClientConnection
        self.host: Optional[str] = None
        self.username: Optional[str] = None
        self.port: int = 22
        self.settings = get_settings()
    
    def is_connected(self) -> bool:
        """
        Check if SSH connection is active.
        
        Returns:
            True if connected, False otherwise
        """
        if not self.connection:
            return False
        
        try:
            return not self.connection.is_closed()
        except AttributeError:
            # Connection object doesn't have is_closed method
            return True
        except Exception:
            return False
    
    async def connect_interactive(self) -> bool:
        """
        Connect to SSH host interactively.
        
        Prompts user for host, username, and password.
        Includes ping check and authentication.
        
        Returns:
            True if connected successfully, False otherwise
        
        Raises:
            SSHConnectionError: If connection fails
            SSHAuthenticationError: If authentication fails
        """
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
        """
        Prompt for host and verify connectivity.
        
        Returns:
            Verified host IP/hostname
        """
        default_host = self.settings.network.default_host
        
        while True:
            try:
                host = await ainput(
                    Fore.CYAN + f"Enter remote host IP [{default_host}]: " + Style.RESET_ALL
                )
                host = host.strip() or default_host
                
                await aprint(Fore.YELLOW + f"Pinging {host}...")
                
                reachable = await ping_host(
                    host,
                    timeout=self.settings.network.timeout
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
        """
        Prompt for SSH username.
        
        Returns:
            SSH username
        """
        default_user = self.settings.network.default_user
        
        try:
            username = await ainput(
                Fore.CYAN + f"Enter SSH username [{default_user}]: " + Style.RESET_ALL
            )
            return username.strip() or default_user
        except Exception as e:
            logger.error(f"Error in username prompt: {e}")
            return default_user
    
    async def _connect_with_password(self) -> bool:
        """
        Connect with password authentication.
        
        Retries up to max_auth_attempts times.
        
        Returns:
            True if connected, False otherwise
        """
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
        """
        Attempt to reconnect using stored credentials.
        
        Returns:
            True if reconnected successfully, False otherwise
        """
        if not self.host or not self.username:
            logger.warning("Cannot reconnect: no previous connection info")
            await aprint(Fore.RED + "❌ No previous connection info available.")
            return False
        
        await aprint(Fore.YELLOW + f"Reconnecting to {self.username}@{self.host}...")
        logger.info(f"Attempting to reconnect to {self.host}")
        
        # Close existing connection if any
        if self.connection:
            try:
                self.connection.close()
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
        """
        Ensure SSH connection is active, reconnect if needed.
        
        Returns:
            True if connected, False otherwise
        """
        if self.is_connected():
            return True
        
        logger.warning("SSH connection lost, attempting reconnect...")
        await aprint(Fore.YELLOW + "⚠️  SSH connection lost, reconnecting...")
        
        return await self.reconnect()
    
    async def run_command(self, command: str, check: bool = True) -> any:
        """
        Run command on remote host.
        
        Args:
            command: Command to run
            check: Whether to check return code
        
        Returns:
            Command result object
        
        Raises:
            SSHConnectionError: If not connected
        """
        if not self.is_connected():
            raise SSHConnectionError("Not connected to SSH server")
        
        logger.debug(f"Running SSH command: {command}")
        return await self.connection.run(command, check=check)
    
    async def close(self) -> None:
        """Close SSH connection gracefully."""
        if self.connection:
            try:
                logger.info("Closing SSH connection...")
                self.connection.close()
                await asyncio.sleep(0.1)  # Give time to close
                self.connection = None
                logger.info("SSH connection closed")
            except Exception as e:
                logger.error(f"Error closing SSH connection: {e}")
    
    def get_connection_info(self) -> dict:
        """
        Get current connection information.
        
        Returns:
            Dictionary with connection details
        """
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