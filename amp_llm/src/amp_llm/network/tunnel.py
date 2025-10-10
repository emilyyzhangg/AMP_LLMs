# ============================================================================
# src/amp_llm/network/tunnel.py
# ============================================================================
"""
SSH tunnel management for port forwarding.
"""
import asyncio
from typing import Optional
from amp_llm.config.logging import get_logger

logger = get_logger(__name__)


class SSHTunnel:
    """SSH tunnel manager for port forwarding."""
    
    def __init__(self, ssh_connection):
        """
        Initialize tunnel manager.
        
        Args:
            ssh_connection: Active AsyncSSH connection
        """
        self.ssh = ssh_connection
        self.listener = None
        self.local_port = None
        self.remote_host = None
        self.remote_port = None
    
    async def create_tunnel(
        self,
        local_port: int,
        remote_host: str = 'localhost',
        remote_port: int = 11434
    ):
        """
        Create SSH tunnel.
        
        Args:
            local_port: Local port to forward from
            remote_host: Remote host (from server's perspective)
            remote_port: Remote port to forward to
        """
        try:
            logger.info(
                f"Creating tunnel: localhost:{local_port} -> "
                f"{remote_host}:{remote_port}"
            )
            
            self.listener = await self.ssh.forward_local_port(
                '',  # Listen on all interfaces
                local_port,
                remote_host,
                remote_port
            )
            
            self.local_port = local_port
            self.remote_host = remote_host
            self.remote_port = remote_port
            
            logger.info(f"Tunnel established on port {local_port}")
            
        except Exception as e:
            logger.error(f"Failed to create tunnel: {e}")
            raise
    
    def close(self):
        """Close the tunnel."""
        if self.listener:
            try:
                self.listener.close()
                logger.info("Tunnel closed")
            except Exception as e:
                logger.error(f"Error closing tunnel: {e}")
    
    async def __aenter__(self):
        """Context manager entry."""
        return self
    
    async def __aexit__(self, exc_type, exc_val, exc_tb):
        """Context manager exit."""
        self.close()