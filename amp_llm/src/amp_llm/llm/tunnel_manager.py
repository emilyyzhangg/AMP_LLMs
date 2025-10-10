"""
SSH Tunnel Manager for Ollama API access.
Handles automatic tunnel creation when direct connection fails.

This fills the gap in your existing llm/tunnel_manager.py
"""
import asyncio
import logging
from typing import Optional
from config import get_logger

logger = get_logger(__name__)


class OllamaTunnelManager:
    """
    Manages SSH tunnel for Ollama API access.
    
    Responsibilities:
    - Create tunnel: localhost:port -> remote:port
    - Test tunnel connectivity
    - Cleanup on exit
    """
    
    def __init__(self, ssh_connection, local_port: int = 11434, remote_port: int = 11434):
        """
        Initialize tunnel manager.
        
        Args:
            ssh_connection: AsyncSSH connection object
            local_port: Local port to forward (default: 11434)
            remote_port: Remote Ollama port (default: 11434)
        """
        self.ssh = ssh_connection
        self.local_port = local_port
        self.remote_port = remote_port
        self.listener = None
        self._active = False
    
    @property
    def is_active(self) -> bool:
        """Check if tunnel is active."""
        return self._active and self.listener is not None
    
    async def create(self) -> bool:
        """
        Create SSH tunnel.
        
        Returns:
            True if successful, False otherwise
        """
        if self._active:
            logger.warning("Tunnel already active")
            return True
        
        try:
            logger.info(f"Creating SSH tunnel: localhost:{self.local_port} -> remote:{self.remote_port}")
            
            # Create port forward
            self.listener = await self.ssh.forward_local_port(
                '',  # Listen on all interfaces
                self.local_port,
                'localhost',  # From server's perspective
                self.remote_port
            )
            
            # Wait for tunnel to be ready
            await asyncio.sleep(1)
            
            self._active = True
            logger.info(f"SSH tunnel established successfully")
            
            return True
            
        except Exception as e:
            logger.error(f"Failed to create SSH tunnel: {e}", exc_info=True)
            self._active = False
            return False
    
    async def test(self) -> bool:
        """
        Test if tunnel is working by attempting connection.
        
        Returns:
            True if tunnel is working
        """
        if not self._active:
            return False
        
        try:
            import aiohttp
            
            # Quick test connection
            timeout = aiohttp.ClientTimeout(total=5)
            async with aiohttp.ClientSession(timeout=timeout) as session:
                async with session.get(f"http://localhost:{self.local_port}/api/tags") as resp:
                    return resp.status == 200
        
        except Exception as e:
            logger.warning(f"Tunnel test failed: {e}")
            return False
    
    def close(self):
        """Close tunnel and cleanup."""
        if self.listener:
            try:
                self.listener.close()
                logger.info("SSH tunnel closed")
            except Exception as e:
                logger.error(f"Error closing tunnel: {e}")
            finally:
                self.listener = None
                self._active = False
    
    async def __aenter__(self):
        """Context manager entry."""
        await self.create()
        return self
    
    async def __aexit__(self, exc_type, exc_val, exc_tb):
        """Context manager exit."""
        self.close()


async def create_ollama_tunnel(
    ssh_connection,
    local_port: int = 11434,
    remote_port: int = 11434
) -> Optional[OllamaTunnelManager]:
    """
    Convenience function to create tunnel.
    
    Args:
        ssh_connection: AsyncSSH connection
        local_port: Local port (default: 11434)
        remote_port: Remote port (default: 11434)
        
    Returns:
        OllamaTunnelManager if successful, None otherwise
    """
    manager = OllamaTunnelManager(ssh_connection, local_port, remote_port)
    
    if await manager.create():
        return manager
    else:
        return None


async def test_ollama_connection(host: str, port: int = 11434) -> bool:
    """
    Test if Ollama is accessible at given host:port.
    
    Args:
        host: Host to test (IP or 'localhost')
        port: Port to test (default: 11434)
        
    Returns:
        True if accessible
    """
    try:
        import aiohttp
        
        timeout = aiohttp.ClientTimeout(total=5)
        async with aiohttp.ClientSession(timeout=timeout) as session:
            async with session.get(f"http://{host}:{port}/api/tags") as resp:
                return resp.status == 200
    
    except Exception:
        return False