import asyncssh
import asyncio
from typing import Optional
from contextlib import asynccontextmanager
from colorama import Fore
from amp_llm.config import get_logger

logger = get_logger(__name__)


class SSHConnection:
    """Wrapper for SSH connection with proper cleanup."""
    
    def __init__(self, connection: asyncssh.SSHClientConnection):
        self.connection = connection
        self._closed = False
    
    async def run(self, *args, **kwargs):
        """Run command on SSH connection."""
        if self._closed:
            raise RuntimeError("Connection is closed")
        return await self.connection.run(*args, **kwargs)
    
    async def close(self):
        """Close connection gracefully."""
        if not self._closed:
            self._closed = True
            try:
                # Close connection with timeout
                await asyncio.wait_for(self._close_connection(), timeout=5.0)
            except asyncio.TimeoutError:
                logger.warning("SSH connection close timeout, forcing close")
                self.connection.abort()
            except Exception as e:
                logger.error(f"Error closing SSH connection: {e}")
    
    async def _close_connection(self):
        """Internal close method."""
        try:
            self.connection.close()
            await self.connection.wait_closed()
        except Exception as e:
            logger.warning(f"Connection close warning: {e}")
    
    def __getattr__(self, name):
        """Proxy other attributes to connection."""
        return getattr(self.connection, name)


async def connect_ssh(
    ip: str,
    username: str,
    password: str,
    keepalive_interval: int = 15,
    keepalive_count_max: int = 3,
    connect_timeout: int = 30
) -> Optional[SSHConnection]:
    """
    Establish SSH connection with keepalive.
    Returns wrapped connection with proper cleanup.
    """
    try:
        logger.info(f"Connecting to {username}@{ip}")
        
        conn = await asyncssh.connect(
            host=ip,
            username=username,
            password=password,
            keepalive_interval=keepalive_interval,
            keepalive_count_max=keepalive_count_max,
            known_hosts=None,
            tcp_keepalive=True,
            client_keys=None,
            connect_timeout=connect_timeout,
            term_type=None,
        )
        
        logger.info(f"Successfully connected to {username}@{ip}")
        return SSHConnection(conn)
        
    except asyncssh.PermissionDenied:
        print(Fore.RED + "❌ Authentication failed.")
        logger.error("SSH authentication failed")
        return None
    except asyncio.TimeoutError:
        print(Fore.RED + f"❌ Connection timeout to {ip}")
        logger.error(f"SSH connection timeout to {ip}")
        return None
    except Exception as e:
        print(Fore.RED + f"❌ SSH connection error: {e}")
        logger.error(f"SSH connection error: {e}", exc_info=True)
        return None


@asynccontextmanager
async def ssh_context(ip: str, username: str, password: str, **kwargs):
    """
    Context manager for SSH connection.
    
    Usage:
        async with ssh_context(ip, user, pass) as ssh:
            await ssh.run("ls")
    """
    connection = await connect_ssh(ip, username, password, **kwargs)
    if connection is None:
        raise ConnectionError("Failed to establish SSH connection")
    
    try:
        yield connection
    finally:
        await connection.close()